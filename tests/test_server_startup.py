"""
The MCP server as a client sees it: it must start from the documented command and register every
tool the docs promise. Unit tests call the tool functions directly, so a registration or
packaging failure (fastmcp's add_tool wants a Tool object; the MCP SDK's 2.x drops a dependency
fastmcp 2.x imports; `python app/main.py` must find the `app` package) passes them all while the
server cannot start at all.
"""

import asyncio
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run_as_a_file(relpath: str):
    """Import a script the way `python <relpath>` does: its own folder first on sys.path, not the
    repository root (run_name keeps __main__ blocks from starting a server)."""
    code = (
        "import sys, runpy; sys.path[:] = [p for p in sys.path if p not in ('', '.')]; "
        f"sys.path.insert(0, {str(Path(relpath).parent)!r}); runpy.run_path({relpath!r}, run_name='not_main')"
    )
    return subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, timeout=120)


def _registered_tools():
    from fastmcp import Client

    from app.main import mcp

    async def names():
        async with Client(mcp) as client:
            return {tool.name for tool in await client.list_tools()}

    return asyncio.run(names())


def test_every_tool_registers():
    tools = _registered_tools()
    assert {"validate_trade_risk", "place_market_order", "place_limit_order", "place_forex_order", "fetch_ohlcv"} <= tools


def test_the_documented_start_command_serves_mcp_over_stdio():
    """`python app/main.py`, as the README, the Dockerfile and the client configs run it."""
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    env = {**os.environ, "PAPER_MODE": "true"}
    params = StdioServerParameters(command=sys.executable, args=["app/main.py"], cwd=str(ROOT), env=env)

    async def session():
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as s:
                await s.initialize()
                tools = {t.name for t in (await s.list_tools()).tools}
                # A SELL needs no market data, so this runs offline.
                result = await s.call_tool(
                    "validate_trade_risk", {"side": "sell", "symbol": "EURUSD", "amount_usd": 100.0, "portfolio_value": 10000.0}
                )
                return tools, json.loads(result.content[0].text)

    tools, verdict = asyncio.run(asyncio.wait_for(session(), timeout=120))
    assert "validate_trade_risk" in tools
    assert verdict["ok"] is True and verdict["data"]["result"]["allowed"] is True


def test_requirements_keep_the_mcp_sdk_on_1x():
    """fastmcp 2.14.1 imports pydantic_settings, which mcp 2.x no longer brings in."""
    text = (ROOT / "requirements.txt").read_text()
    assert re.search(r"^mcp>=1\.24\.0,<2$", text, re.M)


def test_the_package_resolves_when_main_is_run_as_a_file():
    out = run_as_a_file("app/main.py")
    assert out.returncode == 0, out.stderr[-800:]


def test_the_api_server_resolves_its_imports_when_run_as_a_file():
    # README and RUNBOOK start it as `python app/api_server.py`; that used to fail on `import app`.
    out = run_as_a_file("app/api_server.py")
    assert out.returncode == 0, out.stderr[-2000:]
