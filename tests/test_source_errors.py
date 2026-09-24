"""A news, calendar or sentiment source that cannot answer is reported as an error (ok:false with a
code), never as an answer - in particular never as "no high-impact events"."""

import asyncio
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

import intelligence.core as core
from intelligence.core import Unavailable

NO_KEYS = {"PATH": "/usr/bin"}


@pytest.fixture(autouse=True)
def empty_calendar_cache(monkeypatch):
    monkeypatch.setitem(core._calendar_cache, "events", None)
    monkeypatch.setitem(core._calendar_cache, "fetched_at", 0.0)


def call(name, args):
    from fastmcp import Client

    from app.main import mcp

    async def go():
        async with Client(mcp) as client:
            result = await client.call_tool(name, args, raise_on_error=False)
            return json.loads(result.content[0].text)

    return asyncio.run(go())


def response(status=200, payload=None):
    r = MagicMock()
    r.status_code = status
    r.json.return_value = payload
    r.raise_for_status.side_effect = None if status < 400 else RuntimeError(f"HTTP {status}")
    return r


# ---------------------------------------------------------------- economic calendar


def test_a_refused_calendar_is_an_error_not_an_all_clear():
    with patch("intelligence.core.requests.get", return_value=response(403)):
        cal = core.get_economic_calendar()
        assert isinstance(cal, Unavailable) and "No High Impact" not in cal and "no high-impact" not in cal
        body = call("get_economic_calendar", {})
    assert body["ok"] is False and body["error"]["code"] == "source_unavailable"


def test_the_calendar_lists_todays_high_impact_events():
    now = datetime.now(timezone.utc)
    events = [
        {"title": "SNB Policy Rate", "country": "CHF", "date": (now + timedelta(hours=1)).isoformat(), "impact": "High", "forecast": "0.00%"},
        {"title": "Rightmove HPI", "country": "GBP", "date": (now + timedelta(hours=2)).isoformat(), "impact": "Low"},
        {"title": "Old news", "country": "USD", "date": (now - timedelta(days=3)).isoformat(), "impact": "High"},
    ]
    with patch("intelligence.core.requests.get", return_value=response(200, events)):
        cal = core.get_economic_calendar()
    assert not isinstance(cal, Unavailable)
    assert "SNB Policy Rate" in cal and "(today)" in cal and "Rightmove" not in cal and "Old news" not in cal


def test_a_week_without_high_impact_events_says_so_from_data():
    with patch("intelligence.core.requests.get", return_value=response(200, [])):
        cal = core.get_economic_calendar()
    assert not isinstance(cal, Unavailable) and "no high-impact events" in cal


def test_the_market_backdrop_is_unavailable_only_when_every_part_is():
    with patch("intelligence.core.get_dxy_trend", return_value="DXY Trend (5d): Bullish"), patch(
        "intelligence.core.get_economic_calendar", return_value=Unavailable("Economic Calendar unavailable")
    ):
        text = core.get_market_sentiment()
        assert not isinstance(text, Unavailable) and "Economic Calendar unavailable" in text
    with patch("intelligence.core.get_dxy_trend", return_value=Unavailable("DXY Trend: Data unavailable.")), patch(
        "intelligence.core.get_economic_calendar", return_value=Unavailable("Economic Calendar unavailable")
    ):
        assert isinstance(core.get_market_sentiment(), Unavailable)


# ---------------------------------------------------------------- keyed sources


@pytest.mark.parametrize(
    "tool,args",
    [
        ("get_market_news", {}),
        ("get_financial_news", {"symbol": "EURUSD"}),
        ("fetch_financial_news", {"symbol": "EURUSD"}),
        ("get_social_sentiment", {"symbol": "EURUSD"}),
        ("analyze_social_sentiment", {"symbol": "EURUSD"}),
    ],
)
def test_a_tool_without_its_key_says_not_configured(tool, args):
    with patch.dict("os.environ", NO_KEYS, clear=True):
        body = call(tool, args)
    assert body["ok"] is False and body["error"]["code"] == "not_configured"


def test_an_alpha_vantage_note_instead_of_a_feed_is_an_error():
    r = response(200, {"Information": "rate limit: 25 requests per day"})
    with patch.dict("os.environ", {"ALPHAVANTAGE_API_KEY": "k"}), patch("intelligence.core.requests.get", return_value=r):
        news = core.get_market_news()
    assert isinstance(news, Unavailable) and "rate limit" in news


def test_every_rss_feed_failing_is_an_error_and_no_error_is_a_headline():
    with patch("intelligence.core.requests.get", side_effect=OSError("offline")):
        out = core.fetch_rss_news("")
        assert isinstance(out, Unavailable) and "offline" in out
        assert isinstance(core.get_forex_news(3), Unavailable)
    with patch("intelligence.core.requests.get", return_value=response(403)):
        assert isinstance(core.get_forex_news(3), Unavailable)


def test_a_cached_calendar_answers_while_the_mirror_refuses_a_refresh(monkeypatch):
    now = datetime.now(timezone.utc)
    events = [{"title": "SNB Policy Rate", "country": "CHF", "date": (now + timedelta(hours=1)).isoformat(), "impact": "High"}]
    with patch("intelligence.core.requests.get", return_value=response(200, events)) as get:
        core.get_economic_calendar()
        core.get_economic_calendar()
        assert get.call_count == 1  # the second read comes from the cache
    monkeypatch.setitem(core._calendar_cache, "fetched_at", core._calendar_cache["fetched_at"] - 3600)
    with patch("intelligence.core.requests.get", return_value=response(429)):
        cal = core.get_economic_calendar()
    assert not isinstance(cal, Unavailable) and "SNB Policy Rate" in cal and "read" in cal


# ---------------------------------------------------------------- custom feeds


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/hostname",
        "http://127.0.0.1:8000/api/pending-approvals",
        "http://localhost/",
        "http://10.0.0.5/feed",
        "http://169.254.169.254/latest/meta-data/",
        "ftp://example.com/feed",
    ],
)
def test_a_custom_feed_must_be_a_public_http_url(url):
    with patch("intelligence.core.requests.get") as get:
        out = core.fetch_custom_feed(url)
        get.assert_not_called()
    assert isinstance(out, Unavailable)


def test_a_redirect_to_a_private_address_is_refused():
    hop = MagicMock(is_redirect=True, headers={"location": "http://127.0.0.1/secret"})
    with patch("intelligence.core._public_http_url", side_effect=lambda u: u if "127.0.0.1" not in u else (_ for _ in ()).throw(ValueError("private"))):
        with patch("intelligence.core.requests.get", return_value=hop) as get:
            out = core.fetch_custom_feed("https://feeds.example.com/rss")
    assert isinstance(out, Unavailable) and get.call_count == 1
