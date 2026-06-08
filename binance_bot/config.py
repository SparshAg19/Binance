from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import find_dotenv, load_dotenv


class ConfigError(RuntimeError):
    def __init__(self, message: str) -> None:
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class Settings:
    api_key: str
    api_secret: str
    futures_base_url: str
    recv_window: int
    request_timeout: int
    default_symbol: str
    log_level: str

    @property
    def futures_api_url(self) -> str:
        base_url = self.futures_base_url.rstrip("/")
        if base_url.endswith("/fapi"):
            return base_url
        return f"{base_url}/fapi"


BASE_DIR = Path(__file__).resolve().parent


def load_settings(env_file: str | Path | None = None) -> Settings:
    _load_environment(env_file)

    api_key = _required_env("BINANCE_API_KEY")
    api_secret = (
        os.getenv("BINANCE_SECRET_KEY")
        or os.getenv("BINANCE_API_SECRET")
        or ""
    ).strip()
    if not api_secret:
        raise ConfigError(
            "Missing BINANCE_SECRET_KEY or BINANCE_API_SECRET in environment."
        )

    return Settings(
        api_key=api_key,
        api_secret=api_secret,
        futures_base_url=_env_str(
            "BINANCE_FUTURES_BASE_URL",
            "https://demo-fapi.binance.com",
        ),
        recv_window=_env_int("BINANCE_RECV_WINDOW", 60000),
        request_timeout=_env_int("BINANCE_REQUEST_TIMEOUT", 10),
        default_symbol=_env_str("BINANCE_DEFAULT_SYMBOL", "BTCUSDT").upper(),
        log_level=_env_str("LOG_LEVEL", "INFO").upper(),
    )


def _load_environment(env_file: str | Path | None) -> None:
    if env_file is not None:
        load_dotenv(Path(env_file), override=False)
        return

    load_dotenv(BASE_DIR / ".env", override=False)
    discovered = find_dotenv(usecwd=True)
    if discovered:
        load_dotenv(discovered, override=False)


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ConfigError(f"Missing {name} in environment.")
    return value


def _env_str(name: str, default: str) -> str:
    return os.getenv(name, default).strip() or default


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default

    try:
        parsed = int(value)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer.") from exc

    if parsed <= 0:
        raise ConfigError(f"{name} must be greater than zero.")
    return parsed
