import os
import sys

import pytest

# Add root directory to sys.path to allow imports from top-level modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Set environment variables BEFORE modules are imported
os.environ["PRIVATE_KEY"] = "0000000000000000000000000000000000000000000000000000000000000001"
os.environ["SIGNER_TYPE"] = "env_private_key"
os.environ["PAPER_MODE"] = "true"
os.environ["EXECUTION_MODE"] = "dex"


@pytest.fixture(autouse=True)
def mock_env_setup():
    # Ensures these are set for every test
    pass


@pytest.fixture(autouse=True)
def calm_market(monkeypatch):
    """
    The Falling Knife check and the volatility halt read daily bars over the network; no test may.
    Every test sees a calm tape unless it patches `app.tools.trading._fetch_daily_bars` itself.
    """
    import market_bars

    import app.tools.trading as trading

    monkeypatch.setattr(trading, "_fetch_daily_bars", lambda symbol: market_bars.calm())


@pytest.fixture
def container():
    from app.core.container import global_container

    return global_container


@pytest.fixture
def backtest_engine(container):
    return container.backtest_engine


@pytest.fixture
def paper_engine(container):
    return container.paper_engine


@pytest.fixture
def policy_engine(container):
    return container.policy_engine


@pytest.fixture
def risk_guardian(container):
    return container.risk_guardian


@pytest.fixture
def marketdata_bus(container):
    return container.marketdata_bus
