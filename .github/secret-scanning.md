## Secret scanning (recommended)

ReadyTrader is capable of live trading. Treat secrets as production-grade:

- never commit `.env` files
- do not store raw private keys in repo
- prefer keystore or remote signer

### Recommended GitHub settings (repo-level)

- Enable **secret scanning** (GitHub Advanced Security if available)
- Enable **push protection** for secrets (if available)

### Local hygiene

- Use `env.example` and keep `.env` in `.gitignore`
- Rotate credentials immediately if exposed
