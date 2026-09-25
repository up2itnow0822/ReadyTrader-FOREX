# ReadyTrader-FOREX Threat Model

An operator-focused threat model for ReadyTrader-FOREX configured for **live trading**
(`PAPER_MODE=false`, `LIVE_TRADING_ENABLED=true`).

## 🌟 Security philosophy
ReadyTrader-FOREX is a safety-first bridge: it limits what a mistaken, manipulated or compromised
agent can do with your brokerage account, and it fails closed when it cannot check something.

---

## 🚫 1. Brokerage credential compromise
- **Threat**: an attacker reads `.env` or the process environment and obtains `OANDA_API_KEY`.
- **Mitigation**:
    - Use a token scoped to one (sub-)account with no withdrawal rights (`docs/CUSTODY.md`).
    - Set the live policy (`MAX_BROKERAGE_ORDER_AMOUNT`, `ALLOW_BROKERAGE_SYMBOLS`, `ALLOW_EXCHANGES`;
      enforced in `core/policy.py`). It limits the server, not someone holding the token directly.
    - Run the server in a container or an isolated user account; never bake `.env` into an image
      (`.dockerignore` excludes every `.env*`, key and database file in any folder, and `data/`; the
      image runs as an unprivileged user).

## 🚫 2. Rogue agent / "fat finger" trades
- **Threat**: the agent sends an oversized order, the wrong side, or trades into a crash.
- **Mitigation**:
    - **Approval**: `EXECUTION_APPROVAL_MODE=approve_each` makes every order a proposal. The
      proposal's `confirm_token` goes to the agent, so on its own it does not prove a person
      approved: with `API_OPERATOR_TOKEN` set on the API server, every approval needs that operator
      secret too, and a live proposal cannot be approved without it.
    - **Position size**: the Risk Guardian refuses any order that adds exposure worth over 5% of the
      account's equity, valued at the market (a pair at its USD notional from the live quote,
      anything else at the market price; never at a price the order carries alone). An order that
      adds exposure and cannot be valued or sized is refused, and so is one on the paper account
      while one of its positions cannot be priced.
    - **Loss limits (paper account only)**: every order that adds exposure (long or short) is
      refused after a 5% daily loss (from the account's last recorded value of the previous UTC
      day) or a 10% drawdown, measured on trading results (deposits are
      neither gains nor losses, and do not end a halt); reducing or closing a position stays
      possible. A live brokerage account has no loss history here, so live orders list both rules
      under `inactive_rules`: watch a live account's losses at OANDA and use the kill switch.
    - **Mode**: a proposal made in paper mode is never executed live (and the reverse).
    - **Market guard**: BUYs into a pair still falling after a 5% drop are refused, and every trade
      on a pair whose daily move is over 4.5x its 20-day norm is halted (`docs/FALLING_KNIFE.md`).
    - **Policy limits**: `MAX_BROKERAGE_ORDER_AMOUNT` caps units per live order; an unreadable
      value refuses every live order.
    - **Kill switch**: `TRADING_HALTED` refuses every live order and approval, closing orders
      included, so it cannot flatten a position: close positions on the OANDA platform. Nothing the
      server sent keeps working behind it: every OANDA order is fill-or-kill (a limit is a market
      order with a `priceBound`), so none rests at the broker.
    - Not active in this release: the price-collar, Pattern Day Trader and news-blackout rules in
      `core/risk.py` are never given the inputs they need, so they never fire; verdicts list the
      news blackout under `inactive_rules`. Use `approve_each` and `MAX_BROKERAGE_ORDER_AMOUNT` for
      fat-finger protection.

## 🚫 3. Prompt injection / social engineering
- **Threat**: text the agent reads (news, posts, a custom feed) or a user tells it to bypass the
  rules or trade maliciously.
- **Mitigation**:
    - The Risk Guardian is Python code the agent cannot change or skip: every order tool runs the
      same checks as `validate_trade_risk`, and an approved proposal is checked again.
    - News, calendar and social text returned to the agent is untrusted; the server never acts on
      it. `fetch_custom_feed` fetches only public http(s) URLs (no local or private addresses, and
      redirects are re-checked).

## 🚫 4. The approval API
- **Threat**: another local program or web page approves a proposal.
- **Mitigation**: the API listens on `127.0.0.1` by default; approving or cancelling needs the
  proposal's `confirm_token`; only the dashboard's origins may call it from a browser
  (`API_CORS_ORIGINS`). Set `API_OPERATOR_TOKEN` on the API server (not on the MCP server): every
  `/api/` endpoint but `/api/health` then needs `Authorization: Bearer <token>` (the dashboard asks
  for it once per tab), and live proposals are approved only with it. It is a shared secret, not a
  login: do not expose the API beyond the host without an authenticating proxy.

---

## 🔒 Best practices
1.  **Never** reuse API tokens across apps.
2.  **Enable MFA** on your brokerage account.
3.  **Audit**: review `data/compliance_audit.log` for unexpected order requests.
4.  **Paper, then practice**: run a strategy with `PAPER_MODE=true`, then against OANDA's practice
    account (`OANDA_ENVIRONMENT=practice`, the default), before `OANDA_ENVIRONMENT=live`.
