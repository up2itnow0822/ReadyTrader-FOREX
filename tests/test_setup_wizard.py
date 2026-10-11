"""tools/setup_wizard.py: no traceback without a terminal, and paper mode needs no keys."""

import importlib.util
import io
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("setup_wizard", ROOT / "tools" / "setup_wizard.py")
wizard = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(wizard)


def test_a_closed_stdin_is_no_answer_not_a_crash(monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)  # no .env here
    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    assert wizard.check_env_file() is False
    assert "cp env.example .env" in capsys.readouterr().out


def test_paper_mode_does_not_ask_for_broker_keys(monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("PAPER_MODE=true\n")
    for key in ("OANDA_API_KEY", "OANDA_ACCOUNT_ID", "PAPER_MODE"):
        monkeypatch.delenv(key, raising=False)
    wizard.check_keys()
    out = capsys.readouterr().out
    assert "MISSING" not in out and "only needed for live trading" in out


def test_live_mode_without_oanda_keys_is_flagged(monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("PAPER_MODE=false\n")
    for key in ("OANDA_API_KEY", "OANDA_ACCOUNT_ID"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("PAPER_MODE", "false")
    wizard.check_keys()
    assert "OANDA_API_KEY is MISSING" in capsys.readouterr().out
