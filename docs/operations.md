# Operations and Security Checklist

## Deployment

1. Create a private `.env` from `.env.example`. Set `SECRET_KEY` and `SIGNING_SECRET` to 32+ random characters each; production refuses to start otherwise.
2. Create the Ed25519 signing key with `flask --app app generate-signing-key` (or set `SIGNING_PRIVATE_KEY`) and **back it up offline**.
3. Set `POSTGRES_PASSWORD`, `SECRET_KEY`, and `SIGNING_SECRET` in the environment before running `docker compose up`; the compose file fails fast if they are missing.
4. Run `flask --app app db upgrade -d migrations` before serving traffic.
5. Put Gunicorn behind an HTTPS reverse proxy and set `FLASK_ENV=production`.
6. Configure `MAIL_BACKEND=smtp` and the `MAIL_*` settings for real email.
7. For on-chain anchoring, deploy the contract and set the `ETH_*` settings ([blockchain.md](blockchain.md)).
8. Schedule jobs with cron:
   ```cron
   */30 * * * *  flask --app app anchor-credentials
   0 * * * *     flask --app app integrity-scan || notify-oncall
   0 8 * * *     flask --app app send-expiry-reminders --days 30
   ```
9. Back up PostgreSQL (`pg_dump`), private uploads, and the signing key as separate encrypted sets, and rehearse restores regularly.

## Security controls implemented

- **Identity:** password hashing, a 12-character minimum, account lockout (5 failures for 15 minutes), single-use signed password-reset tokens, email verification, "strong" session protection, SameSite and Secure cookies in production.
- **Authorisation:** server-side role guards, institution scoping on every issuer route, administrator verification of universities, and IDOR regression tests.
- **Web:** CSRF on every form; a strict CSP (no `unsafe-inline`, `frame-ancestors 'none'`, `form-action 'self'`); `nosniff`, `DENY` framing, and a referrer policy; targeted rate limits (login, registration, issuance, verification, reset).
- **Uploads:** PDF signature and size checks; rejection of active content (`/JavaScript`, `/Launch`, `/EmbeddedFile`…, including hex-escaped names); an optional antivirus hook (`MALWARE_SCAN_COMMAND`); randomised private storage names; authorised downloads only.
- **Integrity:** SHA-256 baselines with FIM; Ed25519 signatures; Merkle anchoring; a hash-chained audit ledger with an advisory lock on PostgreSQL; anchoring of the audit head.
- **Privacy:** only hashes are published on-chain; public pages never show emails, revocation reasons, or documents; share links expire and can be revoked.

## Remaining hardening before an internet-facing deployment

- Use Redis-backed rate limiting (`REDIS_URL`) instead of in-memory limits when running more than one worker.
- Move documents to encrypted object storage and enable a managed antivirus scanner.
- Keep the signing key in a KMS or HSM, and add key rotation with a published key history.
- Add centralised logging, monitoring and alerting, dependency scanning, and a TOTP second factor for administrators.
