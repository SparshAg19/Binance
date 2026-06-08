from __future__ import annotations

import logging
import time
from dataclasses import asdict, dataclass
from typing import Any, Callable, TypeVar

from binance.client import Client
from binance.exceptions import BinanceAPIException, BinanceRequestException
from requests.exceptions import RequestException

from config import Settings
from logger import get_logger
from orders import OrderRequest, OrderSide, TimeInForce, coerce_decimal


T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class ApiResponse:
    success: bool
    message: str
    data: Any | None = None
    error: str | None = None
    error_type: str | None = None
    code: int | None = None
    status_code: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            key: value
            for key, value in asdict(self).items()
            if value is not None
        }


class BinanceFuturesDemoClient:
    _TIMESTAMP_ERROR_CODES = {-1021, -1022}
    _INVALID_SYMBOL_CODES = {-1121}
    _INSUFFICIENT_BALANCE_CODES = {-2010, -2019}

    def __init__(
        self,
        settings: Settings,
        logger: logging.Logger | None = None,
        raw_client: Client | None = None,
    ) -> None:
        self.settings = settings
        self.logger = logger or get_logger(__name__)
        self._client = raw_client or self._create_client(settings)

    def connect(self) -> ApiResponse:
        ping_response = self._execute(
            self._client.futures_ping,
            "Connected to Binance Futures Demo.",
            activity="futures_ping",
            retry_timestamp=False,
        )
        if not ping_response.success:
            return ping_response

        sync_response = self.sync_timestamp()
        if not sync_response.success:
            return sync_response

        return ApiResponse(
            success=True,
            message="Connected to Binance Futures Demo.",
            data={
                "endpoint": self.settings.futures_base_url,
                "timestamp_offset_ms": sync_response.data[
                    "timestamp_offset_ms"
                ],
            },
        )

    def sync_timestamp(self) -> ApiResponse:
        try:
            server_payload = self._client.futures_time()
            server_time = int(server_payload["serverTime"])
            local_time = int(time.time() * 1000)
            offset = server_time - local_time
            self._client.timestamp_offset = offset

            self.logger.info(
                "Timestamp synchronized with offset %sms.",
                offset,
            )
            return ApiResponse(
                success=True,
                message="Timestamp synchronized.",
                data={
                    "server_time": server_time,
                    "local_time": local_time,
                    "timestamp_offset_ms": offset,
                },
            )
        except Exception as exc:
            return self._exception_response(
                exc,
                fallback_message="Failed to synchronize timestamp.",
                activity="sync_timestamp",
            )

    def get_account_balances(self) -> ApiResponse:
        return self._execute(
            lambda: self._client.futures_account_balance(
                recvWindow=self.settings.recv_window,
            ),
            "Account balances retrieved.",
            activity="get_account_balances",
        )

    def get_usdt_balance(self) -> ApiResponse:
        balances_response = self.get_account_balances()
        if not balances_response.success:
            return balances_response

        balances = balances_response.data or []
        usdt_balance = next(
            (
                balance
                for balance in balances
                if balance.get("asset") == "USDT"
            ),
            None,
        )
        if usdt_balance is None:
            return ApiResponse(
                success=False,
                message="USDT balance was not found.",
                error="USDT balance was not present in the futures account.",
                error_type="balance_not_found",
            )

        return ApiResponse(
            success=True,
            message="USDT balance retrieved.",
            data={
                "asset": "USDT",
                "balance": usdt_balance.get("balance"),
                "available_balance": usdt_balance.get("availableBalance"),
                "cross_wallet_balance": usdt_balance.get(
                    "crossWalletBalance"
                ),
            },
        )

    def get_ticker_price(self, symbol: str) -> ApiResponse:
        try:
            normalized_symbol = self._normalize_symbol(symbol)
        except ValueError as exc:
            return self._invalid_request_response(exc)

        return self._execute(
            lambda: self._client.futures_symbol_ticker(
                symbol=normalized_symbol,
            ),
            f"{normalized_symbol} ticker price retrieved.",
            activity=f"get_ticker_price:{normalized_symbol}",
            retry_timestamp=False,
        )

    def place_market_buy(
        self,
        symbol: str,
        quantity: str | int,
    ) -> ApiResponse:
        return self.place_order(
            OrderRequest.market(
                symbol=symbol,
                side=OrderSide.BUY,
                quantity=coerce_decimal(quantity),
            ),
        )

    def place_market_sell(
        self,
        symbol: str,
        quantity: str | int,
    ) -> ApiResponse:
        return self.place_order(
            OrderRequest.market(
                symbol=symbol,
                side=OrderSide.SELL,
                quantity=coerce_decimal(quantity),
            ),
        )

    def place_limit_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: str | int,
        price: str | int,
        time_in_force: TimeInForce = TimeInForce.GTC,
    ) -> ApiResponse:
        return self.place_order(
            OrderRequest.limit(
                symbol=symbol,
                side=side,
                quantity=coerce_decimal(quantity),
                price=coerce_decimal(price),
                time_in_force=time_in_force,
            ),
        )

    def place_order(self, order_request: OrderRequest) -> ApiResponse:
        params = order_request.to_binance_params()
        params["recvWindow"] = self.settings.recv_window

        return self._execute(
            lambda: self._client.futures_create_order(**params),
            (
                f"{order_request.order_type.value} "
                f"{order_request.side.value} order placed."
            ),
            activity=(
                "place_order:"
                f"{order_request.symbol}:"
                f"{order_request.side.value}:"
                f"{order_request.order_type.value}"
            ),
        )

    def get_open_orders(self, symbol: str | None = None) -> ApiResponse:
        try:
            params = {"recvWindow": self.settings.recv_window}
            if symbol:
                params["symbol"] = self._normalize_symbol(symbol)
        except ValueError as exc:
            return self._invalid_request_response(exc)

        return self._execute(
            lambda: self._client.futures_get_open_orders(**params),
            "Open orders retrieved.",
            activity="get_open_orders",
        )

    def cancel_order(
        self,
        symbol: str,
        order_id: int | None = None,
        orig_client_order_id: str | None = None,
    ) -> ApiResponse:
        try:
            params: dict[str, Any] = {
                "symbol": self._normalize_symbol(symbol),
                "recvWindow": self.settings.recv_window,
            }
            if order_id is not None:
                params["orderId"] = order_id
            if orig_client_order_id:
                params["origClientOrderId"] = orig_client_order_id.strip()
            if "orderId" not in params and "origClientOrderId" not in params:
                raise ValueError(
                    "Provide an order ID or original client order ID."
                )
        except ValueError as exc:
            return self._invalid_request_response(exc)

        return self._execute(
            lambda: self._client.futures_cancel_order(**params),
            "Order canceled.",
            activity=f"cancel_order:{params['symbol']}",
        )

    def _create_client(self, settings: Settings) -> Client:
        client = Client(
            settings.api_key,
            settings.api_secret,
            requests_params={"timeout": settings.request_timeout},
            demo=True,
            ping=False,
        )
        client.FUTURES_DEMO_URL = settings.futures_api_url
        client.FUTURES_URL = settings.futures_api_url
        return client

    def _execute(
        self,
        action: Callable[[], T],
        success_message: str,
        *,
        activity: str,
        retry_timestamp: bool = True,
    ) -> ApiResponse:
        try:
            data = action()
            self.logger.info("%s succeeded.", activity)
            return ApiResponse(
                success=True,
                message=success_message,
                data=data,
            )
        except BinanceAPIException as exc:
            if retry_timestamp and exc.code in self._TIMESTAMP_ERROR_CODES:
                self.logger.warning(
                    "%s failed due to timestamp drift; resynchronizing.",
                    activity,
                )
                sync_response = self.sync_timestamp()
                if sync_response.success:
                    return self._execute(
                        action,
                        success_message,
                        activity=activity,
                        retry_timestamp=False,
                    )

            return self._exception_response(
                exc,
                fallback_message=f"{activity} failed.",
                activity=activity,
            )
        except Exception as exc:
            return self._exception_response(
                exc,
                fallback_message=f"{activity} failed.",
                activity=activity,
            )

    def _exception_response(
        self,
        exc: Exception,
        *,
        fallback_message: str,
        activity: str,
    ) -> ApiResponse:
        if isinstance(exc, BinanceAPIException):
            error_type = self._classify_api_error(exc)
            error = self._api_error_message(exc, error_type)
            self.logger.warning(
                "%s failed with Binance API error %s: %s",
                activity,
                exc.code,
                error,
            )
            return ApiResponse(
                success=False,
                message=fallback_message,
                error=error,
                error_type=error_type,
                code=exc.code,
                status_code=exc.status_code,
            )

        if isinstance(exc, BinanceRequestException):
            self.logger.warning(
                "%s failed with Binance request error: %s",
                activity,
                exc,
            )
            return ApiResponse(
                success=False,
                message=fallback_message,
                error=str(exc),
                error_type="binance_request_error",
            )

        if isinstance(exc, RequestException):
            self.logger.warning("%s failed with network error: %s", activity, exc)
            return ApiResponse(
                success=False,
                message=fallback_message,
                error=str(exc),
                error_type="network_error",
            )

        if isinstance(exc, ValueError):
            return self._invalid_request_response(exc)

        self.logger.exception("%s failed unexpectedly.", activity)
        return ApiResponse(
            success=False,
            message=fallback_message,
            error=str(exc),
            error_type="unexpected_error",
        )

    def _invalid_request_response(self, exc: ValueError) -> ApiResponse:
        self.logger.warning("Invalid request: %s", exc)
        return ApiResponse(
            success=False,
            message="Invalid request.",
            error=str(exc),
            error_type="invalid_request",
        )

    def _classify_api_error(self, exc: BinanceAPIException) -> str:
        if exc.code in self._TIMESTAMP_ERROR_CODES:
            return "timestamp_error"
        if exc.code in self._INVALID_SYMBOL_CODES:
            return "invalid_symbol"
        if exc.code in self._INSUFFICIENT_BALANCE_CODES:
            return "insufficient_balance"
        if exc.status_code in {408, 429, 500, 502, 503, 504}:
            return "network_or_exchange_error"
        return "binance_api_error"

    def _api_error_message(
        self,
        exc: BinanceAPIException,
        error_type: str,
    ) -> str:
        if error_type == "timestamp_error":
            return "Timestamp synchronization failed. Please try again."
        if error_type == "invalid_symbol":
            return "Invalid futures symbol. Verify it exists on USDT-M Futures."
        if error_type == "insufficient_balance":
            return "Insufficient futures balance or margin for this order."
        return exc.message or str(exc)

    def _normalize_symbol(self, symbol: str) -> str:
        normalized = symbol.strip().upper()
        if not normalized:
            raise ValueError("Symbol is required.")
        return normalized
