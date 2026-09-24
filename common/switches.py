"""How on/off settings are read. Every switch fails toward the safe side, so a typo or an
unexpected spelling ("1", "yes", "TRUE ") can never quietly turn a protection off."""

from __future__ import annotations

_OFF = ("false", "0", "no", "off")


def safety_switch_on(value: str | None) -> bool:
    """A protection that is on by default (PAPER_MODE, MARKET_GUARD_ENABLED): only an explicit
    false/0/no/off turns it off, so "treu" or an empty value leaves it on."""
    return (value or "").strip().lower() not in _OFF


def kill_switch_on(value: str | None) -> bool:
    """TRADING_HALTED: unset, empty or an explicit false/0/no/off means trading continues; any
    other value ("true", "1", "yes", "on", a typo) halts it."""
    return (value or "").strip().lower() not in ("",) + _OFF



def approval_mode(value: str | None) -> str:
    """EXECUTION_APPROVAL_MODE: unset or "auto" executes orders directly; any other value
    ("approve_each", a misspelling, a value with a trailing comment) requires approval."""
    return "auto" if (value or "auto").strip().lower() == "auto" else "approve_each"


def opt_in_switch_on(value: str | None) -> bool:
    """An opt-in setting that is off by default (ETRADE_SANDBOX): "true", "1", "yes" or "on" in any
    case turns it on."""
    return (value or "").strip().lower() in ("true", "1", "yes", "on")
