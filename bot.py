import websocket
import json
import time
import logging
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options

# === Logging Config ===
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

# === Deriv API & Bot Settings ===
DERIV_API = "wss://ws.derivws.com/websockets/v3?app_id=1089"
API_TOKEN = "fu_ku"  # ⚠️ Replace with your own
STAKE_AMOUNT = 500.00
RECOVERY_AMOUNT = 100.00
SYMBOL = "R_50"
CONTRACT_TYPE = "CALL"
DURATION = 60  # seconds

# === Risk Management ===
LOSS_THRESHOLD = 0.50
MAX_LOSS = -0.50
TAKE_PROFIT_TARGET = 2.00

# === Global State ===
contract_id = None
proposal_id = None
current_trade = "main"
max_profit = 0.0
retry_once = False


# === WEBSOCKET HANDLERS ===
def on_message(ws, message):
    global contract_id, proposal_id, current_trade, max_profit, retry_once

    data = json.loads(message)
    logging.debug(json.dumps(data, indent=2))

    if "error" in data:
        error_msg = data["error"]["message"]
        logging.error(f"❌ Error: {error_msg}")
        if "price" in error_msg and not retry_once:
            logging.warning("⚠️ Retrying with reduced stake ($100)...")
            retry_once = True
            request_proposal(ws, RECOVERY_AMOUNT)
            return
        ws.close()
        return

    msg_type = data.get("msg_type")

    if msg_type == "authorize":
        logging.info("✅ Authorized successfully.")
        request_proposal(ws, STAKE_AMOUNT)

    elif msg_type == "proposal":
        proposal_id = data["proposal"]["id"]
        price = data["proposal"].get("ask_price", STAKE_AMOUNT)
        logging.info(f"📥 Proposal received: {proposal_id} at ${price}")
        buy_contract(ws, proposal_id, price)

    elif msg_type == "buy":
        contract_id = data["buy"]["contract_id"]
        logging.info(f"🟢 Bought contract ID: {contract_id}")
        max_profit = 0.0
        subscribe_to_contract(ws, contract_id)

    elif msg_type == "proposal_open_contract":
        handle_contract_update(ws, data["proposal_open_contract"])


def handle_contract_update(ws, contract_info):
    global max_profit, current_trade

    profit_loss = contract_info.get("profit", 0)
    is_sold = contract_info.get("is_sold", False)

    if not is_sold:
        logging.info(f"📈 Live PnL: ${profit_loss:.2f}")

        if profit_loss > max_profit:
            max_profit = profit_loss
            logging.info(f"🔼 New max profit: ${max_profit:.2f}")

        if profit_loss <= MAX_LOSS:
            logging.warning("🛑 Stop loss triggered.")
            sell_contract(ws)

        elif profit_loss >= TAKE_PROFIT_TARGET:
            logging.info("🎯 Take profit reached.")
            sell_contract(ws)

        elif profit_loss < (max_profit - LOSS_THRESHOLD):
            logging.warning("🔻 Trailing stop hit.")
            sell_contract(ws)

    else:
        logging.info("📤 Contract closed.")
        if current_trade == "main":
            current_trade = "recovery"
            time.sleep(3)
            logging.info("🔁 Restaking using Selenium...")
            restake_with_selenium(amount=RECOVERY_AMOUNT)
            request_proposal(ws, RECOVERY_AMOUNT)
        else:
            logging.info("✅ Recovery complete. Exiting.")
            ws.close()


def request_proposal(ws, amount):
    ws.send(json.dumps({
        "proposal": 1,
        "amount": amount,
        "basis": "stake",
        "contract_type": CONTRACT_TYPE,
        "currency": "USD",
        "duration": DURATION,
        "duration_unit": "s",
        "symbol": SYMBOL
    }))


def buy_contract(ws, proposal_id, price):
    if not proposal_id:
        logging.error("❌ Missing proposal ID.")
        return
    ws.send(json.dumps({"buy": proposal_id, "price": price}))


def subscribe_to_contract(ws, contract_id):
    ws.send(json.dumps({"proposal_open_contract": 1, "contract_id": contract_id}))


def sell_contract(ws):
    global contract_id
    if contract_id:
        ws.send(json.dumps({"sell": contract_id}))
    else:
        logging.warning("⚠️ No active contract to sell.")


# === SELENIUM RESTAKING ===
def restake_with_selenium(amount):
    """Use Selenium to restake from Deriv web UI (for demo accounts)."""
    try:
        chrome_options = Options()
        chrome_options.add_argument("--headless")  # Remove to see the browser
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")

        service = Service("/usr/bin/chromedriver")  # adjust path if needed
        driver = webdriver.Chrome(service=service, options=chrome_options)

        driver.get("https://app.deriv.com/")
        logging.info("🌐 Opened Deriv dashboard.")

        # Example — adjust selectors for your interface version
        time.sleep(5)
        stake_input = driver.find_element(By.CSS_SELECTOR, "input[name='stake']")
        stake_input.clear()
        stake_input.send_keys(str(amount))

        time.sleep(2)
        buy_button = driver.find_element(By.CSS_SELECTOR, "button.purchase-button__buy")
        buy_button.click()
        logging.info(f"🪙 Restaked ${amount} using Selenium")

        time.sleep(5)
        driver.quit()
    except Exception as e:
        logging.error(f"❌ Selenium restake failed: {e}")


# === MAIN ===
def on_open(ws):
    ws.send(json.dumps({"authorize": API_TOKEN}))


def on_error(ws, error):
    logging.error(f"❌ WebSocket error: {error}")


def on_close(ws, close_status_code, close_msg):
    logging.info("🔌 Connection closed.")


def start_bot():
    ws = websocket.WebSocketApp(
        DERIV_API,
        on_open=on_open,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close
    )
    ws.run_forever()


if __name__ == "__main__":
    start_bot()

