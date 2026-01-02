from __future__ import annotations


def venue_allowed(execution_mode: str, venue: str) -> bool:
    """
    Forex-optimized router.

    In this version, we support 'live' and 'paper' modes.
    Legacy 'cex'/'dex' terminology is removed.
    """
    m = (execution_mode or "").strip().lower()
    v = (venue or "").strip().lower()

    # If live mode is enabled, we allow configured brokerages
    if m == "live":
        return v != "paper"

    # In paper mode, we only allow simulated execution
    if m == "paper":
        return v == "paper"

    # Default to paper for safety if unspecified
    return v == "paper"
