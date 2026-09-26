# Market Data (ReadyTrader-FOREX)

## Where rates come from

Every rate and candle the server uses comes from **yfinance** (Yahoo), through
`marketdata/exchange_provider.py`. A six-letter pair (`EURUSD`, `EUR/USD`) is read as Yahoo's
`EURUSD=X`.

- `get_stock_price(symbol)` and `get_multiple_prices(symbols)`: the latest quote (`price`, and
  `bid`/`ask` where Yahoo gives them), cached for `TICKER_CACHE_TTL_SEC` (5 s).
- `fetch_ohlcv(symbol, timeframe, limit)`: candles, cached for `OHLCV_CACHE_TTL_SEC` (60 s). FX
  volume is usually 0.
- The Risk Guardian values each order at its USD notional from the latest rates (the base currency's USD
  rate: 10,000 EURGBP is 10,000 EUR at EURUSD); paper orders fill at the latest rate;
  the market guard reads the last 40 daily bars (`docs/FALLING_KNIFE.md`).

No brokerage key is needed for market data. Yahoo's FX rates are indicative, not a dealer's
quotes, and Yahoo rate-limits bursts; when a rate cannot be read the tools answer
`fetch_price_error` / `fetch_ohlcv_error`, and a BUY is refused rather than priced on a guess.

## The market-data bus

`get_stock_price`, `get_multiple_prices` and `fetch_ohlcv` go through `MarketDataBus`, which picks
the freshest acceptable source among: ingested websocket ticks (`exchange_ws`, empty unless a
stream is started), plugins you register, and yfinance. Tuning:

- `MARKETDATA_PROVIDER_PRIORITY_JSON`: provider priorities, lower first, e.g.
  `{"exchange_ws": 0, "yfinance": 1}`.
- `MARKETDATA_MAX_AGE_MS` (30000): a quote older than this is stale.
- `MARKETDATA_OUTLIER_MAX_PCT` (20) and `MARKETDATA_OUTLIER_WINDOW_MS` (10000): a quote that jumps
  more than this against the last good one is flagged.
- `MARKETDATA_FAIL_CLOSED=true`: refuse a stale or outlier quote instead of returning it flagged.
- `MARKETDATA_PLUGINS_JSON`: load your own provider at start-up, e.g.

```json
[
  {
    "class": "marketdata.plugin_examples:StaticJsonFileProvider",
    "provider_id": "file_feed",
    "kwargs": { "path": "/data/feed.json" }
  }
]
```

No tool starts a websocket stream in this release, so in practice the bus answers from yfinance.
The API server's `/ws` endpoint forwards ingested ticks and stays silent until a stream exists.
