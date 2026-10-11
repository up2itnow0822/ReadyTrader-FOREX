## ReadyTrader-FOREX — Brokerage Capabilities

A truthful capability matrix. "Supported" means the order path is covered by tests (against a fake
brokerage) and documented; "Experimental" means the connector exists but has not been exercised
against that brokerage in this project's tests. None has been exercised against a live account by
this project: start with OANDA's practice account and `EXECUTION_APPROVAL_MODE=approve_each`.

Live orders go out only with `PAPER_MODE=false` and `LIVE_TRADING_ENABLED=true`, through
`place_market_order` / `place_limit_order` (OANDA) or `place_forex_order` / `place_stock_order`
(`exchange`, default `oanda`). Every live order passes the Risk Guardian (sized by USD notional against
the brokerage's reported equity), the market guard, the kill switch and the live policy
(`ALLOW_EXCHANGES`, `ALLOW_BROKERAGE_SYMBOLS`, `MAX_BROKERAGE_ORDER_AMOUNT`) first. Paper mode
never contacts a brokerage: orders fill in the local paper FX account.

### Market data
Rates and candles come from **yfinance** (Yahoo), not from the brokerage (`docs/MARKETDATA.md`).
No brokerage key is needed for market data.

---

## Capability matrix

| `exchange` | Currency pairs | Market / limit orders | Account equity (for sizing) | Keys (env) | Status |
|-----------|------|--------------|--------------|----------------|-------|
| `oanda` (default) | Yes | Yes (both fill-or-kill: a limit is a market order with a `priceBound`) | Yes (account NAV) | `OANDA_API_KEY`, `OANDA_ACCOUNT_ID`; practice API unless `OANDA_ENVIRONMENT=live` | Supported |
| `ibkr`, `alpaca`, `tradier`, `schwab`, `etrade`, `robinhood` | No | Stocks only (the IBKR connector builds stock contracts) | Yes | see `env.example` (Alpaca paper, Tradier sandbox, TWS paper port by default) | Inherited from ReadyTrader-Stocks |

Notes for OANDA:
- Units are whole units of the base currency; a fractional amount is truncated.
- Every order is fill-or-kill: it fills now or OANDA cancels it (the tool then answers
  `execution_error` with OANDA's reason, e.g. `BOUNDS_VIOLATION` for a limit the market is beyond).
  A limit order is a market order whose `priceBound` is the limit: the worst price it may fill at.
  Nothing rests at OANDA, because the Risk Guardian judges an order against the positions at the
  time it is checked; a resting order could fill later, past the kill switch and every check.
- Orders are sent with `positionFill: REDUCE_FIRST`, netting against the open position as the
  Risk Guardian sizes it. An account that cannot net (some hedging accounts) rejects the order, and
  nothing trades.
- Sizing reads the account's NAV as reported, in the account's currency. The Risk Guardian compares
  it with the order's USD notional, so a non-USD account is sized approximately.

**Test the live path without real money:** with `PAPER_MODE=false` and `LIVE_TRADING_ENABLED=true`,
OANDA orders go to OANDA's practice (demo) API until `OANDA_ENVIRONMENT=live`.

---

## What the server does not do

- Cancel, amend or list brokerage orders, or list positions: manage those with the brokerage.
- Count open orders. At the stock brokerages a limit order can rest (Alpaca `GTC`, Tradier `day`);
  the Risk Guardian sizes each order against the positions at the time it is checked, not against
  open orders, and the kill switch does not cancel them: cancel them at the brokerage.
- Close positions while `TRADING_HALTED` is set: the kill switch refuses closing orders too; flatten
  on the OANDA platform (or the brokerage's own).
- Stream private order updates: `start_brokerage_private_ws` answers `not_implemented`.
- Show the live account in the API (`/api/portfolio` is paper-only).
