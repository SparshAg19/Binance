from __future__ import annotations

import json
import sys
from dataclasses import dataclass

from binance_client import ApiResponse, BinanceFuturesDemoClient
from config import ConfigError, Settings, load_settings
from logger import setup_logging
from orders import OrderSide, TimeInForce, coerce_decimal


@dataclass(slots=True)
class TradingCli:
    client: BinanceFuturesDemoClient
    settings: Settings

    def run(self) -> int:
        print("Connecting to Binance Futures Demo...")
        connection = self.client.connect()
        self._print_response(connection)
        if not connection.success:
            return 1

        self._display_startup_snapshot()
        self._menu_loop()
        return 0

    def _display_startup_snapshot(self) -> None:
        balance = self.client.get_usdt_balance()
        if balance.success and isinstance(balance.data, dict):
            available = balance.data.get("available_balance")
            total = balance.data.get("balance")
            print(f"USDT balance: {total} | available: {available}")
        else:
            self._print_response(balance)

        ticker = self.client.get_ticker_price(self.settings.default_symbol)
        if ticker.success and isinstance(ticker.data, dict):
            print(
                f"{ticker.data.get('symbol')} price: "
                f"{ticker.data.get('price')}"
            )
        else:
            self._print_response(ticker)

    def _menu_loop(self) -> None:
        while True:
            print()
            print("1. Market BUY")
            print("2. Market SELL")
            print("3. Limit order")
            print("4. View open orders")
            print("5. Cancel order")
            print("6. Get ticker price")
            print("0. Exit")

            choice = input("Select an option: ").strip()
            if choice == "0":
                print("Goodbye.")
                return
            if choice == "1":
                self._place_market_order(OrderSide.BUY)
            elif choice == "2":
                self._place_market_order(OrderSide.SELL)
            elif choice == "3":
                self._place_limit_order()
            elif choice == "4":
                self._view_open_orders()
            elif choice == "5":
                self._cancel_order()
            elif choice == "6":
                self._show_ticker_price()
            else:
                print("Invalid option.")

    def _place_market_order(self, side: OrderSide) -> None:
        try:
            symbol = self._prompt_symbol()
            quantity = self._prompt_decimal("Quantity")
        except ValueError as exc:
            print(f"Invalid input: {exc}")
            return

        if not self._confirm_order(side.value, symbol, quantity):
            print("Order skipped.")
            return

        if side is OrderSide.BUY:
            response = self.client.place_market_buy(symbol, quantity)
        else:
            response = self.client.place_market_sell(symbol, quantity)
        self._print_response(response)

    def _place_limit_order(self) -> None:
        try:
            symbol = self._prompt_symbol()
            side = self._prompt_side()
            quantity = self._prompt_decimal("Quantity")
            price = self._prompt_decimal("Limit price")
            time_in_force = self._prompt_time_in_force()
        except ValueError as exc:
            print(f"Invalid input: {exc}")
            return

        description = f"LIMIT {side.value}"
        if not self._confirm_order(description, symbol, quantity, price):
            print("Order skipped.")
            return

        response = self.client.place_limit_order(
            symbol=symbol,
            side=side,
            quantity=quantity,
            price=price,
            time_in_force=time_in_force,
        )
        self._print_response(response)

    def _view_open_orders(self) -> None:
        symbol = input("Symbol filter, blank for all: ").strip()
        response = self.client.get_open_orders(symbol or None)
        self._print_response(response)

    def _cancel_order(self) -> None:
        symbol = self._prompt_symbol()
        order_id_value = input("Order ID, blank to use client order ID: ").strip()
        client_order_id = ""

        try:
            order_id = int(order_id_value) if order_id_value else None
        except ValueError:
            print("Order ID must be a whole number.")
            return

        if order_id is None:
            client_order_id = input("Original client order ID: ").strip()

        response = self.client.cancel_order(
            symbol=symbol,
            order_id=order_id,
            orig_client_order_id=client_order_id or None,
        )
        self._print_response(response)

    def _show_ticker_price(self) -> None:
        symbol = self._prompt_symbol()
        response = self.client.get_ticker_price(symbol)
        self._print_response(response)

    def _prompt_symbol(self) -> str:
        prompt = f"Symbol [{self.settings.default_symbol}]: "
        symbol = input(prompt).strip().upper()
        return symbol or self.settings.default_symbol

    def _prompt_decimal(self, label: str) -> str:
        value = input(f"{label}: ").strip()
        coerce_decimal(value)
        return value

    def _prompt_side(self) -> OrderSide:
        value = input("Side [BUY/SELL]: ").strip().upper()
        try:
            return OrderSide(value)
        except ValueError as exc:
            raise ValueError("Side must be BUY or SELL.") from exc

    def _prompt_time_in_force(self) -> TimeInForce:
        value = input("Time in force [GTC]: ").strip().upper() or "GTC"
        try:
            return TimeInForce(value)
        except ValueError as exc:
            raise ValueError("Time in force must be GTC, IOC, FOK, or GTX.") from exc

    def _confirm_order(
        self,
        order_description: str,
        symbol: str,
        quantity: str,
        price: str | None = None,
    ) -> bool:
        detail = f"{order_description} {quantity} {symbol}"
        if price is not None:
            detail = f"{detail} at {price}"
        confirmation = input(f"Place demo order: {detail}? [y/N]: ")
        return confirmation.strip().lower() == "y"

    def _print_response(self, response: ApiResponse) -> None:
        print(json.dumps(response.to_dict(), indent=2, default=str))


def main() -> int:
    try:
        settings = load_settings()
        app_logger = setup_logging(settings.log_level)
        client = BinanceFuturesDemoClient(settings=settings, logger=app_logger)
        return TradingCli(client=client, settings=settings).run()
    except ConfigError as exc:
        setup_logging("ERROR")
        print(f"Configuration error: {exc}")
        return 1
    except KeyboardInterrupt:
        print()
        print("Interrupted.")
        return 130


if __name__ == "__main__":
    sys.exit(main())
