import json
from typing import Any, Dict, Optional

from fastmcp import FastMCP

from app.core.container import global_container
from app.tools.params import Integer


def _json_ok(data: Dict[str, Any] | None = None) -> str:
    payload = {"ok": True, "data": data or {}}
    return json.dumps(payload, indent=2, sort_keys=True)


def _json_err(code: str, message: str, data: Dict[str, Any] | None = None) -> str:
    payload = {"ok": False, "error": {"code": code, "message": message, "data": data or {}}}
    return json.dumps(payload, indent=2, sort_keys=True)


def _answer(key: str, value: str, **context: Any) -> str:
    """A source's text as {"ok": true}, or, when the source could not answer (intelligence.core.
    Unavailable), {"ok": false, "error": {"code": "not_configured" | "source_unavailable"}}."""
    from intelligence.core import Unavailable

    if isinstance(value, Unavailable):
        return _json_err(value.code, str(value), context)
    return _json_ok({**context, key: value})


def register_market_tools(mcp: FastMCP):
    @mcp.tool()
    def get_market_sentiment() -> str:
        """The FX backdrop: the 5-day DXY (US dollar index) trend and this week's high-impact calendar. Not a sentiment score."""
        from intelligence import get_market_sentiment

        return _answer("sentiment", get_market_sentiment())

    @mcp.tool()
    def get_market_news() -> str:
        """Top market headlines from Alpha Vantage's news feed (ALPHAVANTAGE_API_KEY required; mostly equities)."""
        from intelligence import get_market_news

        return _answer("news", get_market_news())

    @mcp.tool()
    def get_economic_calendar() -> str:
        """High-impact economic events for the rest of this week (ForexFactory calendar, times in UTC)."""
        from intelligence.core import get_economic_calendar

        return _answer("calendar", get_economic_calendar())

    @mcp.tool()
    def fetch_custom_feed(url: str, keyword: Optional[str] = None) -> str:
        """Fetch headlines from an RSS or Atom feed at a public http(s) URL (local and private addresses are refused)."""
        from intelligence.core import fetch_custom_feed

        return _answer("news", fetch_custom_feed(url, keyword))

    @mcp.tool()
    def fetch_rss_news(symbol: str = "") -> str:
        """Free MarketWatch and Yahoo Finance headlines, optionally filtered by `symbol` (no key)."""
        from intelligence.core import fetch_rss_news

        return _answer("news", fetch_rss_news(symbol))

    @mcp.tool()
    def analyze_social_sentiment(symbol: str) -> str:
        """Recent X and Reddit posts about a pair, as text for you to judge (TWITTER_BEARER_TOKEN / REDDIT_CLIENT_ID+SECRET). Same as get_social_sentiment."""
        from intelligence.core import analyze_social_sentiment

        return _answer("sentiment", analyze_social_sentiment(symbol))

    @mcp.tool()
    def fetch_financial_news(symbol: str) -> str:
        """NewsAPI headlines about a pair (NEWSAPI_KEY required). Same as get_financial_news."""
        from intelligence.core import fetch_financial_news

        return _answer("news", fetch_financial_news(symbol))

    @mcp.tool()
    def get_forex_news(limit: Integer = 10) -> str:
        """Latest FX headlines from free RSS feeds (Investing.com, FXStreet, DailyFX, ForexLive, Reuters).

        Feeds that refuse are listed; ok:false only if none answers. No key needed.
        """
        from intelligence.core import get_forex_news

        return _answer("news", get_forex_news(limit))

    @mcp.tool()
    def get_forex_market_brief(symbol: str = "EURUSD") -> str:
        """One-call FX overview for a pair: latest rate, DXY trend, this week's high-impact calendar and FX headlines (no key)."""
        from intelligence.core import get_forex_market_brief

        return _json_ok({"brief": get_forex_market_brief(symbol)})

    @mcp.tool()
    async def get_stock_price(symbol: str, exchange: str = "") -> str:
        """
        Latest quote for a currency pair (e.g. EURUSD or EUR/USD) or other symbol: price, bid, ask and
        source. Quotes come from the market-data provider (yfinance); `exchange` is accepted for
        compatibility and not used.
        """
        try:
            res = await global_container.marketdata_bus.fetch_ticker(symbol)
            ticker = res.data
            price = ticker.get("last") or ticker.get("close")
            if not price:
                return _json_err("fetch_price_error", f"No price for {symbol}.", {"symbol": symbol})
            # It used to answer with a sentence ("The current price of EURUSD is ...").
            return _json_ok({"symbol": symbol, "price": float(price), "bid": ticker.get("bid"), "ask": ticker.get("ask"), "source": res.source})
        except Exception as e:
            return _json_err("fetch_price_error", str(e), {"symbol": symbol})

    @mcp.tool()
    async def get_multiple_prices(symbols: str) -> str:
        """
        Latest prices for several pairs, comma-separated (e.g. "EURUSD,GBP/USD,USDJPY").

        `prices` maps each symbol to a number, or to null when it could not be priced; `errors`
        gives the reason for each null.
        """
        sym_list = [s.strip().upper() for s in (symbols or "").split(",") if s.strip()]
        if not sym_list:
            return _json_err("invalid_request", "symbols must list at least one symbol, e.g. 'EURUSD,GBPUSD'.")
        prices: dict = {}
        errors: dict = {}
        for sym in sym_list:
            try:
                res = await global_container.marketdata_bus.fetch_ticker(sym)
                last = res.data.get("last") or res.data.get("close")
                prices[sym] = float(last) if last else None
                if not last:
                    errors[sym] = "no price in the quote"
            except Exception as e:
                prices[sym], errors[sym] = None, str(e)
        return _json_ok({"prices": prices, "errors": errors})

    @mcp.tool()
    async def fetch_ohlcv(symbol: str, timeframe: str = "1h", limit: Integer = 24) -> str:
        """
        Historical candles for a pair: timestamp, open, high, low, close, volume (FX volume is often 0).
        `timeframe` such as 1h or 1d; `limit` candles, most recent last.
        """
        try:
            res = await global_container.marketdata_bus.fetch_ohlcv(symbol, timeframe, limit)
            df = res.data
            return _json_ok(
                {
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "limit": limit,
                    "data": df.to_dict(orient="records") if hasattr(df, "to_dict") else df,
                    "source": res.source,
                }
            )
        except Exception as e:
            return _json_err("fetch_ohlcv_error", str(e))