# Final Demonstration Script (about 15 minutes)

**Setup:** run `flask --app app demo-reset --yes`, then `flask --app app run`. Open two browser windows: one normal and one private (for the verifier). Password for every demo account: `DemoPassword1`.
**Optional on-chain setup:** start `anvil`, deploy with `python blockchain/deploy.py`, and set `BLOCKCHAIN_ANCHOR_PROVIDER=ethereum` (see [blockchain.md](blockchain.md)).

## 1. Governance (admin@demo.local), 2 minutes

1. Show the dashboard: stats and the latest hash-chained audit events.
2. In a private window, register a new university on **Register a university**, then back as admin open **University reviews**. The pending badge is showing. Approve it with a note. Point out that the representative can now issue credentials.

## 2. Issuance (issuer@demo.local), 4 minutes

3. **Branding:** set an accent colour and upload a logo.
4. **Workspace:** add a student and link `student@demo.local`. Choose a **template**, pick **Generate automatically**, and issue. Open the PDF: it shows the branding, recipient, and embedded QR code.
5. **Bulk issuance:** upload the sample CSV with a blank row. The report shows the created IDs, and the blank row was skipped.
6. **Credentials → Manage:** show the details, the integrity history, and the Replace and Revoke forms.

## 3. Student (student@demo.local), 2 minutes

7. The notification badge shows the new credential. Open **Certificates**, then create a **7-day share link** and copy it.
8. (Optional) **Claim a credential:** a second student submits a claim, and the issuer approves it under **Claim requests**.

## 4. Verifier (private window), 3 minutes

9. Open the share link: the holder's name and a valid credential, with no email and no PDF exposed.
10. Scan the QR code, or use **Verify a credential** with the ID. Show the green verdict, timeline, and **Cryptographic proof** (Ed25519 verified, Merkle proof, anchor with transaction link).
11. **Check a document:** upload the genuine PDF (it matches exactly), then an edited copy ("Document does not match").
12. Download the **proof bundle** and run in a terminal:
    `python blockchain/verify_proof.py <bundle>.json <certificate>.pdf`. The output is **VERIFIED** with no vault code involved.
13. Print the **Receipt**.

## 5. Tamper detection (admin), 4 minutes

14. As admin, **Audit ledger → Anchor credentials** anchors the batch (on-chain if configured).
15. **Tamper with the database:** in a disposable database, run
    `sqlite3 instance/dev.sqlite "update credential set title='PhD' where id=1"`, then reload the public page. It shows **"Record integrity failure"**: the signature no longer matches.
16. **Tamper with a stored file:** edit a PDF in `instance/private_uploads/`, then run **Integrity monitor → Run scan now**. The incident shows as "modified".
17. **Tamper with the audit log:** edit an `audit_event` row, then **Validate chain**. It names the tampered event, and **Anchor audit head** is refused.
18. As the issuer, **Revoke** a credential. The public page turns red; the reason stays private.

## Talking points

- Only hashes go on-chain. No personal data or documents are ever published.
- One transaction anchors a whole batch through a Merkle root, so the cost stays constant however many credentials there are.
- The `local` provider is labelled honestly in the UI. The Ethereum path is exercised by automated tests on a real EVM.
