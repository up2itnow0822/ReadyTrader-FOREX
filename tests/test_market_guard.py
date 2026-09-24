"""
Falling Knife (price) and the volatility halt: core/market_guard.py and its wiring into the trade
check and every order entry point.

The rules and thresholds come from a study on real daily FX history (docs/FALLING_KNIFE.md). The
real-bar fixture pins the shipped code to actual episodes, including ones it must not block.
"""

import json
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

import market_bars as mb
import pytest

import app.tools.trading as trading
import intelligence.core as core
from app.core.config import safety_switch_on, settings
from app.core.container import global_container
from app.tools.execution import place_forex_order, place_limit_order, place_market_order, place_stock_order
from core import market_guard as mg

REAL = json.loads((Path(__file__).parent / "fixtures" / "market_guard_real_bars.json").read_text())["cases"]
SYMBOL = "EURUSD"


def use_bars(monkeypatch, bars):
    monkeypatch.setattr(trading, "_fetch_daily_bars", lambda symbol: bars)


def fail_fetch(monkeypatch, exc=RuntimeError("provider down")):
    def boom(symbol):
        raise exc

    monkeypatch.setattr(trading, "_fetch_daily_bars", boom)


def validate(side, amount=1000.0):
    """Call the registered validate_trade_risk tool, which is nested inside the registrar."""
    from fastmcp import FastMCP

    captured = {}

    class _Recorder(FastMCP):
        def tool(self, *args, **kwargs):
            def deco(fn):
                captured[fn.__name__] = fn
                return fn

            return deco

    trading.register_trading_tools(_Recorder("recorder"))
    return json.loads(captured["validate_trade_risk"](side, SYMBOL, amount, 100000.0, None))


@pytest.fixture(autouse=True)
def steady_paper_metrics(monkeypatch):
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


# ---------------------------------------------------------------- the rules on real history


@pytest.mark.parametrize("case", REAL, ids=[f"{c['symbol']}-{c['date']}" for c in REAL])
def test_real_episodes_score_as_recorded(case):
    reading = mg.assess(case["bars"], now_ms=case["bars"][-1][0])
    assert reading.status == mg.STATUS_OK
    assert reading.falling_knife is case["expect_falling_knife"], case["note"]
    assert reading.drop_pct == pytest.approx(case["expect_drop_pct"], abs=1e-4)
    assert reading.volatility_ratio == pytest.approx(case["expect_volatility_ratio"], rel=1e-3)


def test_the_real_fixture_covers_every_outcome():
    """Knife and halt, each present and absent: a one-sided fixture would pass a broken rule."""
    knives = {c["expect_falling_knife"] for c in REAL}
    halts = {c["expect_volatility_ratio"] > mg.VOLATILITY_HALT_RATIO for c in REAL}
    assert knives == {True, False} and halts == {True, False}


def test_the_snb_day_halts_both_legs_and_is_a_knife_only_for_the_currency_that_fell():
    by_symbol = {c["symbol"]: c for c in REAL if c["date"] == "2015-01-16"}
    eur = mg.assess(by_symbol["EURCHF"]["bars"], now_ms=by_symbol["EURCHF"]["bars"][-1][0])
    chf = mg.assess(by_symbol["CHFEUR"]["bars"], now_ms=by_symbol["CHFEUR"]["bars"][-1][0])
    assert eur.falling_knife and not chf.falling_knife
    assert eur.volatility_ratio > mg.VOLATILITY_HALT_RATIO and chf.volatility_ratio > mg.VOLATILITY_HALT_RATIO


def test_the_shipped_thresholds_are_the_frozen_ones():
    """docs/FALLING_KNIFE.md: 5% from the highest of four closes; halt above 4.5x the 20-day norm."""
    assert (mg.KNIFE_WINDOW, mg.KNIFE_MIN_DROP) == (3, 0.05)
    assert (mg.VOLATILITY_BASELINE, mg.VOLATILITY_HALT_RATIO) == (20, 4.5)


# ---------------------------------------------------------------- the rules on synthetic bars


def test_a_calm_tape_is_neither_a_knife_nor_a_halt():
    reading = mg.assess(mb.calm())
    assert reading.status == mg.STATUS_OK and not reading.falling_knife
    assert reading.volatility_ratio < mg.VOLATILITY_HALT_RATIO


def test_a_steady_fall_is_a_knife_without_a_halt():
    reading = mg.assess(mb.collapse(drop=0.08))
    assert reading.falling_knife and reading.drop_pct >= 0.08
    assert reading.volatility_ratio < mg.VOLATILITY_HALT_RATIO


def test_a_drop_under_the_floor_is_not_a_knife():
    reading = mg.assess(mb.collapse(drop=0.04))
    assert reading.drop_pct < mg.KNIFE_MIN_DROP and not reading.falling_knife


def test_a_one_day_jump_is_a_halt_without_a_knife():
    reading = mg.assess(mb.spike(move=0.06))
    assert reading.volatility_ratio > mg.VOLATILITY_HALT_RATIO and not reading.falling_knife


def test_a_bad_high_or_low_print_moves_neither_rule():
    """Only closes count: phantom wicks (bad provider prints) must not look like a crash."""
    bars = mb.calm()
    for i in (-2, -1):
        row = bars[i]
        bars[i] = [row[0], row[1], row[2] * 1.2, row[3] * 0.8, row[4], row[5]]
    reading = mg.assess(bars)
    assert reading.drop_pct < 0.01 and not reading.falling_knife
    assert reading.volatility_ratio < 2


def test_a_bounce_above_the_prior_close_is_not_still_falling():
    bars = mb.collapse(drop=0.08)
    last, prev = bars[-1], bars[-2]
    bounced = prev[4] * 1.001
    bars[-1] = [last[0], last[1], max(last[2], bounced), last[3], bounced, last[5]]
    reading = mg.assess(bars)
    assert reading.drop_pct >= mg.KNIFE_MIN_DROP and not reading.still_falling and not reading.falling_knife


def test_the_volatility_ratio_needs_a_full_baseline():
    reading = mg.assess(mb.calm(n=mg.VOLATILITY_BASELINE + 1))
    assert reading.status == mg.STATUS_OK and reading.volatility_ratio is None


def test_too_few_bars_is_insufficient_not_a_verdict():
    reading = mg.assess(mb.calm(n=mg.KNIFE_WINDOW))
    assert reading.status == mg.STATUS_INSUFFICIENT and not reading.falling_knife


def test_stale_bars_are_not_read_as_now():
    old_end = mb.calm()[-1][0] - 10 * mb.DAY_MS
    reading = mg.assess(mb.collapse(end_ms=old_end))
    assert reading.status == mg.STATUS_STALE and not reading.falling_knife


def test_a_weekend_is_not_stale():
    end = mb.calm()[-1][0]
    assert mg.assess(mb.calm(end_ms=end - 3 * mb.DAY_MS), now_ms=end).status == mg.STATUS_OK


@pytest.mark.parametrize(
    "bad_row",
    [[None, 1, 1, 1, 1, 0], [0, "x", 1, 1, 1, 0], [0, 1, float("nan"), 1, 1, 0], [0, 1, 1, 1, -5, 0], [0, 1, 0.5, 2, 1, 0], [1]],
)
def test_malformed_rows_are_dropped_not_trusted(bad_row):
    bars = mb.calm()
    reading = mg.assess(bars[:-1] + [bad_row] + bars[-1:])
    assert reading.status == mg.STATUS_OK and reading.bars == len(bars)


def test_empty_or_none_input_is_insufficient():
    assert mg.assess([]).status == mg.STATUS_INSUFFICIENT
    assert mg.assess(None).status == mg.STATUS_INSUFFICIENT


# ---------------------------------------------------------------- the trade check


def test_a_buy_into_a_falling_pair_is_blocked(monkeypatch):
    use_bars(monkeypatch, mb.collapse(drop=0.08))
    payload = validate("buy")
    assert payload["data"]["result"]["allowed"] is False
    assert "Falling Knife protection, price" in payload["data"]["result"]["reason"]
    assert payload["data"]["market"]["falling_knife"] is True


def test_a_sell_of_a_falling_pair_is_not_blocked(monkeypatch):
    use_bars(monkeypatch, mb.collapse(drop=0.08))
    assert validate("sell")["data"]["result"]["allowed"] is True


@pytest.mark.parametrize("side", ["buy", "sell"])
def test_a_volatility_halt_blocks_both_sides(monkeypatch, side):
    use_bars(monkeypatch, mb.spike(move=0.06))
    payload = validate(side)
    assert payload["data"]["result"]["allowed"] is False
    assert "Volatility Halt" in payload["data"]["result"]["reason"]
    assert payload["data"]["market"]["volatility_ratio"] > mg.VOLATILITY_HALT_RATIO


def test_a_calm_pair_is_allowed_and_reports_the_reading():
    payload = validate("buy")
    assert payload["data"]["result"]["allowed"] is True
    market = payload["data"]["market"]
    assert market["status"] == "ok" and market["falling_knife"] is False
    assert market["rule"] == {
        "window_bars": mg.KNIFE_WINDOW + 1,
        "min_drop": mg.KNIFE_MIN_DROP,
        "volatility_halt_ratio": mg.VOLATILITY_HALT_RATIO,
    }


def test_disabling_the_guard_is_declared(monkeypatch):
    monkeypatch.setattr(settings, "MARKET_GUARD_ENABLED", False)
    use_bars(monkeypatch, mb.spike(move=-0.10))
    payload = validate("buy")
    assert payload["data"]["result"]["allowed"] is True
    assert payload["data"]["market"]["status"] == "disabled"
    assert {"volatility_halt", "falling_knife_price"} <= set(payload["data"]["inactive_rules"])


# ---------------------------------------------------------------- when the data cannot be read


def test_unreadable_data_blocks_a_live_buy(monkeypatch):
    monkeypatch.setattr(settings, "PAPER_MODE", False)
    monkeypatch.setattr(settings, "MARKET_GUARD_ON_DATA_ERROR", "")
    fail_fetch(monkeypatch)
    payload = validate("buy")
    assert payload["data"]["result"]["allowed"] is False
    assert "could not run" in payload["data"]["result"]["reason"]


def test_unreadable_data_never_blocks_a_sell(monkeypatch):
    monkeypatch.setattr(settings, "PAPER_MODE", False)
    monkeypatch.setattr(settings, "MARKET_GUARD_ON_DATA_ERROR", "block")
    fail_fetch(monkeypatch)
    payload = validate("sell")
    assert payload["data"]["result"]["allowed"] is True
    assert payload["data"]["market"]["status"] == "unavailable"


def test_unreadable_data_allows_a_paper_buy_but_says_so(monkeypatch):
    monkeypatch.setattr(settings, "MARKET_GUARD_ON_DATA_ERROR", "")
    fail_fetch(monkeypatch)
    payload = validate("buy")
    assert payload["data"]["result"]["allowed"] is True
    assert payload["data"]["market"]["on_data_error"] == "allow"


@pytest.mark.parametrize("value,paper,blocks", [("block", True, True), ("allow", False, False), ("bogus", True, True)])
def test_the_data_error_policy_can_be_set_and_fails_closed(monkeypatch, value, paper, blocks):
    monkeypatch.setattr(settings, "PAPER_MODE", paper)
    monkeypatch.setattr(settings, "MARKET_GUARD_ON_DATA_ERROR", value)
    fail_fetch(monkeypatch)
    assert validate("buy")["data"]["result"]["allowed"] is (not blocks)


def test_stale_data_counts_as_unreadable_in_live_mode(monkeypatch):
    monkeypatch.setattr(settings, "PAPER_MODE", False)
    monkeypatch.setattr(settings, "MARKET_GUARD_ON_DATA_ERROR", "")
    use_bars(monkeypatch, mb.calm(end_ms=mb.calm()[-1][0] - 10 * mb.DAY_MS))
    payload = validate("buy")
    assert payload["data"]["result"]["allowed"] is False
    assert payload["data"]["market"]["status"] == "stale"


# ---------------------------------------------------------------- the order path


ENTRY_POINTS = {
    "stock": lambda side: place_stock_order(SYMBOL, side, 10.0, price=1.05),
    "forex": lambda side: place_forex_order(SYMBOL, side, 10.0, price=1.05),
    "market": lambda side: place_market_order(SYMBOL, side, 10.0),
    "limit": lambda side: place_limit_order(SYMBOL, side, 10.0, 1.05),
}


@pytest.mark.parametrize("entry", ENTRY_POINTS, ids=list(ENTRY_POINTS))
def test_every_order_entry_point_blocks_a_buy_into_a_falling_pair(monkeypatch, quiet_ledger, entry):
    use_bars(monkeypatch, mb.collapse(drop=0.08))
    payload = json.loads(ENTRY_POINTS[entry]("buy"))
    assert payload["error"]["code"] == "risk_blocked"
    assert payload["error"]["data"]["market"]["falling_knife"] is True


@pytest.mark.parametrize("entry", ENTRY_POINTS, ids=list(ENTRY_POINTS))
def test_every_order_entry_point_applies_the_volatility_halt(monkeypatch, quiet_ledger, entry):
    use_bars(monkeypatch, mb.spike(move=0.06))
    payload = json.loads(ENTRY_POINTS[entry]("sell"))
    assert payload["error"]["code"] == "risk_blocked"
    assert "Volatility Halt" in payload["error"]["message"]


def test_the_order_path_lets_a_sell_of_a_falling_pair_through(monkeypatch, quiet_ledger):
    use_bars(monkeypatch, mb.collapse(drop=0.08))
    payload = json.loads(place_stock_order(SYMBOL, "sell", 10.0, price=1.05))
    assert payload.get("error", {}).get("code") != "risk_blocked"


def test_the_order_path_blocks_a_live_buy_when_data_is_unreadable(monkeypatch, quiet_ledger):
    monkeypatch.setattr(settings, "PAPER_MODE", False)
    monkeypatch.setattr(settings, "MARKET_GUARD_ON_DATA_ERROR", "")
    fail_fetch(monkeypatch)
    payload = json.loads(place_stock_order(SYMBOL, "buy", 10.0, price=1.05))
    assert payload["error"]["code"] == "risk_blocked"
    assert "could not run" in payload["error"]["message"]


# ---------------------------------------------------------------- the network seam


class FakeProvider:
    def __init__(self, bars=None, exc=None):
        self.bars, self.exc, self.calls = bars, exc, []

    def fetch_ohlcv(self, symbol, timeframe, limit):
        self.calls.append((symbol, timeframe, limit))
        if self.exc:
            raise self.exc
        return self.bars


def test_the_fetch_asks_the_provider_for_daily_bars(monkeypatch):
    """Undo the conftest stub for one call and check what the real seam requests."""
    monkeypatch.undo()
    provider = FakeProvider(bars=mb.calm())
    monkeypatch.setattr(global_container, "exchange_provider", provider)
    bars = trading._fetch_daily_bars(SYMBOL)
    assert provider.calls == [(SYMBOL, "1d", mg.BARS_REQUESTED)]
    assert mg.assess(bars).status == mg.STATUS_OK


def test_get_volatility_status_reads_the_same_ratio(monkeypatch):
    monkeypatch.setattr(global_container, "exchange_provider", FakeProvider(bars=mb.spike(move=0.06)))
    assert core.get_volatility_status(SYMBOL) > mg.VOLATILITY_HALT_RATIO


def test_get_volatility_status_is_none_when_it_cannot_be_computed(monkeypatch):
    """Never a made-up "normal" 1.0."""
    monkeypatch.setattr(global_container, "exchange_provider", FakeProvider(exc=RuntimeError("down")))
    assert core.get_volatility_status(SYMBOL) is None
    monkeypatch.setattr(global_container, "exchange_provider", FakeProvider(bars=mb.calm(n=5)))
    assert core.get_volatility_status(SYMBOL) is None


# ---------------------------------------------------------------- today's session must have a bar

LONDON = ZoneInfo("Europe/London")


def london_ms(year, month, day, hour=0, minute=0):
    return int(datetime(year, month, day, hour, minute, tzinfo=LONDON).timestamp() * 1000)


def bars_through(year, month, day, maker=mb.calm, **kw):
    """Daily bars stamped at London midnight, as yfinance stamps FX bars, the last on that date."""
    return maker(end_ms=london_ms(year, month, day), **kw)


def at(monkeypatch, now_ms):
    monkeypatch.setattr(mg, "_now_ms", lambda: now_ms)


def test_the_fx_session_is_the_london_weekday():
    assert (mg.FX_SESSION.tz, mg.FX_SESSION.open_hhmm, mg.FX_SESSION.weekdays) == ("Europe/London", "00:00", (0, 1, 2, 3, 4))


def test_yesterdays_bar_is_stale_during_todays_session():
    # Thursday 2026-09-24, 10:00 London: the provider still ends at Wednesday.
    reading = mg.assess(bars_through(2026, 9, 23), now_ms=london_ms(2026, 9, 24, 10), session=mg.FX_SESSION)
    assert reading.status == mg.STATUS_STALE and reading.volatility_ratio is None
    assert "no daily bar yet for today's session (2026-09-24" in reading.detail


def test_a_halt_today_is_not_hidden_by_yesterdays_calm_bars():
    calm_until_yesterday = bars_through(2026, 9, 23)
    assert mg.assess(calm_until_yesterday, now_ms=london_ms(2026, 9, 24, 10)).status == mg.STATUS_OK
    assert mg.assess(calm_until_yesterday, now_ms=london_ms(2026, 9, 24, 10), session=mg.FX_SESSION).status == mg.STATUS_STALE


@pytest.mark.parametrize(
    "now,last_bar",
    [
        (london_ms(2026, 9, 24, 10), (2026, 9, 24)),  # today's partial bar
        (london_ms(2026, 9, 26, 12), (2026, 9, 25)),  # Saturday
        (london_ms(2026, 9, 27, 22, 30), (2026, 9, 25)),  # Sunday evening: no London session day yet
        (london_ms(2026, 12, 3, 15), (2026, 12, 3)),  # a winter (GMT) day
    ],
    ids=["today", "saturday", "sunday-evening", "winter"],
)
def test_outside_a_missing_session_the_last_bar_is_current(now, last_bar):
    assert mg.assess(bars_through(*last_bar), now_ms=now, session=mg.FX_SESSION).status == mg.STATUS_OK


def test_monday_needs_mondays_bar():
    reading = mg.assess(bars_through(2026, 9, 25), now_ms=london_ms(2026, 9, 28, 0, 30), session=mg.FX_SESSION)
    assert reading.status == mg.STATUS_STALE


def test_a_live_buy_with_no_bar_for_today_is_blocked(monkeypatch):
    monkeypatch.setattr(settings, "PAPER_MODE", False)
    monkeypatch.setattr(settings, "MARKET_GUARD_ON_DATA_ERROR", "")
    at(monkeypatch, london_ms(2026, 9, 24, 10))
    use_bars(monkeypatch, bars_through(2026, 9, 23))
    payload = validate("buy")
    assert payload["data"]["result"]["allowed"] is False
    assert payload["data"]["market"]["status"] == "stale"
    assert "today's session" in payload["data"]["market"]["detail"]


def test_a_sell_with_no_bar_for_today_is_not_blocked(monkeypatch):
    """Missing data never blocks a SELL; the halt needs today's move, which is not there to read."""
    monkeypatch.setattr(settings, "PAPER_MODE", False)
    monkeypatch.setattr(settings, "MARKET_GUARD_ON_DATA_ERROR", "")
    at(monkeypatch, london_ms(2026, 9, 24, 10))
    use_bars(monkeypatch, bars_through(2026, 9, 23, maker=mb.spike, move=0.06))
    payload = validate("sell")
    assert payload["data"]["result"]["allowed"] is True
    assert payload["data"]["market"]["status"] == "stale"


def test_get_volatility_status_is_none_without_todays_bar(monkeypatch):
    at(monkeypatch, london_ms(2026, 9, 24, 10))
    monkeypatch.setattr(global_container, "exchange_provider", FakeProvider(bars=bars_through(2026, 9, 23, maker=mb.spike)))
    assert core.get_volatility_status(SYMBOL) is None
    monkeypatch.setattr(global_container, "exchange_provider", FakeProvider(bars=bars_through(2026, 9, 24, maker=mb.spike)))
    assert core.get_volatility_status(SYMBOL) > mg.VOLATILITY_HALT_RATIO


# ---------------------------------------------------------------- the on/off switch


@pytest.mark.parametrize(
    "raw,on",
    [("true", True), ("", True), (None, True), ("treu", True), ("1", True), ("yes", True),
     ("false", False), (" FALSE ", False), ("0", False), ("no", False), ("off", False)],
)
def test_only_an_explicit_off_value_disables_the_guard(raw, on):
    assert safety_switch_on(raw) is on


# ---------------------------------------------------------------- approval-time recheck


@pytest.fixture
def approvals(monkeypatch, quiet_ledger):
    from fastapi.testclient import TestClient

    import app.api_server as api

    monkeypatch.setattr(settings, "PAPER_MODE", True)
    monkeypatch.setattr(settings, "EXECUTION_APPROVAL_MODE", "approve_each")
    executed = []

    class PaperBrokerage:
        def is_available(self):
            return True

        def place_order(self, **kw):
            executed.append(kw)
            return {"status": "filled"}

    monkeypatch.setattr(global_container, "forex_paper_brokerage", PaperBrokerage())
    return TestClient(api.app), executed


def propose(side):
    payload = json.loads(place_stock_order(SYMBOL, side, 10.0, price=1.05))
    assert payload["data"]["status"] == "pending_approval", payload
    return payload["data"]


def approve(client, proposal):
    return client.post(
        "/api/approve-trade",
        json={"request_id": proposal["request_id"], "confirm_token": proposal["confirm_token"], "approve": True},
    )


def test_an_approved_buy_is_rechecked_against_fresh_bars(monkeypatch, approvals):
    client, executed = approvals
    proposal = propose("buy")
    use_bars(monkeypatch, mb.collapse(drop=0.08))  # the pair falls while the proposal waits
    response = approve(client, proposal)
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "risk_blocked"
    assert response.json()["detail"]["market"]["falling_knife"] is True
    assert executed == []


def test_an_approved_sell_is_refused_during_a_volatility_halt(monkeypatch, approvals):
    client, executed = approvals
    proposal = propose("sell")
    use_bars(monkeypatch, mb.spike(move=0.06))
    response = approve(client, proposal)
    assert response.status_code == 409 and "Volatility Halt" in response.json()["detail"]["reason"]
    assert executed == []


def test_an_approved_trade_on_a_calm_tape_executes(approvals):
    client, executed = approvals
    response = approve(client, propose("buy"))
    assert response.status_code == 200 and response.json()["ok"] is True
    assert len(executed) == 1 and executed[0]["side"] == "buy"


def test_the_recheck_uses_the_proposals_sentiment_reading(monkeypatch, approvals):
    client, executed = approvals
    guardian = global_container.risk_guardian
    seen = []
    real = guardian.validate_trade

    def spy(*args, **kwargs):
        seen.append(kwargs.get("sentiment_score"))
        return real(*args, **kwargs)

    monkeypatch.setattr(guardian, "validate_trade", spy)
    payload = json.loads(place_stock_order(SYMBOL, "buy", 10.0, price=1.05, sentiment_score=-0.4))
    assert approve(client, payload["data"]).status_code == 200
    assert seen == [-0.4, -0.4]  # at proposal and again at approval
