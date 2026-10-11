## ReadyTrader-FOREX Prompt Pack

Copy/paste prompts for Agent Zero, Claude, or any MCP-capable agent. Every tool they name is in
`docs/TOOLS.md`.

---

## Prompt 1 — 10-minute paper-mode evaluation

You have access to the ReadyTrader-FOREX MCP server. We are in PAPER_MODE=true.

Goals:
- Validate you can use the tools safely
- Produce a short "operator report" that proves the system works

Steps:
1) Call `get_forex_market_brief("EURUSD")` and `get_economic_calendar()`; summarize the rate, the
   dollar trend and any high-impact events this week.
2) Call `reset_paper_account()` and then `deposit_paper_funds("USD", 100000)`.
3) Call `validate_trade_risk("buy", "EURUSD", 2000, 100000)` and explain the verdict, including the
   `market` reading (Falling Knife and volatility ratio) and `inactive_rules`.
4) Place a paper market order: `place_market_order("EUR/USD", "buy", 2000)`. It fills at the latest
   rate; 2,000 is units of EUR.
5) Place a paper limit order below the market: `place_limit_order("EURUSD", "buy", 2000, <1% below
   the rate>)`. Explain the `limit_not_marketable` answer (resting orders are not simulated).
6) Open a short: `place_market_order("USDJPY", "sell", 3000)`.
7) Try an oversized order: `place_market_order("GBPUSD", "buy", 1000000)` and report the
   `risk_blocked` reason.
8) Call `get_paper_account()` and produce a final summary with:
   - each position, its unrealized P&L in USD and the margin in use
   - every refusal, with its `code` and `message`

Constraints:
- Do not attempt live trading.
- Every failed call returns `{"ok": false, "error": {"code", "message"}}`: quote both.

---

## Prompt 2 — Synthetic Stress Lab (deterministic)

We are in PAPER_MODE=true. I will provide strategy code. You will:
- run `run_synthetic_stress_test(strategy_code, config_json)`
- summarize tail risk and regime failures
- output recommended settings

Use this config as a baseline:
```json
{
  "master_seed": 1337,
  "scenarios": 200,
  "length": 500,
  "timeframe": "1h",
  "initial_capital": 10000,
  "start_price": 100,
  "base_vol": 0.015,
  "black_swan_prob": 0.03,
  "parabolic_prob": 0.03
}
```

Output requirements:
- Show max drawdown stats (p95 + max) and return tail (p05).
- List the worst-case seed(s) and their event metadata.
- Provide parameter recommendations (and explain what failure mode they address).

---

## Prompt 3 — Live trading preflight (DO NOT EXECUTE TRADES)

We are preparing for live mode, but you must not place any orders.

Tasks:
1) For each pair I plan to trade, call `get_stock_price(<pair>)` and
   `validate_trade_risk("buy", <pair>, <typical order in USD>, <account equity>)`; report any
   refusal, the Falling Knife reading and the volatility ratio.
2) Call `get_market_regime(<pair>)` and `get_economic_calendar()`; say whether my strategy suits the
   regime and which events this week touch the pair's currencies.
3) Output a "go/no-go" checklist for the operator to confirm before enabling live trading:
   - `PAPER_MODE=false` and `LIVE_TRADING_ENABLED=true`, and `TRADING_HALTED` unset
   - `EXECUTION_APPROVAL_MODE=approve_each` for the first live week
   - `MAX_BROKERAGE_ORDER_AMOUNT`, `ALLOW_BROKERAGE_SYMBOLS` and `ALLOW_EXCHANGES=oanda` set to the
     smallest workable values
   - OANDA on its practice account first (`OANDA_ENVIRONMENT=practice`, the default)
   - the approval API running with the same `EXECUTION_SESSION_ID` (see `RUNBOOK.md`)
   - a plan for news releases: the server does not pause trading around them
