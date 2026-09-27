# Report and Viva Outline

## Abstract

Academic Credential Vault lets verified universities issue academic credentials that anyone can verify. Each credential carries a SHA-256 document fingerprint and an Ed25519 signature, and is anchored to an EVM blockchain through Merkle-batched roots. Students hold their credentials in a private vault and share them through expiring links. File integrity monitoring and a hash-chained audit ledger detect tampering with stored files and internal records.

## 1. Problem and objectives

Forged and altered certificates are common, and manual verification is slow. The objectives are: authorised issuance only; verification by anyone without an account; detection of any modification (document, record, or log); privacy (no personal data made public); and verification that does not depend on trusting the platform operator.

## 2. Architecture

- **Components:** a Flask application factory with blueprints (auth, university, student, verification, credentials, chain, audit, integrity); PostgreSQL; private file storage; an EVM smart contract. Use `README.md` "Project structure" and the Phase 0 ER and data-flow diagrams, extended with `claim_request`, `credential_anchor_proof`, and anchor receipts.
- **Trust layers:** the table in `docs/blockchain.md`. Draw the issuance sequence (payload → signature → leaf → batch root → transaction) and the verification sequence (signature → Merkle path → on-chain lookup → PDF hash).
- **Roles and access control:** the role matrix, server-side role guards, and institution scoping (IDOR tests).

## 3. Implementation highlights

- Atomic issuance service (one transaction; file removed on failure).
- Canonical JSON payloads, Ed25519 signatures, and a public key endpoint.
- Merkle tree with domain separation; `CredentialAnchor.sol` (owner-only, immutable roots); a pluggable provider (`local` or `ethereum`).
- Deterministic certificate PDFs with an embedded QR code.
- Security controls: strict CSP with no inline code, CSRF, rate limits, account lockout, single-use signed reset tokens, PDF active-content screening, production secret checks.
- Design system: role-aware app shell, light and dark themes, responsive down to 375 px, progressive enhancement.

## 4. Testing and results

- 138 automated tests at 92% coverage, run in CI on Python 3.12 and 3.13, with a PostgreSQL job.
- Evidence table, one row per threat: forged PDF (hash mismatch), edited database record (signature invalid / "Record integrity failure"), record re-signed by an insider (Merkle leaf no longer matches the anchored root), edited stored file (FIM "modified"), edited audit log (chain validation names the event), cross-institution access (403/404), CSRF (400), brute force (423 lockout).
- Include screenshots of each role's journey (see `docs/final-demo.md`) and the terminal output of `verify_proof.py`.

## 5. Limitations and future work

- A single platform signing key. Future work: per-institution keys, key rotation, and a published key history.
- Anchoring is batched on a schedule, so a newly issued credential is "pending" until the next batch.
- The public-testnet deployment needs a funded testnet wallet. The Ethereum path is tested on an in-process EVM.
- Local file storage. Future work: encrypted object storage and a managed antivirus scanner (a hook already exists).
- Possible extensions: W3C Verifiable Credentials export, DID-based issuer identity, ERP integration, SMS notifications.

## Viva answers

- **Is it really blockchain-based?** Yes, for the part a blockchain is good at: public, immutable, timestamped commitments. Merkle roots of signed credential records are written to the `CredentialAnchor` contract, and anyone can check inclusion with the proof bundle. Documents and personal data stay off-chain for privacy (GDPR and DPDP) and cost reasons.
- **Why not store certificates on-chain?** Chains are public and permanent (a privacy risk), storage is expensive, and a document cannot be erased there. A hash gives the same tamper evidence.
- **Why Merkle trees?** One transaction commits thousands of credentials, and each needs only log₂(n) hashes to prove inclusion.
- **Why Ed25519 rather than HMAC?** HMAC needs the shared secret to verify, so only the server could check it. Ed25519 lets anyone verify with the public key, and it is fast, with deterministic signatures.
- **What if an insider edits the database and re-signs the record?** The signature would then be valid, but the Merkle leaf no longer matches the root anchored on-chain. The verification page shows "altered" (there is a test for this).
- **What if the vault operator disappears?** The verifier still has the proof bundle, the public key, and the on-chain root, and `verify_proof.py` needs nothing else.
- **Why SHA-256?** It is collision-resistant and widely supported; changing one byte gives a completely different digest.
- **How does FIM work?** It re-hashes the stored files, compares them with the issuance baselines, records each result, and audits new incidents. Run it from cron with `flask integrity-scan`.
