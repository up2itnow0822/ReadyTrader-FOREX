# Error Catalog & Troubleshooting

Every tool answers `{"ok": true, "data": ...}` or `{"ok": false, "error": {"code", "message", "data"}}`.
The `code` is stable; the `message` says what happened in words; `data` carries the numbers
(limits, rates, the market guard's `market` reading). The approval API (`/api/approve-trade`)
answers a refusal with HTTP `409` and the same `code` in `detail`; an unknown proposal answers
`404`, a wrong `confirm_token` `403`, and an expired, cancelled or already-approved proposal `409`
with the reason as text. With `API_OPERATOR_TOKEN` set, a call without `Authorization: Bearer
<it>` answers `401` `operator_token_required`; approving a live proposal while it is not set answers
`403` `operator_token_required`. An error inside the API answers `500` `internal_error` naming only
the request's `X-Request-ID` (the details are in the API log); a brokerage that refuses an approved
live order answers `502` `execution_error` with the brokerage's reason.

| Issue | Potential Fix |
| :--- | :--- |
| **Missing .env** | Paper mode needs none. `python tools/setup_wizard.py` offers to copy `env.example` to `.env`. |
| **Missing news/social keys** | See `docs/SENTIMENT.md` for which tool needs which key; the calendar and `get_forex_news` need none. |
| **Blocked trade** | Read the error `code` below. `risk_blocked` gives the Risk Guardian's reason. |
| **Dependency error** | Use Python 3.12+ and `pip install -r requirements.txt`. |

---

## Error codes

### Risk
- `risk_blocked`: the Risk Guardian refused the trade. The message is the reason: new exposure
  worth over 5% of equity (valued at the market, never at a price the order carries alone), the 5%
  daily-loss or 10% drawdown limit (orders that add exposure; paper account only), the
  Falling Knife rule (BUYs that add exposure), the volatility halt (every side), your own
  `sentiment_score` below -0.5, or an account, rate or market price the check could not read,
  including a paper position that cannot be priced now (an order that adds exposure then fails
  closed). Orders that only reduce or close a position pass every rule but the
  volatility halt. `data` of a refused order includes `position_units`, `exposure_added_units` and
  `reference_price`. `data.market` has the market guard's reading and `data.inactive_rules` lists
  the rules that did not run (the news blackout; on live orders, the daily-loss and drawdown
  limits). An executed order lists them too.
- `risk_validation_error`: the risk check itself raised; the message has the exception.

### Requests
- `invalid_request`: a malformed request, e.g. a side other than buy/sell, a non-positive,
  non-finite or non-numeric amount, a non-finite `sentiment_score`, a deposit over
  1e12 USD (or cash over 1e15), an order type other than market/limit, a limit with no positive price, a
  paper order for something that is not a currency pair, a deposit that is not positive USD, an
  empty `get_multiple_prices` list, a `validate_trade_risk` call without a buy/sell side or with a
  non-positive amount or portfolio value, or an insight outside the documented fields.
- Arguments of the wrong type (text that is not a number, or `true`/`false` for an amount, price,
  value or score) are refused by the MCP argument validation before the tool runs: the client gets
  a tool error naming the argument, not this envelope.
- `invalid_mode`: `get_paper_account`, `deposit_paper_funds` or `reset_paper_account` called in
  live mode.

### Live trading switches and policy
- `live_trading_disabled`: `PAPER_MODE=false` but `LIVE_TRADING_ENABLED` is not `true`.
- `trading_halted`: the kill switch `TRADING_HALTED` is set.
- `exchange_not_allowed`, `symbol_not_allowed`: outside `ALLOW_EXCHANGES` /
  `ALLOW_BROKERAGE_SYMBOLS` (`EUR/USD` and `EURUSD` match the same entry).
- `order_amount_too_large`: more base-currency units than `MAX_BROKERAGE_ORDER_AMOUNT`.
- `invalid_policy_config`: `MAX_BROKERAGE_ORDER_AMOUNT` is not a number; every live order is
  refused until it is fixed or unset.

These are checked when a live order is placed or proposed, and again when a proposal is approved.
The switches (`live_trading_disabled`, `trading_halted`) answer before anything else, even an
unconfigured brokerage. When the brokerage account cannot be read, `risk_blocked` for an order that
adds exposure carries the brokerage's own reason (e.g. OANDA's `HTTP 401: Insufficient
authorization`).

### Execution
- `brokerage_not_supported`: an `exchange` that is not registered (oanda, ibkr, alpaca, tradier,
  schwab, etrade, robinhood). The message lists them.
- `brokerage_not_configured`: that brokerage's keys are not set; no order was sent.
- `execution_error`: the paper account or the brokerage raised; the message has its reason.
- `limit_not_marketable`: (paper) a limit BUY below / SELL above the market; resting orders are
  not simulated.
- `insufficient_margin`: (paper) the order needs more margin than the account has free.
- `mode_mismatch`: (approval API) the proposal was made in paper mode and the API runs live, or the
  reverse; nothing was executed.
- `market_data_error`: (paper) no rate to fill the order at, or to value the account; retry.

### Market data, news and research
- `fetch_price_error`: `get_stock_price` could not read a rate.
- `fetch_ohlcv_error`: candles could not be read.
- `not_configured`: a news or social tool whose key is missing (the message names it).
- `source_unavailable`: a calendar, news or social source did not answer (never reported as "no
  events" or "no news").
- `backtest_error`: the strategy did not compile, had no `on_candle`, or raised.
- `stress_test_error`, `market_regime_error`: those tools failed; the message says why.

### Not available
- `not_implemented`: `start_brokerage_private_ws` in live mode (private order streams are not
  implemented; poll the brokerage instead).
- `paper_mode_not_supported`: the same tool in paper mode.