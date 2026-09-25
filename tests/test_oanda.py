"""The OANDA connector against a fake v20 API: instruments, units, fills, cancels and OANDA's own error text."""

from unittest.mock import MagicMock, patch

import pytest
import requests

from execution.oanda_service import OandaBrokerage


@pytest.fixture
def oanda(monkeypatch):
    monkeypatch.setenv("OANDA_API_KEY", "token")
    monkeypatch.setenv("OANDA_ACCOUNT_ID", "101-001-1-001")
    monkeypatch.delenv("OANDA_ENVIRONMENT", raising=False)
    return OandaBrokerage()


def reply(status=201, body=None):
    r = MagicMock(status_code=status, text=str(body))
    r.json.return_value = body or {}
    if status >= 400:
        r.raise_for_status.side_effect = requests.HTTPError(f"{status} Client Error", response=r)
    return r


def test_the_practice_api_is_the_default(oanda):
    assert oanda.base_url == "https://api-fxpractice.oanda.com/v3"


@pytest.mark.parametrize("symbol", ["EURUSD", "eur/usd", "EUR_USD", "EURUSD=X"])
def test_a_filled_market_order_uses_oanda_instrument_names(oanda, symbol):
    with patch("execution.oanda_service.requests.post", return_value=reply(201, {"orderFillTransaction": {"id": "7"}})) as post:
        out = oanda.place_order(symbol, "sell", 1000)
    sent = post.call_args.kwargs["json"]["order"]
    assert sent["instrument"] == "EUR_USD" and sent["units"] == "-1000" and out["status"] == "filled"


def test_a_market_order_oanda_cancels_is_a_failure_not_a_submission(oanda):
    body = {"orderCreateTransaction": {"id": "8"}, "orderCancelTransaction": {"id": "9", "reason": "INSUFFICIENT_MARGIN"}}
    with patch("execution.oanda_service.requests.post", return_value=reply(201, body)):
        with pytest.raises(RuntimeError, match="INSUFFICIENT_MARGIN"):
            oanda.place_order("EURUSD", "buy", 1000)


def test_a_limit_order_fills_now_at_its_price_or_better_or_not_at_all(oanda):
    with patch("execution.oanda_service.requests.post", return_value=reply(201, {"orderFillTransaction": {"id": "10"}})) as post:
        assert oanda.place_order("EURUSD", "buy", 1000, order_type="limit", price=1.05)["status"] == "filled"
    sent = post.call_args.kwargs["json"]["order"]
    assert sent == {"units": "1000", "instrument": "EUR_USD", "type": "MARKET", "timeInForce": "FOK", "positionFill": "REDUCE_FIRST", "priceBound": "1.05"}
    body = {"orderCreateTransaction": {"id": "11"}, "orderCancelTransaction": {"id": "12", "reason": "BOUNDS_VIOLATION"}}
    with patch("execution.oanda_service.requests.post", return_value=reply(201, body)):
        with pytest.raises(RuntimeError, match="BOUNDS_VIOLATION"):
            oanda.place_order("EURUSD", "buy", 1000, order_type="limit", price=1.05)


def test_oandas_own_reason_reaches_the_operator(oanda):
    with patch("execution.oanda_service.requests.post", return_value=reply(400, {"errorMessage": "Invalid value specified for 'accountID'"})):
        with pytest.raises(RuntimeError, match="Invalid value specified for 'accountID'"):
            oanda.place_order("EURUSD", "sell", 1000)
    with patch("execution.oanda_service.requests.get", return_value=reply(401, {"errorMessage": "Insufficient authorization to perform request."})):
        with pytest.raises(RuntimeError, match="Insufficient authorization"):
            oanda.get_account_balance()


@pytest.mark.parametrize("qty", [0.4, 0.99])
def test_less_than_one_unit_is_refused_before_anything_is_sent(oanda, qty):
    with patch("execution.oanda_service.requests.post") as post:
        with pytest.raises(RuntimeError, match="whole units"):
            oanda.place_order("EURUSD", "buy", qty)
    post.assert_not_called()


def test_a_symbol_that_is_not_a_pair_is_refused(oanda):
    with patch("execution.oanda_service.requests.post") as post:
        with pytest.raises(RuntimeError, match="currency pairs"):
            oanda.place_order("AAPL", "buy", 1)
    post.assert_not_called()