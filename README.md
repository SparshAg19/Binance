# Binance USDT-M Futures Demo Bot

Production-oriented Python CLI for Binance USDT-M Futures Demo Trading using `python-binance`.

## Features

- Connects to `https://demo-fapi.binance.com`
- Synchronizes Binance Futures server time automatically
- Reads API credentials from `.env`
- Retrieves futures balances and ticker prices
- Places market buy, market sell, and limit orders
- Lists and cancels open orders
- Returns structured responses from every client operation
- Logs API activity, order placement, and failures to `logs/app.log`
- Handles Binance API errors, timestamp drift, invalid symbols, network failures, and insufficient balance responses

## Requirements

- Python 3.11+
- Binance Futures Demo API key and secret

## Setup

```bash
cd binance_bot
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

Edit `.env` with your Binance Futures Demo credentials:

```env
BINANCE_API_KEY=your_demo_api_key
BINANCE_SECRET_KEY=your_demo_secret_key
BINANCE_FUTURES_BASE_URL=https://demo-fapi.binance.com
BINANCE_RECV_WINDOW=60000
BINANCE_REQUEST_TIMEOUT=10
BINANCE_DEFAULT_SYMBOL=BTCUSDT
LOG_LEVEL=INFO
```

## Run

```bash
python main.py
```

The CLI connects to Binance Futures Demo, displays your USDT balance, displays the BTCUSDT price by default, and then opens the order menu.

## Test

```bash
pytest
```

Tests use fake clients and do not send real API requests.

## Project Structure

```text
binance_bot/
├── main.py
├── config.py
├── binance_client.py
├── orders.py
├── logger.py
├── requirements.txt
├── .env.example
├── README.md
├── logs/
│   └── app.log
└── tests/
    └── test_client.py
```
