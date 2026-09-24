"""On/off settings fail toward the safe side (common/switches.py)."""

import json
import os
import subprocess  # nosec B404 - runs this repo's own interpreter on a fixed script
import sys
from pathlib import Path

import pytest

from common.switches import approval_mode, kill_switch_on, safety_switch_on

ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.parametrize("value", ["true", "TRUE", " True ", "1", "yes", "on", "halt", "treu"])
def test_kill_switch_halts_on_any_value_but_off(value):
    assert kill_switch_on(value) is True


@pytest.mark.parametrize("value", [None, "", "  ", "false", "FALSE", "0", "no", "off"])
def test_kill_switch_stays_off_when_unset_or_explicitly_off(value):
    assert kill_switch_on(value) is False


@pytest.mark.parametrize("value", [None, "", "true", "1", "yes", " TRUE ", "treu"])
def test_safety_switch_stays_on_unless_explicitly_off(value):
    assert safety_switch_on(value) is True


@pytest.mark.parametrize("value", ["false", " False ", "0", "no", "off"])
def test_safety_switch_turns_off_only_on_an_explicit_off(value):
    assert safety_switch_on(value) is False


def _settings_under(env: dict) -> dict:
    """Read Settings in a fresh interpreter: the values are fixed when app.core.config is imported."""
    code = (
        "import json; from app.core.config import settings as s; from app.tools.execution import live_execution_refusal as r;"
        "print(json.dumps({'paper': s.PAPER_MODE, 'live': s.LIVE_TRADING_ENABLED, 'halted': s.TRADING_HALTED, 'refusal': r()}))"
    )
    clean = {k: v for k, v in os.environ.items() if k not in ("PAPER_MODE", "LIVE_TRADING_ENABLED", "TRADING_HALTED")}
    out = subprocess.run(  # nosec B603 - fixed argv, no shell
        [sys.executable, "-W", "ignore", "-c", code],
        cwd=ROOT,
        env={**clean, **env},
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return json.loads(out.strip().splitlines()[-1])


@pytest.mark.parametrize("value", ["true", "1", "yes", "on"])
def test_trading_halted_refuses_live_orders_for_every_on_value(value):
    got = _settings_under({"PAPER_MODE": "false", "LIVE_TRADING_ENABLED": "true", "TRADING_HALTED": value})
    assert got["halted"] is True
    assert got["refusal"]["code"] == "trading_halted"


def test_live_trading_needs_the_exact_word_true():
    got = _settings_under({"PAPER_MODE": "false", "LIVE_TRADING_ENABLED": "1"})
    assert got["live"] is False
    assert got["refusal"]["code"] == "live_trading_disabled"


@pytest.mark.parametrize("value", ["1", "yes", " true", "TRUE"])
def test_paper_mode_spelled_as_on_stays_paper(value):
    assert _settings_under({"PAPER_MODE": value})["paper"] is True


@pytest.mark.parametrize(
    "value, mode",
    [
        (None, "auto"),
        ("", "auto"),
        ("auto", "auto"),
        (" AUTO ", "auto"),
        ("approve_each", "approve_each"),
        ("APPROVE_EACH ", "approve_each"),
        ("approve-each", "approve_each"),
        ("approve_each  # auto or approve_each", "approve_each"),
        ("manual", "approve_each"),
    ],
)
def test_approval_mode_fails_closed(value, mode):
    assert approval_mode(value) == mode


def test_settings_read_a_commented_approval_mode_as_approve_each():
    code = "from app.core.config import settings; print(settings.EXECUTION_APPROVAL_MODE)"
    out = subprocess.run(  # nosec B603 - fixed argv, no shell
        [sys.executable, "-W", "ignore", "-c", code],
        cwd=ROOT,
        env={**os.environ, "EXECUTION_APPROVAL_MODE": "approve-each"},
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert out.strip().splitlines()[-1] == "approve_each"


def test_env_example_has_no_inline_comments():
    """docker run --env-file keeps everything after '=', so an inline comment becomes part of the value."""
    for n, line in enumerate((ROOT / "env.example").read_text().splitlines(), 1):
        body = line.lstrip("# ").strip()
        if "=" in body and body.split("=", 1)[0].isupper():
            assert " #" not in body.split("=", 1)[1], f"env.example:{n} has an inline comment: {line!r}"


@pytest.mark.parametrize("value", [None, "true", "TRUE", "1", "yes", "on"])
def test_tradier_stays_in_the_sandbox_unless_explicitly_off(monkeypatch, value):
    from execution.tradier_service import TradierBrokerage

    if value is None:
        monkeypatch.delenv("TRADIER_SANDBOX", raising=False)
    else:
        monkeypatch.setenv("TRADIER_SANDBOX", value)
    assert TradierBrokerage().base_url == "https://sandbox.tradier.com/v1"


def test_tradier_production_needs_an_explicit_off(monkeypatch):
    from execution.tradier_service import TradierBrokerage

    monkeypatch.setenv("TRADIER_SANDBOX", "false")
    assert TradierBrokerage().base_url == "https://api.tradier.com/v1"


@pytest.mark.parametrize("value", ["true", "TRUE", "1", "yes", "on"])
def test_etrade_sandbox_covers_every_call(monkeypatch, value):
    from execution.retail_services import EtradeBrokerage

    monkeypatch.setenv("ETRADE_SANDBOX", value)
    broker = EtradeBrokerage()
    assert broker.sandbox is True and broker.api_host == "https://apisb.etrade.com"
    assert broker.base_url.startswith("https://apisb.etrade.com/")


def test_etrade_uses_production_when_the_sandbox_is_not_asked_for(monkeypatch):
    from execution.retail_services import EtradeBrokerage

    monkeypatch.delenv("ETRADE_SANDBOX", raising=False)
    assert EtradeBrokerage().api_host == "https://api.etrade.com"


def test_etrade_endpoints_are_not_hard_coded():
    source = (ROOT / "execution" / "retail_services.py").read_text()
    assert source.count("api.etrade.com") == 1 and source.count("apisb.etrade.com") == 1


@pytest.mark.parametrize("value, paper", [(None, True), ("true", True), ("1", True), ("false", False), ("off", False)])
def test_alpaca_trades_its_paper_account_unless_explicitly_off(monkeypatch, value, paper):
    pytest.importorskip("alpaca")
    from alpaca.common.enums import BaseURL

    from execution.alpaca_service import AlpacaBrokerage

    monkeypatch.setenv("ALPACA_API_KEY", "PKTEST")
    monkeypatch.setenv("ALPACA_API_SECRET", "secret")
    monkeypatch.setenv("PAPER_MODE", "false")
    if value is None:
        monkeypatch.delenv("ALPACA_PAPER", raising=False)
    else:
        monkeypatch.setenv("ALPACA_PAPER", value)
    broker = AlpacaBrokerage()
    assert broker.paper_mode is paper
    assert broker.client._base_url == (BaseURL.TRADING_PAPER if paper else BaseURL.TRADING_LIVE)


def test_env_example_carries_no_placeholder_credentials():
    """A .env copied from env.example must not look configured: a placeholder key reads as set."""
    for n, line in enumerate((ROOT / "env.example").read_text().splitlines(), 1):
        if line.strip() and not line.lstrip().startswith("#"):
            value = line.split("=", 1)[1].strip() if "=" in line else ""
            assert not value.lower().startswith("your_"), f"env.example:{n} sets a placeholder: {line!r}"


def test_a_malformed_setting_that_nothing_applies_does_not_stop_the_server():
    code = "from app.core.config import settings as s; print(s.CIRCUIT_BREAKER_PCT, s.RATE_LIMIT_DEFAULT_PER_MIN)"
    out = subprocess.run(  # nosec B603 - fixed argv, no shell
        [sys.executable, "-W", "ignore", "-c", code],
        cwd=ROOT,
        env={**os.environ, "CIRCUIT_BREAKER_PCT": "7%", "RATE_LIMIT_DEFAULT_PER_MIN": "lots"},
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert out.strip().splitlines()[-1] == "0.07 120"
