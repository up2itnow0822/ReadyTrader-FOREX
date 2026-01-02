## ReadyTrader-FOREX Threat Model (Live Trading)

This document is an operator-focused threat model for ReadyTrader-FOREX when configured for **live trading** (`PAPER_MODE=false`). It is intentionally concise and actionable.

### Scope

- **In scope**:
  - Brokerage credentials (OANDA, Alpaca, etc.)
  - Live execution path (Forex orders, PnL management)
  - Market data correctness (stale/outlier data leading to bad execution)
- **Out of scope**:
  - Brokerage-side compromise (assumed handled by broker security)
  - OS/hypervisor compromise (assumed handled by your infra)

______________________________________________________________________

## Primary assets

- **Funds**: brokerage account balances
- **Keys**:
  - Brokerage API keys / Tokens
- **Execution authority**: ability to place orders and manage positions
- **Operational evidence**: audit logs and operator telemetry

______________________________________________________________________

## Threats and mitigations

### 1) Secret leakage (keys logged or committed)

- **Threat**: accidental logging of secrets; committing `.env`; exposing keystore/password.
- **Mitigations**:
  - Never commit `.env` (use `env.example`).
  - Phase 4 logging redaction reduces risk, but do not rely on it—avoid logging secrets entirely.
  - Prefer **keystore** or **remote signer** for production over `PRIVATE_KEY`.

### 2) Wrong-account / wrong-broker usage

- **Threat**: ReadyTrader-FOREX points at an unintended account or live vs paper misconfiguration.
- **Mitigations**:
  - Use `ALLOW_EXCHANGES` (PolicyEngine) to pin the expected brokerage venues.
  - Verify account IDs at startup.

### 3) Overbroad execution authority

- **Threat**: compromised agent places massive orders or drains account.
- **Mitigations**:
  - Enforce via PolicyEngine:
    - `ALLOW_BROKERAGE_SYMBOLS`
    - `MAX_BROKERAGE_ORDER_AMOUNT`
    - `ALLOW_BROKERAGE_MARKET_TYPES`

### 4) Malicious or stale market data drives bad trades

- **Threat**: stale/outlier tick causes market order at wrong time/venue.
- **Mitigations**:
  - Phase 3 guardrails:
    - `MARKETDATA_FAIL_CLOSED=true`
    - tune `MARKETDATA_MAX_AGE_MS*` and outlier thresholds
  - Prefer websocket-first + ingest-first for trusted feeds.

### 5) Execution replay / double-submit from agent retries

- **Threat**: an agent retries and duplicates an order or tx.
- **Mitigations**:
  - Use `idempotency_key` wherever supported (CEX order placement, swaps).
  - Use approve-each mode for early deployments (`EXECUTION_APPROVAL_MODE=approve_each`).

### 6) Operator mistakes / unsafe configuration

- **Threat**: loosening limits too far, disabling policy allowlists, enabling live trading without supervision.
- **Mitigations**:
  - Live-trading consent gate + kill switch (`TRADING_HALTED=true`).
  - Advanced Risk Mode requires additional consent.
  - Keep policy allowlists/limits enabled in production.

______________________________________________________________________

## Recommended production baseline

- **Execution**:
  - start with `EXECUTION_APPROVAL_MODE=approve_each`
  - use `TRADING_HALTED=true` by default; enable only during controlled windows
- **Keys**:
  - never commit API keys
  - set `ALLOW_EXCHANGES=<expected>`
  - enable order-side policy (`MAX_BROKERAGE_ORDER_AMOUNT` + allowlists)
- **Market data**:
  - enable `MARKETDATA_FAIL_CLOSED=true`
  - use WS + trusted ingest feeds; REST as fallback
