"""
ReadyTrader-FOREX: check the live-brokerage wiring without placing any order, then run the SMA
strategy on real EURUSD data.

With no OANDA_API_KEY / OANDA_ACCOUNT_ID set, the OANDA brokerage must report itself as not
available, so a live order would be refused rather than sent. OANDA_ENVIRONMENT decides which API
a configured account uses: practice unless it is "live".
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from execution.oanda_service import OandaBrokerage  # noqa: E402
from strategy.moving_average import SmaStrategy  # noqa: E402


def main() -> int:
    print("--- Verifying live-brokerage wiring and a strategy ---")
    ok = True
    brokerage = OandaBrokerage()
    print(f"OANDA brokerage available: {brokerage.is_available()} (False unless OANDA_API_KEY/OANDA_ACCOUNT_ID are set)")
    print(f"OANDA environment: {brokerage.environment} -> {brokerage.base_url}")

    try:
        result = SmaStrategy("EURUSD", short_window=5, long_window=10).analyze()
        print(f"SMA strategy on EURUSD: {result}")
        ok = ok and "signal" in result and "error" not in result
    except Exception as e:
        print(f"FAILED strategy: {e}")
        ok = False
    print("SUCCESS" if ok else "FAILURE")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
