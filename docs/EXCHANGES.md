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
| `oanda` (default) | Yes | Yes (market FOK, limit GTC) | Yes (account NAV) | `OANDA_API_KEY`, `OANDA_ACCOUNT_ID`; practice API unless `OANDA_ENVIRONMENT=live` | Supported |
| `ibkr`, `alpaca`, `tradier`, `schwab`, `etrade`, `robinhood` | No | Stocks only (the IBKR connector builds stock contracts) | Yes | see `env.example` (Alpaca paper, Tradier sandbox, TWS paper port by default) | Inherited from ReadyTrader-Stocks |

Notes for OANDA:
- Units are whole units of the base currency; a fractional amount is truncated.
- Sizing reads the account's NAV as reported, in the account's currency. The Risk Guardian compares
  it with the order's USD notional, so a non-USD account is sized approximately.

**Test the live path without real money:** with `PAPER_MODE=false` and `LIVE_TRADING_ENABLED=true`,
OANDA orders go to OANDA's practice (demo) API until `OANDA_ENVIRONMENT=live`.

---

## What the server does not do

- Cancel, amend or list brokerage orders, or list positions: manage those with the brokerage.
- Stream private order updates: `start_brokerage_private_ws` answers `not_implemented`.
- Show the live account in the API (`/api/portfolio` is paper-only).
