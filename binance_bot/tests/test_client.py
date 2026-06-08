from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from binance.exceptions import BinanceAPIException
from requests.exceptions import Timeout

from binance_client import BinanceFuturesDemoClient
from config import Settings
from orders import OrderRequest, OrderSide, OrderType, TimeInForce


class FakeResponse:
    text = ""
    request = None


class FakeClient:
    def __init__(self) -> None:
        self.timestamp_offset = 0
        self.created_orders: list[dict[str, object]] = []
        self.open_orders_params: dict[str, object] | None = None
        self.cancel_params: dict[str, object] | None = None
        self.order_failures_before_success = 0

    def futures_ping(self) -> dict[str, object]:
        return {}

    def futures_time(self) -> dict[str, int]:
        return {"serverTime": 1_700_000_000_000}

    def futures_account_balance(self, **params: object) -> list[dict[str, str]]:
        return [
            {
                "asset": "USDT",
                "balance": "1000.00000000",
                "availableBalance": "900.00000000",
                "crossWalletBalance": "1000.00000000",
            }
        ]

    def futures_symbol_ticker(self, **params: object) -> dict[str, str]:
        return {"symbol": str(params["symbol"]), "price": "65000.00"}

    def futures_create_order(self, **params: object) -> dict[str, object]:
        if self.order_failures_before_success:
            self.order_failures_before_success -= 1
            raise_binance_error(-1021, "Timestamp for this request is outside")

        self.created_orders.append(params)
        return {"orderId": 123, "status": "NEW", **params}

    def futures_get_open_orders(self, **params: object) -> list[dict[str, object]]:
        self.open_orders_params = params
        return [{"orderId": 123, "symbol": params.get("symbol", "BTCUSDT")}]

    def futures_cancel_order(self, **params: object) -> dict[str, object]:
        self.cancel_params = params
        return {"status": "CANCELED", **params}


def test_order_request_builds_market_params() -> None:
    order = OrderRequest(
        symbol="btcusdt",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity="0.001",
    )

    assert order.to_binance_params() == {
        "symbol": "BTCUSDT",
        "side": "BUY",
        "type": "MARKET",
        "quantity": "0.001",
    }


def test_order_request_builds_limit_params() -> None:
    order = OrderRequest.limit(
        symbol="ETHUSDT",
        side=OrderSide.SELL,
        quantity="0.25",
        price="3500.50",
        time_in_force=TimeInForce.GTC,
    )

    assert order.to_binance_params() == {
        "symbol": "ETHUSDT",
        "side": "SELL",
        "type": "LIMIT",
        "quantity": "0.25",
        "price": "3500.5",
        "timeInForce": "GTC",
    }


def test_connect_synchronizes_timestamp() -> None:
    fake_client = FakeClient()
    client = BinanceFuturesDemoClient(settings(), raw_client=fake_client)

    response = client.connect()

    assert response.success is True
    assert fake_client.timestamp_offset != 0
    assert response.data["endpoint"] == "https://demo-fapi.binance.com"


def test_get_usdt_balance_returns_structured_response() -> None:
    client = BinanceFuturesDemoClient(settings(), raw_client=FakeClient())

    response = client.get_usdt_balance()

    assert response.success is True
    assert response.data["asset"] == "USDT"
    assert response.data["available_balance"] == "900.00000000"


def test_market_buy_adds_recv_window_and_order_params() -> None:
    fake_client = FakeClient()
    client = BinanceFuturesDemoClient(settings(), raw_client=fake_client)

    response = client.place_market_buy("btcusdt", "0.001")

    assert response.success is True
    assert fake_client.created_orders == [
        {
            "symbol": "BTCUSDT",
            "side": "BUY",
            "type": "MARKET",
            "quantity": "0.001",
            "recvWindow": 60000,
        }
    ]


def test_timestamp_error_syncs_and_retries_once() -> None:
    fake_client = FakeClient()
    fake_client.order_failures_before_success = 1
    client = BinanceFuturesDemoClient(settings(), raw_client=fake_client)

    response = client.place_market_sell("BTCUSDT", "0.001")

    assert response.success is True
    assert len(fake_client.created_orders) == 1
    assert fake_client.timestamp_offset != 0


def test_invalid_symbol_error_is_classified() -> None:
    class InvalidSymbolClient(FakeClient):
        def futures_symbol_ticker(self, **params: object) -> dict[str, str]:
            raise_binance_error(-1121, "Invalid symbol.")

    client = BinanceFuturesDemoClient(settings(), raw_client=InvalidSymbolClient())

    response = client.get_ticker_price("badpair")

    assert response.success is False
    assert response.error_type == "invalid_symbol"


def test_generic_binance_api_error_is_classified() -> None:
    class ApiFailureClient(FakeClient):
        def futures_account_balance(
            self,
            **params: object,
        ) -> list[dict[str, str]]:
            raise_binance_error(-1100, "Illegal characters found.")

    client = BinanceFuturesDemoClient(settings(), raw_client=ApiFailureClient())

    response = client.get_account_balances()

    assert response.success is False
    assert response.error_type == "binance_api_error"
    assert response.code == -1100


def test_network_error_is_classified() -> None:
    class NetworkFailureClient(FakeClient):
        def futures_symbol_ticker(self, **params: object) -> dict[str, str]:
            raise Timeout("request timed out")

    client = BinanceFuturesDemoClient(settings(), raw_client=NetworkFailureClient())

    response = client.get_ticker_price("BTCUSDT")

    assert response.success is False
    assert response.error_type == "network_error"


def test_cancel_order_requires_identifier() -> None:
    client = BinanceFuturesDemoClient(settings(), raw_client=FakeClient())

    response = client.cancel_order("BTCUSDT")

    assert response.success is False
    assert response.error_type == "invalid_request"


def settings() -> Settings:
    return Settings(
        api_key="key",
        api_secret="secret",
        futures_base_url="https://demo-fapi.binance.com",
        recv_window=60000,
        request_timeout=10,
        default_symbol="BTCUSDT",
        log_level="INFO",
    )


def raise_binance_error(code: int, message: str) -> None:
    payload = json.dumps({"code": code, "msg": message})
    raise BinanceAPIException(FakeResponse(), 400, payload)
