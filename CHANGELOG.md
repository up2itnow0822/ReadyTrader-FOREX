## Changelog

This project follows a lightweight changelog format. Major changes are summarized here to help operators and integrators understand what changed between versions.

### Unreleased

- **Falling Knife gate repaired (security-relevant)**: `analyze_social_sentiment` added a flat `+0.2` for each configured source, so the "sentiment score" measured how many API keys were set rather than what anyone was saying. A panicking feed and a euphoric feed both scored `+0.4`, and the only reachable values were `0.0`, `0.2` and `0.4`. The rule blocks below `-0.5`, so it could never fire.
- **The order path was a bypass**: every order entry point passed a hardcoded `sentiment_score = 0.0` to the Risk Guardian, and passed neither daily loss nor drawdown. Three risk rules were therefore inert on every real order even though `validate_trade_risk` applied them. They now apply.
- **Nothing fabricates a sentiment number any more**: `get_social_sentiment(symbol)` returns the posts themselves, for the calling agent to read and judge. A deterministic text scorer was built and measured first; `docs/SENTIMENT.md` records what it scored and why it was rejected. On 30 simulated pair searches written blind to its vocabulary it caught **none** of eight currency crashes, and it read a rising quote-convention pair (`USDTRY +10.9%`, the lira collapsing) as bullish.
- **The agent can supply its own reading**: `validate_trade_risk(..., sentiment_score=...)` and every order entry point accept a score on `[-1, +1]`, clamped, and the response records `source` as `agent_supplied` rather than as a measurement.
- **The absence of a measurement is visible**: every verdict carries a `sentiment` block (`score`, `source`, `status`, `posts_available`, `posts_age_seconds`) with a `hint`, so a neutral `0.0` is never mistaken for a measured calm market.
- **Cache keyed by normalised symbol**: `EUR/USD`, `eurusd`, `eur_usd` and `EURUSD=X` reach one entry; a pair is never reduced to a base currency, because `USDJPY` and `JPYUSD` are different instruments. Expiry uses the monotonic clock, so a wall-clock step cannot pin or expire an entry, and expired entries are evicted rather than accumulating.
- **Unimplemented risk rules are now declared instead of hidden**: `get_volatility_status` and `get_news_status` are stubs that always return the permissive value, so the 3x-ATR flash-crash halt and the high-impact-news guard never fire. `validate_trade_risk` and blocked orders now return an `inactive_rules` block naming them, so an `allowed` verdict is never mistaken for a fully checked one. Implementing them is tracked as follow-up.
- **49 new tests** covering the contract above. No new dependency.

### 0.1.0 (2025-12-29)

- **Agent-first MCP server** for crypto trading workflows (paper mode + optional live execution).
- **Safety governance**: risk disclosure consent gate, kill switch, optional approve-each execution with replay protection.
- **Execution breadth**: CEX via CCXT + DEX swaps (1inch builder) with execution routing (`dex`/`cex`/`hybrid`).
- **Market data quality**: websocket-first public streams (opt-in), MarketDataBus freshness selection, plugin feed interface.
- **Stress lab**: deterministic synthetic stress testing with exportable artifacts + heuristic recommendations.
- **Operator layer**: structured logs with redaction, metrics snapshots, optional Prometheus text export, runbook and error catalog.
- **Custody hardening**: signer abstraction (env/keystore/remote), signing intents, defense-in-depth signer policy wrapper.
