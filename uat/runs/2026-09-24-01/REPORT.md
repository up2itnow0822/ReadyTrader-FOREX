# UAT run 2026-09-24-01 — ReadyTrader-FOREX: CLEAN with BLOCKED items

90 checks · 11 pass · 78 fail (78 fixed & verified, 0 open, 0 fixed-unverified, 0 regressed) · 1 blocked

Scope: Stacked on PR #4 (feat/market-falling-knife). In: MCP server (stdio) tools, paper trading, risk guardian + FX Falling Knife/halt, api_server approvals, dashboard, CLI scripts, config, docs, registry manifest, Docker configs (static). Out: live brokerage orders (no credentials; live trading is a hard gate), Docker build (no daemon in sandbox)

## What was broken and is now fixed

- **critical** PRE-01 — README local install (pip install -r requirements-dev.txt) then python app/main.py → requirements.txt pins mcp>=1.24.0,<2 (`a12f405`) · **VERIFIED**
- **critical** PRE-03 — MCP server registers its tools (python -m app.main, mcp 1.x) → execution tools registered with mcp.tool(fn) (`a12f405`) · **VERIFIED**
- **high** AR-01 — The operator token cannot be steered past (Host header, root path) → require_operator is a dependency of the operator_api router that holds every protected route; the middleware no longer checks paths. (`fc571242`) · **VERIFIED**
- **high** BE-01 — Paper market order executes (README: place_market_order('EUR/USD','buy',1000)) → orders fill in core/fx_account.FxPaperAccount at the latest rate (execute_order) (`9976ddc`) · **VERIFIED**
- **high** BE-02 — A paper limit order fills only when the market reaches it → paper_fill_price: limits fill only when marketable, at the market (`9976ddc`) · **VERIFIED**
- **high** BE-05 — The 5%-of-account size rule values an FX order at its USD notional against the real account → size rule values base-currency notional in USD (core/fx_account.notional_usd) against the account's equity (paper) or the brokerage's (live); a BUY it cannot size fails closed (`9976ddc`) · **VERIFIED**
- **high** BE-06 — Live orders pass LIVE_TRADING_ENABLED and TRADING_HALTED, then reach the brokerage → live_order_refusal (LIVE_TRADING_ENABLED, TRADING_HALTED, policy with order_type) at proposal and execution; PolicyError codes returned; MAX_BROKERAGE_ORDER_AMOUNT fails closed (`9976ddc`) · **VERIFIED**
- **high** BE-10 — approve_each: a proposal made by the MCP server can be approved through the API → EXECUTION_SESSION_ID shares the proposal namespace across processes; approvals execute through execute_order (`9976ddc`) · **VERIFIED**
- **high** BE-11 — The API's portfolio (dashboard) is the paper account the agent trades → the API reads and executes on the shared FxPaperAccount (global_container.paper_engine) (`9976ddc`) · **VERIFIED**
- **high** BE-13 — run_synthetic_stress_test, documented in the README and the stress demo, is an MCP tool → run_synthetic_stress_test registered as an MCP tool (`33bf5e1`) · **VERIFIED**
- **high** BE-22 — A live-mode order never reports a simulated fill as a live trade → Retired execution/forex_paper.py to _deprecated/ and removed it from the brokerage map; a live order to an unregistered venue is refused with brokerage_not_supported before any check runs (`cfc094e`) · **VERIFIED**
- **high** BE-26 — The risk rules judge the exposure an order adds, not its side (FX positions go both ways) → pre_trade_check reads the position (paper account / brokerage list_positions) and sizes only the exposure an order adds; drawdown, daily-loss, sentiment and Falling Knife rules refuse only orders that add exposure (`eed8f6f`) · **VERIFIED**
- **high** BE-27 — Every live order that adds exposure is sized, whichever its side → An order that adds exposure fails closed without equity or a rate, whatever its side; unknown live positions count as new exposure; an unconfigured brokerage is refused first (`eed8f6f`) · **VERIFIED**
- **high** BE-28 — A proposal executes in the mode it was proposed in → Proposals record paper_mode; /api/approve-trade refuses a proposal made in the other mode (409 mode_mismatch) (`eed8f6f`) · **VERIFIED**
- **high** CF-02 — Safety settings fail closed: approval mode and paper mode → PAPER_MODE, TRADING_HALTED and EXECUTION_APPROVAL_MODE parsed with common/switches (fail closed) (`9976ddc`) · **VERIFIED**
- **high** CF-03 — Brokerage sandbox switches keep Tradier and E*TRADE out of production → Tradier uses safety_switch_on(TRADIER_SANDBOX, default true); E*TRADE uses opt_in_switch_on(ETRADE_SANDBOX) and one api_host for market data, orders and balances (`c07f92b`) · **VERIFIED**
- **high** CF-04 — Alpaca live-mode orders go to the Alpaca paper account unless explicitly switched → AlpacaBrokerage reads ALPACA_PAPER (default true, only an explicit off reaches a real account) (`c07f92b`) · **VERIFIED**
- **high** DOC-01 — Every doc names only tools, files, links and settings that exist → Docs rewritten against the running server; generator reads the live registry; smithery.yaml rewritten (`592428a`) · **VERIFIED**
- **high** DOC-02 — The documented Docker path ships a clean image and keeps the paper account → .dockerignore excludes local state; configs and README mount readytrader-forex-data:/app/data; real sidecar command; sentinel compose to _deprecated (`874799c`) · **VERIFIED**
- **high** FE-02 — Dashboard shows the operator's real paper account, not made-up figures → dashboard renders the shared paper account from /api/portfolio; no fabricated figures (`a065ac4`) · **VERIFIED**
- **high** IN-02 — get_economic_calendar reports the week's high-impact events, or says it could not → calendar reads cached 15 min (CALENDAR_CACHE_TTL_SEC); a refused refresh uses a read up to 6 h old, dated in the answer (`6ccc5ff`) · **VERIFIED**
- **high** PRE-02 — Documented start command python app/main.py resolves the app package → app/main.py inserts the repo root on sys.path when run as a file (`a12f405`) · **VERIFIED**
- **high** PRE-05 — CI runs the project's tests → ci.yml: python job (pip install -r requirements-dev.txt; ruff; pytest; bandit) and frontend job (npm ci, lint, build) (`9551325`) · **VERIFIED**
- **high** XR-01 — Every spelling of a pair gets the same market checks → canonical_symbol() maps every pair spelling to EURUSD before validate_trade_risk, pre_trade_check and place_stock_order run any check. (`4f72e15d`) · **VERIFIED**
- **high** XR-02 — Resting limit orders cannot build exposure the Guardian never sees → Every OANDA order is fill-or-kill: a limit is a MARKET order with priceBound=limit, timeInForce FOK; positionFill REDUCE_FIRST nets as the Guardian sizes (an account that cannot net rejects the order). Nothing rests at the broker. (`4f72e15d`) · **VERIFIED**
- **high** XR-03 — Orders at every brokerage are valued at the market, not the caller's price → The reference price is the market price (a limit at max(limit, market)); a market order's price is dropped; without a market price an order that adds exposure is refused. The approval API re-runs the check with the order type. (`4f72e15d`) · **VERIFIED**
- **high** XR-04 — A paper deposit does not end a drawdown halt → get_risk_metrics chains results into a time-weighted index (per period: equity change less deposits, over the prior equity): a deposit is neither a gain nor a loss and cannot end a halt. (`4f72e15d`) · **VERIFIED**
- **high** XR-05 — Docs say which loss limits apply to live orders → Live verdicts (and executed orders) list daily_loss_limit and max_drawdown under inactive_rules; README, THREAT_MODEL, RUNBOOK and ERRORS say the limits run on the paper account only and how to watch a live account. (`4f72e15d`) · **VERIFIED**
- **high** XR-06 — A live approve_each order needs an approval the agent cannot give itself → API_OPERATOR_TOKEN: when set, every /api/ route but /api/health needs Authorization: Bearer; a live proposal is approved only when it is set (403 operator_token_required, checked before the proposal is consumed). The dashboard sends it (asked once per tab). (`4f72e15d`) · **VERIFIED**
- **medium** AR-02 — The dashboard can read a 401 and ask for the operator token → CORS is added after request_context and wraps every answer. (`fc571242`) · **VERIFIED**
- **medium** AR-03 — A NaN quote is no price → Quotes must be finite and positive, else they are no price (the fail-closed paths then refuse). (`fc571242`) · **VERIFIED**
- **medium** BE-03 — Malformed trade requests are refused (unknown side, non-positive amount) → side buy/sell, positive finite amount, market/limit with a positive limit price (`9976ddc`) · **VERIFIED**
- **medium** BE-07 — start_brokerage_private_ws tells the truth → start_brokerage_private_ws returns not_implemented in live mode (`9976ddc`) · **VERIFIED**
- **medium** BE-09 — API server starts as documented (python app/api_server.py) → api_server.py puts the repo root on sys.path when run as a file (`9976ddc`) · **VERIFIED**
- **medium** BE-12 — The approval API answers only the dashboard's browser origin → CORS from API_CORS_ORIGINS (default the dashboard on :3000, '*' ignored); cancel checks the confirm_token (`9976ddc`) · **VERIFIED**
- **medium** BE-14 — A backtest that fails reports failure (ok:false), not success → run_backtest_simulation returns ok:false backtest_error on failure (`33bf5e1`) · **VERIFIED**
- **medium** BE-29 — validate_trade_risk refuses a malformed request instead of calling it safe → validate_trade_risk validates side, symbol, amount_usd and portfolio_value (invalid_request) (`eed8f6f`) · **VERIFIED**
- **medium** BE-32 — A quote without a price (Yahoo's unfinished session row) is never answered as a price → provider rows without a finite positive OHLC are dropped; quote tools answer only finite positive prices (`79192fb8`) · **VERIFIED**
- **medium** CF-01 — env.example lists the variables the code reads, with safe values → Rewrote env.example: every variable a FOREX path reads, grouped, with safe defaults; API_HOST commented at 127.0.0.1; unread names removed (`240727d`) · **VERIFIED**
- **medium** CL-01 — The setup wizard checks this project's setup and never crashes → ask() treats EOF as no answer; FX sources probed with a User-Agent; keys judged by PAPER_MODE; FX dependencies; documented start command (`7cf76f1`) · **VERIFIED**
- **medium** CL-02 — The shipped example scripts run and demonstrate this server's paper account → paper_quick_demo.py rewritten on FxPaperAccount with self-checks; verify_live_strategy.py checks OANDA wiring and runs SMA on EURUSD; moving_average registers pandas_ta (`6886e25`) · **VERIFIED**
- **medium** FE-05 — The dashboard is readable at phone width (390x844) → Media query below 900 px: static top sidebar, single-column grid, tighter padding (`c24e42b`) · **VERIFIED**
- **medium** FE-07 — The operator can see what a proposal is before approving it, and can reject it → Card wording: a paper proposal reads 'paper account', a live one 'LIVE via <venue>'; actions wrap under the details (`61a7cdd`) · **VERIFIED**
- **medium** IN-01 — A news or sentiment source that cannot answer is reported as an error, not as news → feeds fetched with requests (10 s timeout) then parsed; refused feeds are failed sources (`6ccc5ff`) · **VERIFIED**
- **medium** IN-03 — fetch_custom_feed only fetches public http(s) feeds → fetch_custom_feed fetches only public http(s) URLs, re-checking redirects (`80e028d`) · **VERIFIED**
- **medium** IN-04 — OANDA (practice API, bogus token): failures reach the operator with OANDA's reason → _oanda_reason() surfaces errorMessage; orderCancelTransaction without a fill raises; <1 unit refused; parse_pair for instruments (`3250d6f`) · **VERIFIED**
- **medium** ME-02 — Shared insights are recalled under any spelling of the pair and expire everywhere → insight_key() normalises the pair on write and read (SQL-side for older rows); policy compares by the same key (`28346fc`) · **VERIFIED**
- **medium** PRE-06 — README states the Python version the project needs → README prerequisites and local install state Python 3.12+ with venv steps (`9551325`) · **VERIFIED**
- **medium** XR-07 — Paper loss limits measure losses against the capital now in the account and today's start → Daily P&L is the index change since the previous UTC day's last snapshot, else the day's first; mark_day_open records one snapshot at the first check of a day. (`4f72e15d`) · **VERIFIED**
- **medium** XR-08 — An unpriceable position does not hide a loss → Equity is None when a position cannot be priced (account() raises or reports unpriced positions); snapshots skip that state; the order checks refuse new exposure; /api/portfolio and the dashboard show the unpriced positions. (`4f72e15d`) · **VERIFIED**
- **medium** XR-09 — A market order's price is validated or ignored → A market order's price is dropped (0.0) before sizing, proposals and the brokerage; the pending list and approval responses are JSON-safe. (`4f72e15d`) · **VERIFIED**
- **medium** XR-10 — The kill switch and its way out are documented as they work → Docs: the kill switch refuses closing orders too; flatten on the OANDA platform. With fill-or-kill orders (XR-02) nothing the server sent rests at the broker behind the switch. (`4f72e15d`) · **VERIFIED**
- **medium** XR-11 — The Docker build context keeps secrets and local state out → **/ patterns for secrets, keys, databases, caches and logs; frontend/ left out; USER readytrader (uid 10001) owning only /app/data. (`4f72e15d bcf733b8`) · **VERIFIED**
- **low** AR-04 — A deposit cannot end a drawdown halt while a position is unpriced → deposit() refuses while the account cannot be valued (an unpriced position or no USD rate). (`fc571242`) · **VERIFIED**
- **low** AR-05 — The docs say how the daily-loss baseline is taken → RUNBOOK and THREAT_MODEL describe the baseline (previous UTC day's last recorded value, else today's first) and that it errs toward halting. (`fc571242`) · **VERIFIED**
- **low** AR-06 — Orders the switches refuse are audited → trade_start is recorded right after input validation, before any refusal. (`fc571242`) · **VERIFIED**
- **low** AR-07 — An approval while halted answers trading_halted → In live mode the switches and the live policy are checked first; pre_trade_check runs only if they pass (execute_order checks them again). (`fc571242`) · **VERIFIED**
- **low** AR-08 — An existing Docker data volume keeps working after the upgrade → RUNBOOK 'Upgrading a Docker data volume' and a CHANGELOG breaking note give the one-time chown to uid 10001. (`fc571242`) · **VERIFIED**
- **low** AR-09 — The RUNBOOK quotes refusal text as the code writes it → RUNBOOK quotes the message the code writes, and the empty-account variant. (`fc571242`) · **VERIFIED**
- **low** AR-10 — Every numeric tool parameter refuses true → app/tools/params.py defines Number and Integer; every numeric tool parameter uses one. (`fc571242`) · **VERIFIED**
- **low** BE-04 — deposit_paper_funds accepts only a positive amount → deposits must be positive USD (`9976ddc`) · **VERIFIED**
- **low** BE-08 — get_stock_price returns the price as a number → get_stock_price returns price, bid, ask, source (`80e028d`) · **VERIFIED**
- **low** BE-23 — Approval API error paths: bad bodies 422, unknown ids 404, no internals → approve_trade maps the store's refusal to 404 (unknown id), 403 (wrong token) or 409 (no longer approvable) (`37e3973`) · **VERIFIED**
- **low** BE-24 — get_multiple_prices returns numbers, and says which symbols it could not price → prices map to a number or null plus an errors map; empty input is invalid_request (`eccb72a`) · **VERIFIED**
- **low** BE-25 — place_stock_order sends a pair to the FX venue unless told otherwise → place_stock_order's exchange defaults to oanda (`ce78cbb`) · **VERIFIED**
- **low** BE-30 — validate_trade_risk does not promise a confirmation the order path never asks for → The over-$5,000 verdict says it is advisory and points at approve_each (`eed8f6f`) · **VERIFIED**
- **low** BE-31 — The API's WebSocket answers only the dashboard's origins → /ws closes (1008) a browser connection whose Origin is not in API_CORS_ORIGINS (`eed8f6f`) · **VERIFIED**
- **low** CF-05 — A malformed optional setting does not stop the server; a malformed LEVERAGE is named → Unapplied numeric settings parse leniently (_unapplied_number); FxPaperAccount names LEVERAGE for any value that is not a positive number (`5d4d9a9`) · **VERIFIED**
- **low** CF-06 — No secrets in the published history; local secrets and environments are ignored → Added .venv/ to .gitignore (`fc3e08f`) · **VERIFIED**
- **low** CF-07 — ALLOW_BROKERAGE_SYMBOLS accepts a pair in any spelling → Policy normalises allowlist entries and orders the same way; env.example explains ALLOW_BROKERAGE_MARKET_TYPES (`eed8f6f`) · **VERIFIED**
- **low** DOC-04 — The README's paper laboratory and feature guide work when followed literally → README order examples use 4,000 EUR (about 4.5% of the documented account) (`2344713`) · **VERIFIED**
- **low** FE-03 — Navigation links lead to pages → nav links without pages removed (`a065ac4`) · **VERIFIED**
- **low** FE-06 — P&L figures never show a negative zero → usd() rounds sub-cent values to 0 before formatting (`37901e9`) · **VERIFIED**
- **low** ME-01 — Insight fields are validated (signal bullish/bearish/neutral, confidence 0..1) → post_market_insight validates signal, confidence and ttl (`33bf5e1`) · **VERIFIED**
- **low** REG-03 — The operator switches answer first; a refusal for an unreadable live account says why → place_stock_order checks live_execution_refusal() first in live mode; _live_equity returns (equity, why) and the equity refusal carries why. (`f875f5ab`) · **VERIFIED**
- **low** XR-12 — API responses and logs identify each request → request_context middleware: per-request X-Request-ID (in the log lines), security headers, JSON 500 naming only the request id; log_event stamps ts_ms per line. (`4f72e15d`) · **VERIFIED**
- **low** XR-13 — Odd numeric inputs are refused → Deposits capped at 1e12 USD (cash at 1e15); tool numbers typed Number (booleans refused before conversion); non-finite sentiment_score refused. (`4f72e15d bcf733b8`) · **VERIFIED**
- **low** XR-14 — The Smithery listing offers only settings that work there → EXECUTION_APPROVAL_MODE is no longer offered; commandFunction passes only the listed settings and sets 'auto'. (`4f72e15d`) · **VERIFIED**

## Still blocked (needs the user)

- IN-05 — A real order round trip on an OANDA practice account: blocked on An OANDA practice (demo) account token: OANDA_API_KEY + OANDA_ACCOUNT_ID for a practice account, with PAPER_MODE=false, LIVE_TRADING_ENABLED=true, OANDA_ENVIRONMENT=practice.

## Coverage

| Section | Checks | Status |
|---|---|---|
| preflight | 6 | covered |
| backend | 37 | covered |
| data | 5 | covered |
| memory | 2 | covered |
| frontend | 8 | covered |
| integrations | 5 | covered |
| cli | 2 | covered |
| config | 10 | covered |
| docs | 8 | covered |
| journeys | 6 | recorded |

## Delivery

- Branch `uat/2026-09-24-forex` has a remote (`origin`) but no upstream — it has not been pushed.
- Base: `main@417a104`
- DOX: root AGENTS.md indexes `uat/AGENTS.md`
- Log: `uat/UAT-LOG.md` · evidence: `uat/evidence/2026-09-24-01/` (1.22 MB)
