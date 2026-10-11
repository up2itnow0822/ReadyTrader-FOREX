## Security Policy

### Reporting a Vulnerability

If you believe you have found a security vulnerability, **do not** open a public issue.

Report it privately through GitHub's private vulnerability reporting:
<https://github.com/up2itnow0822/ReadyTrader-FOREX/security/advisories/new> (the repository's
**Security** tab, **Report a vulnerability**). Include:

- **Description** of the issue
- **Reproduction steps**
- **Impact** assessment
- Any relevant **logs** or **screenshots** (redact secrets)

### Scope Notes

- This project can be configured for **live trading** (`PAPER_MODE=false`). Keep API keys and secrets out of source control.
- Brokerage and data keys are read from the environment (or a git-ignored `.env`) and are never written by the server; prefer a secrets manager over a plain `.env` in shared environments.
- The approval API has no authentication beyond each proposal's `confirm_token`: keep it on `127.0.0.1` (the default).
- For live trading deployments, review `docs/THREAT_MODEL.md` and follow least-privilege patterns.

### Secret scanning guidance

- See `.github/secret-scanning.md` for recommended GitHub settings and local hygiene.
