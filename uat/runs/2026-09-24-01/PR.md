## UAT run `2026-09-24-01` — ready for release review (2 items blocked on credentials / Docker)

Acting as the user, exercised every surface of ReadyTrader-FOREX end to end (MCP server over stdio,
approval API, dashboard, CLI scripts, config, docs, registry manifest), fixed every failure on this
branch, and retested each fix with fresh evidence. Money paths ran in paper mode, against fake
brokerages, or against OANDA's **practice** API with a bogus token (the failure path only); no order
was placed on any account.

**Stacked on #4** (`feat/market-falling-knife`, the price-based Falling Knife and volatility halt).
Review and merge #4 first; this PR's diff is the UAT work on top of it.

**Totals:** 60 checks · 6 pass · 52 fail (52 fixed & verified) · 2 blocked · 429 tests pass, ruff and bandit clean, dashboard installs, lints and builds.

| Section | Pass | Fail | Verified fixed | Blocked |
|---|---|---|---|---|
| preflight | 1 | 5 | 5 | 0 |
| backend | 0 | 24 | 24 | 0 |
| data | 1 | 0 | 0 | 0 |
| memory | 0 | 2 | 2 | 0 |
| frontend | 2 | 5 | 5 | 0 |
| integrations | 0 | 4 | 4 | 1 |
| cli | 0 | 2 | 2 | 0 |
| config | 0 | 7 | 7 | 0 |
| docs | 0 | 3 | 3 | 1 |
| regression | 2 | 0 | 0 | 0 |

### What was broken and is now fixed
- **critical** PRE-01 — README local install (pip install -r requirements-dev.txt) then python app/main.py → requirements.txt pins mcp>=1.24.0,<2 (`a12f405`)
- **critical** PRE-03 — MCP server registers its tools (python -m app.main, mcp 1.x) → execution tools registered with mcp.tool(fn) (`a12f405`)
- **high** BE-01 — Paper market order executes (README: place_market_order('EUR/USD','buy',1000)) → orders fill in core/fx_account.FxPaperAccount at the latest rate (execute_order) (`9976ddc`)
- **high** BE-02 — A paper limit order fills only when the market reaches it → paper_fill_price: limits fill only when marketable, at the market (`9976ddc`)
- **high** BE-05 — The 5%-of-account size rule values an FX order at its USD notional against the real account → size rule values base-currency notional in USD (core/fx_account.notional_usd) against the account's equity (paper) or the brokerage's (live); a BUY it cannot size fails closed (`9976ddc`)
- **high** BE-06 — Live orders pass LIVE_TRADING_ENABLED and TRADING_HALTED, then reach the brokerage → live_order_refusal (LIVE_TRADING_ENABLED, TRADING_HALTED, policy with order_type) at proposal and execution; PolicyError codes returned; MAX_BROKERAGE_ORDER_AMOUNT fails closed (`9976ddc`)
- **high** BE-10 — approve_each: a proposal made by the MCP server can be approved through the API → EXECUTION_SESSION_ID shares the proposal namespace across processes; approvals execute through execute_order (`9976ddc`)
- **high** BE-11 — The API's portfolio (dashboard) is the paper account the agent trades → the API reads and executes on the shared FxPaperAccount (global_container.paper_engine) (`9976ddc`)
- **high** BE-13 — run_synthetic_stress_test, documented in the README and the stress demo, is an MCP tool → run_synthetic_stress_test registered as an MCP tool (`33bf5e1`)
- **high** BE-22 — A live-mode order never reports a simulated fill as a live trade → Retired execution/forex_paper.py to _deprecated/ and removed it from the brokerage map; a live order to an unregistered venue is refused with brokerage_not_supported before any check runs (`cfc094e`)
- **high** BE-26 — The risk rules judge the exposure an order adds, not its side (FX positions go both ways) → pre_trade_check reads the position (paper account / brokerage list_positions) and sizes only the exposure an order adds; drawdown, daily-loss, sentiment and Falling Knife rules refuse only orders that add exposure (`eed8f6f`)
- **high** BE-27 — Every live order that adds exposure is sized, whichever its side → An order that adds exposure fails closed without equity or a rate, whatever its side; unknown live positions count as new exposure; an unconfigured brokerage is refused first (`eed8f6f`)
- **high** BE-28 — A proposal executes in the mode it was proposed in → Proposals record paper_mode; /api/approve-trade refuses a proposal made in the other mode (409 mode_mismatch) (`eed8f6f`)
- **high** CF-02 — Safety settings fail closed: approval mode and paper mode → PAPER_MODE, TRADING_HALTED and EXECUTION_APPROVAL_MODE parsed with common/switches (fail closed) (`9976ddc`)
- **high** CF-03 — Brokerage sandbox switches keep Tradier and E*TRADE out of production → Tradier uses safety_switch_on(TRADIER_SANDBOX, default true); E*TRADE uses opt_in_switch_on(ETRADE_SANDBOX) and one api_host for market data, orders and balances (`c07f92b`)
- **high** CF-04 — Alpaca live-mode orders go to the Alpaca paper account unless explicitly switched → AlpacaBrokerage reads ALPACA_PAPER (default true, only an explicit off reaches a real account) (`c07f92b`)
- **high** DOC-01 — Every doc names only tools, files, links and settings that exist → Docs rewritten against the running server; generator reads the live registry; smithery.yaml rewritten (`592428a`)
- **high** DOC-02 — The documented Docker path ships a clean image and keeps the paper account → .dockerignore excludes local state; configs and README mount readytrader-forex-data:/app/data; real sidecar command; sentinel compose to _deprecated (`874799c`)
- **high** FE-02 — Dashboard shows the operator's real paper account, not made-up figures → dashboard renders the shared paper account from /api/portfolio; no fabricated figures (`a065ac4`)
- **high** IN-02 — get_economic_calendar reports the week's high-impact events, or says it could not → calendar reads cached 15 min (CALENDAR_CACHE_TTL_SEC); a refused refresh uses a read up to 6 h old, dated in the answer (`6ccc5ff`)
- **high** PRE-02 — Documented start command python app/main.py resolves the app package → app/main.py inserts the repo root on sys.path when run as a file (`a12f405`)
- **high** PRE-05 — CI runs the project's tests → ci.yml: python job (pip install -r requirements-dev.txt; ruff; pytest; bandit) and frontend job (npm ci, lint, build) (`9551325`)
- **medium** BE-03 — Malformed trade requests are refused (unknown side, non-positive amount) → side buy/sell, positive finite amount, market/limit with a positive limit price (`9976ddc`)
- **medium** BE-07 — start_brokerage_private_ws tells the truth → start_brokerage_private_ws returns not_implemented in live mode (`9976ddc`)
- **medium** BE-09 — API server starts as documented (python app/api_server.py) → api_server.py puts the repo root on sys.path when run as a file (`9976ddc`)
- **medium** BE-12 — The approval API answers only the dashboard's browser origin → CORS from API_CORS_ORIGINS (default the dashboard on :3000, '*' ignored); cancel checks the confirm_token (`9976ddc`)
- **medium** BE-14 — A backtest that fails reports failure (ok:false), not success → run_backtest_simulation returns ok:false backtest_error on failure (`33bf5e1`)
- **medium** BE-29 — validate_trade_risk refuses a malformed request instead of calling it safe → validate_trade_risk validates side, symbol, amount_usd and portfolio_value (invalid_request) (`eed8f6f`)
- **medium** CF-01 — env.example lists the variables the code reads, with safe values → Rewrote env.example: every variable a FOREX path reads, grouped, with safe defaults; API_HOST commented at 127.0.0.1; unread names removed (`240727d`)
- **medium** CL-01 — The setup wizard checks this project's setup and never crashes → ask() treats EOF as no answer; FX sources probed with a User-Agent; keys judged by PAPER_MODE; FX dependencies; documented start command (`7cf76f1`)
- **medium** CL-02 — The shipped example scripts run and demonstrate this server's paper account → paper_quick_demo.py rewritten on FxPaperAccount with self-checks; verify_live_strategy.py checks OANDA wiring and runs SMA on EURUSD; moving_average registers pandas_ta (`6886e25`)
- **medium** FE-05 — The dashboard is readable at phone width (390x844) → Media query below 900 px: static top sidebar, single-column grid, tighter padding (`c24e42b`)
- **medium** FE-07 — The operator can see what a proposal is before approving it, and can reject it → Card wording: a paper proposal reads 'paper account', a live one 'LIVE via <venue>'; actions wrap under the details (`61a7cdd`)
- **medium** IN-01 — A news or sentiment source that cannot answer is reported as an error, not as news → feeds fetched with requests (10 s timeout) then parsed; refused feeds are failed sources (`6ccc5ff`)
- **medium** IN-03 — fetch_custom_feed only fetches public http(s) feeds → fetch_custom_feed fetches only public http(s) URLs, re-checking redirects (`80e028d`)
- **medium** IN-04 — OANDA (practice API, bogus token): failures reach the operator with OANDA's reason → _oanda_reason() surfaces errorMessage; orderCancelTransaction without a fill raises; <1 unit refused; parse_pair for instruments (`3250d6f`)
- **medium** ME-02 — Shared insights are recalled under any spelling of the pair and expire everywhere → insight_key() normalises the pair on write and read (SQL-side for older rows); policy compares by the same key (`28346fc`)
- **medium** PRE-06 — README states the Python version the project needs → README prerequisites and local install state Python 3.12+ with venv steps (`9551325`)
- **low** BE-04 — deposit_paper_funds accepts only a positive amount → deposits must be positive USD (`9976ddc`)
- **low** BE-08 — get_stock_price returns the price as a number → get_stock_price returns price, bid, ask, source (`80e028d`)
- **low** BE-23 — Approval API error paths: bad bodies 422, unknown ids 404, no internals → approve_trade maps the store's refusal to 404 (unknown id), 403 (wrong token) or 409 (no longer approvable) (`37e3973`)
- **low** BE-24 — get_multiple_prices returns numbers, and says which symbols it could not price → prices map to a number or null plus an errors map; empty input is invalid_request (`eccb72a`)
- **low** BE-25 — place_stock_order sends a pair to the FX venue unless told otherwise → place_stock_order's exchange defaults to oanda (`ce78cbb`)
- **low** BE-30 — validate_trade_risk does not promise a confirmation the order path never asks for → The over-$5,000 verdict says it is advisory and points at approve_each (`eed8f6f`)
- **low** BE-31 — The API's WebSocket answers only the dashboard's origins → /ws closes (1008) a browser connection whose Origin is not in API_CORS_ORIGINS (`eed8f6f`)
- **low** CF-05 — A malformed optional setting does not stop the server; a malformed LEVERAGE is named → Unapplied numeric settings parse leniently (_unapplied_number); FxPaperAccount names LEVERAGE for any value that is not a positive number (`5d4d9a9`)
- **low** CF-06 — No secrets in the published history; local secrets and environments are ignored → Added .venv/ to .gitignore (`fc3e08f`)
- **low** CF-07 — ALLOW_BROKERAGE_SYMBOLS accepts a pair in any spelling → Policy normalises allowlist entries and orders the same way; env.example explains ALLOW_BROKERAGE_MARKET_TYPES (`eed8f6f`)
- **low** DOC-04 — The README's paper laboratory and feature guide work when followed literally → README order examples use 4,000 EUR (about 4.5% of the documented account) (`2344713`)
- **low** FE-03 — Navigation links lead to pages → nav links without pages removed (`a065ac4`)
- **low** FE-06 — P&L figures never show a negative zero → usd() rounds sub-cent values to 0 before formatting (`37901e9`)
- **low** ME-01 — Insight fields are validated (signal bullish/bearish/neutral, confidence 0..1) → post_market_insight validates signal, confidence and ttl (`33bf5e1`)

Commit ids above are from the local UAT history recorded in the ledger; the pushed branch carries
the same changes in fewer commits (the GitHub connector used here writes whole trees).

### An independent review, and what it changed
After the run, a separate agent given only the repo, this branch and `uat/UAT-LOG.md` re-opened every
retest capture, walked the surface for gaps and read the diff for fixes that broke something. It
found real defects the run had missed, all now fixed and retested: exits sized as new exposure and
shorts trapped by BUY-only limits (BE-26), live SELLs unsized without equity (BE-27), paper
proposals executable by a live API (BE-28), `validate_trade_risk` accepting malformed input
(BE-29), a misleading large-trade verdict (BE-30), the allowlist spelling (CF-07), the WebSocket
origin (BE-31) and blind approvals on the dashboard (FE-07). Weak retest evidence it flagged was
re-captured.

### Still blocked (needs the owner)
- **IN-05** a real order round trip needs an OANDA **practice** (demo) token: `OANDA_API_KEY`, `OANDA_ACCOUNT_ID`, with `PAPER_MODE=false`, `LIVE_TRADING_ENABLED=true`, `OANDA_ENVIRONMENT=practice` (the default). No real money is involved. The failure path against the same API is verified (IN-04).
- **DOC-03** `docker build` / `docker run`: needs a machine with a Docker daemon. The build context (0.7 MB, no local state) and the configs were checked without one (DOC-02).
- **CI workflow**: `.github/workflows/ci.yml` (ruff, pytest, bandit on Python 3.12; dashboard npm ci/lint/build) is on the local branch but the connector used to push cannot write workflow files. Please add it (Actions → new workflow, or commit it):

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

permissions:
  contents: read

jobs:
  python:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5
      - uses: actions/setup-python@v6
        with:
          python-version: "3.12"
          cache: pip
      - name: Install (as the README does)
        run: python -m pip install -r requirements-dev.txt
      - name: Lint
        run: ruff check .
      - name: Tests (includes a real stdio MCP session through python app/main.py)
        run: pytest
      - name: Security scan
        run: bandit -q -c bandit.yaml -r app core common execution intelligence marketdata observability strategy

  frontend:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: frontend
    steps:
      - uses: actions/checkout@v5
      - uses: actions/setup-node@v5
        with:
          node-version: "20"
          cache: npm
          cache-dependency-path: frontend/package-lock.json
      - run: npm ci
      - run: npm run lint
      - run: npm run build
```
- **Repo setting**: SECURITY.md now points reporters at GitHub private vulnerability reporting; switch it on under Settings → Code security if it is off.

### Review these with extra care
- **Risk semantics** (`app/tools/execution.py`, `core/risk.py`; BE-05, BE-26, BE-27): orders are sized by the USD notional of the exposure they **add**, read from the paper account or the brokerage's positions; reducing or closing a position is never sized as new exposure and passes the daily-loss and drawdown limits; any order that adds exposure (a SELL opening a short included) fails closed without equity or a rate. The volatility halt still blocks every side, exits included (as in #4).
- **Paper account** (`core/fx_account.py`, BE-01..05): one netted position per pair, margin at `LEVERAGE` (30), P&L converted to USD; persistent in `data/paper.db` and shared with the API. `deposit_paper_funds` takes USD only.
- **Trading gates** (`app/tools/execution.py`, `app/api_server.py`, `core/policy.py`, `common/switches.py`): `live_order_refusal` at proposal and execution; switches fail closed; proposals carry their mode (`mode_mismatch`); approvals answer 404/403/409.
- **Retired live venue** (BE-22): `execution/forex_paper.py` moved to `_deprecated/`; `exchange="forex_paper"` is now `brokerage_not_supported`. `place_stock_order` defaults to `oanda` (BE-25).
- **Brokerage defaults** (CF-03, CF-04): Alpaca live orders go to the Alpaca **paper** account unless `ALPACA_PAPER=false`; Tradier/E*TRADE sandbox switches parse 1/yes/on.
- **Tool response contract**: failures that used to be `ok: true` are now `ok: false` with codes (`source_unavailable`, `not_configured`, `backtest_error`, `limit_not_marketable`, `insufficient_margin`, ...). Agents that relied on the old shape will see errors.
- **Dependency pin** (PRE-01): `mcp>=1.24.0,<2` because fastmcp 2.14.1 imports a module mcp 2.x removed.

### Known limits (documented, not changed)
- The news blackout rule in `core/risk.py` gets no input; every verdict lists it under `inactive_rules`. The economic calendar now works, so it could drive one (follow-up).
- Live-mode `/api/portfolio` answers 200 with an `error` field (the live account view is not implemented).
- The Live Markets dot means "WebSocket connected"; no tool starts a market-data stream in this release.

### Evidence
Full log: [`uat/UAT-LOG.md`](uat/UAT-LOG.md) · ledger `uat/runs/2026-09-24-01/findings.json` · captures under `uat/evidence/2026-09-24-01/` (the dashboard screenshots and DOM dumps, and `findings.json` (149 KB), stay with the local run because the connector used to push takes text files under ~100 KB; each screenshot's `.json`/`.txt` capture carries its assertions, and `UAT-LOG.md` is rendered from the full ledger).

### DOX pass
- Root `AGENTS.md` created (the repo had none): purpose, ownership, the fail-closed, exposure, mode and response contracts, data paths, the docs-must-match rule, verification commands; indexes `uat/AGENTS.md`.
- `uat/AGENTS.md`: created by the UAT tooling; owns the log, ledger and evidence.
- `_deprecated/README.md`: why the in-memory FX simulator and the crypto signer compose file left the shipped tree.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

https://claude.ai/code/session_01JoGpymL6LG3N8Mx7Btuxp5
