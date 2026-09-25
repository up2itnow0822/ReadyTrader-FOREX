## ReadyTrader-FOREX Runbook

Two processes make up a deployment:

- **The MCP server** (`python app/main.py`, stdio): the tools your agent calls. An MCP client
  launches it; it has no port.
- **The API server** (`python app/api_server.py`, `127.0.0.1:8000` by default): health, the paper
  account, pending approvals and the approval endpoint the dashboard uses. Only needed for
  `approve_each` and the dashboard.

Every setting is read when a process starts, so **restart both processes after changing `.env`**.

### Common operations

#### Check that it is up
- MCP server: in your client, list the tools (29 are registered; see `docs/TOOLS.md`), or call
  `get_stock_price("EURUSD")` and `get_paper_account()`.
- API server: `curl -s 127.0.0.1:8000/api/health` returns `{"status": "ok", "mode": "paper"}`
  (or `"live"`).
- Environment: `python tools/setup_wizard.py` checks the dependencies, the FX data sources and
  the keys it finds.

#### Kill switch (live trading)
- Set `TRADING_HALTED=true` (any value other than empty, `false`, `0`, `no` or `off` halts) and
  restart both processes. Every live order, and every approval of one, is then refused with
  `trading_halted`, closing orders included: the server cannot flatten a position while halted,
  so close positions on the OANDA platform (web or app). Nothing the server sent keeps trading
  behind the switch: every OANDA order is fill-or-kill, so no order of its rests at the broker.
  Paper trading is unaffected.
- To stop live trading entirely, set `PAPER_MODE=true` or `LIVE_TRADING_ENABLED=false` and restart.

#### Approve trades (`EXECUTION_APPROVAL_MODE=approve_each`)
- Start both processes with the same `EXECUTION_DB_PATH` and `EXECUTION_SESSION_ID`; without them
  the API cannot see the MCP server's proposals.
- Set `API_OPERATOR_TOKEN` for the API process (not the MCP server): the agent holds each
  proposal's `confirm_token`, so a live proposal is approved only with this operator secret, and
  every `/api/` call but `/api/health` needs `-H "Authorization: Bearer $API_OPERATOR_TOKEN"`.
- `curl -s -H "Authorization: Bearer $API_OPERATOR_TOKEN" 127.0.0.1:8000/api/pending-approvals`
  lists proposals (they expire after 120 s).
- Approve: `POST /api/approve-trade` with `{"request_id", "confirm_token", "approve": true}`; the
  agent received the `confirm_token` with the proposal. The Risk Guardian (with fresh daily bars),
  the kill switch and the live policy are checked again before anything executes; a refusal
  answers `409` with its `code` (`mode_mismatch` if the proposal was made in the other mode), an
  unknown proposal `404`, a wrong token `403`, a missing operator token `401` (or `403
  operator_token_required` for a live proposal when `API_OPERATOR_TOKEN` is not set).
- Cancel: the same call with `"approve": false` (the `confirm_token` is required here too).
- The dashboard (`frontend/`) does the same from a browser at `http://localhost:3000`. Other
  browser origins are refused unless listed in `API_CORS_ORIGINS`.

#### Rotate brokerage credentials
- Update `OANDA_API_KEY` / `OANDA_ACCOUNT_ID` (or the other brokerage variables in
  `env.example`), then restart. Keys live only in the environment; nothing is written to disk.

#### Debug a refused or failed order
- Every tool answers `{"ok": false, "error": {"code", "message", "data"}}` on failure; the codes
  are listed in `docs/ERRORS.md`. `risk_blocked` carries the Risk Guardian's reason, the market
  guard's `market` reading and the rules that are not active (`inactive_rules`).
- The API server writes one JSON log line per event to stdout (`api_server_started`,
  `api_approval_risk_blocked`, ...), each with its own `ts_ms` and the `request_id` of the request
  it belongs to (returned as the `X-Request-ID` header; an internal error answers `500` naming only
  that id); set `LOG_LEVEL=DEBUG` for more. The MCP server keeps stdout
  for the protocol and does not log there.

---

### Incident playbooks

#### 1) Orders refused with `risk_blocked`
- **Read the reason** in the error. Common ones:
  - `Position size too large`: the part of the order that opens or adds to a position is more than
    5% of the account's equity (paper equity, or the brokerage's reported equity in live mode).
    Reducing or closing a position is never refused by this rule. Reduce the size.
  - `Daily Loss Limit Hit` / `Max Drawdown` (paper account only): trading lost 5% today or is 10%
    below its best level, measured on trading results (a deposit is neither a gain nor a loss, and
    does not end a halt). "Today" starts from the account's last recorded value of the previous UTC
    day (a trade, a deposit or the first check of a day records one), else its first value today: a
    move made after a day's last record counts toward the next day's loss too, which errs toward
    halting. Orders that add exposure (long or short) resume when the
    condition clears; orders that reduce or close a position are allowed. A live account has no
    loss history here, so these two rules do not run on live orders (`inactive_rules` lists them):
    watch its losses at OANDA and use the kill switch.
  - `Could not read the account's equity (paper) for the position-size check (a position cannot
    be priced now)`: a paper position has no current rate, so its loss cannot be measured; orders
    that add exposure (and deposits) wait until it can be priced. `... (the paper account is empty:
    deposit_paper_funds first)` means just that.
  - Falling Knife: the pair fell 5%+ over four daily closes and is still at its low; BUYs that add
    exposure only (buying back a short is an exit).
  - Volatility Halt: today's move is more than 4.5x the pair's 20-day norm. Every trade on that
    pair, SELLs included, is refused until the move subsides; close urgent positions through the
    broker. See `docs/FALLING_KNIFE.md`.
  - `Could not value` / `equity`: the check could not price the order in USD or read the
    account, so it refused an order that adds exposure (fail closed). In live mode the position is
    read from the brokerage; if it cannot be read, every order counts as adding exposure. Check the
    brokerage keys and the network.

#### 2) Market data unavailable (yfinance)
- **Symptoms**: `fetch_price_error` / `fetch_ohlcv_error`, or a market guard `market.status` of
  `unavailable` or `stale`.
- **Behaviour**: in live mode a BUY is refused while the daily bars cannot be read (unless
  `MARKET_GUARD_ON_DATA_ERROR=allow`); SELLs are not refused for missing data.
- **Mitigation**: wait for the provider to recover. Yahoo rate-limits bursts; bars are cached for
  `OHLCV_CACHE_TTL_SEC` (60 s) and rates for `TICKER_CACHE_TTL_SEC` (5 s).

#### 3) Calendar or news sources failing
- **Symptoms**: `source_unavailable` from `get_economic_calendar`, `get_forex_news` or the other
  news tools; `not_configured` when a key is missing.
- **Behaviour**: a source that cannot answer is never reported as "no events". The calendar is
  cached for `CALENDAR_CACHE_TTL_SEC` (900 s) and, when a refresh is refused, the last read (up to
  6 hours old) is served with its time.

#### 4) Brokerage outage or rejected order
- **Symptoms**: `execution_error` with the brokerage's message, or `brokerage_not_configured`.
- **Mitigation**: set `TRADING_HALTED=true` and restart while the brokerage recovers; check the
  order and positions with the brokerage directly. This server does not cancel or list brokerage
  orders.

#### 5) Live policy refusals
- **Symptoms**: `symbol_not_allowed`, `exchange_not_allowed`, `order_amount_too_large` or
  `invalid_policy_config`.
- **Triage**: the error data names the rule and its limit. `invalid_policy_config` means
  `MAX_BROKERAGE_ORDER_AMOUNT` is not a number; every live order is refused until it is fixed or
  unset.
- **Mitigation**: adjust `ALLOW_BROKERAGE_SYMBOLS`, `ALLOW_EXCHANGES` or
  `MAX_BROKERAGE_ORDER_AMOUNT` and restart. Keep `EXECUTION_APPROVAL_MODE=approve_each` while
  validating a new configuration.

### Upgrading a Docker data volume
- Images before this release ran as root; this one runs as `readytrader` (uid 10001), which cannot
  write files a root container left in an existing volume (`attempt to write a readonly
  database`). Hand the volume to the new user once, then start as usual:
  `docker run --rm --user 0 -v readytrader-forex-data:/app/data --entrypoint chown readytrader-forex -R 10001:10001 /app/data`

### Backup/restore (paper mode)
- The paper account is `data/paper.db` (`PAPER_DB_PATH`; ignored by git; with Docker, the
  `readytrader-forex-data` volume). Back it up by copying the file while the processes are
  stopped. `reset_paper_account()` clears it.