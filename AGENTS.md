# ReadyTrader-FOREX

Root AGENTS.md (DOX rail).

## Purpose
A stdio MCP server (`app/main.py`, 29 tools) that lets an AI agent research currency pairs, trade a
persistent paper FX account, and optionally place live orders through OANDA behind a Risk Guardian,
a price-based market guard, an operator policy and a kill switch; plus an approval/dashboard API
(`app/api_server.py`) and a Next.js dashboard (`frontend/`).

## Ownership
- `app/`: MCP tool surface (`app/tools/`), settings (`app/core/config.py`), the container, the
  approval API.
- `core/`: pure rules and state: risk (`risk.py`), Falling Knife and volatility halt
  (`market_guard.py`), policy, the paper FX account (`fx_account.py`), backtest.
- `execution/`: brokerage connectors (OANDA is the only FX venue) and the approval store;
  `marketdata/`, `intelligence/`: data, calendar and news sources. `common/`: shared helpers
  (`switches.py`, `paths.py`).
- `research/falling_knife/`: the study behind `docs/FALLING_KNIFE.md`; nothing imports it.
- `_deprecated/`: history only, never loaded or shipped (see its README).

## Local Contracts
- Fail closed. Safety switches are parsed with `common/switches.py`: protections stay on unless
  explicitly `false/0/no/off`; `LIVE_TRADING_ENABLED` needs exactly `true`; the kill switch halts
  on any value but empty/off; an unknown `EXECUTION_APPROVAL_MODE` requires approval; an unreadable
  limit refuses live orders. Brokerage connectors default to practice/paper/sandbox accounts.
- Every live order passes `pre_trade_check` and `live_order_refusal` when placed or proposed, and
  again at execution (including `/api/approve-trade`). No simulated venue is registered for live
  orders, and a proposal executes only in the mode (paper/live) it was made in.
- FX positions go both ways: risk rules judge the exposure an order adds (from the paper account or
  the brokerage's positions), not its side. Size = USD notional of the added part; an order that adds
  exposure and cannot be valued or sized is refused; reducing or closing a position is never sized as
  new exposure. Unknown live positions count as new exposure.
- Paper orders fill only in `core/fx_account.FxPaperAccount` (shared by the MCP server and the API
  through `data/paper.db`).
- Tools answer `{"ok": true, "data"}` or `{"ok": false, "error": {"code", "message", "data"}}`; a
  source that cannot answer is an error, never a payload (never "no events"). New codes go in
  `docs/ERRORS.md`.
- Default data files live in `<repo>/data/` via `common/paths.data_path` (never the working
  directory); `READYTRADER_DATA_DIR` and each `*_PATH` variable override.
- Every variable the code reads is in `env.example`, with no inline comments or placeholder keys.
- Docs describe only what runs: after changing a tool, run `python tools/generate_tool_docs.py`
  (it reads the live registry) and update README / `docs/` in the same change.

## Work Guidance
- Python 3.12+. Regression test for every fix, failing on the old code.
- Money paths are paper or practice/sandbox only in development and UAT.

## Verification
- `ruff check .`, `pytest`, `bandit -q -c bandit.yaml -r app core common execution intelligence marketdata observability strategy`; the dashboard: `cd frontend && npm ci && npm run lint && npm run build` (CI runs all of them).
- `tests/test_tool_docs.py` keeps `docs/TOOLS.md` and the README's tool names in step with the server.
- Release UAT: `uat/UAT-LOG.md`.

## Child DOX Index
- `uat/AGENTS.md` — owns the UAT reporting log, ledger, and evidence for this project
