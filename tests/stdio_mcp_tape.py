"""Test-only MCP stdio launcher: install a JSON daily-bar tape, then run the production server.

Not imported by app/ or core/. tests/test_server_startup.py starts this instead of
`python app/main.py` so a subprocess can exercise validate_trade_risk without a production
env hook.

Usage: python tests/stdio_mcp_tape.py <tape.json>
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import app.tools.trading as trading  # noqa: E402
from app.main import mcp  # noqa: E402


def _load_tape(path: str) -> list:
    payload = json.loads(Path(path).read_text())
    if not isinstance(payload, list):
        raise SystemExit(f"tape {path} must be a JSON list of OHLCV rows")
    return payload


def main(argv: list[str] | None = None) -> None:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1:
        raise SystemExit("usage: python tests/stdio_mcp_tape.py <tape.json>")
    bars = _load_tape(args[0])
    trading._fetch_daily_bars = lambda symbol, _bars=bars: list(_bars)
    mcp.run()


if __name__ == "__main__":
    main()
