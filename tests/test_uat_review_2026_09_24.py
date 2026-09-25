"""
Regression tests for the cross-repository review of the 2026-09-24 UAT (uat/runs/2026-09-24-01,
checks XR-01..XR-14): defect classes found in ReadyTrader-Crypto, checked here. Each fails on the
code before its fix. Live orders reach a fake brokerage only; the OANDA connector talks to a patched
HTTP client.
"""

import json
import math
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import market_bars
import pytest
import yaml
from fastapi.testclient import TestClient

import app.api_server as api
import app.tools.execution as execution
import app.tools.trading as trading
from app.core.config import settings
from app.core.container import global_container
from core.fx_account import FxPaperAccount
from execution.oanda_service import OandaBrokerage
from observability import log_event

REPO = Path(__file__).resolve().parents[1]
U = "agent_zero"
OPERATOR = {"Authorization": "Bearer review-operator-token"}


class Broker:
    def __init__(self, positions=None, equity=100_000.0):
        self.orders, self.positions, self.equity = [], positions or [], equity

    def is_available(self):
        return True

    def get_account_balance(self):
        return {"equity": self.equity, "cash": self.equity}

    def list_positions(self):
        return list(self.positions)

    def place_order(self, **kw):
        self.orders.append(kw)
        return {"id": "fake", **kw}


@pytest.fixture(autouse=True)
def quiet(monkeypatch):
    monkeypatch.setattr(execution.global_compliance_ledger, "record_event", MagicMock())


@pytest.fixture
def live(monkeypatch):
    broker = Broker()
    monkeypatch.setenv("API_OPERATOR_TOKEN", "review-operator-token")
    for key, value in dict(PAPER_MODE=False, LIVE_TRADING_ENABLED=True, TRADING_HALTED=False, MARKET_GUARD_ON_DATA_ERROR="").items():
        monkeypatch.setattr(settings, key, value)
    monkeypatch.setitem(global_container.brokerages, "oanda", broker)
    monkeypatch.setitem(global_container.brokerages, "alpaca", broker)
    return broker


@pytest.fixture
def rates(monkeypatch):
    """Quotes the test can move: the paper account and the order checks read them."""
    table = {"EURUSD": 1.10, "GBPUSD": 1.25, "USDJPY": 150.0}

    def fetch_ticker(symbol):
        key = str(symbol).upper().replace("/", "").replace("_", "")
        if key not in table:
            raise ValueError(f"no rate for {symbol}")
        return {"symbol": key, "last": table[key], "close": table[key]}

    monkeypatch.setattr(global_container.exchange_provider, "fetch_ticker", fetch_ticker)
    return table


def _j(out):
    return json.loads(out)


# ------------------------------------------------------------------------------ XR-01


@pytest.mark.parametrize("spelling", ["EURUSD", "EUR/USD", "EUR_USD", "eur-usd"])
def test_every_spelling_of_a_pair_gets_the_same_market_checks(live, monkeypatch, spelling):
    def bars(symbol):  # the market-data source knows the pair under one name only, as Yahoo does
        if symbol != "EURUSD":
            raise ValueError(f"no bars for {symbol}")
        return market_bars.spike()  # volatility about 7x normal: the halt applies to both sides

    monkeypatch.setattr(trading, "_fetch_daily_bars", bars)
    out = _j(execution.place_forex_order(spelling, "sell", 4_000))
    assert out["error"]["code"] == "risk_blocked" and "olatility" in out["error"]["message"], out
    assert live.orders == []


# ------------------------------------------------------------------------------ XR-02


def test_a_live_limit_order_never_rests_at_oanda(monkeypatch):
    monkeypatch.setenv("OANDA_API_KEY", "token")
    monkeypatch.setenv("OANDA_ACCOUNT_ID", "101-001-1-001")
    reply = MagicMock(status_code=201)
    reply.json.return_value = {"orderFillTransaction": {"id": "1"}}
    with patch("execution.oanda_service.requests.post", return_value=reply) as post:
        OandaBrokerage().place_order("EURUSD", "sell", 100_000, order_type="limit", price=1.20)
    sent = post.call_args.kwargs["json"]["order"]
    assert (sent["type"], sent["timeInForce"], sent["priceBound"], sent["positionFill"]) == ("MARKET", "FOK", "1.2", "REDUCE_FIRST")
    assert "price" not in sent


# ------------------------------------------------------------------------------ XR-03


def test_an_order_at_any_brokerage_is_valued_at_the_market(live, rates):
    rates["AAPL"] = 190.0
    out = _j(execution.place_stock_order("AAPL", "buy", 10_000, price=0.0001, exchange="alpaca"))
    assert out["error"]["code"] == "risk_blocked" and "Position size" in out["error"]["message"], out
    assert out["error"]["data"]["reference_price"] == pytest.approx(190.0)
    limit = execution.pre_trade_check("AAPL", "sell", 10_000, 1.0, exchange="alpaca", order_type="limit")
    assert limit["allowed"] is False and limit["reference_price"] == pytest.approx(190.0)
    assert live.orders == []


def test_without_a_market_price_an_order_that_adds_exposure_is_refused(live, rates, monkeypatch):
    monkeypatch.setattr(trading, "_fetch_daily_bars", lambda s: (_ for _ in ()).throw(RuntimeError("no bars")))
    out = _j(execution.place_stock_order("AAPL", "sell", 10_000, price=0.01, order_type="limit", exchange="alpaca"))
    assert out["error"]["code"] == "risk_blocked" and "Could not value" in out["error"]["message"], out
    assert live.orders == []


# ------------------------------------------------------------------------------ XR-04 / XR-07


def _account(tmp_path, table):
    return FxPaperAccount(db_path=str(tmp_path / "fx.db"), quote=lambda s: table[s])


def test_a_deposit_does_not_end_a_drawdown_halt(tmp_path):
    table = {"EURUSD": 1.10}
    e = _account(tmp_path, table)
    e.deposit(U, "USD", 100_000)
    e.execute_trade(U, "buy", "EURUSD", 1_000_000, 1.10)
    table["EURUSD"] = 1.085  # -15,000: 15% below the peak
    assert e.get_risk_metrics(U)["drawdown_pct"] == pytest.approx(0.15, abs=1e-6)
    e.deposit(U, "USD", 1_000_000)
    m = e.get_risk_metrics(U)
    assert m["drawdown_pct"] == pytest.approx(0.15, abs=1e-6) and m["daily_pnl_pct"] == pytest.approx(-0.15, abs=1e-6)


def test_a_small_loss_after_a_large_top_up_is_a_small_loss(tmp_path):
    table = {"EURUSD": 1.10}
    e = _account(tmp_path, table)
    e.deposit(U, "USD", 1_000)
    e.execute_trade(U, "buy", "EURUSD", 10_000, 1.10)
    table["EURUSD"] = 1.099  # -10 on 1,000: -1%
    e.deposit(U, "USD", 1_000_000)
    e.execute_trade(U, "buy", "EURUSD", 990_000, 1.099)
    table["EURUSD"] = 1.098  # -1,000 on about 1,001,000: -0.1%
    daily = e.get_risk_metrics(U)["daily_pnl_pct"]
    assert -0.012 < daily < -0.01  # about -1.1% (it read -101%: the loss over the first 1,000)


def test_a_week_old_snapshot_is_not_the_start_of_today(tmp_path, monkeypatch):
    table = {"EURUSD": 1.10}
    e = _account(tmp_path, table)
    e.deposit(U, "USD", 100_000)
    e.execute_trade(U, "buy", "EURUSD", 500_000, 1.10)
    table["EURUSD"] = 1.0857  # -7,150 over the week
    conn = sqlite3.connect(e.db_path)
    conn.execute("UPDATE fx_equity SET ts='2026-09-17T12:00:00+00:00'")
    conn.commit()
    conn.close()
    monkeypatch.setattr(e, "_now", lambda: "2026-09-24T12:00:00+00:00")
    e.mark_day_open(U)
    m = e.get_risk_metrics(U)
    assert m["daily_pnl_pct"] == pytest.approx(0.0, abs=1e-12) and m["drawdown_pct"] == pytest.approx(0.0715, abs=1e-4)


def test_the_order_check_halts_on_a_drawdown_a_deposit_cannot_hide(rates):
    paper = global_container.paper_engine
    paper.deposit(U, "USD", 100_000)
    paper.execute_trade(U, "buy", "EURUSD", 1_000_000, 1.10)
    rates["EURUSD"] = 1.085  # -15,000, three days ago: not today's loss, still a 15% drawdown
    with paper._conn() as c:
        paper._snapshot(c, U)
    earlier = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
    conn = sqlite3.connect(paper.db_path)
    conn.execute("UPDATE fx_equity SET ts=?", (earlier,))
    conn.commit()
    conn.close()
    paper.deposit(U, "USD", 1_000_000)  # today
    check = execution.pre_trade_check("GBPUSD", "buy", 1_000)
    assert check["allowed"] is False and "Drawdown" in check["reason"], check["reason"]


# ------------------------------------------------------------------------------ XR-05


def test_live_orders_say_which_loss_rules_do_not_run(live):
    inactive = execution.pre_trade_check("EURUSD", "buy", 1_000)["inactive_rules"]
    assert {"daily_loss_limit", "max_drawdown"} <= set(inactive)
    for doc, marker in (("README.md", "paper account only"), ("docs/THREAT_MODEL.md", "paper account only"), ("RUNBOOK.md", "paper account only")):
        assert marker in (REPO / doc).read_text(), doc


# ------------------------------------------------------------------------------ XR-06


def test_a_live_proposal_needs_the_operator_token(live, monkeypatch):
    monkeypatch.setattr(settings, "EXECUTION_APPROVAL_MODE", "approve_each")
    proposal = _j(execution.place_forex_order("EURUSD", "buy", 1_000))["data"]
    body = {"request_id": proposal["request_id"], "confirm_token": proposal["confirm_token"], "approve": True}
    assert TestClient(api.app).post("/api/approve-trade", json=body).status_code == 401  # the agent's token alone
    monkeypatch.delenv("API_OPERATOR_TOKEN")
    denied = TestClient(api.app).post("/api/approve-trade", json=body)
    assert denied.status_code == 403 and denied.json()["detail"]["code"] == "operator_token_required"
    assert live.orders == []
    monkeypatch.setenv("API_OPERATOR_TOKEN", "review-operator-token")
    assert TestClient(api.app, headers=OPERATOR).post("/api/approve-trade", json=body).status_code == 200
    assert len(live.orders) == 1


# ------------------------------------------------------------------------------ XR-08


def test_an_unpriceable_position_does_not_hide_a_loss(rates, monkeypatch):
    paper = global_container.paper_engine
    paper.deposit(U, "USD", 100_000)
    paper.execute_trade(U, "buy", "EURUSD", 1_000_000, 1.10)
    rates["EURUSD"] = 1.085  # a 15% loss the snapshots never saw
    del rates["EURUSD"]  # and now EURUSD cannot be priced
    assert paper.get_risk_metrics(U)["equity"] is None
    check = execution.pre_trade_check("GBPUSD", "buy", 1_000)
    assert check["allowed"] is False and "cannot be priced" in check["reason"]


# ------------------------------------------------------------------------------ XR-09


def test_a_market_orders_price_is_ignored_and_the_pending_list_still_answers(monkeypatch):
    global_container.paper_engine.deposit(U, "USD", 100_000)
    monkeypatch.setattr(settings, "EXECUTION_APPROVAL_MODE", "approve_each")
    out = _j(execution.place_forex_order("EURUSD", "buy", 1_000, price=float("nan")))
    assert out["ok"] is True and out["data"]["order_details"]["price"] == 0.0
    assert TestClient(api.app).get("/api/pending-approvals").status_code == 200


# ------------------------------------------------------------------------------ XR-10


def test_the_kill_switch_docs_say_what_it_refuses_and_how_to_flatten():
    text = (REPO / "RUNBOOK.md").read_text() + (REPO / "docs/THREAT_MODEL.md").read_text()
    assert "closing" in text and "OANDA platform" in text
    assert "fill-or-kill" in (REPO / "README.md").read_text()


# ------------------------------------------------------------------------------ XR-11


def test_the_docker_build_context_leaves_out_secrets_in_any_folder():
    rules = {line.strip() for line in (REPO / ".dockerignore").read_text().splitlines()}
    assert {"**/.env*", "**/*.pem", "**/*.key", "**/*.db", "**/__pycache__/", "frontend/"} <= rules
    assert "USER readytrader" in (REPO / "Dockerfile").read_text()


# ------------------------------------------------------------------------------ XR-12


def test_api_responses_carry_a_request_id_and_hide_internal_errors(monkeypatch):
    client = TestClient(api.app, raise_server_exceptions=False)
    a, b = client.get("/api/health"), client.get("/api/health")
    assert a.headers["x-request-id"] != b.headers["x-request-id"] and a.headers["x-frame-options"] == "DENY"

    def boom(*args, **kwargs):
        raise RuntimeError("secret internal detail: /home/op/.env line 3")

    monkeypatch.setattr(type(global_container.paper_engine), "account", boom)
    r = client.get("/api/portfolio")
    assert r.status_code == 500 and r.headers["x-request-id"] and "secret" not in r.text
    assert r.json()["detail"]["code"] == "internal_error"


def test_each_log_line_carries_its_own_time(capsys, monkeypatch):
    import observability.logging as obs

    ctx = {"request_id": "fixed", "ts_ms": 1}
    clock = iter([1_000.0, 2_000.0])
    monkeypatch.setattr(obs.time, "time", lambda: next(clock))
    log_event("a", ctx=ctx)
    log_event("b", ctx=ctx)
    lines = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert [line["ts_ms"] for line in lines] == [1_000_000, 2_000_000]


# ------------------------------------------------------------------------------ XR-13


def test_odd_numbers_are_refused():
    for amount in (1.7e308, float("inf"), 2e12):
        assert _j(execution.deposit_paper_funds("USD", amount))["error"]["code"] == "invalid_request"
    assert math.isfinite(global_container.paper_engine.account(U)["equity_usd"])
    assert _j(execution.deposit_paper_funds("USD", True))["error"]["code"] == "invalid_request"
    assert _j(execution.place_forex_order("EURUSD", "buy", True))["error"]["code"] == "invalid_request"
    for score in (float("nan"), float("inf")):
        assert _j(execution.place_forex_order("EURUSD", "buy", 1_000, sentiment_score=score))["error"]["code"] == "invalid_request"


def test_an_mcp_client_cannot_send_true_as_a_number():
    import asyncio

    from fastmcp import Client

    from app.main import mcp

    async def calls():
        async with Client(mcp) as client:
            return [
                await client.call_tool(tool, args, raise_on_error=False)
                for tool, args in (
                    ("place_market_order", {"symbol": "EURUSD", "side": "buy", "amount": True}),
                    ("deposit_paper_funds", {"asset": "USD", "amount": True}),
                    ("validate_trade_risk", {"side": "buy", "symbol": "EURUSD", "amount_usd": True, "portfolio_value": 1e5}),
                )
            ]

    for result in asyncio.run(calls()):  # argument validation used to turn true into 1.0
        assert result.is_error and "not true/false" in result.content[0].text
    assert global_container.paper_engine.get_balances(U) == {"USD": 0.0}


# ------------------------------------------------------------------------------ XR-14


def test_the_smithery_listing_offers_only_settings_that_work_there():
    start = yaml.safe_load((REPO / "smithery.yaml").read_text())["startCommand"]
    assert "EXECUTION_APPROVAL_MODE" not in start["configSchema"]["properties"]
    assert "EXECUTION_APPROVAL_MODE: 'auto'" in start["commandFunction"]


# ------------------------------------------------------------------------------ REG-03


def test_the_operator_switches_answer_before_the_brokerage_configuration(monkeypatch):
    class Unconfigured:
        def is_available(self):
            return False

    monkeypatch.setattr(settings, "PAPER_MODE", False)
    monkeypatch.setitem(global_container.brokerages, "oanda", Unconfigured())
    for enabled, halted, code in ((False, False, "live_trading_disabled"), (True, True, "trading_halted"), (True, False, "brokerage_not_configured")):
        monkeypatch.setattr(settings, "LIVE_TRADING_ENABLED", enabled)
        monkeypatch.setattr(settings, "TRADING_HALTED", halted)
        assert _j(execution.place_forex_order("EURUSD", "sell", 1_000))["error"]["code"] == code


def test_an_unreadable_live_account_is_refused_with_the_brokerages_reason(live, monkeypatch):
    def fails():
        raise RuntimeError("OANDA balance fetch failed: HTTP 401: Insufficient authorization")

    monkeypatch.setattr(live, "get_account_balance", fails)
    out = _j(execution.place_forex_order("EURUSD", "sell", 1_000))
    assert out["error"]["code"] == "risk_blocked" and "HTTP 401: Insufficient authorization" in out["error"]["message"]
    assert live.orders == []


# ------------------------------------------------------------------------------ AR-01 / AR-02
# The independent review of the fixes above.


def _asgi(path, root_path="", host=b"127.0.0.1:8000", headers=()):
    import asyncio

    sent = []
    scope = {
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "GET", "scheme": "http",
        "path": path, "raw_path": path.encode(), "root_path": root_path, "query_string": b"",
        "headers": [(b"host", host), *headers], "client": ("127.0.0.1", 1), "server": ("127.0.0.1", 8000),
    }

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        sent.append(message)

    asyncio.run(api.app(scope, receive, send))
    start = next(m for m in sent if m["type"] == "http.response.start")
    return start["status"], dict((k.decode(), v.decode()) for k, v in start["headers"])


def test_the_operator_token_cannot_be_steered_past(monkeypatch):
    monkeypatch.setenv("API_OPERATOR_TOKEN", "review-operator-token")
    for host in (b"127.0.0.1:8000", b"127.0.0.1:8000#", b"127.0.0.1:8000?", b"127.0.0.1:8000/x"):
        assert _asgi("/api/portfolio", host=host)[0] == 401, host
    assert _asgi("/rt/api/pending-approvals", root_path="/rt")[0] == 401
    assert _asgi("/rt/api/health", root_path="/rt")[0] == 200
    assert _asgi("/api/portfolio", headers=[(b"authorization", b"Bearer review-operator-token")])[0] == 200


def test_every_answer_carries_the_cors_headers(monkeypatch):
    monkeypatch.setenv("API_OPERATOR_TOKEN", "review-operator-token")
    status, headers = _asgi("/api/portfolio", headers=[(b"origin", b"http://localhost:3000")])
    assert status == 401 and headers.get("access-control-allow-origin") == "http://localhost:3000"


# ------------------------------------------------------------------------------ AR-03


def test_a_nan_quote_is_no_price(live, rates):
    rates["AAPL"] = float("nan")
    with pytest.raises(ValueError, match="no usable price"):
        execution._quote("AAPL")
    out = execution.place_stock_order("AAPL", "buy", 1_000_000, exchange="alpaca")
    assert "NaN" not in out and _j(out)["error"]["code"] == "risk_blocked"
    assert live.orders == []


# ------------------------------------------------------------------------------ AR-04


def test_a_deposit_waits_while_a_position_cannot_be_priced(tmp_path):
    table = {"EURUSD": 1.10}
    e = _account(tmp_path, table)
    e.deposit(U, "USD", 100_000)
    e.execute_trade(U, "buy", "EURUSD", 1_000_000, 1.10)
    table["EURUSD"] = 1.089  # -11,000: 11%
    assert e.get_risk_metrics(U)["drawdown_pct"] == pytest.approx(0.11, abs=1e-4)
    del table["EURUSD"]
    with pytest.raises(ValueError, match="deposit refused"):
        e.deposit(U, "USD", 900_000)
    table["EURUSD"] = 1.089
    assert e.get_risk_metrics(U)["drawdown_pct"] == pytest.approx(0.11, abs=1e-4)


# ------------------------------------------------------------------------------ AR-06 / AR-07


def test_orders_the_switches_refuse_are_still_audited(live, monkeypatch):
    events = MagicMock()
    monkeypatch.setattr(execution.global_compliance_ledger, "record_event", events)
    monkeypatch.setattr(settings, "TRADING_HALTED", True)
    assert _j(execution.place_forex_order("EURUSD", "buy", 5_000))["error"]["code"] == "trading_halted"
    assert events.call_args.args[0] == "trade_start"


def test_an_approval_while_halted_answers_halted_without_calling_the_brokerage(live, monkeypatch):
    monkeypatch.setattr(settings, "EXECUTION_APPROVAL_MODE", "approve_each")
    proposal = _j(execution.place_forex_order("EURUSD", "buy", 1_000))["data"]
    monkeypatch.setattr(settings, "TRADING_HALTED", True)
    calls = []
    monkeypatch.setattr(live, "get_account_balance", lambda: calls.append("balance") or {"equity": 1e5})
    body = {"request_id": proposal["request_id"], "confirm_token": proposal["confirm_token"], "approve": True}
    r = TestClient(api.app, headers=OPERATOR).post("/api/approve-trade", json=body)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "trading_halted"
    assert calls == [] and live.orders == []


# ------------------------------------------------------------------------------ AR-08 / AR-09 / AR-10


def test_the_runbook_says_how_to_upgrade_a_volume_and_quotes_the_code():
    runbook = (REPO / "RUNBOOK.md").read_text()
    assert "--entrypoint chown readytrader-forex -R 10001:10001 /app/data" in runbook
    assert "Could not read the account's equity (paper) for the position-size check (a position cannot" in runbook


def test_every_numeric_tool_parameter_refuses_true():
    import asyncio

    from fastmcp import Client

    from app.main import mcp

    insight = {"symbol": "EURUSD", "agent_id": "a", "signal": "bullish", "reasoning": "r"}

    async def calls():
        async with Client(mcp) as client:
            return [
                await client.call_tool(tool, args, raise_on_error=False)
                for tool, args in (
                    ("fetch_ohlcv", {"symbol": "EURUSD", "limit": True}),
                    ("get_forex_news", {"limit": True}),
                    ("post_market_insight", {**insight, "confidence": True}),
                    ("post_market_insight", {**insight, "confidence": 0.5, "ttl_seconds": True}),
                )
            ]

    for result in asyncio.run(calls()):
        assert result.is_error and "not true/false" in result.content[0].text