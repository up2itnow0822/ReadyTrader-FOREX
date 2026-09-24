"""Research and market-data tools as an MCP client calls them (in-process fastmcp client)."""

import asyncio
import json

import pytest

from app.core.container import global_container


def call(name, args):
    from fastmcp import Client

    from app.main import mcp

    async def go():
        async with Client(mcp) as client:
            result = await client.call_tool(name, args, raise_on_error=False)
            return json.loads(result.content[0].text)

    return asyncio.run(go())


@pytest.mark.parametrize(
    "outcome",
    [{"error": "Strategy Compilation Error: Importing 'os' is forbidden."}, {"error": "Strategy code must define 'def on_candle(close, rsi, state):'"}],
)
def test_a_failed_backtest_is_an_error_not_a_result(monkeypatch, outcome):
    monkeypatch.setattr(global_container.backtest_engine, "run", lambda *a, **k: outcome)
    body = call("run_backtest_simulation", {"strategy_code": "x = 1", "symbol": "EURUSD", "timeframe": "1d"})
    assert body["ok"] is False and body["error"]["code"] == "backtest_error"


def test_the_stress_test_is_an_mcp_tool_and_runs():
    code = "def on_candle(close, rsi, state):\n    return 'hold'\n"
    body = call("run_synthetic_stress_test", {"strategy_code": code, "config_json": json.dumps({"scenarios": 3, "master_seed": 1, "length": 120})})
    assert body["ok"] is True, body
    assert "metrics" in json.dumps(body["data"]["result"])


@pytest.mark.parametrize("signal,confidence", [("sideways-ish", 0.5), ("bullish", 7.5), ("bearish", -0.1)])
def test_an_insight_outside_the_documented_fields_is_refused(tmp_path, monkeypatch, signal, confidence):
    from intelligence.insights import InsightStore

    monkeypatch.setattr(global_container, "insight_store", InsightStore(db_path=str(tmp_path / "insights.db")))
    body = call("post_market_insight", {"symbol": "EURUSD", "agent_id": "a", "signal": signal, "confidence": confidence, "reasoning": "x"})
    assert body["ok"] is False and body["error"]["code"] == "invalid_request"


def test_get_stock_price_returns_a_number(monkeypatch):
    class Res:
        data = {"last": 1.1044, "bid": 1.1043, "ask": 1.1045}
        source = "test"

    async def fetch_ticker(symbol):
        return Res()

    monkeypatch.setattr(global_container.marketdata_bus, "fetch_ticker", fetch_ticker)
    body = call("get_stock_price", {"symbol": "EURUSD"})
    assert body["ok"] is True and body["data"]["price"] == pytest.approx(1.1044) and body["data"]["bid"] == pytest.approx(1.1043)


def test_get_multiple_prices_answers_numbers_and_names_what_it_could_not_price(monkeypatch):
    class Res:
        def __init__(self, last):
            self.data, self.source = {"last": last}, "test"

    async def fetch_ticker(symbol):
        if symbol == "NOTAPAIR":
            raise ValueError("no data for NOTAPAIR")
        return Res({"EURUSD": 1.1044, "GBP/USD": 1.25}[symbol])

    monkeypatch.setattr(global_container.marketdata_bus, "fetch_ticker", fetch_ticker)
    body = call("get_multiple_prices", {"symbols": "EURUSD, GBP/USD,NOTAPAIR"})
    assert body["ok"] is True
    assert body["data"]["prices"] == {"EURUSD": 1.1044, "GBP/USD": 1.25, "NOTAPAIR": None}
    assert "no data" in body["data"]["errors"]["NOTAPAIR"]
    assert call("get_multiple_prices", {"symbols": " , "})["error"]["code"] == "invalid_request"


def test_financial_news_searches_for_the_pair_not_a_stock(monkeypatch):
    from unittest.mock import MagicMock, patch

    client = MagicMock()
    client.get_everything.return_value = {"status": "ok", "articles": []}
    monkeypatch.setenv("NEWSAPI_KEY", "k")
    with patch("intelligence.core.NewsApiClient", return_value=client):
        from intelligence.core import fetch_financial_news

        fetch_financial_news("EUR/USD")
    assert client.get_everything.call_args.kwargs["q"] == '"EUR/USD" OR EURUSD'


def test_an_insight_is_found_under_every_spelling_of_the_pair(tmp_path, monkeypatch):
    import sqlite3

    from intelligence.insights import InsightStore

    store = InsightStore(db_path=str(tmp_path / "insights.db"))
    monkeypatch.setattr(global_container, "insight_store", store)
    assert call("post_market_insight", {"symbol": "EUR/USD", "agent_id": "a", "signal": "bearish", "confidence": 0.8, "reasoning": "x"})["ok"]
    for spelling in ("EUR/USD", "eurusd", "EURUSD", "eur_usd", "EURUSD=X"):
        found = call("get_latest_insights", {"symbol": spelling})["data"]["insights"]
        assert [i["symbol"] for i in found] == ["EURUSD"], spelling
    # A row written before the normalisation (symbol stored as 'GBP/USD') is still found.
    with sqlite3.connect(store.db_path) as conn:
        conn.execute("UPDATE insights SET symbol = 'GBP/USD'")
    assert len(call("get_latest_insights", {"symbol": "GBPUSD"})["data"]["insights"]) == 1


@pytest.mark.parametrize(
    "args",
    [
        {"side": "hold", "symbol": "EURUSD", "amount_usd": 100, "portfolio_value": 10_000},
        {"side": "buy", "symbol": "EURUSD", "amount_usd": -5, "portfolio_value": 10_000},
        {"side": "buy", "symbol": "EURUSD", "amount_usd": 1e9, "portfolio_value": 0},
        {"side": "buy", "symbol": " ", "amount_usd": 100, "portfolio_value": 10_000},
    ],
)
def test_validate_trade_risk_refuses_a_malformed_request(args):
    body = call("validate_trade_risk", args)
    assert body["ok"] is False and body["error"]["code"] == "invalid_request"


def test_a_large_trade_verdict_does_not_promise_a_confirmation():
    body = call("validate_trade_risk", {"side": "buy", "symbol": "EURUSD", "amount_usd": 8_000, "portfolio_value": 200_000})
    assert body["ok"] and "requires manual confirmation" not in body["data"]["result"]["reason"]
    assert "approve_each" in body["data"]["result"]["reason"]


def test_the_paper_account_tools_read_and_reset_it():
    global_container.paper_engine.deposit("agent_zero", "USD", 5_000)
    assert call("get_paper_account", {})["data"]["cash_usd"] == 5_000
    assert call("reset_paper_account", {})["ok"]
    assert call("get_paper_account", {})["data"]["cash_usd"] == 0


def test_get_market_regime_reads_daily_bars(monkeypatch):
    import math

    rows = [[1_700_000_000_000 + i * 86_400_000, 1.1, 1.1 + 0.002 * math.sin(i) + 0.003, 1.1 - 0.003, 1.1 + 0.001 * i, 0.0] for i in range(120)]
    import pandas as pd

    frame = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
    monkeypatch.setattr(global_container.backtest_engine, "fetch_ohlcv", lambda *a, **k: frame)
    body = call("get_market_regime", {"symbol": "EURUSD"})
    assert body["ok"] and {"regime", "direction", "adx", "atr_pct"} <= set(body["data"]["result"])


def test_the_free_news_tools_report_a_dead_feed_as_an_error(monkeypatch):
    from unittest.mock import patch

    with patch("intelligence.core.requests.get", side_effect=OSError("offline")):
        for tool in ("get_free_news", "fetch_rss_news"):
            body = call(tool, {})
            assert body["ok"] is False and body["error"]["code"] == "source_unavailable", tool
