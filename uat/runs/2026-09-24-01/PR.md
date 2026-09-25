## UAT run `2026-09-24-01` — ready for release review (1 item blocked on a practice-account token)

Acting as the user, exercised every surface of ReadyTrader-FOREX end to end (MCP server over stdio,
approval API, dashboard, CLI scripts, config, docs, the Docker image, the registry manifest), fixed
every failure on this branch, and retested each fix with fresh evidence. Money paths ran in paper
mode, against fake brokerages, or against OANDA's **practice** API with a bogus token (the failure
path only); no order was placed on any account.

**Stacked on #4** (`feat/market-falling-knife`, the price-based Falling Knife and volatility halt).
Review and merge #4 first; this PR's diff is the UAT work on top of it.

**Totals:** 89 checks · 11 pass · 77 fail (77 fixed & verified) · 1 blocked · 461 tests pass, ruff and bandit clean, dashboard installs, lints and builds; the README's Docker path builds and runs.

| Section | Pass | Fail | Verified fixed | Blocked |
|---|---|---|---|---|
| preflight | 1 | 5 | 5 | 0 |
| backend | 0 | 36 | 36 | 0 |
| data | 1 | 4 | 4 | 0 |
| memory | 0 | 2 | 2 | 0 |
| frontend | 2 | 6 | 6 | 0 |
| integrations | 0 | 4 | 4 | 1 |
| cli | 0 | 2 | 2 | 0 |
| config | 0 | 10 | 10 | 0 |
| docs | 1 | 7 | 7 | 0 |
| regression | 6 | 1 | 1 | 0 |

### Breaking changes (read before merging)
- **Approving a live proposal needs `API_OPERATOR_TOKEN`** on the API server (XR-06). The agent receives each proposal's `confirm_token`, so it could approve its own live order. With the token set, every `/api/` call but `/api/health` needs `Authorization: Bearer <token>`; the dashboard asks for it once per tab. Paper approvals work without it.
- **Live OANDA limit orders are fill-or-kill** (XR-02): a limit is a MARKET order with `priceBound`, `timeInForce: FOK`, `positionFill: REDUCE_FIRST`. Nothing rests at OANDA (a resting order could fill past the Risk Guardian and the kill switch). A hedging account that cannot net rejects the order.
- **The Docker image runs as `readytrader` (uid 10001)** (XR-11): a volume written by an earlier root image must be handed over once (RUNBOOK, "Upgrading a Docker data volume"; AR-08, verified with Docker).
- **Loss limits measure trading results** (XR-04/07): deposits no longer end a drawdown halt; the daily baseline is the previous UTC day's last recorded value; limits run on the paper account only and live verdicts say so (`inactive_rules`).

### What was broken and is now fixed
- **critical** PRE-01 — README local install (pip install -r requirements-dev.txt) then python app/main.py → requirements.txt pins mcp>=1.24.0,<2 (`a12f405`)
- **critical** PRE-03 — MCP server registers its tools (python -m app.main, mcp 1.x) → execution tools registered with mcp.tool(fn) (`a12f405`)
- **high** AR-01 — The operator token cannot be steered past (Host header, root path) → require_operator is a dependency of the operator_api router that holds every protected route; the middleware no longer checks paths. (`fc571242`)
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
- **high** XR-01 — Every spelling of a pair gets the same market checks → canonical_symbol() maps every pair spelling to EURUSD before validate_trade_risk, pre_trade_check and place_stock_order run any check. (`4f72e15d`)
- **high** XR-02 — Resting limit orders cannot build exposure the Guardian never sees → Every OANDA order is fill-or-kill: a limit is a MARKET order with priceBound=limit, timeInForce FOK; positionFill REDUCE_FIRST nets as the Guardian sizes (an account that cannot net rejects the order). Nothing rests at the broker. (`4f72e15d`)
- **high** XR-03 — Orders at every brokerage are valued at the market, not the caller's price → The reference price is the market price (a limit at max(limit, market)); a market order's price is dropped; without a market price an order that adds exposure is refused. The approval API re-runs the check with the order type. (`4f72e15d`)
- **high** XR-04 — A paper deposit does not end a drawdown halt → get_risk_metrics chains results into a time-weighted index (per period: equity change less deposits, over the prior equity): a deposit is neither a gain nor a loss and cannot end a halt. (`4f72e15d`)
- **high** XR-05 — Docs say which loss limits apply to live orders → Live verdicts (and executed orders) list daily_loss_limit and max_drawdown under inactive_rules; README, THREAT_MODEL, RUNBOOK and ERRORS say the limits run on the paper account only and how to watch a live account. (`4f72e15d`)
- **high** XR-06 — A live approve_each order needs an approval the agent cannot give itself → API_OPERATOR_TOKEN: when set, every /api/ route but /api/health needs Authorization: Bearer; a live proposal is approved only when it is set (403 operator_token_required, checked before the proposal is consumed). The dashboard sends it (asked once per tab). (`4f72e15d`)
- **medium** AR-02 — The dashboard can read a 401 and ask for the operator token → CORS is added after request_context and wraps every answer. (`fc571242`)
- **medium** AR-03 — A NaN quote is no price → Quotes must be finite and positive, else they are no price (the fail-closed paths then refuse). (`fc571242`)
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
- **medium** XR-07 — Paper loss limits measure losses against the capital now in the account and today's start → Daily P&L is the index change since the previous UTC day's last snapshot, else the day's first; mark_day_open records one snapshot at the first check of a day. (`4f72e15d`)
- **medium** XR-08 — An unpriceable position does not hide a loss → Equity is None when a position cannot be priced (account() raises or reports unpriced positions); snapshots skip that state; the order checks refuse new exposure; /api/portfolio and the dashboard show the unpriced positions. (`4f72e15d`)
- **medium** XR-09 — A market order's price is validated or ignored → A market order's price is dropped (0.0) before sizing, proposals and the brokerage; the pending list and approval responses are JSON-safe. (`4f72e15d`)
- **medium** XR-10 — The kill switch and its way out are documented as they work → Docs: the kill switch refuses closing orders too; flatten on the OANDA platform. With fill-or-kill orders (XR-02) nothing the server sent rests at the broker behind the switch. (`4f72e15d`)
- **medium** XR-11 — The Docker build context keeps secrets and local state out → **/ patterns for secrets, keys, databases, caches and logs; frontend/ left out; USER readytrader (uid 10001) owning only /app/data. (`4f72e15d bcf733b8`)
- **low** AR-04 — A deposit cannot end a drawdown halt while a position is unpriced → deposit() refuses while the account cannot be valued (an unpriced position or no USD rate). (`fc571242`)
- **low** AR-05 — The docs say how the daily-loss baseline is taken → RUNBOOK and THREAT_MODEL describe the baseline (previous UTC day's last recorded value, else today's first) and that it errs toward halting. (`fc571242`)
- **low** AR-06 — Orders the switches refuse are audited → trade_start is recorded right after input validation, before any refusal. (`fc571242`)
- **low** AR-07 — An approval while halted answers trading_halted → In live mode the switches and the live policy are checked first; pre_trade_check runs only if they pass (execute_order checks them again). (`fc571242`)
- **low** AR-08 — An existing Docker data volume keeps working after the upgrade → RUNBOOK 'Upgrading a Docker data volume' and a CHANGELOG breaking note give the one-time chown to uid 10001. (`fc571242`)
- **low** AR-09 — The RUNBOOK quotes refusal text as the code writes it → RUNBOOK quotes the message the code writes, and the empty-account variant. (`fc571242`)
- **low** AR-10 — Every numeric tool parameter refuses true → app/tools/params.py defines Number and Integer; every numeric tool parameter uses one. (`fc571242`)
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
- **low** REG-03 — The operator switches answer first; a refusal for an unreadable live account says why → place_stock_order checks live_execution_refusal() first in live mode; _live_equity returns (equity, why) and the equity refusal carries why. (`f875f5ab`)
- **low** XR-12 — API responses and logs identify each request → request_context middleware: per-request X-Request-ID (in the log lines), security headers, JSON 500 naming only the request id; log_event stamps ts_ms per line. (`4f72e15d`)
- **low** XR-13 — Odd numeric inputs are refused → Deposits capped at 1e12 USD (cash at 1e15); tool numbers typed Number (booleans refused before conversion); non-finite sentiment_score refused. (`4f72e15d bcf733b8`)
- **low** XR-14 — The Smithery listing offers only settings that work there → EXECUTION_APPROVAL_MODE is no longer offered; commandFunction passes only the listed settings and sets 'auto'. (`4f72e15d`)

Commit ids above are from the local UAT history recorded in the ledger; the pushed branch carries
the same changes in fewer commits (the GitHub connector used here writes whole trees).

### Three review rounds, and what they changed
1. **Independent review of the run** (BE-26..BE-31, CF-07, FE-07): exits sized as new exposure, live SELLs unsized without equity, paper proposals executable live, malformed `validate_trade_risk` input, the allowlist spelling, the WebSocket origin and blind dashboard approvals.
2. **Cross-repository review** (XR-01..XR-14): every defect class found in ReadyTrader-Crypto, checked here: pair spellings that skipped the market checks, resting OANDA limits, caller-price sizing, deposits ending halts, the live loss-limit scope, agent self-approval, the daily baseline, unpriced positions hiding losses, NaN prices, the kill switch docs, the Docker build context, request ids, odd numbers, and the Smithery listing. The regression sweep then found the operator switches answering after the brokerage check (REG-03).
3. **Adversarial review of those fixes** (AR-01..AR-10): the operator-token check could be steered past with a `Host: …#` header or a root path (the agent could approve its own live order); 401s carried no CORS headers; a NaN quote passed the size rule; a deposit while a position was unpriced ended a halt; halted orders went unaudited; an approval while halted read the brokerage; existing Docker volumes broke; four tool parameters took `true` as 1. All fixed and retested.

### Still blocked (needs the owner)
- **IN-05** a real order round trip needs an OANDA **practice** (demo) token: `OANDA_API_KEY`, `OANDA_ACCOUNT_ID`, with `PAPER_MODE=false`, `LIVE_TRADING_ENABLED=true`, `OANDA_ENVIRONMENT=practice` (the default). No real money is involved. The failure path against the same API is verified (IN-04).
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
- **Operator token** (`app/api_server.py`, XR-06, AR-01): the check is a dependency of the `operator_api` router (never a path check in a middleware); CORS is outermost; live approvals refuse with `403 operator_token_required` while the token is unset, before the proposal is consumed.
- **Paper loss metrics** (`core/fx_account.py`, XR-04/07/08, AR-04): a time-weighted index over `fx_equity`; `mark_day_open`; equity `None` while a position cannot be priced; deposits refused in that state.
- **OANDA orders** (`execution/oanda_service.py`, XR-02): fill-or-kill only; `REDUCE_FIRST` is untested against a hedging account (a practice token would settle it: IN-05).
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
Full log: [`uat/UAT-LOG.md`](uat/UAT-LOG.md) · ledger `uat/runs/2026-09-24-01/findings.json` · captures under `uat/evidence/2026-09-24-01/` (the dashboard screenshots (PNG) stay with the local run because the connector used to push writes text only; each screenshot's `.json`/`.txt` capture carries its assertions, and `UAT-LOG.md` is rendered from the ledger).

### DOX pass
- Root `AGENTS.md` now also records: symbol normalisation, fill-or-kill OANDA orders, the paper loss-metric contract, the operator-token router, `app/tools/params.py`, switches-first and audit order, the Docker user.
- Root `AGENTS.md` created (the repo had none): purpose, ownership, the fail-closed, exposure, mode and response contracts, data paths, the docs-must-match rule, verification commands; indexes `uat/AGENTS.md`.
- `uat/AGENTS.md`: created by the UAT tooling; owns the log, ledger and evidence.
- `_deprecated/README.md`: why the in-memory FX simulator and the crypto signer compose file left the shipped tree.

### Branch parity
`git push` was not available to the session that ran this UAT, so this branch was written through the GitHub
connector. Every file on it is byte-identical to the tested local branch (checked with `git hash-object`
against the fetched branch), the run ledger `uat/runs/2026-09-24-01/findings.json` included, except the PNG screenshots and `.github/workflows/ci.yml` (above), which the connector cannot write; the owner has those in the run's local archive.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

https://claude.ai/code/session_01JoGpymL6LG3N8Mx7Btuxp5
