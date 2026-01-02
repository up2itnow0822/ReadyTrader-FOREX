# ReadyTrader-FOREX

[![CI](https://github.com/up2itnow/ReadyTrader-FOREX/actions/workflows/ci.yml/badge.svg)](https://github.com/up2itnow/ReadyTrader-FOREX/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

## Important Disclaimer (Read Before Use)

ReadyTrader-FOREX is provided for informational and educational purposes only and does not constitute financial, investment, legal, or tax advice. Trading forex and CFDs involves substantial risk and may result in partial or total loss of funds. Past performance is not indicative of future results. You are solely responsible for any decisions, trades, configurations, supervision, and the security of your credentials/API keys. ReadyTrader-FOREX is provided “AS IS”, without warranties of any kind, and we make no guarantees regarding profitability, performance, availability, or outcomes. By using ReadyTrader-FOREX, you acknowledge and accept these risks.

See also: `DISCLAIMER.md`.

______________________________________________________________________

______________________________________________________________________

## 🌎 The Big Picture

**ReadyTrader-FOREX** is a specialized bridge that turns your AI Agent (like Gemini or Claude) into a professional forex trading operator.

Think of it this way: Your AI agent provides the **Intelligence** (analyzing charts, earnings reports, and news sentiment), while ReadyTrader-FOREX provides the **Hands** (connecting to brokerages and data providers) and the **Safety Brakes** (enforcing your risk rules). It allows you to delegate complex trading tasks to an AI without giving it unchecked access to your capital.

## 🛡️ The Trust Model: Intelligence vs. Execution

The core philosophy of this project is a strict separation of powers:

- **The AI Agent (The Brain):** Decides *what* and *when* to trade. It can research historical data, scan social media, and simulate strategies, but it has no direct power to move money.
- **The MCP Server (The Guardrail):** Owns the API keys and enforces your safety policies. It filters every AI request through a "Risk Guardian" that rejects any trade that is too large, too risky, or violates your personal limits.

## 💰 Funding Model (Non-Custodial)

ReadyTrader-FOREX operates on a **User-Custodied** basis. This means:

- **You keep your funds**: Your capital remains in your own brokerage account (e.g., OANDA, Forex.com, IG).
- **You control the keys**: You provide API keys that allow the agent to *trade* but (recommended) not *withdraw*.
- **Agent as Operator**: The agent acts as a remote operator. It sends order instructions to your broker using your keys, and the broker handles actual execution and settlement.

> **Note**: In **Paper Mode** (default), we simulate a virtual wallet with fake funds so you can practice without linking a real brokerage.

## 🔄 A Day in the Life of a Trade

1. **Research:** You ask your agent, "Find a good entry for EUR/USD." The agent calls `fetch_ohlcv` and `get_sentiment`.
1. **Proposal:** The agent concludes, "AAPL is oversold; I want to buy $1000 worth of shares." It calls `place_market_order`.
1. **Governance:** The MCP server checks its rules. Is $1000 within your `MAX_TRADE_AMOUNT`? If yes, it creates a **Pending Execution**.
1. **Consent:** If you've enabled "Human-in-the-loop," the agent notifies you. You click **Confirm** in the [Web UI](#-optional-web-ui), and only then does the trade hit the market.

______________________________________________________________________

### 🖥️ Premium Next.js Dashboard

`ReadyTrader-FOREX` includes a professional Next.js dashboard for real-time monitoring, multi-agent coordination, and trade approvals.

**How to Enable:**

1. Navigate to the directory: `cd frontend`
1. Install dependencies: `npm install`
1. Run the development server: `npm run dev`
1. Access it at `http://localhost:3000`.

**Features:**

- **Real-time Tickers**: Low-latency price streaming via WebSockets.
- **Multi-Agent Insights**: Shared "Market Insights" for collaborative research.
- **Mobile Guard**: Push notifications for trades requiring manual approval.
- **Glassmorphic UI**: High-performance charting and portfolio visualization.

______________________________________________________________________

## 🚀 Key Features

- **📉 Paper Trading Simulator**: Zero-risk practice environment with persistent balances and realistic order handling.
- **🧠 Strategy Factory**: Built-in Backtesting Engine with a **Strategy Marketplace** for saving and sharing agent configurations.
- **🏦 Deep DeFi Integration**: Direct support for **Aave V3** (Lending) and **Uniswap V3** (Concentrated Liquidity).
- **🛡️ Risk Guardian**: Hard-coded safety layer. Automatically rejects trade requests that violate risk rules.
- **🤝 Multi-Agent Orchestration**: Support for "Researcher" and "Executor" agent handoffs via a shared **Insight Store**.
- **📰 Advanced Intelligence**: Real-time sentiment feeds from X, Reddit, and News APIs with local NLP fallbacks.

______________________________________________________________________

## ⚡ 10-minute evaluation (Phase 6)

Run both demos locally (no exchange keys, no RPC needed):

```bash
python examples/paper_quick_demo.py
python examples/stress_test_demo.py
```

You’ll get exportable artifacts under `artifacts/demo_stress/` (gitignored).

Prompt pack (copy/paste): `prompts/READYTRADER_PROMPT_PACK.md`.

![ReadyTrader-FOREX demo flow](docs/assets/demo-flow.svg)

## 🛠️ Installation & Setup

### Prerequisites

- Docker (Docker Compose optional)

### 1. Build & Run (Standalone)

Run the server in a container. It exposes stdio for MCP clients.

```bash
cd ReadyTrader-FOREX
docker build -t readytrader-forex .
# Run interactively (to test)
docker run --rm -i readytrader-forex
```

### Local development (no Docker)

If you want to run or test ReadyTrader-FOREX locally:

```bash
pip install -r requirements-dev.txt
python app/main.py
```

### 2. Configuration (`.env`)

Create a `.env` file or pass environment variables. Start from `env.example` (copy to `.env`).

<details>
<summary><b>🛡️ Live Trading Safety & Approval</b></summary>

| Variable | Default | Description |
| :--- | :--- | :--- |
| `PAPER_MODE` | `true` | Set to `false` for live trading. |
| `LIVE_TRADING_ENABLED` | `false` | Must be `true` for any live execution. |
| `TRADING_HALTED` | `false` | Global kill switch to halt all live actions. |
| `EXECUTION_APPROVAL_MODE` | `auto` | `auto` executes immediately; `approve_each` requires manual confirmation. |
| `API_PORT` | `8000` | Port for the FastAPI/WebSocket server (`api_server.py`). |
| `DISCORD_WEBHOOK_URL`| `""` | Optional webhook for trade approval notifications. |

</details>

<details>
<summary><b>🔑 Exchange & Signing Credentials</b></summary>

| Variable | Description |
| :--- | :--- |
| `PRIVATE_KEY` | Hex private key for signing (if `SIGNER_TYPE=env_private_key`). |
| `CEX_API_KEY` | API Key for your primary exchange. |
| `CEX_API_SECRET` | API Secret for your primary exchange. |
| `SIGNER_TYPE` | `env_private_key`, `keystore`, or `remote`. |
| `CEX_BINANCE_API_KEY` | Exchange-specific keys (e.g., `CEX_BINANCE_...`). |

</details>

<details>
<summary><b>📈 Market Data & CCXT Tuning</b></summary>

| Variable | Default | Description |
| :--- | :--- | :--- |
| `MARKETDATA_EXCHANGES` | `binance...` | Comma-separated list of exchanges to use for data. |
| `TICKER_CACHE_TTL_SEC` | `5` | How long to cache price data. |
| `DEX_SLIPPAGE_PCT` | `1.0` | Default slippage for DEX swaps. |
| `ALLOW_TOKENS` | `*` | Comma-separated allowlist of tradeable tokens. |

</details>

<details>
<summary><b>🛠️ Ops, Observability & Limits</b></summary>

| Variable | Default | Description |
| :--- | :--- | :--- |
| `RATE_LIMIT_DEFAULT_PER_MIN` | `120` | Default API rate limit. |
| `RISK_PROFILE` | `conservative`| Presets for sizing and safety limits. |
| `ALLOW_CHAINS` | `ethereum...` | Allowlists for EVM networks. |

</details>

______________________________________________________________________

#### Brokerage credentials

To place live orders or fetch balances, configure brokerage credentials via env.

- `OANDA_API_KEY=...`
- `OANDA_ACCOUNT_ID=...`

Tools:

- `place_forex_order(symbol, side, amount, order_type='market', price=0.0, exchange='oanda', rationale='')`
- `get_portfolio_balance()`
- `reset_paper_wallet()` - **New: Reset all simulated data**
- `deposit_paper_funds(asset, amount)` - **New: Add virtual cash**

Market-data introspection:

- `get_marketdata_capabilities(exchange_id='')`

Market-data introspection:

- `get_marketdata_capabilities(exchange_id='')`

______________________________________________________________________

## 🔌 Integration Guide

### Option A: Agent Zero (Recommended)

To give Agent Zero these powers, add the following to your **Agent Zero Settings** (or `agent.yaml`).
The MCP server key/name is arbitrary; we use `readytrader_forex` in examples.

Quick copy/paste file: `configs/agent_zero.mcp.yaml`.

**Via User Interface:**

1. Go to **Settings** -> **MCP Servers**.
1. Add a new server:
   - **Name**: `readytrader_forex`
   - **Type**: `stdio`
   - **Command**: `docker`
   - **Args**: `run`, `-i`, `--rm`, `-e`, `PAPER_MODE=true`, `readytrader-forex`

**Via `agent.yaml`:**

```yaml
mcp_servers:
  readytrader_forex:
    command: "docker"
    args: 
      - "run"
      - "-i" 
      - "--rm"
      - "-e"
      - "PAPER_MODE=true"
      - "readytrader-forex"
```

Prebuilt config: `configs/agent_zero.mcp.yaml`.
*Restart Agent Zero after saving.*

### Option B: Generic MCP Client (Claude Desktop, etc.)

Add this to your `mcp-server-config.json`:

Quick copy/paste file: `configs/claude_desktop.mcp-server-config.json`.

```json
{
  "mcpServers": {
    "readytrader_forex": {
      "command": "docker",
      "args": [
        "run", 
        "-i", 
        "--rm", 
        "-e", "PAPER_MODE=true", 
        "readytrader-forex"
      ]
    }
  }
}
```

Prebuilt config: `configs/claude_desktop.mcp-server-config.json`.

______________________________________________________________________

## 📚 Feature Guide

**Example Prompt:**

> "Create a mean-reversion strategy for GBP/USD. Write a Python function `on_candle` that uses RSI. Run a backtest simulation on the last 500 hours and tell me the Win Rate and PnL."

**What happens:**

1. Agent calls `fetch_ohlcv("GBP/USD")` to see data structure.
1. Agent writes code for `on_candle(close, rsi, state)`.
1. Agent calls `run_backtest_simulation(code, "GBP/USD")`.
1. Server runs the code in a sandbox and returns `{ "pnl": 15.5%, "win_rate": 60% }`.

### 2. Paper Trading Laboratory (Zero-Key Flow)

Perfect for "interning" your agent without any paid API keys.

- **Fund your account**: `deposit_paper_funds("USD", 100000)`
- **Researching Markets**: Use `fetch_ohlcv` and `get_forex_price`.
- **Analyze Sentiment**: `fetch_rss_news` (MarketWatch/Yahoo Finance) provides real-time "Free" signals.
- **Place Orders**: `place_market_order("EUR/USD", "buy", 1000)`
- **Reset Everything**: `reset_paper_wallet()`

### 3. Market Regime & Risk

The agent can query the "weather" before flying.

- **Tool**: `get_market_regime("EUR/USD")`
- **Output**: `{"regime": "TRENDING", "direction": "UP", "adx": 45.2}`
- **Agent Logic**: "The market is Trending Up (ADX > 25). I will switch to my Trend-Following Strategy and disable Mean-Reversion."

**The Guardian (Passive Safety):**
You don't need to do anything. If the agent tries to bet 50% of the portfolio on a whim, `validate_trade_risk` will **BLOCK** the trade automatically.

______________________________________________________________________

## 🧰 Tool Reference

For the complete (generated) tool catalog with signatures and docstrings, see: `docs/TOOLS.md`.

| Category | Tool | Description |
| :--- | :--- | :--- |
| **Market Data** | `get_stock_price` | Live price from brokerage/data provider. |
| | `fetch_ohlcv` | Historical candles for research. |
| | `get_market_regime` | **Trend/Chop Detection** (Phase 6). |
| **Intelligence** | `get_sentiment` | Fear & Greed Index (Market). |
| | `get_social_sentiment` | X/Reddit Analysis (Financial focus). |
| | `get_financial_news` | Bloomberg/Reuters (Simulated/Real). |
| **Trading** | `place_market_order` | Execute market order. |
| | `place_limit_order` | **Limit Order** (Paper Mode). |
| | `check_orders` | Update Order Book (Paper Mode). |
| **Account** | `get_portfolio_balance`| Check Account Balance. |
| | `deposit_paper_funds`| Get fake money (Paper Mode). |
| **Research** | `run_backtest_simulation` | **Run Strategy Backtest**. |
| **Research** | `run_synthetic_stress_test` | Run **synthetic black-swan stress test** with deterministic replay + recommendations. |

______________________________________________________________________

*Built for the Agentic Future.*

## 🧪 Synthetic Stress Testing (Phase 5)

This MCP includes a **100% randomized (but deterministic-by-seed)** synthetic market simulator. It can generate trending, ranging, and volatile regimes and inject **black swan crashes** and **parabolic blow-off tops**.

### Tool: `run_synthetic_stress_test(strategy_code, config_json='{}')`

Returns JSON containing:

- **metrics summary** across scenarios
- **replay seeds** (master + per-scenario)
- **artifacts**: CSV scenario metrics, plus worst-case equity curve CSV + trades JSON
- **recommendations**: suggested parameter changes (and applies to `PARAMS` keys if present)

Example `config_json`:

```json
{
  "master_seed": 123,
  "scenarios": 200,
  "length": 500,
  "timeframe": "1h",
  "initial_capital": 10000,
  "start_price": 100,
  "base_vol": 0.01,
  "black_swan_prob": 0.02,
  "parabolic_prob": 0.02
}
```

______________________________________________________________________

## 📌 Project docs

- `docs/README.md`: docs index / navigation
- `docs/TOOLS.md`: complete tool catalog (generated from `app/tools`)
- `docs/ERRORS.md`: common error codes and operator troubleshooting
- `docs/EXCHANGES.md`: exchange capability matrix (Supported vs Experimental)
- `docs/MARKETDATA.md`: market data routing, freshness scoring, plugins, and guardrails
- `docs/THREAT_MODEL.md`: operator-focused threat model (live trading)
- `docs/CUSTODY.md`: key custody + rotation guidance
- `docs/POSITIONING.md`: credibility-safe marketing + messaging
- `RELEASE_READINESS_CHECKLIST.md`: what must be green before distribution
- `CHANGELOG.md`: version-to-version change summary
