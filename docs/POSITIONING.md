## ReadyTrader-FOREX Positioning (Aggressive Marketing, Credibility-Safe)

### What ReadyTrader-FOREX is (credible one-liner)

**ReadyTrader-FOREX is a safety-governed forex trading MCP server** that lets AI agents (Claude, Agent Zero, any MCP client) research currency pairs, trade a realistic paper FX account, and optionally trade live through OANDA, with every order passing a Risk Guardian that reads real market data.

### What ReadyTrader-FOREX is not (set expectations up front)

- **Not a "guaranteed profitable bot"**. It is tooling; outcomes depend on strategy, supervision, market conditions and execution.
- **Not financial advice** (see `DISCLAIMER.md`).
- **Not a trading platform UI**. It is an MCP server for agents and developers, with a small approval dashboard.

---

## Messaging pillars

### 1) Safety-first automation (the "trust" hook)

- **Paper mode by default** (`PAPER_MODE=true`), and OANDA's practice API by default when live.
- **Live trading is opt-in twice**: `PAPER_MODE=false` and `LIVE_TRADING_ENABLED=true`.
- **Kill switch** (`TRADING_HALTED`) and **approve-each mode** with a per-proposal token and a re-check at approval time.
- **Risk Guardian**: 5% of equity per trade by USD notional, daily-loss and drawdown limits.
- **Market guard with evidence**: the Falling Knife rule and the volatility halt were chosen on 2003-2016 data and tested once on 24 pairs the choice never saw (`docs/FALLING_KNIFE.md`).
- **Fails closed**: a check it cannot run refuses a BUY instead of guessing.

### 2) Agent-first UX (the "why MCP" hook)

Every tool answers structured JSON with a stable error code (`docs/ERRORS.md`), so agents can plan, recover from failures and respect operator limits. A source that cannot answer says so; it is never reported as "no events".

### 3) FX-native paper account (the "realism" hook)

USD cash, one netted position per pair (long or short), margin at configurable leverage, P&L in the quote currency converted to USD, persisted between runs.

### 4) Research & robustness (the "seriousness" hook)

Backtesting of agent-written strategies, synthetic black-swan stress tests with deterministic replay, market-regime detection, the week's economic calendar and FX news, with no key needed.

---

## Differentiation

### vs "place order" MCP wrappers
ReadyTrader-FOREX adds live-trading governance (opt-in switches, kill switch, approval mode), a policy engine, a data-driven market guard, a margin-aware paper account and a stress lab.

### vs purpose-built AI trading bots
ReadyTrader-FOREX is **infrastructure**, not an opinionated strategy: it works with any MCP agent and lets you keep your own logic on a safer execution layer.

---

## Safe claims (copy/paste)

- "**Safety-governed** forex trading tools for AI agents"
- "Safe by default: **paper mode**, then OANDA **practice**, then live only by explicit opt-in"
- "A Falling Knife rule and volatility halt **tested on 24 pairs they had never seen**"
- "Designed for **agent workflows**: structured outputs and consistent error codes"

Avoid:

- "Guaranteed profit" or any performance claim
- "Institutional-grade execution" (no production references)
- "Supports every broker" (OANDA is the only FX connector; see `docs/EXCHANGES.md`)
- "News-aware trading halts" (the news blackout is not implemented; verdicts list it under `inactive_rules`)

---

## Recommended copy

### Short
ReadyTrader-FOREX turns your MCP-capable AI agent into a **risk-aware FX operator**: research pairs, trade a margin-aware paper account, and go live through OANDA only when you opt in, with every order checked against your account and the market.

### Longer (GitHub / Discord)
ReadyTrader-FOREX is a forex MCP server for Claude, Agent Zero or any MCP client. It ships a persistent paper FX account (netted positions, margin, USD P&L), the week's economic calendar and FX news without keys, backtesting and synthetic stress tests, and a live-trading safety layer: opt-in switches, a kill switch, approve-each mode, a policy engine and a market guard whose thresholds were tested on pairs they never saw.

---

## Audiences

- **Agent Zero / Claude Desktop users**: Docker-first, paper by default, one config file (`configs/`).
- **Developers building agent workflows**: structured JSON, consistent error codes, a generated tool catalog (`docs/TOOLS.md`).
- **Risk-conscious operators**: opt-in live trading, kill switch, approval with re-check, policy limits, fail-closed checks.

## Demo ideas

- **5-minute paper demo**: `examples/paper_quick_demo.py`, then in an agent: brief → calendar → order → `get_paper_account()`.
- **Stress test demo**: `examples/stress_test_demo.py` and its report artifacts.
- **Safety demo**: a live order refused until both switches are on; `TRADING_HALTED` stopping it; an oversized order refused by the Risk Guardian.

## Assets to keep aligned before marketing pushes

- `README.md`, `docs/TOOLS.md` (regenerate with `python tools/generate_tool_docs.py`), `env.example`, `RUNBOOK.md`, `docs/FALLING_KNIFE.md`
