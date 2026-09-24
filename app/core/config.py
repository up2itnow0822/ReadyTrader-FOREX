import os

from dotenv import load_dotenv

load_dotenv()


def safety_switch_on(value: str | None) -> bool:
    """A safety check's on/off setting: only an explicit false/0/no/off turns it off, so a typo
    such as "treu" can never silently disable it."""
    return (value or "").strip().lower() not in ("false", "0", "no", "off")


class Settings:
    PROJECT_NAME: str = "ReadyTrader-FOREX"
    VERSION: str = "0.1.0"

    # Stock Market Specifics
    MARKET_HOURS_START: str = os.getenv("MARKET_HOURS_START", "09:30")
    MARKET_HOURS_END: str = os.getenv("MARKET_HOURS_END", "16:00")
    MARKET_TIMEZONE: str = os.getenv("MARKET_TIMEZONE", "US/Eastern")
    # Not read by any check. The price-based Falling Knife rule and the volatility halt
    # (core/market_guard.py) are configured with the MARKET_GUARD_* settings below.
    CIRCUIT_BREAKER_PCT: float = float(os.getenv("CIRCUIT_BREAKER_PCT", "0.07"))

    PAPER_MODE: bool = os.getenv("PAPER_MODE", "true").lower() == "true"
    LIVE_TRADING_ENABLED: bool = os.getenv("LIVE_TRADING_ENABLED", "false").strip().lower() == "true"
    TRADING_HALTED: bool = os.getenv("TRADING_HALTED", "false").strip().lower() == "true"

    # Risk & execution
    EXECUTION_APPROVAL_MODE: str = os.getenv("EXECUTION_APPROVAL_MODE", "auto").strip().lower()
    EXECUTION_MODE: str = os.getenv("EXECUTION_MODE", "auto").strip().lower()
    RISK_PROFILE: str = os.getenv("RISK_PROFILE", "conservative").strip().lower()

    # Falling Knife (price) and volatility halt - docs/FALLING_KNIFE.md. Every trade check and order
    # reads recent daily bars for the pair. Only an explicit false/0/no/off turns it off.
    MARKET_GUARD_ENABLED: bool = safety_switch_on(os.getenv("MARKET_GUARD_ENABLED", "true"))
    # What a BUY does when the daily bars cannot be read: "block" or "allow". Unset means block in
    # live mode (a missed buy is recoverable, a buy into a collapse is not) and allow in paper mode.
    # A SELL is never blocked for missing data.
    MARKET_GUARD_ON_DATA_ERROR: str = os.getenv("MARKET_GUARD_ON_DATA_ERROR", "").strip().lower()

    # Observability
    RATE_LIMIT_DEFAULT_PER_MIN: int = int(os.getenv("RATE_LIMIT_DEFAULT_PER_MIN", "120"))

    # Forex Specifics
    LEVERAGE: int = int(os.getenv("LEVERAGE", "30"))
    DEFAULT_LOT_SIZE: int = 100000


settings = Settings()
