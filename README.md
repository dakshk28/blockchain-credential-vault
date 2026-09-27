# Blockchain-Based Academic Credential Vault

Verified universities issue tamper-evident academic credentials. Students keep them in a private vault and share them. Anyone can verify a credential, offline if needed, down to the on-chain anchor.

| For | What they can do |
| --- | --- |
| **Universities** | Register and pass administrator verification. Issue single, bulk (CSV), or **auto-generated branded certificates with a QR code**. Use templates. Revoke or replace credentials. Review student claims. |
| **Students** | See credentials in a private vault, download PDFs, create expiring share links, claim credentials by student ID, and receive in-app and email notifications. |
| **Verifiers** | Look up a credential by ID or QR code, compare a PDF byte for byte, see the signature and blockchain-anchor status, download a proof bundle, and print a receipt. |
| **Administrators** | Verify universities, manage users, run integrity scans, validate and anchor the audit ledger, and view reports. |

## Trust model

Every credential is protected by independent layers ([details](docs/blockchain.md)):

1. **SHA-256 document fingerprint.** Any edit to the PDF is detected.
2. **Ed25519 digital signature** over the credential record. The public key is at `/.well-known/acv-signing-key.json`.
3. **Merkle batch anchoring** to the `CredentialAnchor` smart contract on an EVM chain (Polygon Amoy, Sepolia, or a local node). A `local` provider is available for offline demos.
4. **Hash-chained audit ledger.** Every action is chained to the previous one, and the chain head can be anchored too.
5. **File integrity monitoring.** Stored PDFs are re-hashed against their baselines.

`blockchain/verify_proof.py` checks all of this **without the vault's code or trust in its operator**.

## Quick start (development)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env                       # SQLite works for local development:
export DATABASE_URL=sqlite:///$PWD/instance/dev.sqlite
flask --app app db upgrade -d migrations
flask --app app seed-demo                  # admin@ / issuer@ / student@demo.local, password DemoPassword1
flask --app app run --debug
```

Open http://127.0.0.1:5000. For PostgreSQL, set `DATABASE_URL=postgresql+psycopg://…`, or use `docker compose up` (see [operations](docs/operations.md)).

## Commands

| Command | Purpose |
| --- | --- |
| `flask seed-demo` / `flask demo-reset --yes` | Create or rebuild deterministic dummy data (development only). |
| `flask anchor-credentials` | Anchor all pending credentials as one Merkle batch (schedule with cron). |
| `flask integrity-scan` | Re-hash stored documents; exits 1 on incidents (schedule with cron). |
| `flask send-expiry-reminders --days 30` | Notify students about credentials that expire soon. |
| `flask generate-signing-key` / `flask upgrade-signatures` | Manage the Ed25519 key; re-sign legacy HMAC credentials. |
| `python blockchain/deploy.py` | Deploy the anchor contract (see [docs/blockchain.md](docs/blockchain.md)). |
| `python blockchain/verify_proof.py bundle.json [cert.pdf]` | Verify a credential independently. |

## Tests

```bash
pytest --cov=vault
```

The suite has 138 tests with 92% coverage. It includes real smart-contract deployment and anchoring on an in-process EVM, security regressions (IDOR, CSRF, lockout, cross-institution access), and a check that every page renders for every role. CI (`.github/workflows/ci.yml`) also checks migrations on SQLite and PostgreSQL.

## Project structure

```text
vault/
  auth/          accounts, login, lockout, password reset, email verification, admin screens
  university/    workspace, credentials, bulk issuance, templates, claims, branding
  student/       vault, share links, claims, notifications
  verification/  public portal, result page, proof bundle, receipt, QR codes
  credentials/   issuance service, PDF screening, certificate generator
  chain/         Ed25519 signing, Merkle tree, anchor providers
  audit/ integrity/   hash-chained ledger, file integrity monitoring
  templates/ static/  design system (light/dark, responsive, strict CSP)
blockchain/      Solidity contract, compiled artifact, deploy and verify scripts
migrations/      Alembic migrations
docs/            design, blockchain, operations, demo script, report outline
```

## Documentation

- [Production plan and improvement roadmap](production.md) (section 16) and [work summary](WORK_SUMMARY.md)
- [Blockchain layer](docs/blockchain.md) · [Operations and security](docs/operations.md)
- [Demo script](docs/final-demo.md) · [Report and viva outline](docs/report-outline.md) · [Phase 0 design](docs/phase-0-design.md)

All demonstrations use dummy data. Never upload real student documents to a development instance.
