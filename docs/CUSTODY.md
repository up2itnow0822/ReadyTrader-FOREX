# Custody & API Management (ReadyTrader-FOREX)

ReadyTrader-FOREX holds no funds and no private keys. Your money stays at your broker; the server
reaches it only through the brokerage API credentials you give it (OANDA by default).

## 🛡️ API credential security
In live mode the server uses your brokerage credentials to read the account's equity (for sizing)
and to place orders. Protecting them is your main security responsibility.

### 1. Minimal permissions
- **Needed**: trade execution and account read (OANDA: a personal access token for the account you
  trade).
- **Never needed**: funding, withdrawals, transfers or password changes. Use a dedicated
  sub-account where the broker offers one, so the token can only touch the capital you allot.

### 2. Secret management
- **Never** commit `.env` (it is in `.gitignore`); pass credentials as environment variables.
- Use a secrets manager (AWS Secrets Manager, GitHub Actions secrets, Docker secrets) when you
  deploy anywhere shared.
- Rotate by replacing `OANDA_API_KEY` (and revoking the old token at OANDA), then restart both
  processes. Nothing is written to disk.

### 3. Practice first
`OANDA_ENVIRONMENT` defaults to `practice`: with a practice-account token you can exercise the whole
live path (`PAPER_MODE=false`, `LIVE_TRADING_ENABLED=true`) without real money.

---

## 🤝 Human-in-the-Loop (HITL)
The agent can propose a trade and a human confirms it before anything executes:

```bash
EXECUTION_APPROVAL_MODE=approve_each
```

The agent gets a `request_id` and `confirm_token`; you approve through the API or the dashboard
(`RUNBOOK.md`), and the Risk Guardian checks the trade again with fresh data before it executes.

## Checking what the server did
- `data/compliance_audit.log`: one JSON line per order request and outcome.
- `get_paper_account()` in paper mode; your broker's own statements in live mode.
