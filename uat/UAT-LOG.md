# UAT Log

> Rendered by `uat_log.py render` from `uat/runs/<run-id>/findings.json`. Do not hand-edit;
> update the ledger and re-render. Latest run is expanded; earlier runs are summarized.

## Run 2026-09-24-01 — ReadyTrader-FOREX

- Branch: `uat/2026-09-24-forex`  |  Base: `main@417a104`
- Started: 2026-09-24T10:51:11+00:00  |  Updated: 2026-09-26T02:18:16+00:00
- Scope: Stacked on PR #4 (feat/market-falling-knife). In: MCP server (stdio) tools, paper trading, risk guardian + FX Falling Knife/halt, api_server approvals, dashboard, CLI scripts, config, docs, registry manifest, Docker configs (static). Out: live brokerage orders (no credentials; live trading is a hard gate), Docker build (no daemon in sandbox)
- Verdict: **CLEAN with BLOCKED items**
- Totals: 91 checks · 11 pass · 79 fail (79 verified fixed, 0 open, 0 fixed-unverified, 0 regressed, 0 wontfix) · 1 blocked

### User journeys exercised

- As an agent developer, I install ReadyTrader-FOREX from the README and connect it to my MCP client so that my agent can list and call its tools
- As a trading agent, I research a currency pair (price, candles, regime) so that I can decide on a trade
- As a trading agent in paper mode, I fund the paper account and place a forex order that passes the Risk Guardian so that I can practise with no real money
- As an operator, I rely on validate_trade_risk and every order path to refuse an unsafe trade (oversized, a falling-knife BUY, a volatility halt) so that my agent cannot make an unrecoverable trade
- As an operator using approve_each, I review a pending trade and approve it through the API so that only trades I confirm execute
- As a strategy builder, I run a backtest and a synthetic stress test so that I can evaluate a strategy before trading it

### Section summary

| Section | Pass | Fail | Verified fixed | Blocked |
|---|---|---|---|---|
| preflight | 1 | 5 | 5 | 0 |
| backend | 0 | 37 | 37 | 0 |
| data | 1 | 4 | 4 | 0 |
| memory | 0 | 2 | 2 | 0 |
| frontend | 2 | 6 | 6 | 0 |
| integrations | 0 | 4 | 4 | 1 |
| cli | 0 | 2 | 2 | 0 |
| config | 0 | 10 | 10 | 0 |
| docs | 1 | 8 | 8 | 0 |
| regression | 6 | 1 | 1 | 0 |

### Findings (80)

#### PRE-01 — README local install (pip install -r requirements-dev.txt) then python app/main.py  [FAIL · critical · **VERIFIED**]

- Section: `preflight`
- Steps: fresh python3.12 venv; pip install -r requirements-dev.txt; python app/main.py and python -m app.main
- Expected: the server starts
- Observed: pip resolves mcp 2.2.0, which dropped pydantic-settings; fastmcp 2.14.1 imports it: ModuleNotFoundError on every start, both ways
- Evidence: [PRE-01.txt](evidence/2026-09-24-01/PRE-01.txt)
- Fix: requirements.txt pins mcp>=1.24.0,<2
  - Root cause: unpinned mcp resolved 2.x, which dropped a dependency fastmcp 2.14.1 imports
  - Files: `requirements.txt`
  - Commit: `a12f405`
  - Regression test: tests/test_server_startup.py
- Retest 1 (2026-09-24T10:55:50+00:00): **PASS** — fresh install resolves mcp 1.30.0; both start commands reach 'Starting MCP server ReadyTrader-FOREX' · evidence: [PRE-01-retest.txt](evidence/2026-09-24-01/PRE-01-retest.txt)

#### PRE-03 — MCP server registers its tools (python -m app.main, mcp 1.x)  [FAIL · critical · **VERIFIED**]

- Section: `preflight`
- Steps: python -m app.main; MCP client list_tools
- Expected: the tool list
- Observed: AttributeError: 'function' object has no attribute 'key' in register_execution_tools (mcp.add_tool(fn) needs a Tool object in fastmcp 2.14): the server never starts, so no client can connect
- Evidence: [PRE-02.txt](evidence/2026-09-24-01/PRE-02.txt)
- Fix: execution tools registered with mcp.tool(fn)
  - Root cause: fastmcp 2.14 add_tool takes a Tool object
  - Files: `app/tools/execution.py`
  - Commit: `a12f405`
  - Regression test: tests/test_server_startup.py
- Retest 1 (2026-09-24T10:55:50+00:00): **PASS** — python -m app.main starts and an MCP client lists 27 tools (registration no longer raises) · evidence: [PRE-02-retest.txt](evidence/2026-09-24-01/PRE-02-retest.txt)

#### AR-01 — The operator token cannot be steered past (Host header, root path)  [FAIL · high · **VERIFIED**]

- Section: `backend`
- Expected: With API_OPERATOR_TOKEN set, every /api/ route but /api/health needs the bearer token, whatever the Host header or path prefix.
- Observed: The middleware checked request.url.path, built from the Host header: Host '127.0.0.1:8000#', '?' or '/x' reached /api/portfolio without a token (200), and with root_path /rt a live approval carrying only the agent's confirm_token executed (order sent to the brokerage).
- Evidence: [AR-01.txt](evidence/2026-09-24-01/AR-01.txt)
- Fix: require_operator is a dependency of the operator_api router that holds every protected route; the middleware no longer checks paths.
  - Root cause: A middleware compared request.url.path (Host header + root_path) instead of the path the router matched.
  - Files: `app/api_server.py`
  - Commit: `fc571242`
  - Regression test: tests/test_uat_review_2026_09_24.py::test_the_operator_token_cannot_be_steered_past
- Retest 1 (2026-09-25T11:38:39+00:00): **PASS** — Every Host variant ('#', '?', '/x') answers 401 without the token; behind root_path /rt the agent's confirm_token alone answers 401 and no live order is sent. · evidence: [AR-01-retest.txt](evidence/2026-09-24-01/AR-01-retest.txt)

#### BE-01 — Paper market order executes (README: place_market_order('EUR/USD','buy',1000))  [FAIL · high · **VERIFIED**]

- Section: `backend`
- Steps: paper, deposit 100000 USD; place_market_order EURUSD buy 1000; place_forex_order USDJPY buy 1000
- Expected: fills at the current rate
- Observed: both raise 'Price for EURUSD is unknown and pulse price was not provided' (an MCP tool error, not a JSON error): no paper market order can execute
- Evidence: [BE-01.txt](evidence/2026-09-24-01/BE-01.txt)
- Fix: orders fill in core/fx_account.FxPaperAccount at the latest rate (execute_order)
  - Root cause: the stock-style ledger never looked up a price and raised
  - Files: `core/fx_account.py`, `app/tools/execution.py`
  - Commit: `9976ddc`
  - Regression test: tests/test_order_path.py
- Retest 1 (2026-09-24T11:21:47+00:00): **PASS** — market orders fill: EURUSD 1000 at the quote 1.13779 (position avg_price 1.1377859, margin 37.93) and USDJPY 1000 (margin 71.26 total) · evidence: [BE-01-retest.txt](evidence/2026-09-24-01/BE-01-retest.txt)

#### BE-02 — A paper limit order fills only when the market reaches it  [FAIL · high · **VERIFIED**]

- Section: `backend`
- Steps: paper; place_limit_order EURUSD buy 1000 @ 0.5 with the market at 1.137
- Expected: not filled (the market is far above the limit)
- Observed: 'Paper Trade Executed: BUY 1000 EURUSD @ 0.5': a buy 56% below the market filled at the limit price, conjuring a paper profit
- Evidence: [BE-01.txt](evidence/2026-09-24-01/BE-01.txt)
- Fix: paper_fill_price: limits fill only when marketable, at the market
  - Root cause: limits filled at their own price
  - Files: `app/tools/execution.py`
  - Commit: `9976ddc`
  - Regression test: tests/test_order_path.py
- Retest 1 (2026-09-24T11:21:48+00:00): **PASS** — the buy limit at 0.5 is refused: limit_not_marketable vs market 1.13779 · evidence: [BE-01-retest.txt](evidence/2026-09-24-01/BE-01-retest.txt)

#### BE-05 — The 5%-of-account size rule values an FX order at its USD notional against the real account  [FAIL · high · **VERIFIED**]

- Section: `backend`
- Steps: paper, 100000 USD; place_forex_order USDJPY buy 4000 limit 159 (notional $4,000 = 4%)
- Expected: allowed by the size rule
- Observed: risk_blocked 'Position size too large (636.0%)': the order is valued as units x JPY price as if in USD, against a hardcoded $100,000 account (pre_trade_check never reads the ledger's equity)
- Evidence: [BE-05.txt](evidence/2026-09-24-01/BE-05.txt)
- Fix: size rule values base-currency notional in USD (core/fx_account.notional_usd) against the account's equity (paper) or the brokerage's (live); a BUY it cannot size fails closed
  - Root cause: amount x price treated as USD; portfolio fixed at 100,000
  - Files: `app/tools/execution.py`, `core/fx_account.py`
  - Commit: `9976ddc`
  - Regression test: tests/test_order_path.py
- Retest 1 (2026-09-24T11:22:15+00:00): **PASS** — the 4,000-unit USDJPY BUY passes the size rule and fills (margin 133.33 = $4,000 / 30) · evidence: [BE-05-retest.txt](evidence/2026-09-24-01/BE-05-retest.txt)

#### BE-06 — Live orders pass LIVE_TRADING_ENABLED and TRADING_HALTED, then reach the brokerage  [FAIL · high · **VERIFIED**]

- Section: `backend`
- Steps: PAPER_MODE=false, no keys: sell EURUSD 1000 with LIVE_TRADING_ENABLED=false; again with LIVE_TRADING_ENABLED=true TRADING_HALTED=true
- Expected: live_trading_disabled, then trading_halted
- Observed: neither switch is read anywhere; both calls fail with execution_error 'validate_brokerage_order() missing ... order_type': every live order fails on a broken policy call, and once that is fixed nothing would stop them
- Evidence: [BE-05.txt](evidence/2026-09-24-01/BE-05.txt)
- Fix: live_order_refusal (LIVE_TRADING_ENABLED, TRADING_HALTED, policy with order_type) at proposal and execution; PolicyError codes returned; MAX_BROKERAGE_ORDER_AMOUNT fails closed
  - Root cause: the switches were never read; the policy call lacked order_type
  - Files: `app/tools/execution.py`, `core/policy.py`, `app/api_server.py`
  - Commit: `9976ddc`
  - Regression test: tests/test_order_path.py
- Retest 1 (2026-09-24T11:22:15+00:00): **PASS** — LIVE_TRADING_ENABLED=false -> live_trading_disabled; TRADING_HALTED=true -> trading_halted; no policy crash · evidence: [BE-05-retest.txt](evidence/2026-09-24-01/BE-05-retest.txt)

#### BE-10 — approve_each: a proposal made by the MCP server can be approved through the API  [FAIL · high · **VERIFIED**]

- Section: `backend`
- Steps: API (python -m app.api_server) and MCP server with the same EXECUTION_DB_PATH; propose a paper limit order over MCP; list and approve it through the API
- Expected: the API lists the proposal and executes it on approval
- Observed: /api/pending-approvals is empty and the approval answers 400 'Unknown request_id': each process scopes proposals to a random session id, so the dashboard/API can never approve an agent's order
- Evidence: [BE-09.txt](evidence/2026-09-24-01/BE-09.txt)
- Fix: EXECUTION_SESSION_ID shares the proposal namespace across processes; approvals execute through execute_order
  - Root cause: random session id per process
  - Files: `execution/store.py`, `app/api_server.py`
  - Commit: `9976ddc`
  - Regression test: tests/test_order_path.py
- Retest 1 (2026-09-24T11:22:53+00:00): **PASS** — with a shared EXECUTION_SESSION_ID the API lists the MCP proposal and the approval executes it (BUY 1000 EURUSD @ 1.13779) · evidence: [BE-09-retest.txt](evidence/2026-09-24-01/BE-09-retest.txt)

#### BE-11 — The API's portfolio (dashboard) is the paper account the agent trades  [FAIL · high · **VERIFIED**]

- Section: `backend`
- Steps: deposit 25,000 USD over MCP; GET /api/portfolio
- Expected: the same account: 25,000 USD
- Observed: a different, in-memory ForexPaperBrokerage with a fixed 100,000 balance; API approvals would also execute there, so orders approved in the dashboard never reach the agent's ledger and vanish on restart
- Evidence: [BE-09.txt](evidence/2026-09-24-01/BE-09.txt)
- Fix: the API reads and executes on the shared FxPaperAccount (global_container.paper_engine)
  - Root cause: API used an in-memory ForexPaperBrokerage
  - Files: `app/api_server.py`, `app/core/container.py`
  - Commit: `9976ddc`
  - Regression test: tests/test_order_path.py
- Retest 1 (2026-09-24T11:22:53+00:00): **PASS** — /api/portfolio shows the agent's account: USD 25,000 plus the approved EURUSD 1000 position, equity 25,000 · evidence: [BE-09-retest.txt](evidence/2026-09-24-01/BE-09-retest.txt)

#### BE-13 — run_synthetic_stress_test, documented in the README and the stress demo, is an MCP tool  [FAIL · high · **VERIFIED**]

- Section: `backend`
- Steps: list the server's tools; grep the README and examples/stress_test_demo.py
- Expected: run_synthetic_stress_test is registered
- Observed: 27 tools, no run_synthetic_stress_test; the README documents it with an example config and the stress demo ends by telling the user to 'run run_synthetic_stress_test via MCP'
- Evidence: [BE-13.txt](evidence/2026-09-24-01/BE-13.txt)
- Fix: run_synthetic_stress_test registered as an MCP tool
  - Root cause: never registered
  - Files: `app/tools/research.py`
  - Commit: `33bf5e1`
  - Regression test: tests/test_research_tools.py
- Retest 1 (2026-09-24T11:23:13+00:00): **PASS** — 29 tools incl. run_synthetic_stress_test; it runs 3 scenarios and returns artifacts · evidence: [BE-13-retest.txt](evidence/2026-09-24-01/BE-13-retest.txt)

#### BE-22 — A live-mode order never reports a simulated fill as a live trade  [FAIL · high · **VERIFIED**]

- Section: `backend`
- Steps: PAPER_MODE=false LIVE_TRADING_ENABLED=true, no brokerage keys; place_forex_order and place_stock_order with exchange=forex_paper
- Expected: Refused: forex_paper is not a brokerage; paper trading is PAPER_MODE=true (the persistent FX account)
- Observed: ok:true, mode 'live', status 'filled', venue forex_paper: a second in-memory 100k simulator (execution/forex_paper.py) still registered as a live venue fills the order; nothing reaches a broker and the fill is lost on restart
- Evidence: [BE-22.txt](evidence/2026-09-24-01/BE-22.txt)
- Fix: Retired execution/forex_paper.py to _deprecated/ and removed it from the brokerage map; a live order to an unregistered venue is refused with brokerage_not_supported before any check runs
  - Root cause: A pre-FxPaperAccount simulator stayed registered as a live venue
  - Files: `app/core/container.py`, `app/tools/execution.py`, `_deprecated/forex_paper.py`
  - Commit: `cfc094e`
  - Regression test: tests/test_order_path.py::test_a_live_order_cannot_be_filled_by_a_simulator
- Retest 1 (2026-09-24T11:46:38+00:00): **PASS** — Live mode: exchange=forex_paper -> brokerage_not_supported listing the real venues, for both order tools; nothing is filled · evidence: [BE-22-retest.txt](evidence/2026-09-24-01/BE-22-retest.txt)

#### BE-26 — The risk rules judge the exposure an order adds, not its side (FX positions go both ways)  [FAIL · high · **VERIFIED**]

- Section: `backend`
- Steps: Paper, faked rates: build a 12,000 EUR long in three allowed 4,000 buys and close it in one SELL; build a 40,000 EURUSD short, move EURUSD 25% against it (drawdown 12.4%), then BUY 3,000 to reduce it and SELL 3,000 to add to it
- Expected: Closing or reducing a position is always allowed by the size, daily-loss and drawdown rules; adding to the short after the drawdown limit is refused
- Observed: Closing the long is refused ('Position size too large (13.3%)': the exit is sized as new exposure). With the short at 12.4% drawdown the risk-reducing BUY is refused ('Max Drawdown Limit Hit ... Trading HALTED for Buys') while the risk-adding SELL fills: the BUY-only rules, written for long-only assets, trap a short. Found by the independent review
- Evidence: [BE-26.txt](evidence/2026-09-24-01/BE-26.txt)
- Fix: pre_trade_check reads the position (paper account / brokerage list_positions) and sizes only the exposure an order adds; drawdown, daily-loss, sentiment and Falling Knife rules refuse only orders that add exposure
  - Root cause: Side-based rules written for long-only assets
  - Files: `app/tools/execution.py`, `core/risk.py`
  - Commit: `eed8f6f`
  - Regression test: tests/test_order_path.py (exposure tests)
- Retest 1 (2026-09-24T13:03:14+00:00): **PASS** — The 12,000 EUR long closes in one SELL; at 12.4% drawdown the BUY that reduces the short fills and the SELL that adds to it is refused ('Orders that add exposure are halted; orders that reduce or close a position are allowed') · evidence: [BE-26-retest.txt](evidence/2026-09-24-01/BE-26-retest.txt)

#### BE-27 — Every live order that adds exposure is sized, whichever its side  [FAIL · high · **VERIFIED**]

- Section: `backend`
- Steps: Live mode, fake OANDA: broker balance call failing; place_forex_order EURUSD sell 10,000,000; the same with equity readable; TRYUSD (unpriceable) sell 50,000,000 with equity unreadable
- Expected: An order that opens or adds to a position is refused when the account or the pair cannot be valued (a SELL opens a short in FX)
- Observed: With the balance unreadable the 10,000,000 EURUSD SELL reached the broker (the same order is refused at 11044% when equity is readable), and the unpriceable TRYUSD SELL went through too: the 'a SELL is an exit' shortcut from the stocks server does not hold for FX. Found by the independent review
- Evidence: [BE-27.txt](evidence/2026-09-24-01/BE-27.txt)
- Fix: An order that adds exposure fails closed without equity or a rate, whatever its side; unknown live positions count as new exposure; an unconfigured brokerage is refused first
  - Files: `app/tools/execution.py`
  - Commit: `eed8f6f`
  - Regression test: tests/test_order_path.py::test_a_live_sell_that_opens_a_short_is_sized_even_without_equity
- Retest 1 (2026-09-24T13:03:28+00:00): **PASS** — With the broker's balance unreadable the 10,000,000 EURUSD SELL is refused and nothing reaches the broker; the unpriceable TRYUSD SELL is refused; the EURGBP long-to-short flip (5,000 against 3,000) is sized by its 2,000 new units and fills · evidence: [BE-27-retest.txt](evidence/2026-09-24-01/BE-27-retest.txt)

#### BE-28 — A proposal executes in the mode it was proposed in  [FAIL · high · **VERIFIED**]

- Section: `backend`
- Steps: approve_each: propose EURUSD buy 1000 in paper mode; approve it through an API process running PAPER_MODE=false
- Expected: Refused: a paper proposal never becomes a live order (and the reverse)
- Observed: 200 ok, mode 'live', venue oanda: the paper proposal was sent to the broker. The proposal records no mode, so two processes that disagree on PAPER_MODE turn a paper trade into a real one. Found by the independent review
- Evidence: [BE-27.txt](evidence/2026-09-24-01/BE-27.txt)
- Fix: Proposals record paper_mode; /api/approve-trade refuses a proposal made in the other mode (409 mode_mismatch)
  - Files: `app/tools/execution.py`, `app/api_server.py`
  - Commit: `eed8f6f`
  - Regression test: tests/test_order_path.py::test_a_paper_proposal_never_executes_live
- Retest 1 (2026-09-24T13:03:31+00:00): **PASS** — The paper proposal approved by a live-mode API answers 409 mode_mismatch ('made in paper mode and this API runs in live mode; nothing was executed'); the broker received no order · evidence: [BE-28-retest.txt](evidence/2026-09-24-01/BE-28-retest.txt)

#### CF-02 — Safety settings fail closed: approval mode and paper mode  [FAIL · high · **VERIFIED**]

- Section: `config`
- Steps: EXECUTION_APPROVAL_MODE in {approve_each, 'approve_each  # comment' (docker --env-file), approve-each}; place an order. PAPER_MODE in {true, 1, yes}
- Expected: every approval variant proposes; PAPER_MODE=1/yes stays paper
- Observed: the commented and misspelt approval modes executed the order with no approval; PAPER_MODE=1 or yes reads as live mode
- Evidence: [CF-02.txt](evidence/2026-09-24-01/CF-02.txt)
- Fix: PAPER_MODE, TRADING_HALTED and EXECUTION_APPROVAL_MODE parsed with common/switches (fail closed)
  - Root cause: exact-string comparisons
  - Files: `common/switches.py`, `app/core/config.py`
  - Commit: `9976ddc`
  - Regression test: tests/test_order_path.py
- Retest 1 (2026-09-24T11:36:21+00:00): **PASS** — all three approval spellings return a proposal; PAPER_MODE=1 and yes stay paper · evidence: [CF-02-retest.txt](evidence/2026-09-24-01/CF-02-retest.txt)
- Notes: Log correction (independent review): the regression tests for this check are in tests/test_switches.py (commented or misspelt EXECUTION_APPROVAL_MODE, PAPER_MODE=1/yes/TRUE), not tests/test_order_path.py as the fix record says.

#### CF-03 — Brokerage sandbox switches keep Tradier and E*TRADE out of production  [FAIL · high · **VERIFIED**]

- Section: `config`
- Steps: Construct TradierBrokerage and EtradeBrokerage with TRADIER_SANDBOX/ETRADE_SANDBOX set to true, 1, yes, TRUE, on
- Expected: Every truthy spelling selects the sandbox; E*TRADE orders and balances use the same host
- Observed: TRADIER_SANDBOX=1/yes/on -> https://api.tradier.com (production); ETRADE_SANDBOX=1/yes/TRUE/on -> https://api.etrade.com; the E*TRADE balance URL is hard-coded to production even with ETRADE_SANDBOX=true
- Evidence: [CF-03.txt](evidence/2026-09-24-01/CF-03.txt)
- Fix: Tradier uses safety_switch_on(TRADIER_SANDBOX, default true); E*TRADE uses opt_in_switch_on(ETRADE_SANDBOX) and one api_host for market data, orders and balances
  - Root cause: Exact-string comparisons ('true') and a hard-coded production balance URL
  - Files: `execution/tradier_service.py`, `execution/retail_services.py`
  - Commit: `c07f92b`
  - Regression test: tests/test_switches.py
- Retest 1 (2026-09-24T11:41:45+00:00): **PASS** — true/1/yes/TRUE/on all select sandbox.tradier.com and apisb.etrade.com; E*TRADE now has one api_host line (orders and balances build on it) · evidence: [CF-03-retest.txt](evidence/2026-09-24-01/CF-03-retest.txt)
- Retest 2 (2026-09-24T13:08:13+00:00): **PASS** — The URLs E*TRADE orders and balances are actually sent to: apisb.etrade.com for ETRADE_SANDBOX=true/1/yes/on/TRUE, api.etrade.com only when unset (captured from the connector's session before sending) · evidence: [CF-03-retest-3.txt](evidence/2026-09-24-01/CF-03-retest-3.txt)

#### CF-04 — Alpaca live-mode orders go to the Alpaca paper account unless explicitly switched  [FAIL · high · **VERIFIED**]

- Section: `config`
- Steps: PAPER_MODE=false with Alpaca keys; construct AlpacaBrokerage with ALPACA_PAPER unset/true/false
- Expected: Alpaca's paper account by default (like Tradier's sandbox); a real account only on an explicit ALPACA_PAPER=false
- Observed: The connector reads PAPER_MODE, which is false whenever it is reached, so every live-mode Alpaca order targets TRADING_LIVE regardless of ALPACA_PAPER; env.example documents ALPACA_SECRET_KEY/ALPACA_BASE_URL, which the code never reads
- Evidence: [CF-04.txt](evidence/2026-09-24-01/CF-04.txt)
- Fix: AlpacaBrokerage reads ALPACA_PAPER (default true, only an explicit off reaches a real account)
  - Root cause: The connector read PAPER_MODE, which is always false when a live order reaches it
  - Files: `execution/alpaca_service.py`
  - Commit: `c07f92b`
  - Regression test: tests/test_switches.py
- Retest 1 (2026-09-24T11:41:46+00:00): **PASS** — With PAPER_MODE=false, ALPACA_PAPER unset or true -> TRADING_PAPER; only ALPACA_PAPER=false -> TRADING_LIVE · evidence: [CF-04-retest.txt](evidence/2026-09-24-01/CF-04-retest.txt)
- Retest 2 (2026-09-24T13:08:23+00:00): **PASS** — Alpaca: paper account unless ALPACA_PAPER=false; env.example now documents ALPACA_API_KEY/ALPACA_API_SECRET/ALPACA_PAPER (the names the code reads) and no longer ALPACA_SECRET_KEY/ALPACA_BASE_URL · evidence: [CF-04-retest-2.txt](evidence/2026-09-24-01/CF-04-retest-2.txt)

#### DOC-01 — Every doc names only tools, files, links and settings that exist  [FAIL · high · **VERIFIED**]

- Section: `docs`
- Steps: doccheck over the 17 Markdown docs against the 29 registered MCP tools; regenerate docs/TOOLS.md; count crypto/stock leftovers; read smithery.yaml
- Expected: Only registered tools and existing paths; TOOLS.md lists every tool; FX wording; smithery.yaml points at this repo with the variables the server reads
- Observed: 68 doccheck problems and 50 calls to unregistered tools: README calls get_forex_price, check_orders, get_portfolio_balance, reset_paper_wallet, get_sentiment, get_marketdata_capabilities; RUNBOOK/EXCHANGES/ERRORS/CUSTODY/MARKETDATA/prompt pack describe the crypto server's CEX, metrics, disclosure and wallet tools; ERRORS.md links to file:///Users/billwilson_home/...ReadyTrader-Crypto; README links files that do not exist (RELEASE_READINESS_CHECKLIST.md, agent.yaml, mcp-server-config.json). TOOLS.md lists 18 of 29 tools (no order tools) with dead anchors and is out of date. smithery.yaml advertises 'deep DeFi integrations (Aave, Uniswap)', links github.com/up2itnow/ (wrong owner) and exposes CEX_API_KEY/SECRET, which nothing reads
- Evidence: [DOC-01.txt](evidence/2026-09-24-01/DOC-01.txt)
- Fix: Docs rewritten against the running server; generator reads the live registry; smithery.yaml rewritten
  - Files: `README.md`, `RUNBOOK.md`, `docs/*.md`, `prompts/READYTRADER_PROMPT_PACK.md`, `smithery.yaml`, `tools/generate_tool_docs.py`
  - Commit: `592428a`
  - Regression test: tests/test_tool_docs.py
- Retest 1 (2026-09-24T12:11:46+00:00): **PASS** — doccheck: 13 remaining hits are all non-tools by design (error codes, internal functions get_volatility_status/get_news_status, the client's own config file names, a /path/to placeholder, GitHub's relative issues link); no call to an unregistered tool; TOOLS.md up to date with all 29 tools; remaining 'stock' words are tool names kept for compatibility and the inherited-connector notes; smithery.yaml parses, every key is in env.example, and its command starts the server with 29 tools · evidence: [DOC-01-retest.txt](evidence/2026-09-24-01/DOC-01-retest.txt)

#### DOC-02 — The documented Docker path ships a clean image and keeps the paper account  [FAIL · high · **VERIFIED**]

- Section: `docs`
- Steps: Apply .dockerignore to the repo (dockerctx); read the documented docker run lines, the Dockerfile's sidecar hint and docker-compose.sentinel.yml
- Expected: A small context without .venv, .git, data/, uat/ or node_modules; docker run lines keep the paper account in a volume; every documented command exists
- Observed: The build context is 1.2 GB and copies .venv/ (471 MB), frontend/node_modules, .git/ and the operator's data/ (paper ledger, audit log) into the image. Every documented docker run is --rm with no volume, so the paper account vanishes when the MCP client restarts the container. The Dockerfile's sidecar hint runs 'uvicorn api_server:app' (no such module at the root). docker-compose.sentinel.yml builds a crypto signing service from a sentinel/ package that does not exist, with SIGNER_TYPE=env_private_key
- Evidence: [DOC-02.txt](evidence/2026-09-24-01/DOC-02.txt)
- Fix: .dockerignore excludes local state; configs and README mount readytrader-forex-data:/app/data; real sidecar command; sentinel compose to _deprecated
  - Files: `.dockerignore`, `Dockerfile`, `configs/*`, `README.md`, `_deprecated/`
  - Commit: `874799c`
  - Regression test: tests/test_configs.py
- Retest 1 (2026-09-24T12:12:37+00:00): **PASS** — Build context 0.7 MB with none of data/.venv/uat/artifacts/.git; every documented docker run mounts readytrader-forex-data:/app/data; the sidecar hint runs python app/api_server.py; the sentinel compose file is in _deprecated/ · evidence: [DOC-02-retest.txt](evidence/2026-09-24-01/DOC-02-retest.txt)

#### FE-02 — Dashboard shows the operator's real paper account, not made-up figures  [FAIL · high · **VERIFIED**]

- Section: `frontend`
- Steps: fund the paper account with 25,000 USD over MCP; run the API and the dashboard; load localhost:3000
- Expected: 25,000 USD (the agent's account)
- Observed: the page shows a hardcoded '$48,500.00 +7.4% Today' and a dummy chart; the fetched portfolio is discarded, and the API's portfolio is a separate 100,000 in-memory account anyway (BE-11)
- Evidence: [FE-02.txt](evidence/2026-09-24-01/FE-02.txt)
- Fix: dashboard renders the shared paper account from /api/portfolio; no fabricated figures
  - Root cause: hardcoded figures and dummy chart
  - Files: `frontend/src/app/page.tsx`, `frontend/src/components/ModePill.tsx`, `frontend/src/lib/api.ts`, `frontend/src/hooks/usePendingApprovals.ts`
  - Commit: `a065ac4`
- Retest 1 (2026-09-24T11:38:32+00:00): **PASS** — Funded 25,000 USD over MCP; /api/portfolio returns it; the dashboard shows $25,000.00 equity, cash, margin 0/25,000 at 30x and drawdown 0.00% (assertion '25,000' passed, no failed requests); the invented $48,500 / +7.4% figures are gone; the Paper Mode pill shows. · evidence: [FE-02-retest.txt](evidence/2026-09-24-01/FE-02-retest.txt)

#### IN-02 — get_economic_calendar reports the week's high-impact events, or says it could not  [FAIL · high · **VERIFIED**]

- Section: `integrations`
- Steps: call get_economic_calendar(); read the ForexFactory feed it parses; read the same calendar from its public JSON mirror
- Expected: the high-impact events (today: the SNB policy rate), or an error when the source cannot be read
- Observed: ForexFactory answers 403, the parser finds 0 entries, and the tool says 'No High Impact events scheduled for today' - on the day of the SNB rate decision; get_market_sentiment and get_forex_market_brief repeat the same all-clear
- Evidence: [IN-02.txt](evidence/2026-09-24-01/IN-02.txt)
- Fix: calendar reads cached 15 min (CALENDAR_CACHE_TTL_SEC); a refused refresh uses a read up to 6 h old, dated in the answer
  - Root cause: the mirror rate-limits frequent polling
  - Files: `intelligence/core.py`
  - Commit: `6ccc5ff`
  - Regression test: tests/test_source_errors.py
- Retest 1 (2026-09-24T11:31:51+00:00): **PASS** — while the XML feed still answers 403, the tool lists today's SNB rate decision and the week's other high-impact events from the JSON mirror (80 events, 7 high impact), dated; a second call is served from the cache · evidence: [IN-02-retest.txt](evidence/2026-09-24-01/IN-02-retest.txt)
- Notes: Log correction (independent review): the calendar source and the 'never no events' behaviour came in 80e028d; 6ccc5ff added the cache and the stale-read fallback. The fix record names only 6ccc5ff.

#### PRE-02 — Documented start command python app/main.py resolves the app package  [FAIL · high · **VERIFIED**]

- Section: `preflight`
- Steps: python app/main.py with mcp 1.x installed
- Expected: the server starts
- Observed: ModuleNotFoundError: No module named 'app' (run as a file, the repo root is not on sys.path); MCP clients configured with app/main.py get 'Connection closed'
- Evidence: [PRE-02.txt](evidence/2026-09-24-01/PRE-02.txt)
- Fix: app/main.py inserts the repo root on sys.path when run as a file
  - Root cause: python app/main.py puts app/ on sys.path, not the repo root
  - Files: `app/main.py`
  - Commit: `a12f405`
  - Regression test: tests/test_server_startup.py
- Retest 1 (2026-09-24T10:55:50+00:00): **PASS** — python app/main.py starts and an MCP client lists 27 tools · evidence: [PRE-02-retest.txt](evidence/2026-09-24-01/PRE-02-retest.txt)

#### PRE-05 — CI runs the project's tests  [FAIL · high · **VERIFIED**]

- Section: `preflight`
- Steps: read .github/workflows/ci.yml
- Expected: CI installs the Python deps and runs pytest (and lint/security scan)
- Observed: the only job runs 'npm install --if-present || true' and 'npm test --if-present || echo No tests configured yet' at the repo root, which has no package.json: CI is green whatever the Python code does
- Evidence: [PRE-04.txt](evidence/2026-09-24-01/PRE-04.txt)
- Fix: ci.yml: python job (pip install -r requirements-dev.txt; ruff; pytest; bandit) and frontend job (npm ci, lint, build)
  - Root cause: placeholder npm workflow at a root with no package.json
  - Files: `.github/workflows/ci.yml`
  - Commit: `9551325`
- Retest 1 (2026-09-24T10:57:02+00:00): **PASS** — the workflow's python steps (ruff, pytest, bandit) run and pass locally; the dashboard lint/build steps are checked in the frontend section · evidence: [PRE-05-retest.txt](evidence/2026-09-24-01/PRE-05-retest.txt)

#### XR-01 — Every spelling of a pair gets the same market checks  [FAIL · high · **VERIFIED**]

- Section: `backend`
- Observed: Live, volatility halt on EURUSD (7.3x normal): SELL 4,000 'EURUSD' or 'EUR/USD' is risk_blocked, but 'EUR_USD' or 'eur-usd' is sent with market status unavailable; with MARKET_GUARD_ON_DATA_ERROR=allow, BUY 'EUR_USD' into an 8% collapse is sent. The bar fetch strips only '/', the position lookup also '_' and '-'.
- Evidence: [XR-01.txt](evidence/2026-09-24-01/XR-01.txt)
- Fix: canonical_symbol() maps every pair spelling to EURUSD before validate_trade_risk, pre_trade_check and place_stock_order run any check.
  - Root cause: The bar lookup read the symbol as given and the provider stripped only '/', so EUR_USD / eur-usd found no bars; the SELL-side halt and the data-error policy then let the order through.
  - Files: `app/tools/trading.py`, `app/tools/execution.py`
  - Commit: `4f72e15d`
  - Regression test: tests/test_uat_review_2026_09_24.py::test_every_spelling_of_a_pair_gets_the_same_market_checks
- Retest 1 (2026-09-24T21:51:19+00:00): **PASS** — Live volatility halt: SELL 4,000 in every spelling (EURUSD, EUR/USD, EUR_USD, eur-usd) is risk_blocked with market.status ok (ratio 7.28); the Falling Knife BUY with EUR_USD is blocked too; orders sent to OANDA: []. · evidence: [XR-01-retest.txt](evidence/2026-09-24-01/XR-01-retest.txt)

#### XR-02 — Resting limit orders cannot build exposure the Guardian never sees  [FAIL · high · **VERIFIED**]

- Section: `backend`
- Observed: Live, long 100,000 EUR_USD: five SELL LIMIT 100,000 @1.20 are each sized as reducing (0 added) and all sent GTC: if filled, a net short of 400,000 EUR (~$432k) on $100k equity. Open orders are never counted.
- Evidence: [XR-02.txt](evidence/2026-09-24-01/XR-02.txt)
- Fix: Every OANDA order is fill-or-kill: a limit is a MARKET order with priceBound=limit, timeInForce FOK; positionFill REDUCE_FIRST nets as the Guardian sizes (an account that cannot net rejects the order). Nothing rests at the broker.
  - Root cause: Live limits went to OANDA as GTC LIMIT orders; the Guardian sizes against current positions, so resting orders (and their later fills) were never counted and outlived the kill switch.
  - Files: `execution/oanda_service.py`, `docs/EXCHANGES.md`, `README.md`
  - Commit: `4f72e15d`
  - Regression test: tests/test_uat_review_2026_09_24.py::test_a_live_limit_order_never_rests_at_oanda; tests/test_oanda.py::test_a_limit_order_fills_now_at_its_price_or_better_or_not_at_all
- Retest 1 (2026-09-24T21:51:19+00:00): **PASS** — Through the tools and the real OANDA connector (fake v20 API): five SELL LIMIT 100,000 @1.20 are sent as MARKET/FOK/REDUCE_FIRST with priceBound 1.2 and cancelled (BOUNDS_VIOLATION, execution_error); a marketable SELL LIMIT @1.07 fills; order types sent: only (MARKET, FOK); orders left resting at OANDA: 0. · evidence: [XR-02-retest.txt](evidence/2026-09-24-01/XR-02-retest.txt)

#### XR-03 — Orders at every brokerage are valued at the market, not the caller's price  [FAIL · high · **VERIFIED**]

- Section: `backend`
- Observed: Live via alpaca: MARKET BUY 10,000 AAPL with price=0.0001 (market 190) is valued at $1 and sent; the approval API re-executes it (200); a MARKET SELL that opens a short is sent even with no quote. Currency pairs are valued at the market quote.
- Evidence: [XR-03.txt](evidence/2026-09-24-01/XR-03.txt)
- Fix: The reference price is the market price (a limit at max(limit, market)); a market order's price is dropped; without a market price an order that adds exposure is refused. The approval API re-runs the check with the order type.
  - Root cause: pre_trade_check used the caller's price as the reference whenever one was given, so a non-pair order carrying price=0.0001 was valued at almost nothing.
  - Files: `app/tools/execution.py`, `app/api_server.py`
  - Commit: `4f72e15d`
  - Regression test: tests/test_uat_review_2026_09_24.py::test_an_order_at_any_brokerage_is_valued_at_the_market; tests/test_uat_review_2026_09_24.py::test_without_a_market_price_an_order_that_adds_exposure_is_refused
- Retest 1 (2026-09-24T21:51:19+00:00): **PASS** — Alpaca MARKET BUY 10,000 AAPL price=0.0001 is valued at 190 (notional 1.9M) and refused; no quote: SELL opening a short is refused 'Could not value'; the approval section: the proposal is refused up front; orders sent to the recorders: []. · evidence: [XR-03-retest.txt](evidence/2026-09-24-01/XR-03-retest.txt)

#### XR-04 — A paper deposit does not end a drawdown halt  [FAIL · high · **VERIFIED**]

- Section: `data`
- Observed: After a 14.9% drawdown a BUY is refused; after deposit_paper_funds(USD, 1,000,000) drawdown reads 1.2% and BUY 40,000 GBPUSD executes (the drawdown divides by current equity).
- Evidence: [XR-04.txt](evidence/2026-09-24-01/XR-04.txt)
- Fix: get_risk_metrics chains results into a time-weighted index (per period: equity change less deposits, over the prior equity): a deposit is neither a gain nor a loss and cannot end a halt.
  - Root cause: The drawdown was the fall in (equity - deposits) divided by the current equity, so new capital shrank it.
  - Files: `core/fx_account.py`
  - Commit: `4f72e15d`
  - Regression test: tests/test_uat_review_2026_09_24.py::test_a_deposit_does_not_end_a_drawdown_halt; tests/test_uat_review_2026_09_24.py::test_the_order_check_halts_on_a_drawdown_a_deposit_cannot_hide
- Retest 1 (2026-09-24T21:51:19+00:00): **PASS** — After a 12.96% loss recorded yesterday the BUY is refused (Max Drawdown 13.0%); after deposit_paper_funds(1,000,000) the drawdown still reads 0.1296 and BUY 40,000 GBPUSD is refused. · evidence: [XR-04-retest.txt](evidence/2026-09-24-01/XR-04-retest.txt)

#### XR-05 — Docs say which loss limits apply to live orders  [FAIL · high · **VERIFIED**]

- Section: `docs`
- Observed: Live equity 100,000 -> 80,000 today: a BUY is allowed ('Trade looks safe'): only paper mode computes the loss metrics. README:37, THREAT_MODEL:26-27, RUNBOOK:63 and ERRORS:23 state the limits without saying paper only.
- Evidence: [XR-05.txt](evidence/2026-09-24-01/XR-05.txt)
- Fix: Live verdicts (and executed orders) list daily_loss_limit and max_drawdown under inactive_rules; README, THREAT_MODEL, RUNBOOK and ERRORS say the limits run on the paper account only and how to watch a live account.
  - Root cause: Only paper mode computes loss metrics, and the docs stated the limits without saying so.
  - Files: `app/tools/trading.py`, `app/tools/execution.py`, `README.md`, `docs/THREAT_MODEL.md`, `RUNBOOK.md`, `docs/ERRORS.md`
  - Commit: `4f72e15d`
  - Regression test: tests/test_uat_review_2026_09_24.py::test_live_orders_say_which_loss_rules_do_not_run
- Retest 1 (2026-09-24T21:51:20+00:00): **PASS** — Live, equity down 20% today: the check still allows (no loss history for a live account), and now says so: inactive_rules lists daily_loss_limit and max_drawdown in the verdict and in the executed order; README:37/172, THREAT_MODEL:34, RUNBOOK:73 and ERRORS:28 say 'paper account only'. · evidence: [XR-05-retest.txt](evidence/2026-09-24-01/XR-05-retest.txt)

#### XR-06 — A live approve_each order needs an approval the agent cannot give itself  [FAIL · high · **VERIFIED**]

- Section: `backend`
- Observed: The agent receives each proposal's confirm_token; POST /api/approve-trade needs only that token, so an agent that can make HTTP requests approves its own live order (200, order sent). THREAT_MODEL:24 says approve_each requires a human for every order.
- Evidence: [XR-06.txt](evidence/2026-09-24-01/XR-06.txt)
- Fix: API_OPERATOR_TOKEN: when set, every /api/ route but /api/health needs Authorization: Bearer; a live proposal is approved only when it is set (403 operator_token_required, checked before the proposal is consumed). The dashboard sends it (asked once per tab).
  - Root cause: Approval needed only the confirm_token, which the agent receives with the proposal.
  - Files: `app/api_server.py`, `frontend/src/lib/api.ts`, `frontend/src/hooks/usePendingApprovals.ts`, `frontend/src/app/page.tsx`, `env.example`, `README.md`, `RUNBOOK.md`, `docs/THREAT_MODEL.md`
  - Commit: `4f72e15d`
  - Regression test: tests/test_uat_review_2026_09_24.py::test_a_live_proposal_needs_the_operator_token
- Retest 1 (2026-09-24T21:51:20+00:00): **PASS** — Without API_OPERATOR_TOKEN a live approval answers 403 operator_token_required (0 orders); with it set, the agent's confirm_token alone or a wrong bearer answers 401 (0 orders); the operator's bearer approves (200, 1 order); /api/health stays open, /api/pending-approvals needs the token. · evidence: [XR-06-retest.txt](evidence/2026-09-24-01/XR-06-retest.txt)

#### AR-02 — The dashboard can read a 401 and ask for the operator token  [FAIL · medium · **VERIFIED**]

- Section: `frontend`
- Expected: 401 and 500 answers carry the CORS headers for the dashboard's origin.
- Observed: request_context ran outside CORSMiddleware: the 401 and the JSON 500 had no Access-Control-Allow-Origin, so the browser hid them and the dashboard showed 'API not reachable' instead of asking for the token.
- Evidence: [AR-02.txt](evidence/2026-09-24-01/AR-02.txt)
- Fix: CORS is added after request_context and wraps every answer.
  - Root cause: CORSMiddleware was added before the http middleware, so it sat inside it.
  - Files: `app/api_server.py`
  - Commit: `fc571242`
  - Regression test: tests/test_uat_review_2026_09_24.py::test_every_answer_carries_the_cors_headers
- Retest 1 (2026-09-25T11:38:39+00:00): **PASS** — CORS is now the outermost middleware: the 401s and the JSON 500 carry Access-Control-Allow-Origin for the dashboard. · evidence: [AR-02-retest.txt](evidence/2026-09-24-01/AR-02-retest.txt)

#### AR-03 — A NaN quote is no price  [FAIL · medium · **VERIFIED**]

- Section: `backend`
- Expected: A non-finite quote is treated as missing: an order that adds exposure is refused, and no NaN reaches JSON.
- Observed: _quote returned NaN (truthy): a live BUY of 1,000,000 AAPL at alpaca passed the size rule (notional nan) and was sent; a refused pair order carried reference_price NaN (invalid JSON); a paper approval answered 500.
- Evidence: [AR-03.txt](evidence/2026-09-24-01/AR-03.txt)
- Fix: Quotes must be finite and positive, else they are no price (the fail-closed paths then refuse).
  - Root cause: The quote functions tested 'if not price', and NaN is truthy.
  - Files: `app/tools/execution.py`, `core/fx_account.py`
  - Commit: `fc571242`
  - Regression test: tests/test_uat_review_2026_09_24.py::test_a_nan_quote_is_no_price
- Retest 1 (2026-09-25T11:38:39+00:00): **PASS** — With a NaN AAPL quote the order is refused (valued from the last close instead, 1104%), nothing is sent, no NaN in the JSON; the paper approval with a NaN rate answers 400 with a reason instead of 500, nothing executed. · evidence: [AR-03-retest.txt](evidence/2026-09-24-01/AR-03-retest.txt)

#### BE-03 — Malformed trade requests are refused (unknown side, non-positive amount)  [FAIL · medium · **VERIFIED**]

- Section: `backend`
- Steps: place_market_order EURUSD side=hold amount=-5
- Expected: invalid_request
- Observed: 'Paper Trade Executed: HOLD -5.0 EURUSD @ 0.5' and the ledger changed
- Evidence: [BE-01.txt](evidence/2026-09-24-01/BE-01.txt)
- Fix: side buy/sell, positive finite amount, market/limit with a positive limit price
  - Root cause: no input validation
  - Files: `app/tools/execution.py`, `core/fx_account.py`
  - Commit: `9976ddc`
  - Regression test: tests/test_order_path.py
- Retest 1 (2026-09-24T11:21:48+00:00): **PASS** — side=hold amount=-5 -> invalid_request, nothing executed · evidence: [BE-01-retest.txt](evidence/2026-09-24-01/BE-01-retest.txt)

#### BE-07 — start_brokerage_private_ws tells the truth  [FAIL · medium · **VERIFIED**]

- Section: `backend`
- Steps: live mode: start_brokerage_private_ws oanda
- Expected: a real stream, or a not_implemented error
- Observed: ok:true {status: connected} without opening anything
- Evidence: [BE-05.txt](evidence/2026-09-24-01/BE-05.txt)
- Fix: start_brokerage_private_ws returns not_implemented in live mode
  - Root cause: stub returned connected
  - Files: `app/tools/execution.py`
  - Commit: `9976ddc`
  - Regression test: tests/test_server.py
- Retest 1 (2026-09-24T11:22:15+00:00): **PASS** — live mode: not_implemented · evidence: [BE-05-retest.txt](evidence/2026-09-24-01/BE-05-retest.txt)

#### BE-09 — API server starts as documented (python app/api_server.py)  [FAIL · medium · **VERIFIED**]

- Section: `backend`
- Steps: python app/api_server.py
- Expected: the API serves /api/health
- Observed: ModuleNotFoundError: No module named 'app'
- Evidence: [BE-09.txt](evidence/2026-09-24-01/BE-09.txt)
- Fix: api_server.py puts the repo root on sys.path when run as a file
  - Root cause: run as a file, app/ was sys.path[0]
  - Files: `app/api_server.py`
  - Commit: `9976ddc`
  - Regression test: tests/test_order_path.py
- Retest 1 (2026-09-24T11:22:52+00:00): **PASS** — python app/api_server.py starts and serves until stopped · evidence: [BE-09-retest.txt](evidence/2026-09-24-01/BE-09-retest.txt)
- Retest 2 (2026-09-24T13:07:13+00:00): **PASS** — python app/api_server.py started as a file answers GET /api/health 200 {status: ok, mode: paper} · evidence: [BE-09-retest-2.txt](evidence/2026-09-24-01/BE-09-retest-2.txt)

#### BE-12 — The approval API answers only the dashboard's browser origin  [FAIL · medium · **VERIFIED**]

- Section: `backend`
- Steps: GET /api/portfolio with Origin https://evil.example
- Expected: no CORS grant for a foreign origin
- Observed: Access-Control-Allow-Origin: * on every route: any web page the operator visits can read the account and post approvals to the local API
- Evidence: [BE-09.txt](evidence/2026-09-24-01/BE-09.txt)
- Fix: CORS from API_CORS_ORIGINS (default the dashboard on :3000, '*' ignored); cancel checks the confirm_token
  - Root cause: allow_origins=['*']
  - Files: `app/api_server.py`, `execution/store.py`
  - Commit: `9976ddc`
  - Regression test: tests/test_order_path.py
- Retest 1 (2026-09-24T11:22:53+00:00): **PASS** — no Access-Control-Allow-Origin for https://evil.example; a cancel with a guessed token is refused and the proposal stays pending · evidence: [BE-09-retest.txt](evidence/2026-09-24-01/BE-09-retest.txt)
- Retest 2 (2026-09-24T13:07:19+00:00): **PASS** — Positive control: Origin http://localhost:3000 gets access-control-allow-origin; https://evil.example gets none · evidence: [BE-12-retest.txt](evidence/2026-09-24-01/BE-12-retest.txt)

#### BE-14 — A backtest that fails reports failure (ok:false), not success  [FAIL · medium · **VERIFIED**]

- Section: `backend`
- Steps: run_backtest_simulation with a forbidden import and with no on_candle
- Expected: ok:false with a code
- Observed: ok:true with the failure inside data.result.error
- Evidence: [BE-13.txt](evidence/2026-09-24-01/BE-13.txt)
- Fix: run_backtest_simulation returns ok:false backtest_error on failure
  - Root cause: engine error dict wrapped in _json_ok
  - Files: `app/tools/research.py`
  - Commit: `33bf5e1`
  - Regression test: tests/test_research_tools.py
- Retest 1 (2026-09-24T11:23:13+00:00): **PASS** — forbidden import and missing on_candle -> ok:false backtest_error · evidence: [BE-13-retest.txt](evidence/2026-09-24-01/BE-13-retest.txt)

#### BE-29 — validate_trade_risk refuses a malformed request instead of calling it safe  [FAIL · medium · **VERIFIED**]

- Section: `backend`
- Steps: validate_trade_risk(side='hold', symbol='NOTAPAIR', amount_usd=-5, portfolio_value=0); validate_trade_risk('buy','EURUSD', 1e9, 0)
- Expected: invalid_request for a side other than buy/sell, a non-positive amount or a non-positive portfolio value
- Observed: Both answer ok with 'Trade looks safe': a 'hold' of -5 USD on a non-pair, and a 1,000,000,000 USD buy against a zero portfolio (the size rule is skipped when portfolio_value is 0). Found by the independent review
- Evidence: [BE-29.txt](evidence/2026-09-24-01/BE-29.txt)
- Fix: validate_trade_risk validates side, symbol, amount_usd and portfolio_value (invalid_request)
  - Files: `app/tools/trading.py`
  - Commit: `eed8f6f`
  - Regression test: tests/test_research_tools.py::test_validate_trade_risk_refuses_a_malformed_request
- Retest 1 (2026-09-24T13:03:57+00:00): **PASS** — hold/-5/NOTAPAIR/portfolio 0 -> invalid_request 'side must be buy or sell'; the 1e9 buy against a zero portfolio -> invalid_request 'portfolio_value must be a positive number' · evidence: [BE-29-retest-2.txt](evidence/2026-09-24-01/BE-29-retest-2.txt)

#### BE-32 — A quote without a price (Yahoo's unfinished session row) is never answered as a price  [FAIL · medium · **VERIFIED**]

- Section: `backend`  |  Journey: paper-trade a pair
- Steps: yfinance history mocked with the row shape Yahoo returned for AAPL on Saturday 2026-09-26 00:14 UTC (Stocks BE-34): a last row with NaN prices; provider fetch_ticker / fetch_ohlcv and the get_stock_price tool
- Expected: the last real rate (or fetch_price_error); bars without the NaN row
- Observed: fetch_ticker last NaN; fetch_ohlcv keeps the NaN bar; get_stock_price answers ok with price/bid/ask NaN (not valid JSON for strict parsers). Orders are safe: the paper account refuses a non-finite rate
- Evidence: [BE-32.txt](evidence/2026-09-24-01/BE-32.txt)
- Fix: provider rows without a finite positive OHLC are dropped; quote tools answer only finite positive prices
  - Root cause: NaN is truthy: 'if not price' let Yahoo's unfinished-session row through as a quote
  - Files: `marketdata/exchange_provider.py`, `app/tools/market_data.py`, `AGENTS.md`, `CHANGELOG.md`
  - Commit: `79192fb8`
  - Regression test: tests/test_exchange_provider.py (2), tests/test_research_tools.py::test_a_quote_without_a_real_price_is_no_price; fail on the old code
- Retest 1 (2026-09-26T00:22:56+00:00): **PASS** — same NaN row: fetch_ticker last 1.1392 (the last real close), bars skip the NaN row, get_stock_price answers ok with real price/bid/ask · evidence: [BE-32-retest.txt](evidence/2026-09-24-01/BE-32-retest.txt)

#### CF-01 — env.example lists the variables the code reads, with safe values  [FAIL · medium · **VERIFIED**]

- Section: `config`
- Steps: scan the code for environment reads; compare with env.example
- Expected: every variable listed; safe defaults
- Observed: 15 of 92 variables listed (no LIVE_TRADING_ENABLED, TRADING_HALTED, EXECUTION_APPROVAL_MODE, OANDA_*, ALPACA_API_SECRET, news keys, policy limits); it sets API_HOST=0.0.0.0, exposing the unauthenticated approval API on every interface, and names ALPACA_SECRET_KEY, which nothing reads
- Evidence: [CF-01.txt](evidence/2026-09-24-01/CF-01.txt)
- Fix: Rewrote env.example: every variable a FOREX path reads, grouped, with safe defaults; API_HOST commented at 127.0.0.1; unread names removed
  - Root cause: The file was copied from an earlier stock template and never updated
  - Files: `env.example`
  - Commit: `240727d`
  - Regression test: tests/test_switches.py (no inline comments, no placeholder credentials)
- Retest 1 (2026-09-24T11:51:18+00:00): **PASS** — 73 variables documented. Still unlisted: the crypto-signing allowlists core/policy.py reads but no FOREX tool calls (named in a comment), MARKET_HOURS_* (applied by no FOREX check), and the READYTRADER_-prefixed path aliases (explained in the Storage note). The three 'never read' names are read through _env_limit/_unapplied_number, which the scanner does not match. No API_HOST=0.0.0.0; uncommented values are all safe defaults. · evidence: [CF-01-retest.txt](evidence/2026-09-24-01/CF-01-retest.txt)

#### CL-01 — The setup wizard checks this project's setup and never crashes  [FAIL · medium · **VERIFIED**]

- Section: `cli`
- Steps: tools/setup_wizard.py from the repo root: without .env and stdin closed; then with .env copied from env.example and no keys
- Expected: No traceback; FX-relevant dependencies and sources; paper mode reported as needing no keys; the documented start command
- Observed: Without .env and a non-interactive stdin it dies with an EOFError traceback. With .env it probes the Yahoo home page (429), the Alpaca API (401) and the crypto Fear & Greed index (used nowhere in FOREX), none of the FX sources the server reads; it marks OANDA_API_KEY and ALPACA_API_KEY as MISSING in red although paper mode needs no keys; it checks alpaca.trading, a stock-broker SDK
- Evidence: [CL-01.txt](evidence/2026-09-24-01/CL-01.txt)
- Fix: ask() treats EOF as no answer; FX sources probed with a User-Agent; keys judged by PAPER_MODE; FX dependencies; documented start command
  - Files: `tools/setup_wizard.py`
  - Commit: `7cf76f1`
  - Regression test: tests/test_setup_wizard.py
- Retest 1 (2026-09-24T11:56:04+00:00): **PASS** — No .env + closed stdin: finishes (no traceback). With .env: FX dependencies, Yahoo FX bars and the calendar reachable, FXStreet's 403 reported as-is (the news tool reports the same failure honestly); paper mode reports OANDA keys as not needed; next step python app/main.py · evidence: [CL-01-retest.txt](evidence/2026-09-24-01/CL-01-retest.txt)

#### CL-02 — The shipped example scripts run and demonstrate this server's paper account  [FAIL · medium · **VERIFIED**]

- Section: `cli`
- Steps: python examples/paper_quick_demo.py (README 'validate the paper engine'); python examples/verify_live_strategy.py
- Expected: The demo exercises the FX paper account the server trades in and every step succeeds; the verify script runs
- Observed: paper_quick_demo exercises the crypto engine (core/paper.PaperTradingEngine: USDC, ETH/USDT limit orders), not FxPaperAccount; its own step 5 prints 'Insufficient fund. Have 0.0 ETH' and it still exits 0. verify_live_strategy.py dies at import: No module named 'execution.stock_executor'
- Evidence: [CL-02.txt](evidence/2026-09-24-01/CL-02.txt)
- Fix: paper_quick_demo.py rewritten on FxPaperAccount with self-checks; verify_live_strategy.py checks OANDA wiring and runs SMA on EURUSD; moving_average registers pandas_ta
  - Files: `examples/paper_quick_demo.py`, `examples/verify_live_strategy.py`, `strategy/moving_average.py`
  - Commit: `6886e25`
  - Regression test: tests/test_examples.py
- Retest 1 (2026-09-24T11:57:56+00:00): **PASS** — paper_quick_demo exercises FxPaperAccount (EURUSD long, USDJPY short with JPY->USD P&L, margin, close, metrics), every self-check ok, exit 0; verify_live_strategy reports OANDA not available/practice API and runs SMA on EURUSD, SUCCESS · evidence: [CL-02-retest.txt](evidence/2026-09-24-01/CL-02-retest.txt)

#### DOC-05 — The README's Agent Zero integration works in current Agent Zero  [FAIL · medium · **VERIFIED**]

- Section: `docs`
- Steps: follow README Option A (Agent Zero) in Agent Zero v2.13; give its block to Agent Zero's MCP settings parser
- Expected: a server entry Agent Zero starts
- Observed: Option A points to 'Settings -> MCP Servers' and an 'agent.yaml' mcp_servers block. Agent Zero v2.13 keeps MCP servers in Settings -> MCP/A2A -> External MCP Servers as JSON ({"mcpServers": {...}}); agent.yaml is agent-profile metadata. The README's block yields no server in Agent Zero's parser (parse_config_string -> []), and configs/agent_zero.mcp.yaml has the same shape. The Agent Zero plugin, the supported path, is not mentioned.
- Evidence: [DOC-05.txt](evidence/2026-09-24-01/DOC-05.txt)
- Fix: README Option A points to the Agent Zero plugin first; the hand-made entry is the {"mcpServers": ...} JSON for Settings -> MCP/A2A -> External MCP Servers (configs/agent_zero.mcp.json, data volume included); the YAML moved to _deprecated/configs/
  - Root cause: the Agent Zero section was written for an older Agent Zero (MCP servers in agent.yaml / a settings page that no longer exists)
  - Files: `README.md`, `configs/agent_zero.mcp.json`, `_deprecated/configs/agent_zero.mcp.yaml`, `CHANGELOG.md`, `AGENTS.md`, `tests/test_configs.py`
  - Commit: `190fb3a6`
  - Regression test: tests/test_configs.py::test_the_agent_zero_config_is_what_agent_zero_reads
- Retest 1 (2026-09-26T02:18:16+00:00): **PASS** — the README's Agent Zero JSON block (identical to configs/agent_zero.mcp.json) parses in Agent Zero v2.13 to one server, readytrader_forex (DOC-05-retest.txt); the README's without-Docker form, written into External MCP Servers of a real Agent Zero tree, connects with 29 tools and answers a price through Agent Zero's MCP client (this capture); the Docker form was not run (no Docker daemon here) · evidence: [DOC-05-retest-nodocker.txt](evidence/2026-09-24-01/DOC-05-retest-nodocker.txt)

#### FE-05 — The dashboard is readable at phone width (390x844)  [FAIL · medium · **VERIFIED**]

- Section: `frontend`
- Steps: Paper account with a EURUSD long and a USDJPY short; load / at 390x844
- Expected: Single-column layout; equity, cash, positions and P&L readable with no horizontal scroll
- Observed: The fixed 260 px sidebar takes two thirds of the screen and the account card is cut off at the right edge (body overflow-x is hidden, so scrollWidth equals 390 but the content is clipped): cash, equity, the positions' P&L and the margin figures are unreadable (screenshot FE-05-mobile.png)
- Evidence: [FE-05.txt](evidence/2026-09-24-01/FE-05.txt)
- Fix: Media query below 900 px: static top sidebar, single-column grid, tighter padding
  - Files: `frontend/src/app/globals.css`
  - Commit: `c24e42b`
- Retest 1 (2026-09-24T12:20:26+00:00): **PASS** — At 390x844 the sidebar is a top bar and the grid one column: equity $25,000.00, cash, both positions with P&L, margin 71.23 / 24,928.77 and drawdown are all readable; scrollWidth equals the viewport (FE-05-retest-mobile.png) · evidence: [FE-05-retest.txt](evidence/2026-09-24-01/FE-05-retest.txt)
- Notes: The proof of the fix is the retest screenshot FE-05-retest-mobile.png (single column, every figure readable); scrollWidth=390 was also true while broken, because body overflow-x is hidden.

#### FE-07 — The operator can see what a proposal is before approving it, and can reject it  [FAIL · medium · **VERIFIED**]

- Section: `frontend`
- Steps: approve_each with the MCP server and API sharing EXECUTION_DB_PATH/EXECUTION_SESSION_ID; the agent proposes buy 4,000 EURUSD; open the dashboard
- Expected: The Guard Rail card names the pair, side, amount and order type, with Approve and Reject
- Observed: It shows 'stock order ID: 88203489... Approve' - no pair, side or amount (/api/pending-approvals returns only id, kind and times), and there is no Reject, so the operator approves blind or not at all. Found by the independent review
- Evidence: [FE-07.txt](evidence/2026-09-24-01/FE-07.txt)
- Fix: Card wording: a paper proposal reads 'paper account', a live one 'LIVE via <venue>'; actions wrap under the details
  - Files: `frontend/src/app/page.tsx`, `frontend/src/app/globals.css`
  - Commit: `61a7cdd`
- Retest 1 (2026-09-24T13:06:00+00:00): **PASS** — The Guard Rail card reads 'BUY 4,000 EURUSD market - paper account' with Approve and Reject (FE-07-retest2-approvals.png); /api/pending-approvals carries the order and no token · evidence: [FE-07-retest-2.txt](evidence/2026-09-24-01/FE-07-retest-2.txt)

#### IN-01 — A news or sentiment source that cannot answer is reported as an error, not as news  [FAIL · medium · **VERIFIED**]

- Section: `integrations`
- Steps: without keys: get_market_news, get_financial_news, fetch_financial_news, get_social_sentiment, analyze_social_sentiment
- Expected: ok:false with not_configured
- Observed: all ok:true with the failure text as the payload ('ALPHAVANTAGE_API_KEY missing', 'NEWSAPI_KEY missing', 'No sentiment APIs configured')
- Evidence: [IN-01.txt](evidence/2026-09-24-01/IN-01.txt)
- Fix: feeds fetched with requests (10 s timeout) then parsed; refused feeds are failed sources
  - Root cause: feedparser.parse(url) has no timeout and hides HTTP errors
  - Files: `intelligence/core.py`
  - Commit: `6ccc5ff`
  - Regression test: tests/test_source_errors.py
- Retest 1 (2026-09-24T11:35:57+00:00): **PASS** — keyed sources without keys answer ok:false not_configured; get_forex_news lists refused feeds as failed sources (✗ FXStreet 403, ✗ DailyFX) and returns the working ones' headlines · evidence: [IN-01-retest.txt](evidence/2026-09-24-01/IN-01-retest.txt)
- Notes: Log correction (independent review): the fixes are 80e028d (every source failure is ok:false with a code; feeds fail honestly) and 6ccc5ff (feed timeouts); the fix record names only 6ccc5ff.

#### IN-03 — fetch_custom_feed only fetches public http(s) feeds  [FAIL · medium · **VERIFIED**]

- Section: `integrations`
- Steps: fetch_custom_feed url=http://127.0.0.1:1/private and url=file:///etc/hostname
- Expected: refused: not a public http(s) URL
- Observed: both are fetched (the server reads local files and loopback/private addresses for whoever controls the agent's prompt); they only 'fail' because neither is a feed
- Evidence: [IN-01.txt](evidence/2026-09-24-01/IN-01.txt)
- Fix: fetch_custom_feed fetches only public http(s) URLs, re-checking redirects
  - Root cause: feedparser.parse(url) on any URL
  - Files: `intelligence/core.py`
  - Commit: `80e028d`
  - Regression test: tests/test_source_errors.py
- Retest 1 (2026-09-24T11:35:57+00:00): **PASS** — loopback and file:// URLs are refused before any request (non-public address / only http(s)) · evidence: [IN-01-retest.txt](evidence/2026-09-24-01/IN-01-retest.txt)

#### IN-04 — OANDA (practice API, bogus token): failures reach the operator with OANDA's reason  [FAIL · medium · **VERIFIED**]

- Section: `integrations`
- Steps: Live mode against OANDA's practice API with a bogus token and account id: place_forex_order buy, then sell
- Expected: The BUY is refused (equity unreadable); the SELL fails with OANDA's own reason; nothing is reported as submitted unless OANDA accepted it
- Observed: BUY refused as expected (risk_blocked: equity unreadable). SELL: execution_error 'OANDA order failure: 400 Client Error: Bad Request for url: ...' - OANDA's answer ('Invalid value specified for accountID', shown by the same request with curl) is dropped, so the operator cannot tell a bad token from a bad account. Reading the connector for the same path: a FOK market order OANDA cancels (201 with orderCancelTransaction, e.g. insufficient margin) is reported as ok/'submitted', and a fractional amount under 1 becomes units '0'
- Evidence: [IN-04.txt](evidence/2026-09-24-01/IN-04.txt)
- Fix: _oanda_reason() surfaces errorMessage; orderCancelTransaction without a fill raises; <1 unit refused; parse_pair for instruments
  - Files: `execution/oanda_service.py`
  - Commit: `3250d6f`
  - Regression test: tests/test_oanda.py
- Retest 1 (2026-09-24T12:23:49+00:00): **PASS** — BUY still refused (risk_blocked, equity unreadable); SELL now reads 'OANDA order failure: HTTP 400: Invalid value specified for accountID', OANDA's own reason. Cancel-without-fill, <1 unit and instrument mapping are pinned by tests/test_oanda.py · evidence: [IN-04-retest.txt](evidence/2026-09-24-01/IN-04-retest.txt)

#### ME-02 — Shared insights are recalled under any spelling of the pair and expire everywhere  [FAIL · medium · **VERIFIED**]

- Section: `memory`
- Steps: post_market_insight for 'EUR/USD' (1 day) and GBPUSD (2 s); get_latest_insights with 'EUR/USD', 'eurusd', 'EURUSD', 'eur_usd' and no symbol; again after 3 s
- Expected: Every spelling the other tools accept finds the EUR/USD insight; the expired GBPUSD insight is gone from both the symbol and the all-symbols reads
- Observed: Only the exact spelling 'EUR/USD' finds it: 'EURUSD', 'eurusd' and 'eur_usd' return [] although every order and data tool treats them as the same pair, so a researcher agent posting EUR/USD and an executor asking for EURUSD never share a signal. Expiry works: after its TTL the GBPUSD insight is gone from both reads
- Evidence: [ME-02.txt](evidence/2026-09-24-01/ME-02.txt)
- Fix: insight_key() normalises the pair on write and read (SQL-side for older rows); policy compares by the same key
  - Files: `intelligence/insights.py`, `core/policy.py`
  - Commit: `28346fc`
  - Regression test: tests/test_research_tools.py::test_an_insight_is_found_under_every_spelling_of_the_pair
- Retest 1 (2026-09-24T12:17:41+00:00): **PASS** — EUR/USD, eurusd, EURUSD and eur_usd all return the insight (stored as EURUSD); the 2 s GBPUSD insight is gone from both reads after its TTL · evidence: [ME-02-retest.txt](evidence/2026-09-24-01/ME-02-retest.txt)

#### PRE-06 — README states the Python version the project needs  [FAIL · medium · **VERIFIED**]

- Section: `preflight`
- Steps: compare pyproject requires-python with the README prerequisites
- Expected: Python 3.12+ stated where the local install is described
- Observed: pyproject requires >=3.12 (pandas_ta has no release for older Pythons); the README lists only Docker and 'pip install -r requirements-dev.txt'
- Evidence: [PRE-04.txt](evidence/2026-09-24-01/PRE-04.txt)
- Fix: README prerequisites and local install state Python 3.12+ with venv steps
  - Root cause: requirement only in pyproject
  - Files: `README.md`
  - Commit: `9551325`
- Retest 1 (2026-09-24T10:57:02+00:00): **PASS** — README prerequisites and local install state Python 3.12+ · evidence: [PRE-05-retest.txt](evidence/2026-09-24-01/PRE-05-retest.txt)

#### XR-07 — Paper loss limits measure losses against the capital now in the account and today's start  [FAIL · medium · **VERIFIED**]

- Section: `data`
- Observed: Deposit 1k, small dip, top up 1M, lose $990 (0.099%): daily -99.0% and 'Daily Loss Limit Hit'; with the last snapshot a week old and a -6.5% drift, every adding order today is refused as a daily loss, even after a trade today.
- Evidence: [XR-07.txt](evidence/2026-09-24-01/XR-07.txt)
- Fix: Daily P&L is the index change since the previous UTC day's last snapshot, else the day's first; mark_day_open records one snapshot at the first check of a day.
  - Root cause: Daily P&L divided the day's loss by the first equity of the day (before a top-up), and a week-old snapshot counted as the start of today.
  - Files: `core/fx_account.py`, `app/tools/execution.py`, `app/tools/trading.py`
  - Commit: `4f72e15d`
  - Regression test: tests/test_uat_review_2026_09_24.py::test_a_small_loss_after_a_large_top_up_is_a_small_loss; tests/test_uat_review_2026_09_24.py::test_a_week_old_snapshot_is_not_the_start_of_today
- Retest 1 (2026-09-24T21:51:20+00:00): **PASS** — (c) 1k deposit, dip, 1M top-up, ~990 USD loss: daily_pnl_pct -0.14% (was -99%), BUY allowed; (d) week-old snapshot with -6.5% drift: daily 0.0 and the BUY allowed, drawdown 6.48% kept. · evidence: [XR-07-retest.txt](evidence/2026-09-24-01/XR-07-retest.txt)

#### XR-08 — An unpriceable position does not hide a loss  [FAIL · medium · **VERIFIED**]

- Section: `data`
- Observed: If EURUSD cannot be priced, account() raises, the metrics fall back to the last snapshot (equity 100,000, drawdown 0) and BUY GBPUSD is allowed during a 14.9% drawdown.
- Evidence: [XR-08.txt](evidence/2026-09-24-01/XR-08.txt)
- Fix: Equity is None when a position cannot be priced (account() raises or reports unpriced positions); snapshots skip that state; the order checks refuse new exposure; /api/portfolio and the dashboard show the unpriced positions.
  - Root cause: When a position could not be priced, get_risk_metrics fell back to the last snapshot's equity and _snapshot recorded positions at their entry price.
  - Files: `core/fx_account.py`, `app/tools/execution.py`, `app/api_server.py`, `frontend/src/app/page.tsx`
  - Commit: `4f72e15d`
  - Regression test: tests/test_uat_review_2026_09_24.py::test_an_unpriceable_position_does_not_hide_a_loss
- Retest 1 (2026-09-24T21:51:20+00:00): **PASS** — EURUSD unpriceable: equity reads None (not the last snapshot's 100,000), the 12.96% drawdown is kept and BUY GBPUSD is refused. · evidence: [XR-08-retest.txt](evidence/2026-09-24-01/XR-08-retest.txt)

#### XR-09 — A market order's price is validated or ignored  [FAIL · medium · **VERIFIED**]

- Section: `backend`
- Observed: A market order with price NaN/inf/-1/0 is accepted and stored in the proposal; GET /api/pending-approvals then answers 500 (JSON cannot encode NaN) with no headers, for as long as the proposal is pending.
- Evidence: [XR-09.txt](evidence/2026-09-24-01/XR-09.txt)
- Fix: A market order's price is dropped (0.0) before sizing, proposals and the brokerage; the pending list and approval responses are JSON-safe.
  - Root cause: A market order's price was stored unvalidated in the proposal; JSON cannot encode NaN, so the pending list answered 500.
  - Files: `app/tools/execution.py`, `app/api_server.py`
  - Commit: `4f72e15d`
  - Regression test: tests/test_uat_review_2026_09_24.py::test_a_market_orders_price_is_ignored_and_the_pending_list_still_answers
- Retest 1 (2026-09-24T21:51:20+00:00): **PASS** — A market order with price NaN is proposed with price 0.0; GET /api/pending-approvals answers 200 (with headers), approving executes, and the list answers 200 after; NaN/inf market prices never reach a proposal. · evidence: [XR-09-retest.txt](evidence/2026-09-24-01/XR-09-retest.txt)

#### XR-10 — The kill switch and its way out are documented as they work  [FAIL · medium · **VERIFIED**]

- Section: `docs`
- Observed: With TRADING_HALTED on, a SELL closing a long is refused like a new order; the server has no cancel/close/list tools; GTC limits placed before the halt keep working at OANDA; every emergency-style route is 404.
- Evidence: [XR-10.txt](evidence/2026-09-24-01/XR-10.txt)
- Fix: Docs: the kill switch refuses closing orders too; flatten on the OANDA platform. With fill-or-kill orders (XR-02) nothing the server sent rests at the broker behind the switch.
  - Root cause: The docs did not say the kill switch refuses closes, nor how to flatten; GTC limits sent before a halt kept working at OANDA.
  - Files: `RUNBOOK.md`, `docs/THREAT_MODEL.md`, `README.md`, `docs/EXCHANGES.md`, `execution/oanda_service.py`
  - Commit: `4f72e15d`
  - Regression test: tests/test_uat_review_2026_09_24.py::test_the_kill_switch_docs_say_what_it_refuses_and_how_to_flatten
- Retest 1 (2026-09-24T21:51:20+00:00): **PASS** — Halted: closes and adds are refused (trading_halted) as documented; RUNBOOK:23-28 and THREAT_MODEL:44 now say closes are refused and to flatten on the OANDA platform; OANDA orders are only (MARKET, FOK), so nothing rests at the broker behind the switch. · evidence: [XR-10-retest.txt](evidence/2026-09-24-01/XR-10-retest.txt)

#### XR-11 — The Docker build context keeps secrets and local state out  [FAIL · medium · **VERIFIED**]

- Section: `config`
- Observed: .dockerignore excludes only a root .env: .env.live, prod.env, frontend/.env.local, app/.env, configs/.env, *.pem, *.key, secrets/, app/paper.db, execution.db, subfolder .pyc would be sent (COPY . .); the image runs as root and ships frontend/.
- Evidence: [XR-11.txt](evidence/2026-09-24-01/XR-11.txt)
- Fix: **/ patterns for secrets, keys, databases, caches and logs; frontend/ left out; USER readytrader (uid 10001) owning only /app/data.
  - Root cause: Patterns without **/ match only at the context root, so .env/.pem/.key/.db files in subfolders reached COPY . .; the image ran as root.
  - Files: `.dockerignore`, `Dockerfile`
  - Commit: `4f72e15d bcf733b8`
  - Regression test: tests/test_uat_review_2026_09_24.py::test_the_docker_build_context_leaves_out_secrets_in_any_folder
- Retest 1 (2026-09-24T21:51:20+00:00): **PASS** — Synthetic tree: every .env*/prod.env, .pem/.key, secrets/, *.db (any folder), pycache and the compliance log are excluded; only app/main.py and Dockerfile are sent; the Dockerfile creates readytrader (uid 10001) and runs as USER readytrader. · evidence: [XR-11-retest.txt](evidence/2026-09-24-01/XR-11-retest.txt)

#### AR-04 — A deposit cannot end a drawdown halt while a position is unpriced  [FAIL · low · **VERIFIED**]

- Section: `data`
- Expected: A deposit is recorded with the account's value, or refused.
- Observed: Deposit while EURUSD priced: drawdown 11.00% -> 10.51% (still halted); the same deposit while EURUSD could not be priced skipped its snapshot and later read as a gain: 11.00% -> 5.50%, halt lifted.
- Evidence: [AR-04.txt](evidence/2026-09-24-01/AR-04.txt)
- Fix: deposit() refuses while the account cannot be valued (an unpriced position or no USD rate).
  - Root cause: _snapshot skipped an unpriced state, so a deposit then went unrecorded and the next period counted it as a gain.
  - Files: `core/fx_account.py`
  - Commit: `fc571242`
  - Regression test: tests/test_uat_review_2026_09_24.py::test_a_deposit_waits_while_a_position_cannot_be_priced
- Retest 1 (2026-09-25T11:38:39+00:00): **PASS** — A deposit while EURUSD cannot be priced is refused ('the account cannot be valued now'). With no new capital the later +5,499 is a real trading gain on 89,000 (94,499/100,000: 5.50%, by hand too); a recorded deposit still keeps the halt (10.51%). · evidence: [AR-04-retest.txt](evidence/2026-09-24-01/AR-04-retest.txt)

#### AR-05 — The docs say how the daily-loss baseline is taken  [FAIL · low · **VERIFIED**]

- Section: `docs`
- Expected: RUNBOOK/THREAT_MODEL describe the daily baseline as the code computes it.
- Observed: RUNBOOK:73 says 'lost 5% since the day began'; the code measures from the previous UTC day's last recorded value, so a late move a day never recorded counts toward the next day too (S2: -5.5% all Tuesday with no move since midnight).
- Evidence: [AR-05.txt](evidence/2026-09-24-01/AR-05.txt)
- Fix: RUNBOOK and THREAT_MODEL describe the baseline (previous UTC day's last recorded value, else today's first) and that it errs toward halting.
  - Root cause: The docs described the intent, not the baseline the code uses.
  - Files: `RUNBOOK.md`, `docs/THREAT_MODEL.md`
  - Commit: `fc571242`
  - Regression test: evidence only (docs)
- Retest 1 (2026-09-25T11:38:39+00:00): **PASS** — RUNBOOK:73-78 and THREAT_MODEL:34-36 now describe the baseline the code uses (previous UTC day's last recorded value, else today's first) and that a late unrecorded move counts toward the next day, erring toward halting; the S2 numbers match that description. · evidence: [AR-05-retest.txt](evidence/2026-09-24-01/AR-05-retest.txt)

#### AR-06 — Orders the switches refuse are audited  [FAIL · low · **VERIFIED**]

- Section: `backend`
- Expected: Every well-formed order request writes trade_start to the compliance log, refused or not.
- Observed: Since the switches answer first (REG-03), a halted order returned before the audit record: audit events=[] (35668a03 recorded it).
- Evidence: [AR-06.txt](evidence/2026-09-24-01/AR-06.txt)
- Fix: trade_start is recorded right after input validation, before any refusal.
  - Root cause: REG-03 moved the switch refusal above the audit record.
  - Files: `app/tools/execution.py`
  - Commit: `fc571242`
  - Regression test: tests/test_uat_review_2026_09_24.py::test_orders_the_switches_refuse_are_still_audited
- Retest 1 (2026-09-25T11:38:39+00:00): **PASS** — A halted order answers trading_halted and writes trade_start (EURUSD buy 5,000,000) to the audit log again. · evidence: [AR-06-retest.txt](evidence/2026-09-24-01/AR-06-retest.txt)

#### AR-07 — An approval while halted answers trading_halted  [FAIL · low · **VERIFIED**]

- Section: `backend`
- Expected: RUNBOOK: every approval is refused with trading_halted while the kill switch is set, without calling the brokerage.
- Observed: The approval ran pre_trade_check first: 409 risk_blocked 'Could not read the account's equity' and get_account_balance was called during the halt.
- Evidence: [AR-07.txt](evidence/2026-09-24-01/AR-07.txt)
- Fix: In live mode the switches and the live policy are checked first; pre_trade_check runs only if they pass (execute_order checks them again).
  - Root cause: approve_trade ran pre_trade_check (which reads the brokerage) before live_order_refusal.
  - Files: `app/api_server.py`
  - Commit: `fc571242`
  - Regression test: tests/test_uat_review_2026_09_24.py::test_an_approval_while_halted_answers_halted_without_calling_the_brokerage
- Retest 1 (2026-09-25T11:38:39+00:00): **PASS** — An approval while halted answers 409 trading_halted; the brokerage is not called; no order sent. · evidence: [AR-07-retest.txt](evidence/2026-09-24-01/AR-07-retest.txt)

#### AR-08 — An existing Docker data volume keeps working after the upgrade  [FAIL · low · **VERIFIED**]

- Section: `config`
- Expected: A volume written by the previous (root) image works with the new image, or the docs say the one step that makes it work.
- Observed: Docker: the image at 35668a03 (root) wrote root-owned paper.db/insights.db/strategies.db to a volume; the new image (uid 10001) on that volume fails deposit_paper_funds with 'attempt to write a readonly database'. Nothing documents it.
- Evidence: [AR-08.txt](evidence/2026-09-24-01/AR-08.txt)
- Fix: RUNBOOK 'Upgrading a Docker data volume' and a CHANGELOG breaking note give the one-time chown to uid 10001.
  - Root cause: The image changed its user (XR-11) without an upgrade note.
  - Files: `RUNBOOK.md`, `CHANGELOG.md`
  - Commit: `fc571242`
  - Regression test: tests/test_uat_review_2026_09_24.py::test_the_runbook_says_how_to_upgrade_a_volume_and_quotes_the_code
- Retest 1 (2026-09-25T11:38:40+00:00): **PASS** — The RUNBOOK's one-time chown, run on the volume the root image wrote, hands the files to 10001; the new image then deposits and reads the account (cash 2,000: the old deposit kept). · evidence: [AR-08-retest.txt](evidence/2026-09-24-01/AR-08-retest.txt)

#### AR-09 — The RUNBOOK quotes refusal text as the code writes it  [FAIL · low · **VERIFIED**]

- Section: `docs`
- Expected: Quoted messages match the code.
- Observed: RUNBOOK:79 quotes "Could not read the account's equity (paper) (a position cannot be priced now)"; the code writes '... (paper) for the position-size check (a position cannot be priced now).'
- Evidence: [AR-09.txt](evidence/2026-09-24-01/AR-09.txt)
- Fix: RUNBOOK quotes the message the code writes, and the empty-account variant.
  - Root cause: The quote was written from memory.
  - Files: `RUNBOOK.md`
  - Commit: `fc571242`
  - Regression test: tests/test_uat_review_2026_09_24.py::test_the_runbook_says_how_to_upgrade_a_volume_and_quotes_the_code
- Retest 1 (2026-09-25T11:38:40+00:00): **PASS** — RUNBOOK:82 quotes the message as execution.py:217 writes it ('... for the position-size check (a position cannot be priced now)'). · evidence: [AR-09-retest.txt](evidence/2026-09-24-01/AR-09-retest.txt)

#### AR-10 — Every numeric tool parameter refuses true  [FAIL · low · **VERIFIED**]

- Section: `backend`
- Expected: true/false is refused for every numeric MCP parameter, not just the trading ones.
- Observed: Of 19 numeric parameters, 4 accepted true as 1: get_forex_news.limit, fetch_ohlcv.limit, post_market_insight.confidence (stored at full confidence) and ttl_seconds.
- Evidence: [AR-10.txt](evidence/2026-09-24-01/AR-10.txt)
- Fix: app/tools/params.py defines Number and Integer; every numeric tool parameter uses one.
  - Root cause: Number covered only the trading tools.
  - Files: `app/tools/params.py`, `app/tools/trading.py`, `app/tools/market_data.py`, `app/tools/research.py`
  - Commit: `fc571242`
  - Regression test: tests/test_uat_review_2026_09_24.py::test_every_numeric_tool_parameter_refuses_true
- Retest 1 (2026-09-25T11:38:40+00:00): **PASS** — All 19 numeric MCP parameters refuse true (was 15 of 19). · evidence: [AR-10-retest.txt](evidence/2026-09-24-01/AR-10-retest.txt)

#### BE-04 — deposit_paper_funds accepts only a positive amount  [FAIL · low · **VERIFIED**]

- Section: `backend`
- Steps: deposit USD -50000 after depositing 100000
- Expected: invalid_request
- Observed: accepted: 'Deposited -50000.0 USD. New Balance: 49500.0'
- Evidence: [BE-01.txt](evidence/2026-09-24-01/BE-01.txt)
- Fix: deposits must be positive USD
  - Root cause: no validation
  - Files: `app/tools/execution.py`, `core/fx_account.py`
  - Commit: `9976ddc`
  - Regression test: tests/test_order_path.py
- Retest 1 (2026-09-24T11:21:48+00:00): **PASS** — deposit -50000 -> invalid_request · evidence: [BE-01-retest.txt](evidence/2026-09-24-01/BE-01-retest.txt)

#### BE-08 — get_stock_price returns the price as a number  [FAIL · low · **VERIFIED**]

- Section: `backend`
- Steps: get_stock_price EURUSD
- Expected: a structured quote an agent can use
- Observed: a sentence ('The current price of EURUSD is 1.137... (Source: yfinance)') with exchange 'alpaca'; get_multiple_prices returns numbers
- Evidence: [BE-01.txt](evidence/2026-09-24-01/BE-01.txt)
- Fix: get_stock_price returns price, bid, ask, source
  - Root cause: returned a sentence
  - Files: `app/tools/market_data.py`
  - Commit: `80e028d`
  - Regression test: tests/test_research_tools.py
- Retest 1 (2026-09-24T11:21:48+00:00): **PASS** — get_stock_price returns {price 1.13779, bid, ask, source yfinance} · evidence: [BE-01-retest.txt](evidence/2026-09-24-01/BE-01-retest.txt)

#### BE-23 — Approval API error paths: bad bodies 422, unknown ids 404, no internals  [FAIL · low · **VERIFIED**]

- Section: `backend`
- Steps: POST /api/approve-trade with {}, invalid JSON, wrong types, an unknown request_id; GET an unknown route; count tracebacks in the API log
- Expected: 422 for malformed bodies; 404 for an unknown proposal; 403 for a wrong token; 409 for one that can no longer be approved; no stack traces
- Observed: Malformed bodies 422 with field errors; unknown route 404; no tracebacks. An unknown request_id answers 400 'Unknown request_id', the same status as a wrong token or an expired proposal, so a client cannot tell them apart
- Evidence: [BE-23.txt](evidence/2026-09-24-01/BE-23.txt)
- Fix: approve_trade maps the store's refusal to 404 (unknown id), 403 (wrong token) or 409 (no longer approvable)
  - Files: `app/api_server.py`
  - Commit: `37e3973`
  - Regression test: tests/test_order_path.py::test_approval_errors_say_which_problem_it_is
- Retest 1 (2026-09-24T11:54:22+00:00): **PASS** — Unknown request_id now 404; malformed bodies 422; unknown route 404; no tracebacks (403/409 paths covered by the regression test) · evidence: [BE-23-retest.txt](evidence/2026-09-24-01/BE-23-retest.txt)
- Retest 2 (2026-09-24T13:07:05+00:00): **PASS** — Against a real proposal made over MCP: wrong token 403, its token 200 (executed), again 409 'Proposal already confirmed', unknown id 404; the approve:false answer for an unknown id stays 200 {ok:false} by design (a cancel does not reveal whether an id exists) · evidence: [BE-23-retest-2.txt](evidence/2026-09-24-01/BE-23-retest-2.txt)

#### BE-24 — get_multiple_prices returns numbers, and says which symbols it could not price  [FAIL · low · **VERIFIED**]

- Section: `backend`
- Steps: get_multiple_prices('EURUSD, GBP/USD,NOTAPAIR') and get_multiple_prices('')
- Expected: Prices as numbers; an unpriceable symbol is null with its reason; an empty list is invalid_request
- Observed: An unpriceable symbol's price is the string 'Error' (a client summing prices breaks) with no reason; an empty argument answers ok:true with {'': 'Error'}
- Evidence: [BE-24.txt](evidence/2026-09-24-01/BE-24.txt)
- Fix: prices map to a number or null plus an errors map; empty input is invalid_request
  - Files: `app/tools/market_data.py`
  - Commit: `eccb72a`
  - Regression test: tests/test_research_tools.py::test_get_multiple_prices_answers_numbers_and_names_what_it_could_not_price
- Retest 1 (2026-09-24T12:02:42+00:00): **PASS** — prices: EURUSD and GBP/USD numbers, NOTAPAIR null with the provider's reason in errors; an empty list is invalid_request · evidence: [BE-24-retest.txt](evidence/2026-09-24-01/BE-24-retest.txt)

#### BE-25 — place_stock_order sends a pair to the FX venue unless told otherwise  [FAIL · low · **VERIFIED**]

- Section: `backend`
- Steps: Read place_stock_order's registered signature (TOOLS.md) and its default venue
- Expected: exchange defaults to oanda, the only connector that trades currency pairs
- Observed: exchange defaults to 'alpaca': a live place_stock_order('EURUSD', ...) without an exchange goes to Alpaca, which trades stocks only (every other order tool defaults to oanda)
- Evidence: [BE-25.txt](evidence/2026-09-24-01/BE-25.txt)
- Fix: place_stock_order's exchange defaults to oanda
  - Files: `app/tools/execution.py`
  - Commit: `ce78cbb`
  - Regression test: tests/test_order_path.py::test_every_order_tool_defaults_to_the_fx_venue
- Retest 1 (2026-09-24T12:12:19+00:00): **PASS** — place_stock_order's registered signature now reads exchange="oanda", like place_forex_order and pre_trade_check · evidence: [BE-25-retest.txt](evidence/2026-09-24-01/BE-25-retest.txt)

#### BE-30 — validate_trade_risk does not promise a confirmation the order path never asks for  [FAIL · low · **VERIFIED**]

- Section: `backend`
- Steps: 200,000 USD account; validate_trade_risk buy EURUSD 8,835 USD; then place_market_order EURUSD buy 8000 in auto mode
- Expected: The verdict describes what will happen
- Observed: The verdict says 'Trade looks safe but requires manual confirmation.' (needs_confirmation: true over 5,000 USD), yet in auto mode the order executes immediately; nothing reads needs_confirmation
- Evidence: [BE-27.txt](evidence/2026-09-24-01/BE-27.txt)
- Fix: The over-$5,000 verdict says it is advisory and points at approve_each
  - Files: `core/risk.py`
  - Commit: `eed8f6f`
  - Regression test: tests/test_research_tools.py::test_a_large_trade_verdict_does_not_promise_a_confirmation
- Retest 1 (2026-09-24T13:03:35+00:00): **PASS** — The verdict now reads 'Trade looks safe. It is over $5,000: consider EXECUTION_APPROVAL_MODE=approve_each to approve such trades.' - no promise of a confirmation the auto-mode order path does not ask for · evidence: [BE-30-retest.txt](evidence/2026-09-24-01/BE-30-retest.txt)

#### BE-31 — The API's WebSocket answers only the dashboard's origins  [FAIL · low · **VERIFIED**]

- Section: `backend`
- Steps: WebSocket upgrade to /ws with Origin https://evil.example and http://localhost:3000
- Expected: 101 for the dashboard, 403 for a foreign page (as the HTTP routes' CORS policy)
- Observed: Both upgrade (HTTP 101): CORS middleware does not cover WebSockets, so any web page the operator visits can subscribe to the tick stream. Found by the independent review
- Evidence: [CF-07.txt](evidence/2026-09-24-01/CF-07.txt)
- Fix: /ws closes (1008) a browser connection whose Origin is not in API_CORS_ORIGINS
  - Files: `app/api_server.py`
  - Commit: `eed8f6f`
  - Regression test: tests/test_order_path.py::test_a_web_page_elsewhere_cannot_open_the_websocket
- Retest 1 (2026-09-24T13:04:39+00:00): **PASS** — A WebSocket upgrade from https://evil.example is refused (HTTP 403); the dashboard's origin still upgrades (101) · evidence: [BE-31-retest.txt](evidence/2026-09-24-01/BE-31-retest.txt)

#### CF-05 — A malformed optional setting does not stop the server; a malformed LEVERAGE is named  [FAIL · low · **VERIFIED**]

- Section: `config`
- Steps: Start the MCP server with LEVERAGE=abc, LEVERAGE=0, CIRCUIT_BREAKER_PCT=7%, RATE_LIMIT_DEFAULT_PER_MIN=lots, MARKETDATA_MAX_AGE_MS=30s; call get_paper_account
- Expected: Settings no check applies are ignored with their defaults; a bad LEVERAGE (it sets paper margin) refuses to start with a message naming LEVERAGE
- Observed: CIRCUIT_BREAKER_PCT=7% and RATE_LIMIT_DEFAULT_PER_MIN=lots (neither is applied anywhere) crash the server at import; LEVERAGE=abc crashes with "invalid literal for int()" instead of naming the setting; LEVERAGE=0 is refused with a clear message; MARKETDATA_MAX_AGE_MS=30s falls back correctly
- Evidence: [CF-05.txt](evidence/2026-09-24-01/CF-05.txt)
- Fix: Unapplied numeric settings parse leniently (_unapplied_number); FxPaperAccount names LEVERAGE for any value that is not a positive number
  - Root cause: int()/float() at import on settings no check uses
  - Files: `app/core/config.py`, `core/fx_account.py`
  - Commit: `5d4d9a9`
  - Regression test: tests/test_switches.py, tests/test_fx_account.py
- Retest 1 (2026-09-24T11:49:48+00:00): **PASS** — CIRCUIT_BREAKER_PCT=7% and RATE_LIMIT_DEFAULT_PER_MIN=lots: the server starts and answers; LEVERAGE=abc and LEVERAGE=0 refuse to start with 'LEVERAGE must be a positive number, got ...' · evidence: [CF-05-retest.txt](evidence/2026-09-24-01/CF-05-retest.txt)

#### CF-06 — No secrets in the published history; local secrets and environments are ignored  [FAIL · low · **VERIFIED**]

- Section: `config`
- Steps: Scan every branch and remote commit for key-shaped strings and committed .env files; check .gitignore against the README's install steps
- Expected: No secrets; .env, data/ and the virtualenv the README creates are ignored
- Observed: 25 commits: no key-shaped strings, no .env ever committed; .env and data/ are ignored. .venv/ (created by the README's install step) is not ignored, so 'git add -A' would commit the virtualenv, including third-party test keys
- Evidence: [CF-06.txt](evidence/2026-09-24-01/CF-06.txt)
- Fix: Added .venv/ to .gitignore
  - Files: `.gitignore`
  - Commit: `fc3e08f`
- Retest 1 (2026-09-24T11:52:42+00:00): **PASS** — No key-shaped strings or .env in any published commit; .venv/ no longer shows as untracked · evidence: [CF-06-retest.txt](evidence/2026-09-24-01/CF-06-retest.txt)

#### CF-07 — ALLOW_BROKERAGE_SYMBOLS accepts a pair in any spelling  [FAIL · low · **VERIFIED**]

- Section: `config`
- Steps: Live-order policy with ALLOW_BROKERAGE_SYMBOLS set to 'EUR/USD', 'eurusd', 'EURUSD'; order EURUSD
- Expected: All three allow EURUSD (the README says EUR/USD and EURUSD match the same entry)
- Observed: 'EUR/USD' refuses the EURUSD order (symbol_not_allowed): only the order's spelling is normalised, not the allowlist's. env.example also says no FOREX tool uses ALLOW_BROKERAGE_MARKET_TYPES, but every live order is checked against it (market type 'spot'). Found by the independent review
- Evidence: [CF-07.txt](evidence/2026-09-24-01/CF-07.txt)
- Fix: Policy normalises allowlist entries and orders the same way; env.example explains ALLOW_BROKERAGE_MARKET_TYPES
  - Files: `core/policy.py`, `env.example`
  - Commit: `eed8f6f`
  - Regression test: tests/test_order_path.py::test_the_symbol_allowlist_accepts_any_spelling
- Retest 1 (2026-09-24T13:04:25+00:00): **PASS** — ALLOW_BROKERAGE_SYMBOLS written EUR/USD, eurusd or EURUSD all allow the EURUSD order; env.example explains ALLOW_BROKERAGE_MARKET_TYPES (spot) · evidence: [CF-07-retest.txt](evidence/2026-09-24-01/CF-07-retest.txt)

#### DOC-04 — The README's paper laboratory and feature guide work when followed literally  [FAIL · low · **VERIFIED**]

- Section: `docs`
- Steps: Over MCP: deposit 100,000 USD, get_stock_price, get_multiple_prices, calendar, brief, validate_trade_risk, place_market_order('EUR/USD','buy',10000), a USDJPY short, get_paper_account, get_market_regime, fetch_ohlcv + the backtest example, reset
- Expected: Every documented call succeeds as described
- Observed: All calls answer as documented (regime fields, backtest pnl_percent/total_trades/trades_log, short opens, reset clears) except the README's own order example: place_market_order('EUR/USD','buy',10000) after the documented 100,000 USD deposit is risk_blocked, 'Position size too large (11.4%)', because 10,000 EUR is about 11,370 USD
- Evidence: [DOC-04.txt](evidence/2026-09-24-01/DOC-04.txt)
- Fix: README order examples use 4,000 EUR (about 4.5% of the documented account)
  - Files: `README.md`
  - Commit: `2344713`
- Retest 1 (2026-09-24T12:14:47+00:00): **PASS** — Followed literally: the 4,000 EURUSD buy fills (margin 151.62), the USDJPY short opens, get_paper_account shows both, every other documented call answers as described, reset clears the account · evidence: [DOC-04-retest.txt](evidence/2026-09-24-01/DOC-04-retest.txt)
- Retest 2 (2026-09-24T13:08:51+00:00): **PASS** — Every documented call answered data (none an error), including get_economic_calendar with this week's events (it was rate-limited in the first retest); the 4,000 EURUSD buy fills, the USDJPY short opens, reset clears the account · evidence: [DOC-04-retest-2.txt](evidence/2026-09-24-01/DOC-04-retest-2.txt)

#### FE-03 — Navigation links lead to pages  [FAIL · low · **VERIFIED**]

- Section: `frontend`
- Steps: read the dashboard layout's links; list the app routes
- Expected: every link has a page
- Observed: Strategy (/strategy), History (/history) and Settings (/settings) link to routes that do not exist (the build lists only / and /_not-found)
- Evidence: [FE-01.txt](evidence/2026-09-24-01/FE-01.txt)
- Fix: nav links without pages removed
  - Root cause: links to routes that were never built
  - Files: `frontend/src/app/layout.tsx`
  - Commit: `a065ac4`
- Retest 1 (2026-09-24T11:38:32+00:00): **PASS** — The rendered dashboard links only to / (plus favicon); layout.tsx has one nav link, Dashboard -> /. No links to pages that do not exist. · evidence: [FE-03-retest.txt](evidence/2026-09-24-01/FE-03-retest.txt)

#### FE-06 — P&L figures never show a negative zero  [FAIL · low · **VERIFIED**]

- Section: `frontend`
- Steps: The same phone-width capture: a USDJPY short marked at its entry rate
- Expected: $0.00
- Observed: The flat short's unrealized P&L renders as '-$0.00' (in green): the API returns -0.0 and the formatter keeps the sign
- Evidence: [FE-05-retest-mobile.png](evidence/2026-09-24-01/FE-05-retest-mobile.png)
- Fix: usd() rounds sub-cent values to 0 before formatting
  - Files: `frontend/src/app/page.tsx`
  - Commit: `37901e9`
- Retest 1 (2026-09-24T12:21:19+00:00): **PASS** — The rebuilt dashboard shows the flat USDJPY short as $0.00; no '-$0.00' anywhere in the rendered page · evidence: [FE-06-retest-2.txt](evidence/2026-09-24-01/FE-06-retest-2.txt)

#### ME-01 — Insight fields are validated (signal bullish/bearish/neutral, confidence 0..1)  [FAIL · low · **VERIFIED**]

- Section: `memory`
- Steps: post_market_insight signal=sideways-ish confidence=7.5, then get_latest_insights
- Expected: invalid_request
- Observed: stored and served back to other agents as a 750%-confidence 'sideways-ish' insight
- Evidence: [BE-13.txt](evidence/2026-09-24-01/BE-13.txt)
- Fix: post_market_insight validates signal, confidence and ttl
  - Root cause: no validation
  - Files: `app/tools/research.py`
  - Commit: `33bf5e1`
  - Regression test: tests/test_research_tools.py
- Retest 1 (2026-09-24T11:23:13+00:00): **PASS** — sideways-ish / 7.5 refused with invalid_request; nothing stored · evidence: [BE-13-retest.txt](evidence/2026-09-24-01/BE-13-retest.txt)

#### REG-03 — The operator switches answer first; a refusal for an unreadable live account says why  [FAIL · low · **VERIFIED**]

- Section: `regression`
- Expected: With LIVE_TRADING_ENABLED off or TRADING_HALTED set, a live order is refused as such; a refusal because the brokerage cannot be read names the brokerage's reason.
- Observed: Regression sweep: with LIVE_TRADING_ENABLED=false (or TRADING_HALTED=true) and no OANDA keys, place_forex_order answers brokerage_not_configured (it answered live_trading_disabled / trading_halted before BE-26 moved the brokerage check first), so a kill-switch test reads as a configuration problem; IN-04's SELL against OANDA with a bogus token is refused 'Could not read the account's equity (oanda)' with OANDA's reason swallowed.
- Evidence: [REG-03.txt](evidence/2026-09-24-01/REG-03.txt)
- Fix: place_stock_order checks live_execution_refusal() first in live mode; _live_equity returns (equity, why) and the equity refusal carries why.
  - Root cause: BE-26 put the brokerage-configured check before the operator switches, and _live_equity returned None without the exception text.
  - Files: `app/tools/execution.py`, `docs/ERRORS.md`, `CHANGELOG.md`, `tests/test_market_guard.py`
  - Commit: `f875f5ab`
  - Regression test: tests/test_uat_review_2026_09_24.py::test_the_operator_switches_answer_before_the_brokerage_configuration; tests/test_uat_review_2026_09_24.py::test_an_unreadable_live_account_is_refused_with_the_brokerages_reason
- Retest 1 (2026-09-25T11:03:04+00:00): **PASS** — No keys: LIVE_TRADING_ENABLED=false answers live_trading_disabled and TRADING_HALTED=true answers trading_halted again; against OANDA with a bogus token both orders are refused before anything is sent, with OANDA's own reason ('HTTP 400: Invalid value specified for accountID'). · evidence: [REG-03-retest.txt](evidence/2026-09-24-01/REG-03-retest.txt)

#### XR-12 — API responses and logs identify each request  [FAIL · low · **VERIFIED**]

- Section: `backend`
- Observed: Two approvals log the same request_id and ts_ms (fixed at import); responses carry no security headers.
- Evidence: [XR-12.txt](evidence/2026-09-24-01/XR-12.txt)
- Fix: request_context middleware: per-request X-Request-ID (in the log lines), security headers, JSON 500 naming only the request id; log_event stamps ts_ms per line.
  - Root cause: The API logged with one context built at import (fixed request_id and ts_ms) and set no security headers.
  - Files: `app/api_server.py`, `observability/logging.py`
  - Commit: `4f72e15d`
  - Regression test: tests/test_uat_review_2026_09_24.py::test_api_responses_carry_a_request_id_and_hide_internal_errors; tests/test_uat_review_2026_09_24.py::test_each_log_line_carries_its_own_time
- Retest 1 (2026-09-24T21:51:20+00:00): **PASS** — GET /api/health carries X-Request-ID, nosniff, DENY, no-referrer, no-store; two approvals log different request_ids and ts_ms; the internal-error and per-line time tests pass. · evidence: [XR-12-retest.txt](evidence/2026-09-24-01/XR-12-retest.txt)

#### XR-13 — Odd numeric inputs are refused  [FAIL · low · **VERIFIED**]

- Section: `backend`
- Observed: Two deposits of 1.7e308 make equity inf and the loss metrics NaN, after which BUY 1e15 EURUSD executes; True is accepted as amount 1; sentiment_score NaN is read as +1.0.
- Evidence: [XR-13.txt](evidence/2026-09-24-01/XR-13.txt)
- Fix: Deposits capped at 1e12 USD (cash at 1e15); tool numbers typed Number (booleans refused before conversion); non-finite sentiment_score refused.
  - Root cause: Deposits had no upper bound (inf equity); MCP argument validation turned true into 1.0; a NaN sentiment read as +1.0.
  - Files: `core/fx_account.py`, `app/tools/trading.py`, `app/tools/execution.py`
  - Commit: `4f72e15d bcf733b8`
  - Regression test: tests/test_uat_review_2026_09_24.py::test_odd_numbers_are_refused; tests/test_uat_review_2026_09_24.py::test_an_mcp_client_cannot_send_true_as_a_number
- Retest 1 (2026-09-24T21:51:20+00:00): **PASS** — Deposits of 1.7e308 are refused (cap 1e12), metrics stay finite, BUY 1e15 is refused (empty account); true for any amount/price/value is refused by MCP argument validation on every tool and mode; sentiment_score NaN -> invalid_request. · evidence: [XR-13-retest-2.txt](evidence/2026-09-24-01/XR-13-retest-2.txt)

#### XR-14 — The Smithery listing offers only settings that work there  [FAIL · low · **VERIFIED**]

- Section: `config`
- Observed: smithery.yaml offers EXECUTION_APPROVAL_MODE=approve_each, but a Smithery-launched server has no API process to approve proposals, so every order becomes a proposal that can only expire.
- Evidence: [XR-14.txt](evidence/2026-09-24-01/XR-14.txt)
- Fix: EXECUTION_APPROVAL_MODE is no longer offered; commandFunction passes only the listed settings and sets 'auto'.
  - Root cause: The listing offered approve_each, but a Smithery launch has no approval API, so every order became a proposal that could only expire.
  - Files: `smithery.yaml`
  - Commit: `4f72e15d`
  - Regression test: tests/test_uat_review_2026_09_24.py::test_the_smithery_listing_offers_only_settings_that_work_there
- Retest 1 (2026-09-24T21:51:20+00:00): **PASS** — smithery.yaml no longer offers EXECUTION_APPROVAL_MODE; its commandFunction (evaluated with node) passes only the listed keys and 'auto' even when approve_each or an unknown key is entered; the server it starts executes a paper order instead of making a proposal. · evidence: [XR-14-retest.txt](evidence/2026-09-24-01/XR-14-retest.txt)

#### IN-05 — A real order round trip on an OANDA practice account  [BLOCKED · **BLOCKED**]

- Section: `integrations`
- Steps: PAPER_MODE=false LIVE_TRADING_ENABLED=true OANDA_ENVIRONMENT=practice with a practice token; place_forex_order EURUSD buy 1000 then sell 1000; check the practice account
- Expected: Both orders fill on the practice account; sizing reads the practice NAV
- Observed: Needs an OANDA practice (demo) account token: set OANDA_API_KEY and OANDA_ACCOUNT_ID for a practice account (free at oanda.com) and run the steps; no real money is involved. The failure path against the same API is verified in IN-04.
- Blocked on: An OANDA practice (demo) account token: OANDA_API_KEY + OANDA_ACCOUNT_ID for a practice account, with PAPER_MODE=false, LIVE_TRADING_ENABLED=true, OANDA_ENVIRONMENT=practice.
- Evidence: [IN-04-retest.txt](evidence/2026-09-24-01/IN-04-retest.txt)

### Passed checks (11)

| ID | Section | Check | Observed |
|---|---|---|---|
| PRE-04 | preflight | Test-suite baseline and the README's two demos | 224 passed; both demos exit 0 (the stress demo then points the user at an MCP tool that is not registered, see BE) |
| DA-01 | data | Paper account, trades and insights survive a restart; free text round-trips unchanged | After restart: cash 50,000, EURUSD +2,000 @ 1.13740, margin 75.83; the insight and the stored trade rationale are identical, including curly quotes, em dash, <b>/<img onerror> (stored as text) and CJK |
| FE-01 | frontend | Dashboard installs, lints and builds (npm ci, lint, build) | npm ci, lint and build succeed |
| FE-04 | frontend | With the API stopped the dashboard says so instead of spinning | The Paper Account card shows 'The API is not reachable at http://localhost:8000. Start it with: python app/api_server.py'; no 'Loading' remains (the failed requests are to the stopped API) |
| DOC-03 | docs | docker build and docker run from the README produce a working MCP server | Unblocked (a Docker daemon now runs in the sandbox). docker build -t readytrader-forex . succeeds (sandbox proxy CA added by a shim only); the image runs as readytrader (uid 10001) and holds no .env/key/db/log/frontend/.venv/.git. docker run --rm -i -v readytrader-forex-data:/app/data readytrader-forex answers an MCP client with 29 tools; a deposit made in one container is there in the next (cash 2,000 after two probe runs); the API sidecar from the Dockerfile comment answers /api/health and /api/portfolio from the same volume. |
| REG-01 | regression | Regression sweep: every verified check re-run after all fixes | All 28 exit 0. 20 identical after masking; the rest differ only by later, intended changes (get_multiple_prices 'errors' field, env.example rewrite, 29 tools instead of 27, new tests in the CI run), by state left in a shared probe database (BE-01), or by live headlines/rates; DOC-04's calendar call, rate-limited in its retest, answered with this week's events |
| REG-02 | regression | Every CI step passes on the final tree | ruff clean, 429 tests pass, bandit clean, the dashboard installs, lints and builds |
| REG-04 | regression | Regression sweep after the cross-repo fixes: every verified check re-run | All 25 exit 0 (code at 6de3f123). 12 identical after masking; the rest differ only by intended changes: new response fields (exposure_added_units, reference_price, inactive_rules for live orders, the pending list's order details from BE-28), smithery's config keys without EXECUTION_APPROVAL_MODE (XR-14), the build context without frontend/ (XR-11) and a Docker daemon now present, the env scan (ALLOW_BROKERAGE_MARKET_TYPES now listed), and ForexFactory answering 429 this time (CL-01/IN-01/IN-02: reported as source_unavailable, as designed). BE-05 and IN-04 showed the switch-order and swallowed-reason problem fixed in REG-03 (f875f5ab), which touched only the live refusal order and its message. |
| REG-05 | regression | Every CI step passes on the final tree | HEAD f875f5ab: ruff clean, 453 tests pass, bandit clean, the dashboard installs, lints and builds. |
| REG-06 | regression | Regression sweep after the AR fixes: the API, order path, dashboard and docs walk re-run | 12 re-run (code at fc571242), all exit 0; 8 identical after masking. BE-01 differs only where its 420-character truncation falls (number widths); BE-05 shows the REG-03 switch order (live_trading_disabled / trading_halted); BE-09 only a request id's width; DOC-04 the calendar's current week. The dashboard sweeps (FE-02, FE-05) and the API edge cases (BE-23) are unchanged with the token check moved into the routes. |
| REG-07 | regression | Every CI step passes on the final tree | HEAD fc571242: ruff clean, 461 tests pass, bandit clean, the dashboard installs, lints and builds. |

### Run notes

- 2026-09-24T11:05:27+00:00: section frontend: N/A cleared
- 2026-09-24T13:11:03+00:00: Independent review (a separate agent given only the repo, the branch and uat/UAT-LOG.md): it re-opened every VERIFIED check's retest evidence, walked the tool/route/page/script surface for gaps, and read the branch's diff for fixes that broke something. It found 5 defects the run had missed - exits sized as new exposure and shorts trapped by BUY-only limits (BE-26), live SELLs unsized without equity (BE-27), paper proposals executable by a live API (BE-28), validate_trade_risk accepting malformed input (BE-29), a misleading large-trade verdict (BE-30) - plus the allowlist spelling (CF-07), the WebSocket origin (BE-31) and blind approvals on the dashboard (FE-07); all fixed and retested. It flagged weak retest evidence for BE-09, BE-12, BE-23, CF-03, CF-04, DOC-04 and FE-05: each now has a stronger fresh capture (or a note), and the BE-09 regression test now runs the file as the README does. Not changed, stated in the PR: live-mode /api/portfolio answers 200 with an 'error' field (the live view is not implemented), and the Live Markets dot means 'WebSocket connected', not 'stream running'.

---
