"""The paper FX account: USD cash, netted positions per pair, P&L converted to USD, margin."""

import pytest

from core.fx_account import FxPaperAccount, notional_usd, parse_pair, usd_per

RATES = {"EURUSD": 1.10, "USDJPY": 150.0, "GBPUSD": 1.25, "EURGBP": 0.88}
U = "agent_zero"


def quote(symbol):
    return RATES[symbol]


@pytest.fixture
def acct(tmp_path):
    a = FxPaperAccount(db_path=str(tmp_path / "paper.db"), quote=quote, leverage=30)
    a.deposit(U, "USD", 100_000)
    return a


@pytest.mark.parametrize("raw", ["EURUSD", "EUR/USD", "eur_usd", "EURUSD=X", " eurusd "])
def test_pairs_parse_in_every_common_spelling(raw):
    assert parse_pair(raw) == ("EUR", "USD")


@pytest.mark.parametrize("raw", ["AAPL", "EUR", "EURUSDX", "USDUSD", ""])
def test_a_non_pair_is_refused(raw):
    with pytest.raises(ValueError):
        parse_pair(raw)


def test_usd_rates_use_the_direct_or_the_inverse_pair():
    assert usd_per("USD", quote) == 1.0
    assert usd_per("EUR", quote) == pytest.approx(1.10)
    assert usd_per("JPY", quote) == pytest.approx(1 / 150.0)
    with pytest.raises(ValueError):
        usd_per("TRY", quote)


def test_notional_is_the_base_currency_in_usd():
    assert notional_usd("USDJPY", 4_000, quote) == pytest.approx(4_000)
    assert notional_usd("EURUSD", 1_000, quote) == pytest.approx(1_100)
    assert notional_usd("EURGBP", 1_000, quote) == pytest.approx(1_100)


def test_a_round_trip_realizes_pnl_in_usd(acct):
    acct.execute_trade(U, "buy", "EURUSD", 10_000, 1.10)
    RATES["EURUSD"] = 1.12
    try:
        assert acct.account(U)["unrealized_usd"] == pytest.approx(200.0)
        msg = acct.execute_trade(U, "sell", "EURUSD", 10_000, 1.12)
        assert "Realized P&L: 200.00 USD" in msg and "flat EURUSD" in msg
        state = acct.account(U)
        assert state["cash_usd"] == pytest.approx(100_200.0) and state["positions"] == []
    finally:
        RATES["EURUSD"] = 1.10


def test_jpy_pnl_is_converted_at_the_usdjpy_rate(acct):
    acct.execute_trade(U, "sell", "USDJPY", 10_000, 151.5)  # short USD, long JPY
    state = acct.account(U)  # marked at 150.0: (150 - 151.5) * -10,000 JPY = +15,000 JPY = +100 USD
    assert state["unrealized_usd"] == pytest.approx(100.0)
    assert state["positions"][0]["qty"] == -10_000


def test_a_sell_larger_than_the_long_flips_to_a_short_at_the_fill(acct):
    acct.execute_trade(U, "buy", "GBPUSD", 1_000, 1.20)
    acct.execute_trade(U, "sell", "GBPUSD", 3_000, 1.25)
    (pos,) = acct.account(U)["positions"]
    assert pos["qty"] == -2_000 and pos["avg_price"] == pytest.approx(1.25)
    assert acct.account(U)["cash_usd"] == pytest.approx(100_050.0)  # +0.05 x 1,000 realized


def test_an_order_beyond_the_margin_is_refused_and_changes_nothing(acct):
    msg = acct.execute_trade(U, "buy", "EURUSD", 3_000_000, 1.10)  # 3.3M notional / 30 = 110k margin
    assert msg.startswith("Insufficient margin")
    assert acct.account(U)["positions"] == [] and acct.get_balances(U) == {"USD": 100_000.0}


def test_reducing_a_position_needs_no_free_margin(acct):
    acct.execute_trade(U, "buy", "EURUSD", 2_000_000, 1.10)  # 73.3k margin of 100k
    RATES["EURUSD"] = 1.08  # -40k: equity 60k < margin 72k
    try:
        assert acct.account(U)["free_margin_usd"] < 0
        assert acct.execute_trade(U, "sell", "EURUSD", 1_000_000, 1.08).startswith("Paper Trade Executed")
    finally:
        RATES["EURUSD"] = 1.10


def test_only_usd_can_be_deposited(acct):
    with pytest.raises(ValueError):
        acct.deposit(U, "EUR", 100)


def test_the_account_persists_and_is_shared(acct):
    acct.execute_trade(U, "buy", "EURUSD", 1_000, 1.10)
    other = FxPaperAccount(db_path=acct.db_path, quote=quote)  # e.g. the API server's process
    assert other.get_balances(U) == {"USD": 100_000.0, "EURUSD": 1_000.0}


def test_risk_metrics_are_net_of_deposits(acct):
    acct.execute_trade(U, "buy", "EURUSD", 100_000, 1.10)
    RATES["EURUSD"] = 1.045  # -5,500 on 100k equity
    try:
        m = acct.get_risk_metrics(U)
        assert m["equity"] == pytest.approx(94_500.0)
        assert m["daily_pnl_pct"] == pytest.approx(-0.055, abs=1e-3)
        assert m["drawdown_pct"] == pytest.approx(0.055, abs=1e-3)  # 5,500 below the 100k peak
        acct.deposit(U, "USD", 50_000)  # new money is neither a gain nor the end of the drawdown
        after = acct.get_risk_metrics(U)
        assert after["daily_pnl_pct"] == pytest.approx(-0.055, abs=1e-3)
        assert after["drawdown_pct"] == pytest.approx(0.055, abs=1e-3)
    finally:
        RATES["EURUSD"] = 1.10


def test_reset_clears_everything(acct):
    acct.execute_trade(U, "buy", "EURUSD", 1_000, 1.10)
    acct.reset_wallet(U)
    assert acct.get_balances(U) == {"USD": 0.0} and acct.get_risk_metrics(U)["equity"] == 0.0


@pytest.mark.parametrize("side,amount,price", [("hold", 1, 1.1), ("buy", 0, 1.1), ("buy", 1, 0), ("sell", -5, 1.1)])
def test_malformed_trades_raise(acct, side, amount, price):
    with pytest.raises(ValueError):
        acct.execute_trade(U, side, "EURUSD", amount, price)


@pytest.mark.parametrize("value", ["abc", "0", "-5", "nan", "inf"])
def test_a_bad_leverage_is_refused_by_name(monkeypatch, tmp_path, value):
    monkeypatch.setenv("LEVERAGE", value)
    with pytest.raises(ValueError, match="LEVERAGE must be a positive number"):
        FxPaperAccount(db_path=str(tmp_path / "paper.db"))
