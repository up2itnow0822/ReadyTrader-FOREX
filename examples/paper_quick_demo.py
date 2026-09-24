"""
ReadyTrader-FOREX paper-mode quick demo (offline).

Exercises the paper FX account the server trades in (core/fx_account.FxPaperAccount) with fixed,
made-up rates, so it needs no network and no MCP client:

- a USD deposit
- a EURUSD long, marked to a new rate (unrealized P&L in USD)
- a USDJPY short, whose P&L is in JPY and is converted to USD
- closing both (realized P&L), margin, and the risk metrics the Risk Guardian reads

It writes to a temporary database and leaves your real paper account (data/paper.db) untouched.
Exit code 0 means every step did what it should.
"""

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.fx_account import FxPaperAccount  # noqa: E402

USER = "demo_user"
# Made-up rates for the demo: {pair: rate}. The account asks this function for every rate it needs.
RATES = {"EURUSD": 1.1000, "USDJPY": 150.00}


def quote(symbol: str) -> float:
    return RATES[symbol.replace("/", "").upper()]


def show(title: str, account: FxPaperAccount) -> dict:
    snap = account.account(USER)
    print(f"\n{title}")
    print(json.dumps({k: snap[k] for k in ("cash_usd", "equity_usd", "unrealized_usd", "margin_used_usd", "free_margin_usd", "positions")}, indent=2))
    return snap


def main() -> int:
    failures = []

    def expect(condition: bool, what: str) -> None:
        print(f"  {'ok  ' if condition else 'FAIL'} {what}")
        if not condition:
            failures.append(what)

    with tempfile.TemporaryDirectory() as td:
        account = FxPaperAccount(db_path=str(Path(td) / "paper_demo.db"), quote=quote, leverage=30)
        print("=== ReadyTrader-FOREX paper-mode quick demo (rates are made up) ===")

        print("\n1) Deposit 10,000 USD")
        print(" ", account.deposit(USER, "USD", 10_000))

        print("\n2) Buy 10,000 EURUSD at 1.1000 (a long of 10,000 EUR)")
        print(" ", account.execute_trade(USER, "buy", "EURUSD", 10_000, RATES["EURUSD"], rationale="demo entry"))
        snap = show("   Account after the buy:", account)
        expect(abs(snap["margin_used_usd"] - 10_000 * 1.10 / 30) < 0.01, "margin is the USD notional / leverage (366.67)")

        print("\n3) EURUSD rises to 1.1100: the long is worth 100 USD more")
        RATES["EURUSD"] = 1.1100
        snap = show("   Marked to 1.1100:", account)
        expect(abs(snap["unrealized_usd"] - 100.0) < 0.01, "unrealized P&L is +100.00 USD")

        print("\n4) Short 5,000 USDJPY at 150.00 (sell 5,000 USD for 750,000 JPY)")
        print(" ", account.execute_trade(USER, "sell", "USDJPY", 5_000, RATES["USDJPY"], rationale="demo short"))
        RATES["USDJPY"] = 148.50
        snap = show("   USDJPY falls to 148.50 (the short gains 7,500 JPY, about 50.51 USD):", account)
        expect(abs(snap["unrealized_usd"] - (100.0 + 5_000 * 1.5 / 148.50)) < 0.01, "JPY P&L is converted to USD at the current rate")

        print("\n5) Close both positions at the current rates")
        print(" ", account.execute_trade(USER, "sell", "EURUSD", 10_000, RATES["EURUSD"], rationale="demo exit"))
        print(" ", account.execute_trade(USER, "buy", "USDJPY", 5_000, RATES["USDJPY"], rationale="demo exit"))
        snap = show("   Flat again:", account)
        expect(not snap["positions"] and snap["margin_used_usd"] == 0, "no open positions, no margin in use")
        expect(abs(snap["cash_usd"] - (10_000 + 100.0 + 5_000 * 1.5 / 148.50)) < 0.01, "realized P&L is in cash")

        print("\n6) Risk metrics (what the Risk Guardian reads before every BUY)")
        print(json.dumps(account.get_risk_metrics(USER), indent=2))

    if failures:
        print(f"\nFAILED: {len(failures)} step(s) did not do what they should: {failures}")
        return 1
    print("\nDone: every step checked out. Next: python examples/stress_test_demo.py for the synthetic stress lab.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
