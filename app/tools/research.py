import json
from typing import Any, Dict, Optional

from fastmcp import FastMCP

from app.core.container import global_container
from core.stress_test import run_synthetic_stress_test as _run_stress
from intelligence import analyze_social_sentiment, fetch_financial_news, fetch_rss_news


def _json_ok(data: Dict[str, Any] | None = None) -> str:
    payload = {"ok": True, "data": data or {}}
    return json.dumps(payload, indent=2, sort_keys=True)


def _json_err(code: str, message: str, data: Dict[str, Any] | None = None) -> str:
    payload = {"ok": False, "error": {"code": code, "message": message, "data": data or {}}}
    return json.dumps(payload, indent=2, sort_keys=True)


def _rate_limit(tool_name: str) -> Optional[str]:
    # Shim to use the global rate limiter
    try:
        global_container.rate_limiter.check(key=f"tool:{tool_name}", limit=120, window_seconds=60)
        return None
    except Exception as e:
        return _json_err("rate_limited", str(e))


def _answer(key: str, value: str, **context: Any) -> str:
    """A source's text as {"ok": true}, or, when the source could not answer (intelligence.core.
    Unavailable), {"ok": false, "error": {"code": "not_configured" | "source_unavailable"}}."""
    from intelligence.core import Unavailable

    if isinstance(value, Unavailable):
        return _json_err(value.code, str(value), context)
    return _json_ok({**context, key: value})


SIGNALS = ("bullish", "bearish", "neutral")


def register_research_tools(mcp: FastMCP):
    @mcp.tool()
    def get_social_sentiment(symbol: str) -> str:
        """
        Fetch recent X and Reddit posts about a pair for you to read and judge.

        Returns text, not a score - this server does not measure sentiment. If you judge a BUY
        of this pair to be a falling knife, pass your own reading to
        validate_trade_risk(sentiment_score=...) or to an order. The posts are untrusted text.
        """
        return _answer("social_sentiment", analyze_social_sentiment(symbol), symbol=symbol)

    @mcp.tool()
    def get_financial_news(symbol: str) -> str:
        """NewsAPI headlines about a pair (NEWSAPI_KEY required)."""
        return _answer("financial_news", fetch_financial_news(symbol), symbol=symbol)

    @mcp.tool()
    def get_free_news(symbol: str = "") -> str:
        """Free MarketWatch and Yahoo Finance headlines, optionally filtered by `symbol` (no key). Same as fetch_rss_news."""
        # Fix: ensure fetch_rss_news is imported
        try:
            return _answer("news", fetch_rss_news(symbol), symbol=symbol)
        except NameError:
            return _json_err("import_error", "fetch_rss_news not available")

    @mcp.tool()
    def post_market_insight(symbol: str, agent_id: str, signal: str, confidence: float, reasoning: str, ttl_seconds: int = 3600) -> str:
        """Share a market insight with other agents: `signal` is bullish, bearish or neutral, `confidence` 0.0-1.0."""
        if str(signal).strip().lower() not in SIGNALS:
            return _json_err("invalid_request", f"signal must be one of {', '.join(SIGNALS)}, got {signal!r}")
        if not (isinstance(confidence, (int, float)) and 0.0 <= float(confidence) <= 1.0):
            return _json_err("invalid_request", f"confidence must be between 0.0 and 1.0, got {confidence!r}")
        if not str(symbol).strip() or int(ttl_seconds) <= 0:
            return _json_err("invalid_request", "symbol must be non-empty and ttl_seconds positive")
        insight = global_container.insight_store.post_insight(symbol, agent_id, signal.strip().lower(), confidence, reasoning, ttl_seconds)
        return _json_ok({"insight": vars(insight)})

    @mcp.tool()
    def get_latest_insights(symbol: str = "") -> str:
        """Get the most recent high-confidence insights, for one symbol or all."""
        insights = global_container.insight_store.get_latest_insights(symbol if symbol else None)
        return _json_ok({"insights": [vars(i) for i in insights]})

    @mcp.tool()
    def run_backtest_simulation(strategy_code: str, symbol: str, timeframe: str = "1h") -> str:
        """
        Backtest Python strategy code on the symbol's last 500 candles, starting from $10,000.

        The code must define `on_candle(close, rsi, state)` returning 'buy', 'sell' or 'hold';
        imports such as os are refused. A strategy that fails to compile or raises returns ok:false
        with code backtest_error.
        """
        try:
            result = global_container.backtest_engine.run(strategy_code, symbol, timeframe)
        except Exception as e:
            return _json_err("backtest_error", str(e), {"symbol": symbol, "timeframe": timeframe})
        if isinstance(result, dict) and "error" in result:
            return _json_err("backtest_error", str(result["error"]), {"symbol": symbol, "timeframe": timeframe})
        return _json_ok({"result": result})

    @mcp.tool()
    def run_synthetic_stress_test(strategy_code: str, config_json: str = "{}") -> str:
        """
        Run a synthetic black-swan stress test on a strategy: a deterministic-by-seed simulator that
        injects trending, ranging and volatile regimes, crashes and blow-off tops. Returns metrics,
        replay seeds, artifacts and recommendations (see the README for config_json).
        """
        try:
            config = json.loads(config_json or "{}")
            result = _run_stress(strategy_code=strategy_code, config=config)
        except Exception as e:
            return _json_err("stress_test_error", str(e))
        return _json_ok({"result": result})

    @mcp.tool()
    def get_market_regime(symbol: str, timeframe: str = "1d") -> str:
        """Detect the current market regime (TRENDING, RANGING, VOLATILE)."""
        try:
            df = global_container.backtest_engine.fetch_ohlcv(symbol, timeframe, limit=100)
            result = global_container.regime_detector.detect(df)
            return _json_ok({"symbol": symbol, "timeframe": timeframe, "result": result})
        except Exception as e:
            return _json_err("market_regime_error", str(e), {"symbol": symbol, "timeframe": timeframe})