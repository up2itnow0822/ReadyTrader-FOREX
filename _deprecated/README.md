# _deprecated

Code kept for reference that the server no longer loads. Nothing here is imported.

| File | Replaced by | Why it was retired |
|---|---|---|
| `forex_paper.py` | `core/fx_account.py` (`FxPaperAccount`, the paper engine) | An in-memory 100,000 USD simulator registered as a live venue (`exchange="forex_paper"`). In live mode it answered orders with `status: filled`, although nothing reached a broker and the fill was lost on restart. Paper trading is `PAPER_MODE=true`, which fills in the persistent FX account. |
| `docker-compose.sentinel.yml` | Nothing: this server signs nothing | A crypto signing sidecar (`SIGNER_TYPE=env_private_key`) copied from ReadyTrader-Crypto. It builds `sentinel.app`, which does not exist in this repository. |
| `configs/agent_zero.mcp.yaml` | `configs/agent_zero.mcp.json` | An `mcp_servers:` YAML block for an `agent.yaml` that current Agent Zero (v2.13) does not read for MCP servers; Agent Zero takes JSON in Settings → MCP/A2A → External MCP Servers. |
