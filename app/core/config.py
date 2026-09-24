import os

from dotenv import load_dotenv

from common.switches import approval_mode, kill_switch_on, safety_switch_on  # noqa: F401 (re-exported)

load_dotenv()


def _unapplied_number(name: str, default: float, cast=float):
    """A setting kept so existing configurations load, which no check applies: a malformed value
    falls back to the default instead of stopping the server."""
    try:
        return cast(os.getenv(name, str(default)).strip())
    except (TypeError, ValueError):
        return cast(default)


class Settings:
    PROJECT_NAME: str = "ReadyTrader-FOREX"
    VERSION: str = "0.1.0"

    # Inherited from ReadyTrader-Stocks and not used by any FOREX check (currency pairs trade 24/5;
    # the market guard judges bar freshness by the FX week, core/market_guard.py).
    MARKET_HOURS_START: str = os.getenv("MARKET_HOURS_START", "09:30")
    MARKET_HOURS_END: str = os.getenv("MARKET_HOURS_END", "16:00")
    MARKET_TIMEZONE: str = os.getenv("MARKET_TIMEZONE", "US/Eastern")
    # Not read by any check. The price-based Falling Knife rule and the volatility halt
    # (core/market_guard.py) are configured with the MARKET_GUARD_* settings below.
    CIRCUIT_BREAKER_PCT: float = _unapplied_number("CIRCUIT_BREAKER_PCT", 0.07)

    # Each switch fails toward the safe side (common/switches.py): paper mode stays on unless
    # explicitly false/0/no/off; live trading needs exactly "true"; the kill switch halts on any
    # value other than empty or false/0/no/off.
    PAPER_MODE: bool = safety_switch_on(os.getenv("PAPER_MODE", "true"))
    LIVE_TRADING_ENABLED: bool = os.getenv("LIVE_TRADING_ENABLED", "false").strip().lower() == "true"
    TRADING_HALTED: bool = kill_switch_on(os.getenv("TRADING_HALTED", "false"))

    # Risk & execution
    # "auto" or "approve_each"; any other value requires approval (fails closed).
    EXECUTION_APPROVAL_MODE: str = approval_mode(os.getenv("EXECUTION_APPROVAL_MODE", "auto"))
    # Read but not applied yet (kept so existing configurations load): the Risk Guardian limits are fixed.
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
    RATE_LIMIT_DEFAULT_PER_MIN: int = _unapplied_number("RATE_LIMIT_DEFAULT_PER_MIN", 120, int)

    # Forex Specifics. The paper account reads and validates LEVERAGE itself (core/fx_account.py) and
    # refuses to start on a value that is not a positive number.
    LEVERAGE: float = _unapplied_number("LEVERAGE", 30.0)
    DEFAULT_LOT_SIZE: int = 100000


settings = Settings()