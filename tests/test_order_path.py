"""
The order path as a client uses it: paper fills in the shared FX account, how an order is valued for
the size rule, the switches and policy every live order must pass, and the approval API. Rates come
from conftest.TEST_RATES; live orders reach a fake brokerage only.
"""

import json
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

import app.tools.execution as execution
from app.core.config import settings
from app.core.container import global_container
from execution.store import ExecutionStore

U = "agent_zero"


@pytest.fixture(autouse=True)
def quiet(monkeypatch):
    monkeypatch.setattr(execution.global_compliance_ledger, "record_event", MagicMock())


@pytest.fixture
def funded():
    global_container.paper_engine.deposit(U, "USD", 100_000)
    return global_container.paper_engine


def ok(payload):
    body = json.loads(payload)
    assert body["ok"] is True, body
    return body["data"]


def err(payload):
    body = json.loads(payload)
    assert body["ok"] is False, body
    return body["error"]


# ---------------------------------------------------------------- paper fills


def test_a_paper_market_order_fills_at_the_latest_rate(funded):
    data = ok(execution.place_market_order("EUR/USD", "buy", 1_000))
    assert "BUY 1000 EURUSD @ 1.10440" in data["result"]
    assert funded.get_balances(U) == {"USD": 100_000.0, "EURUSD": 1_000.0}


def test_a_usd_based_pair_fills_too(funded):
    assert "USDJPY @ 150.00000" in ok(execution.place_forex_order("USDJPY", "buy", 4_000))["result"]


def test_a_buy_limit_below_the_market_does_not_fill(funded):
    e = err(execution.place_limit_order("EURUSD", "buy", 1_000, 0.5))
    assert e["code"] == "limit_not_marketable" and funded.get_balances(U) == {"USD": 100_000.0}


def test_a_marketable_limit_fills_at_the_market_not_the_limit(funded):
    assert "@ 1.10440" in ok(execution.place_limit_order("EURUSD", "buy", 1_000, 1.2))["result"]


def test_an_order_beyond_the_margin_is_an_error(funded, monkeypatch):
    monkeypatch.setattr(global_container.risk_guardian, "validate_trade", lambda *a, **k: {"allowed": True})
    assert err(execution.place_market_order("EURUSD", "buy", 5_000_000))["code"] == "insufficient_margin"


def test_paper_mode_trades_currency_pairs_only(funded):
    e = err(execution.place_stock_order("AAPL", "buy", 1))
    assert e["code"] == "invalid_request" and "currency pair" in e["message"]


@pytest.mark.parametrize(
    "side,amount,order_type,price,fragment",
    [
        ("hold", 1, "market", 0, "side must be"),
        ("buy", -5, "market", 0, "amount"),
        ("buy", 1, "stop", 0, "order_type"),
        ("buy", 1, "limit", 0, "positive price"),
    ],
)
def test_a_malformed_order_is_refused_before_anything_runs(funded, side, amount, order_type, price, fragment):
    e = err(execution.place_stock_order("EURUSD", side, amount, price=price, order_type=order_type))
    assert e["code"] == "invalid_request" and fragment in e["message"]
    assert funded.get_balances(U) == {"USD": 100_000.0}


@pytest.mark.parametrize("asset,amount", [("USD", -50_000), ("USD", 0), ("USD", float("nan")), ("EUR", 100)])
def test_a_deposit_must_be_positive_usd(asset, amount):
    assert err(execution.deposit_paper_funds(asset, amount))["code"] == "invalid_request"


# ---------------------------------------------------------------- the size rule


def test_an_order_is_valued_at_its_usd_notional_against_the_real_account(funded):
    # 4,000 USDJPY is $4,000: 4% of the account. It used to read 4,000 x 150 = $600,000.
    check = execution.pre_trade_check("USDJPY", "buy", 4_000)
    assert check["allowed"] is True and check["notional_usd"] == pytest.approx(4_000)
    assert execution.pre_trade_check("EURUSD", "buy", 1_000)["notional_usd"] == pytest.approx(1_104.4)


def test_a_small_account_cannot_put_more_than_5pct_on_one_trade():
    global_container.paper_engine.deposit(U, "USD", 1_000)
    check = execution.pre_trade_check("USDJPY", "buy", 4_000)
    assert check["allowed"] is False and "Position size too large" in check["reason"]


def test_a_buy_that_cannot_be_sized_fails_closed(funded):
    check = execution.pre_trade_check("TRYUSD", "buy", 1_000)  # no TRY rate in TEST_RATES
    assert check["allowed"] is False and "Could not value" in check["reason"]


def test_an_empty_account_cannot_buy():
    assert "equity" in execution.pre_trade_check("EURUSD", "buy", 1_000)["reason"]


# ---------------------------------------------------------------- live mode


class FakeBroker:
    def __init__(self, available=True, equity=100_000.0):
        self.available, self.orders, self.equity = available, [], equity

    def is_available(self):
        return self.available

    def get_account_balance(self):
        return {"equity": self.equity}

    def place_order(self, **kw):
        self.orders.append(kw)
        return {"id": "fake-1", **kw}


# The approval API approves a live proposal only with the operator token (the agent holds the
# confirm_token, so on its own that token never proved a human approved).
OPERATOR_TOKEN = "test-operator-token"
HEADERS = {"Authorization": f"Bearer {OPERATOR_TOKEN}"}


@pytest.fixture
def live(monkeypatch):
    broker = FakeBroker()
    monkeypatch.setenv("API_OPERATOR_TOKEN", OPERATOR_TOKEN)
    monkeypatch.setattr(settings, "PAPER_MODE", False)
    monkeypatch.setattr(settings, "MARKET_GUARD_ON_DATA_ERROR", "")
    monkeypatch.setattr(settings, "LIVE_TRADING_ENABLED", True)
    monkeypatch.setattr(settings, "TRADING_HALTED", False)
    monkeypatch.setitem(global_container.brokerages, "oanda", broker)
    return broker


def test_a_live_order_reaches_the_brokerage_with_its_order_type(live):
    ok(execution.place_forex_order("EURUSD", "buy", 1_000, order_type="limit", price=1.1))
    assert live.orders == [{"symbol": "EURUSD", "side": "buy", "qty": 1_000.0, "order_type": "limit", "price": 1.1}]


def test_a_live_order_needs_live_trading_enabled(monkeypatch, live):
    monkeypatch.setattr(settings, "LIVE_TRADING_ENABLED", False)
    assert err(execution.place_forex_order("EURUSD", "sell", 1_000))["code"] == "live_trading_disabled"
    assert live.orders == []


def test_the_kill_switch_halts_live_orders(monkeypatch, live):
    monkeypatch.setattr(settings, "TRADING_HALTED", True)
    assert err(execution.place_forex_order("EURUSD", "sell", 1_000))["code"] == "trading_halted"
    assert live.orders == []


@pytest.mark.parametrize(
    "env,code",
    [
        ({"MAX_BROKERAGE_ORDER_AMOUNT": "500"}, "order_amount_too_large"),
        ({"MAX_BROKERAGE_ORDER_AMOUNT": "1,000"}, "invalid_policy_config"),
        ({"ALLOW_BROKERAGE_SYMBOLS": "GBPUSD"}, "symbol_not_allowed"),
        ({"ALLOW_EXCHANGES": "alpaca"}, "exchange_not_allowed"),
    ],
)
def test_a_live_policy_refusal_names_the_rule(monkeypatch, live, env, code):
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    assert err(execution.place_forex_order("EUR/USD", "sell", 1_000))["code"] == code
    assert live.orders == []


def test_the_symbol_allowlist_matches_any_spelling_of_the_pair(monkeypatch, live):
    monkeypatch.setenv("ALLOW_BROKERAGE_SYMBOLS", "EURUSD")
    ok(execution.place_forex_order("EUR/USD", "sell", 1_000))


def test_a_live_order_is_sized_against_the_brokerage_account(monkeypatch, live):
    monkeypatch.setitem(global_container.brokerages, "oanda", FakeBroker(equity=1_000.0))
    e = err(execution.place_forex_order("USDJPY", "buy", 4_000))
    assert e["code"] == "risk_blocked" and "Position size too large" in e["message"]


def test_a_live_order_without_keys_is_refused(monkeypatch, live):
    broker = FakeBroker(available=False)
    monkeypatch.setitem(global_container.brokerages, "oanda", broker)
    for side in ("buy", "sell"):
        assert err(execution.place_forex_order("EURUSD", side, 1_000))["code"] == "brokerage_not_configured"
    assert broker.orders == []


# ---------------------------------------------------------------- the approval API


@pytest.fixture
def api():
    import app.api_server as api_server

    return TestClient(api_server.app, headers=HEADERS)


def propose(monkeypatch, *args, **kwargs):
    monkeypatch.setattr(settings, "EXECUTION_APPROVAL_MODE", "approve_each")
    data = ok(execution.place_forex_order(*args, **kwargs))
    assert data["status"] == "pending_approval"
    return data


def approve(api, proposal, approve=True, token=None):
    return api.post(
        "/api/approve-trade",
        json={"request_id": proposal["request_id"], "confirm_token": token or proposal["confirm_token"], "approve": approve},
    )


def test_an_approval_executes_in_the_agents_paper_account(monkeypatch, funded, api):
    proposal = propose(monkeypatch, "EURUSD", "buy", 1_000)
    response = approve(api, proposal)
    assert response.status_code == 200 and response.json()["ok"] is True
    assert funded.get_balances(U)["EURUSD"] == 1_000.0


def test_the_portfolio_view_is_the_agents_account(funded, api):
    execution.place_market_order("EURUSD", "buy", 1_000)
    body = api.get("/api/portfolio").json()
    assert body["balances"] == {"USD": 100_000.0, "EURUSD": 1_000.0}
    assert body["metrics"]["equity"] == pytest.approx(100_000.0)
    assert body["positions"][0]["symbol"] == "EURUSD"


def test_an_approved_live_proposal_still_passes_the_policy(monkeypatch, live, api):
    proposal = propose(monkeypatch, "EURUSD", "sell", 1_000)
    monkeypatch.setenv("MAX_BROKERAGE_ORDER_AMOUNT", "10")
    response = approve(api, proposal)
    assert response.status_code == 409 and response.json()["detail"]["code"] == "order_amount_too_large"
    assert live.orders == []


def test_cancelling_needs_the_confirm_token(monkeypatch, funded, api):
    proposal = propose(monkeypatch, "EURUSD", "buy", 1_000)
    assert approve(api, proposal, approve=False, token="guess").json() == {"ok": False}
    assert approve(api, proposal, approve=False).json() == {"ok": True}


def test_a_foreign_web_page_gets_no_cors_grant(api):
    assert "access-control-allow-origin" not in api.get("/api/health", headers={"Origin": "https://evil.example"}).headers
    assert api.get("/api/health", headers={"Origin": "http://localhost:3000"}).headers["access-control-allow-origin"] == "http://localhost:3000"


def test_a_shared_session_id_lets_the_api_see_the_servers_proposals(monkeypatch, tmp_path):
    monkeypatch.setenv("EXECUTION_DB_PATH", str(tmp_path / "execution.db"))
    monkeypatch.setenv("EXECUTION_SESSION_ID", "desk-1")
    mcp_store, api_store = ExecutionStore(), ExecutionStore()
    proposal = mcp_store.create(kind="stock_order", payload={"symbol": "EURUSD"})
    assert [p["request_id"] for p in api_store.list_pending()["pending"]] == [proposal.request_id]


def test_a_live_order_cannot_be_filled_by_a_simulator(live):
    # The old in-memory simulator answered live orders with status "filled" (_deprecated/forex_paper.py).
    assert "forex_paper" not in global_container.brokerages
    assert err(execution.place_forex_order("EURUSD", "buy", 1_000, exchange="forex_paper"))["code"] == "brokerage_not_supported"
    assert live.orders == []


def test_approval_errors_say_which_problem_it_is(monkeypatch, funded, api):
    assert approve(api, {"request_id": "nope", "confirm_token": "x"}).status_code == 404
    proposal = propose(monkeypatch, "EURUSD", "buy", 1_000)
    assert approve(api, proposal, token="guess").status_code == 403
    assert approve(api, proposal).status_code == 200
    assert approve(api, proposal).status_code == 409  # already approved


def test_every_order_tool_defaults_to_the_fx_venue(live):
    ok(execution.place_stock_order("EURUSD", "sell", 1_000))  # no exchange given
    assert live.orders and live.orders[-1]["symbol"] == "EURUSD"  # reached the oanda fake


# ---------------------------------------------------------------- exposure, not side (FX goes both ways)


def test_a_position_bigger_than_one_trade_can_be_closed_in_one_order(funded):
    for _ in range(3):
        ok(execution.place_market_order("EURUSD", "buy", 4_000))
    ok(execution.place_market_order("EURUSD", "sell", 12_000))  # 13% of the account, but an exit
    assert funded.position(U, "EURUSD") == 0


def test_a_flip_is_sized_by_the_part_that_opens_the_new_position(funded):
    ok(execution.place_market_order("EURUSD", "buy", 4_000))
    check = execution.pre_trade_check("EURUSD", "sell", 7_000)
    assert check["allowed"] and check["exposure_added_units"] == 3_000
    assert check["notional_usd"] == pytest.approx(3_000 * 1.1044)
    assert not execution.pre_trade_check("EURUSD", "sell", 12_000)["allowed"]  # opens an 8,000 short: 8.8%


def test_after_the_drawdown_limit_only_orders_that_reduce_a_position_pass(funded, monkeypatch):
    for _ in range(10):
        ok(execution.place_market_order("EURUSD", "sell", 4_000))  # a 40,000 EUR short
    monkeypatch.setattr(funded, "get_risk_metrics", lambda user: {"equity": 88_000.0, "daily_pnl_pct": -0.11, "drawdown_pct": 0.124})
    ok(execution.place_market_order("EURUSD", "buy", 3_000))  # covering part of the short
    e = err(execution.place_market_order("EURUSD", "sell", 3_000))  # adding to it
    assert e["code"] == "risk_blocked" and "add exposure" in e["message"]


def test_a_live_sell_that_opens_a_short_is_sized_even_without_equity(monkeypatch, live):
    class NoBalance(FakeBroker):
        def get_account_balance(self):
            raise RuntimeError("OANDA balance fetch failed: HTTP 503")

        def list_positions(self):
            return []

    broker = NoBalance()
    monkeypatch.setitem(global_container.brokerages, "oanda", broker)
    e = err(execution.place_forex_order("EURUSD", "sell", 10_000_000))
    assert e["code"] == "risk_blocked" and "equity" in e["message"] and broker.orders == []
    assert err(execution.place_forex_order("TRYUSD", "sell", 50_000))["code"] == "risk_blocked"


def test_a_live_exit_needs_no_equity(monkeypatch, live):
    class Long(FakeBroker):
        def get_account_balance(self):
            raise RuntimeError("down")

        def list_positions(self):
            return [{"symbol": "EUR_USD", "qty": 5_000.0}]

    broker = Long()
    monkeypatch.setitem(global_container.brokerages, "oanda", broker)
    ok(execution.place_forex_order("EURUSD", "sell", 5_000))
    assert broker.orders[-1]["side"] == "sell"


def test_a_paper_proposal_never_executes_live(monkeypatch, funded, api):
    proposal = propose(monkeypatch, "EURUSD", "buy", 1_000)
    broker = FakeBroker()
    monkeypatch.setenv("API_OPERATOR_TOKEN", OPERATOR_TOKEN)
    monkeypatch.setattr(settings, "PAPER_MODE", False)
    monkeypatch.setattr(settings, "LIVE_TRADING_ENABLED", True)
    monkeypatch.setitem(global_container.brokerages, "oanda", broker)
    response = approve(api, proposal)
    assert response.status_code == 409 and response.json()["detail"]["code"] == "mode_mismatch"
    assert broker.orders == []


def test_the_pending_list_shows_the_order_but_never_the_token(monkeypatch, funded, api):
    proposal = propose(monkeypatch, "EURUSD", "buy", 1_000)
    pending = [p for p in api.get("/api/pending-approvals").json()["pending"] if p["request_id"] == proposal["request_id"]]
    assert pending[0]["order"]["symbol"] == "EURUSD" and pending[0]["order"]["side"] == "buy"
    assert pending[0]["order"]["amount"] == 1_000 and pending[0]["order"]["paper_mode"] is True
    assert proposal["confirm_token"] not in json.dumps(pending)


def test_a_web_page_elsewhere_cannot_open_the_websocket(api):
    from starlette.websockets import WebSocketDisconnect

    with pytest.raises(WebSocketDisconnect):
        with api.websocket_connect("/ws", headers={"Origin": "https://evil.example"}):
            pass
    with api.websocket_connect("/ws", headers={"Origin": "http://localhost:3000"}):
        pass


@pytest.mark.parametrize("allow", ["EUR/USD", "eur_usd", "EURUSD"])
def test_the_symbol_allowlist_accepts_any_spelling(monkeypatch, live, allow):
    monkeypatch.setenv("ALLOW_BROKERAGE_SYMBOLS", allow)
    ok(execution.place_forex_order("EURUSD", "sell", 1_000))