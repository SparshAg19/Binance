from dotenv import load_dotenv
from binance.client import Client
import os
import time

load_dotenv()

client = Client(
    os.getenv("BINANCE_API_KEY"),
    os.getenv("BINANCE_SECRET_KEY")
)

# Demo Futures endpoint
client.FUTURES_URL = "https://demo-fapi.binance.com/fapi"

# Get Binance server time
server_time = client.get_server_time()["serverTime"]
local_time = int(time.time() * 1000)

print("Server:", server_time)
print("Local :", local_time)
print("Diff  :", server_time - local_time)

# Set time offset
client.timestamp_offset = server_time - local_time

try:
    balance = client.futures_account_balance(recvWindow=60000)
    print(balance)
except Exception as e:
    print(e)