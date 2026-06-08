from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Any


class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"


class TimeInForce(str, Enum):
    GTC = "GTC"
    IOC = "IOC"
    FOK = "FOK"
    GTX = "GTX"


@dataclass(frozen=True, slots=True)
class OrderRequest:
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: Decimal | str | int
    price: Decimal | str | int | None = None
    time_in_force: TimeInForce = TimeInForce.GTC

    def __post_init__(self) -> None:
        symbol = self.symbol.strip().upper()
        if not symbol:
            raise ValueError("Symbol is required.")

        object.__setattr__(self, "symbol", symbol)
        object.__setattr__(self, "quantity", coerce_decimal(self.quantity))

        if self.quantity <= Decimal("0"):
            raise ValueError("Quantity must be greater than zero.")

        if self.order_type is OrderType.LIMIT:
            if self.price is None:
                raise ValueError("Limit orders require a price.")

            price = coerce_decimal(self.price)
            if price <= Decimal("0"):
                raise ValueError("Price must be greater than zero.")
            object.__setattr__(self, "price", price)

    @classmethod
    def market(
        cls,
        symbol: str,
        side: OrderSide,
        quantity: Decimal | str | int,
    ) -> OrderRequest:
        return cls(
            symbol=symbol,
            side=side,
            order_type=OrderType.MARKET,
            quantity=quantity,
        )

    @classmethod
    def limit(
        cls,
        symbol: str,
        side: OrderSide,
        quantity: Decimal | str | int,
        price: Decimal | str | int,
        time_in_force: TimeInForce = TimeInForce.GTC,
    ) -> OrderRequest:
        return cls(
            symbol=symbol,
            side=side,
            order_type=OrderType.LIMIT,
            quantity=quantity,
            price=price,
            time_in_force=time_in_force,
        )

    def to_binance_params(self) -> dict[str, Any]:
        params: dict[str, Any] = {
            "symbol": self.symbol,
            "side": self.side.value,
            "type": self.order_type.value,
            "quantity": format_decimal(self.quantity),
        }

        if self.order_type is OrderType.LIMIT:
            params["price"] = format_decimal(self.price or Decimal("0"))
            params["timeInForce"] = self.time_in_force.value

        return params


def coerce_decimal(value: Decimal | str | int) -> Decimal:
    if isinstance(value, Decimal):
        parsed = value
    else:
        try:
            parsed = Decimal(str(value).strip())
        except (InvalidOperation, ValueError) as exc:
            raise ValueError(f"Invalid decimal value: {value}") from exc

    if not parsed.is_finite():
        raise ValueError("Decimal value must be finite.")
    return parsed


def format_decimal(value: Decimal) -> str:
    return format(value.normalize(), "f")
