"""
The Falling Knife gate: what the Risk Guardian actually receives, and from where.

Three defects motivated these tests.

1. `analyze_social_sentiment` added a flat +0.2 for each configured source, so a panicking feed
   and a euphoric one both scored +0.4, the only reachable values were {0.0, 0.2, 0.4}, and the
   rule - which blocks below -0.5 - could never fire.
2. `place_stock_order` (and so every order entry point) passed a hardcoded 0.0 for sentiment and
   passed neither daily loss nor drawdown, so three risk rules were inert on every real order.
3. `get_volatility_status` and `get_news_status` were unimplemented stubs that always returned the
   permissive value, so the volatility halt and news guard silently never fired. The volatility
   halt now reads daily bars (tests/test_market_guard.py); the news guard is still a stub.

This server measures no sentiment (see `analyze_social_sentiment`), so these tests pin the honest
contract: nothing fabricates a score, a neutral 0.0 is always reported as unmeasured, an agent may
supply its own reading, every implemented rule reaches the order path, and the unimplemented ones
are declared rather than hidden.
"""

import json
from unittest.mock import MagicMock

import pytest

import intelligence.core as core
from app.core.container import global_container
from app.tools.execution import place_forex_order, place_limit_order, place_market_order, place_stock_order
from app.tools.trading import _sentiment_context, inactive_rules

GATE = -0.5  # RiskGuardian blocks a BUY below this
SYMBOL = "EURUSD"

POSTS = [
    "EURUSD 1.0412 -> 1.0198 in about ninety seconds",
    "ECB cut 50bp unscheduled, no press conference",
    "real money selling EUR against everything",
    "no bid depth, spreads out to 4 pips",
    "cancelled the whole EUR book",
]


@pytest.fixture(autouse=True)
def clean_cache():
    core._sentiment_cache.cache.clear()
    yield
    core._sentiment_cache.cache.clear()


@pytest.fixture(autouse=True)
def steady_paper_metrics(monkeypatch):
    """Isolate these tests from whatever data/paper.db happens to hold."""
    engine = global_container.paper_engine
    if engine is not None:
        monkeypatch.setattr(
            type(engine),
            "get_risk_metrics",
            lambda self, account: {"equity": 100000.0, "daily_pnl_pct": 0.0, "drawdown_pct": 0.0},
        )


@pytest.fixture
def quiet_ledger(monkeypatch):
    from app.tools import execution

    monkeypatch.setattr(execution.global_compliance_ledger, "record_event", MagicMock())
    return execution


def _sources(monkeypatch, tweets, titles, tweet_state="ok", title_state="ok"):
    monkeypatch.setattr(core, "_recent_tweets", lambda s: (tweets, "Twitter (Real): stub", tweet_state))
    monkeypatch.setattr(core, "_recent_reddit_titles", lambda s: (titles, "Reddit (Real): stub", title_state))


# ---------------------------------------------------------------- nothing fabricates a score


def test_no_score_is_invented_from_the_number_of_configured_sources(monkeypatch):
    """The original defect: +0.2 per source, so configuring sources moved the 'sentiment'."""
    _sources(monkeypatch, POSTS, [])
    core.analyze_social_sentiment(SYMBOL)
    one_source = core.get_cached_sentiment_score(SYMBOL)

    _sources(monkeypatch, POSTS, POSTS)
    core.analyze_social_sentiment(SYMBOL)
    assert one_source == core.get_cached_sentiment_score(SYMBOL) == 0.0


def test_the_cached_score_is_always_neutral(monkeypatch):
    for tweets, titles in ((POSTS, []), ([], POSTS), (POSTS, POSTS), ([], [])):
        _sources(monkeypatch, tweets, titles)
        core.analyze_social_sentiment(SYMBOL)
        assert core.get_cached_sentiment_score(SYMBOL) == 0.0


def test_the_posts_are_returned_for_the_agent_to_read(monkeypatch):
    _sources(monkeypatch, POSTS, [])
    report = core.analyze_social_sentiment(SYMBOL)
    for post in POSTS:
        assert post in report
    assert "does not score this text" in report


def test_the_report_warns_about_the_quote_convention(monkeypatch):
    """A rising USDTRY is the lira collapsing; a naive reader gets the sign backwards."""
    _sources(monkeypatch, POSTS, [])
    report = core.analyze_social_sentiment("USD/TRY")
    assert "quote convention" in report
    assert "base currency is strengthening" in report


def test_repeated_posts_are_listed_once(monkeypatch):
    _sources(monkeypatch, POSTS, list(POSTS))
    core.analyze_social_sentiment(SYMBOL)
    assert core.get_cached_sentiment(SYMBOL)["texts"] == len(POSTS)


def test_blank_and_junk_posts_are_dropped(monkeypatch):
    _sources(monkeypatch, ["", "   ", None, 42] + POSTS[:2], [])
    core.analyze_social_sentiment(SYMBOL)
    assert core.get_cached_sentiment(SYMBOL)["texts"] == 2


def test_unconfigured_sources_say_so_and_do_not_claim_a_reading(monkeypatch):
    _sources(monkeypatch, [], [], tweet_state="not_configured", title_state="not_configured")
    report = core.analyze_social_sentiment(SYMBOL)
    assert "No sentiment APIs configured" in report
    assert core.get_cached_sentiment(SYMBOL)["configured"] is False


def test_a_source_error_does_not_raise(monkeypatch):
    _sources(monkeypatch, [], [], tweet_state="error")
    assert core.analyze_social_sentiment(SYMBOL)


def test_blank_symbol_does_not_reach_the_sources():
    assert "no symbol given" in core.analyze_social_sentiment("")


# ---------------------------------------------------------------- pair normalisation


@pytest.mark.parametrize(
    "given,expected",
    [
        ("EURUSD", "EURUSD"),
        ("eurusd", "EURUSD"),
        ("EUR/USD", "EURUSD"),
        ("eur_usd", "EURUSD"),
        ("eur-usd", "EURUSD"),
        (" EURUSD=X ", "EURUSD"),
    ],
)
def test_pair_normalisation(given, expected):
    assert core.pair(given) == expected


def test_a_pair_is_not_reduced_to_a_base_currency():
    """Both legs matter: USDJPY and JPYUSD are different instruments, unlike BTC/USDT -> BTC."""
    assert core.pair("USD/JPY") == "USDJPY"
    assert core.pair("JPY/USD") == "JPYUSD"
    assert core.pair("USD/JPY") != core.pair("JPY/USD")


@pytest.mark.parametrize("given", [None, 123, ["EURUSD"], {"s": 1}, "   ", ""])
def test_a_symbol_that_is_not_a_pair_is_empty_not_garbage(given):
    assert core.pair(given) == ""


# ---------------------------------------------------------------- cache


def test_cache_is_keyed_by_normalised_pair():
    """The original second defect: stored under one spelling, read under another."""
    core._sentiment_cache.set("eur/usd", 12)
    assert core.get_cached_sentiment("EURUSD")["texts"] == 12
    assert core.get_cached_sentiment("EUR_USD")["texts"] == 12


def test_missing_symbol_reads_as_nothing_fetched():
    assert core.get_cached_sentiment("ZZZZZZ") is None
    assert core.get_cached_sentiment_score("ZZZZZZ") == 0.0


def test_stale_entry_expires(monkeypatch):
    core._sentiment_cache.set(SYMBOL, 12)
    real = core.time.monotonic
    monkeypatch.setattr(core.time, "monotonic", lambda: real() + core._sentiment_cache.ttl + 1)
    assert core.get_cached_sentiment(SYMBOL) is None


def test_expired_entries_are_evicted_on_write(monkeypatch):
    core._sentiment_cache.set("AUDUSD", 12)
    real = core.time.monotonic
    monkeypatch.setattr(core.time, "monotonic", lambda: real() + core._sentiment_cache.ttl + 1)
    core._sentiment_cache.set("GBPUSD", 3)
    assert "AUDUSD" not in core._sentiment_cache.cache


# ---------------------------------------------------------------- what the rule reports


def test_a_neutral_score_is_reported_as_unmeasured_not_as_calm():
    context = _sentiment_context(SYMBOL, None)
    assert context["score"] == 0.0
    assert context["source"] == "unmeasured"
    assert context["status"] == "not_measured"
    assert "does not score sentiment" in context["hint"]


def test_missing_credentials_are_reported_distinctly():
    core._sentiment_cache.set(SYMBOL, 0, configured=False)
    context = _sentiment_context(SYMBOL, None)
    assert context["status"] == "no_source_configured"
    assert "TWITTER_BEARER_TOKEN" in context["hint"]


def test_an_agent_supplied_score_is_labelled_as_such():
    context = _sentiment_context(SYMBOL, -0.9)
    assert context["score"] == -0.9
    assert context["source"] == "agent_supplied"
    assert "hint" not in context


@pytest.mark.parametrize("given,expected", [(-4.0, -1.0), (4.0, 1.0), (-0.5, -0.5), (0, 0.0)])
def test_an_agent_supplied_score_is_clamped_to_the_documented_range(given, expected):
    assert _sentiment_context(SYMBOL, given)["score"] == expected


# ---------------------------------------------------------------- unimplemented rules are declared


def test_the_stub_gate_is_declared_inactive():
    """An 'allowed' verdict must never be read as a fully checked one."""
    inactive = inactive_rules()
    assert "news_guard" in inactive
    assert "volatility_halt" not in inactive  # implemented: reads daily bars


def test_the_news_stub_really_is_permissive():
    """Pins why it is declared: it returns the value that lets every trade through."""
    assert core.get_news_status() is False
    assert core.NEWS_STATUS_IMPLEMENTED is False
    assert core.VOLATILITY_STATUS_IMPLEMENTED is True


def test_the_declaration_tracks_the_code(monkeypatch):
    """The declaration must follow the implementation flags, not be a hardcoded string that rots."""
    import app.tools.trading as trading

    monkeypatch.setattr(trading, "VOLATILITY_STATUS_IMPLEMENTED", False)
    assert "not implemented" in trading.inactive_rules()["volatility_halt"]
    monkeypatch.setattr(trading, "NEWS_STATUS_IMPLEMENTED", True)
    assert "news_guard" not in trading.inactive_rules()


def test_the_trade_check_reports_inactive_rules():
    payload = json.loads(_validate("buy", SYMBOL, 1000.0, 100000.0))
    assert "news_guard" in payload["data"]["inactive_rules"]
    assert "volatility_halt" not in payload["data"]["inactive_rules"]


# ---------------------------------------------------------------- the trade check


def _validate(side, symbol, amount, portfolio, sentiment_score=None):
    """Call the registered validate_trade_risk tool, which is nested inside the registrar."""
    from fastmcp import FastMCP

    from app.tools.trading import register_trading_tools

    captured = {}

    class _Recorder(FastMCP):
        def tool(self, *args, **kwargs):
            def deco(fn):
                captured[fn.__name__] = fn
                return fn

            return deco

    register_trading_tools(_Recorder("recorder"))
    return captured["validate_trade_risk"](side, symbol, amount, portfolio, sentiment_score)


def test_an_agent_supplied_bearish_score_blocks_a_buy():
    payload = json.loads(_validate("buy", SYMBOL, 1000.0, 100000.0, -0.9))
    assert payload["data"]["result"]["allowed"] is False
    assert "Falling Knife" in payload["data"]["result"]["reason"]
    assert payload["data"]["sentiment"]["source"] == "agent_supplied"


def test_an_agent_supplied_bearish_score_does_not_block_a_sell():
    payload = json.loads(_validate("sell", SYMBOL, 1000.0, 100000.0, -0.9))
    assert payload["data"]["result"]["allowed"] is True


def test_without_a_supplied_score_the_rule_cannot_fire():
    payload = json.loads(_validate("buy", SYMBOL, 1000.0, 100000.0))
    assert payload["data"]["result"]["allowed"] is True
    assert payload["data"]["sentiment"]["status"] == "not_measured"


# ---------------------------------------------------------------- the order path


def test_the_order_path_honours_an_agent_supplied_score(quiet_ledger):
    """The other half of the defect: place_stock_order passed a hardcoded 0.0."""
    payload = json.loads(place_stock_order(SYMBOL, "buy", 10.0, price=1.05, sentiment_score=-0.9))
    assert payload["ok"] is False
    assert payload["error"]["code"] == "risk_blocked"
    assert "Falling Knife" in payload["error"]["message"]
    assert payload["error"]["data"]["sentiment"]["source"] == "agent_supplied"


@pytest.mark.parametrize(
    "call",
    [
        lambda: place_market_order(SYMBOL, "buy", 10.0, sentiment_score=-0.9),
        lambda: place_limit_order(SYMBOL, "buy", 10.0, 1.05, sentiment_score=-0.9),
        lambda: place_forex_order(SYMBOL, "buy", 10.0, price=1.05, sentiment_score=-0.9),
    ],
    ids=["market", "limit", "forex"],
)
def test_every_order_entry_point_inherits_the_gate(call, quiet_ledger):
    payload = json.loads(call())
    assert payload["error"]["code"] == "risk_blocked"


def test_a_blocked_order_reports_the_inactive_rules(quiet_ledger):
    payload = json.loads(place_stock_order(SYMBOL, "buy", 10.0, price=1.05, sentiment_score=-0.9))
    assert "news_guard" in payload["error"]["data"]["inactive_rules"]


def test_the_order_path_allows_a_sell_on_a_bearish_score(quiet_ledger):
    payload = json.loads(place_stock_order(SYMBOL, "sell", 10.0, price=1.05, sentiment_score=-0.9))
    assert payload.get("error", {}).get("code") != "risk_blocked"


def test_the_order_path_applies_the_daily_loss_rule(monkeypatch, quiet_ledger):
    """Previously never passed, so this rule was inert on every real order."""
    engine = global_container.paper_engine
    monkeypatch.setattr(
        type(engine),
        "get_risk_metrics",
        lambda self, account: {"equity": 100000.0, "daily_pnl_pct": -0.09, "drawdown_pct": 0.0},
    )
    payload = json.loads(place_stock_order(SYMBOL, "buy", 10.0, price=1.05))
    assert payload["ok"] is False
    assert payload["error"]["code"] == "risk_blocked"


def test_the_order_path_applies_the_drawdown_rule(monkeypatch, quiet_ledger):
    """Drawdown is reported as a positive fraction by the paper engine (peak-to-trough)."""
    engine = global_container.paper_engine
    monkeypatch.setattr(
        type(engine),
        "get_risk_metrics",
        lambda self, account: {"equity": 100000.0, "daily_pnl_pct": 0.0, "drawdown_pct": 0.25},
    )
    payload = json.loads(place_stock_order(SYMBOL, "buy", 10.0, price=1.05))
    assert payload["ok"] is False
    assert payload["error"]["code"] == "risk_blocked"


def test_an_ordinary_order_is_not_blocked(quiet_ledger):
    payload = json.loads(place_stock_order(SYMBOL, "buy", 10.0, price=1.05))
    assert payload.get("error", {}).get("code") != "risk_blocked"
