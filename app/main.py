import sys
from pathlib import Path

if __package__ in (None, ""):
    # `python app/main.py` (README, Dockerfile, MCP client configs) puts app/ on sys.path, not the
    # repository root that the `app`, `core` and `marketdata` packages live in.
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastmcp import FastMCP  # noqa: E402

from app.tools.execution import register_execution_tools  # noqa: E402
from app.tools.market_data import register_market_tools  # noqa: E402
from app.tools.research import register_research_tools  # noqa: E402
from app.tools.trading import register_trading_tools  # noqa: E402

# Initialize FastMCP server
mcp = FastMCP("ReadyTrader-FOREX")

# Register Tools
register_market_tools(mcp)
register_trading_tools(mcp)
register_research_tools(mcp)
register_execution_tools(mcp)

if __name__ == "__main__":
    mcp.run()
