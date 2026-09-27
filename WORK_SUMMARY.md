# Work Summary

This log records completed work by production-plan phase. It is updated after each completed unit of work.

## Phase 0 — Requirements, research, and design

Status: complete

- Documented the MVP scope and the honest boundary: a tamper-evident internal audit ledger, not a decentralized public blockchain.
- Finalized the four user roles and server-enforced permission boundaries.
- Defined public verification fields and protected private fields.
- Defined credential lifecycle and file-integrity states.
- Added ER and data-flow diagrams and a seven-threat mitigation model.
- Chose PDF-only documents for the MVP and dummy data for demos.

Design record: [docs/phase-0-design.md](docs/phase-0-design.md)

## Phase 1 — Foundation and project cleanup

Status: complete

- Initialized Git and excluded virtual environments, secrets, uploads, local databases, dumps, and caches.
- Replaced the one-file prototype with an application factory and `auth`, `credentials`, `verification`, `integrity`, `audit`, and `models` modules.
- Added development, test, and production configuration; PostgreSQL SQLAlchemy and Flask-Migrate integration; structured errors; and baseline tests.
- Generated and applied the initial database migration during an isolated SQLite migration verification.
- Existing local uploaded documents were left untouched and excluded from Git; future demos will use dummy documents only.

Verification: `pytest` (passing).

## Phase 2 — Identity, authentication, and role access

Status: complete

- Added student and issuer registration, login, logout, password hashing, password-strength checks, and disabled-account protection.
- Added administrator-only issuer approval and user-management API access; issuers begin in the pending state.
- Added role guards, CSRF protection, rate limits for registration/login, and audit records for registration, login, failed login, logout, and issuer approval.
- Added database migration `679f5e2da96e` for issuer profiles and audit events.
- Added authorization and password-security tests; the full suite passes (6 tests).
- Fixed browser-form/API route collision: browser signup/login use `/auth/...`; JSON endpoints use `/auth/api/...`.

## Phase 3 — Secure credential issuance and storage

Status: complete

- Added an approved-issuer-only issuance endpoint with PDF signature/size validation, randomized private storage keys, SHA-256 baseline generation, unique public IDs, and issuance audit records.
- Added institution-scoped, authorized document downloads and a visible duplicate-content warning; non-PDF uploads are rejected.
- Generated and applied migration `55970b0b7a9f`; issuance integration tests pass.

## Phase 4 — Public verification, QR code, and lifecycle

Status: complete for the core MVP

- Added public credential-ID lookup and uploaded-document hash comparison, including separate authenticity and modification results.
- Added issuer-owned revocation with mandatory reason and audit record.
- Added QR-code generation and migration `f3e0dcf0da7d` for revocations.
- Limitation: revocation is implemented; replacement is explicitly deferred advanced work.

## Phase 5 — File Integrity Monitoring

Status: complete

- Added stored-file SHA-256 integrity checks, persisted check results, and new-incident-only audit records.
- Added administrator-only manual run and integrity-dashboard API endpoints.

Verification: FIM detects both unchanged and modified stored files; 9 tests pass.

## Phase 6 — Tamper-evident audit chain

Status: complete

- Added canonical event hashing chained to the previous event, plus administrator-only validation that reports the first invalid record.
- Generated/applied migration `7e0101b4a656`; tampering detection test passes.

## Phase 7 — Security hardening, QA, and deployment

Status: complete for the college-project MVP

- Added security response headers, Docker/Gunicorn/PostgreSQL deployment artifacts, backup/restore guidance, and a documented remaining-hardening list.
- Automated suite passes: 10 tests.

## Phase 8 — Report, presentation, and demonstration

Status: complete for supporting materials

- Added an assessed demo script and report/viva outline. Use Phase 0 diagrams as the report architecture figures.

## Planned feature expansion — Student Vault and University Portal

Status: planned

- Added a seven-phase extension roadmap for student-owned certificate visibility, university onboarding/authentication, administrator verification, and institution-scoped issuance.
- No application behavior changed in this planning step.
- Plan: [docs/feature-expansion-plan.md](docs/feature-expansion-plan.md)

## Feature expansion implementation

Status: complete

- Expanded the approved roadmap with student sharing/claiming, university templates and bulk issuance, notifications, digital-signature design, operations, API/webhook boundaries, and production integrations.
- Beginning with the student/university ownership foundation because it is required by the vault, issuer workspace, and authorization features.
- Implemented the first unit: student profiles, university-verification request records, in-app notification records, credential-to-student ownership, and an isolated student-certificate API endpoint.

## Expansion Phase B — Student certificate vault

Status: complete

- Added the browser vault route and student-only, credential-scoped document download authorization.
- Updated the student dashboard with a direct entry into the vault.
- Verified student vault isolation and empty-state rendering; full test suite passes (14 tests).

## Expansion Phase C — University onboarding and authentication

Status: complete

- Implemented university registration, pending-review state, separate university entry points, and registration auditing; 15 tests pass.

## Expansion Phase D — Administrator university verification

Status: complete

- Added an administrator-only review console with approve, reject, and suspend actions requiring a review note.
- Verified approval activates both the institution and representative issuer profile; full suite passes (16 tests).

## Expansion Phase E — University workspace

Status: complete for the college-project MVP

- Build the approved issuer dashboard, institution-scoped student lookup/creation, and browser issuance workflow that assigns credentials to student profiles.

## Expansion Phases F–G — UX, operations, and demo readiness

Status: complete for the local MVP

- Added student notification pages and certificate status filters.
- Added institution-scoped issuer counts and recent-credential views.
- Hardened student-profile linking so only student accounts can be attached.
- Full automated suite passes: 19 tests.
- Remaining external-provider integrations are documented as optional production hardening.

---

# Improvement roadmap (production.md section 16)

A code review on 27 September 2026 found confirmed bugs, backend features with no UI, a mismatch between the "Blockchain-Based" title and the implementation, and a minimal interface. All items are listed by phase in [production.md §16](production.md). Progress is recorded below.

## Phase P1 — Critical bug fixes

Status: complete (27 September 2026)

- **Bulk issuance crash fixed.** PDF handling is split into `read_pdf()` (validate) and `store_pdf()` (write). Bulk issuance now runs in one transaction and returns a per-row `errors` list for blank `student_identifier` rows. A missing PDF returns a clean 400 instead of a 500.
- **Global rate limit removed.** Ordinary browsing no longer returns 429 after 50 page views. Targeted limits on login, registration, issuance, bulk issuance, and verification remain.
- **`flask seed-demo` now builds a working demo.** It creates a verified "Demo Institute of Technology", an approved issuer profile, a student profile linked to `student@demo.local`, and one issued credential. It is safe to run more than once (`vault/demo.py`).
- **Students can now be linked from the UI.** The university workspace accepts an optional student account email when adding a student and has a "Link account" form for existing profiles. Linking notifies the student about credentials already issued to that profile. Non-student accounts are rejected.
- **Browser errors are readable.** Browser issuance shows success, warning, and error flash messages instead of raw JSON. One handler serves styled HTML error pages for 400, 401, 403, 404, 410, 413, 429, and 500 to browsers and JSON to API clients. A 401 in the browser redirects to the login page.
- **Expiry works end to end.** `Credential.effective_status` reports active credentials past their expiry date as `expired`. It is used by verification, the student vault (including a new Expired filter), share links, and the workspace. The issue form accepts an expiry date, which must be after the issue date.
- **Document comparison checks expiry.** It no longer reports an expired credential as authentic.
- **Issuance is atomic.** The new service `issue_credential()` validates first and writes the credential, signature, audit event, replacement status, and notification in one commit. If anything fails, it rolls back and deletes the stored file. The JSON API and the browser form share this code.

Tests: `tests/test_phase_p1_regressions.py` adds 14 regression tests. Full suite: **33 passed**.

## Phase P2 — Security and code-quality hardening

Status: complete (27 September 2026)

- **Refuses weak secrets.** `ProductionConfig.validate()` stops startup unless `SECRET_KEY` and `SIGNING_SECRET` are set to 32+ character, non-default values. `docker-compose.yml` no longer contains hard-coded secrets and fails fast when they are missing. `.env.example` documents all settings.
- **Real PDF screening.** The byte-substring check (`<script`, `javascript:`) is replaced with structural checks for active PDF content: `/JavaScript`, `/JS`, `/Launch`, `/EmbeddedFile(s)`, `/RichMedia`, `/SubmitForm`, and `/ImportData`. Hex-escaped names (for example `/J#61vaScript`) are decoded first. The optional `MALWARE_SCAN_COMMAND` hook pipes each PDF to an antivirus scanner such as ClamAV. Ordinary PDFs that merely mention "JavaScript" are no longer rejected.
- **Audit-chain race fixed.** On PostgreSQL, `append_event()` takes a transaction-scoped advisory lock, so concurrent events cannot chain to the same previous hash.
- **Account lockout.** Five failed logins lock an account for 15 minutes (both are configurable). The API returns HTTP 423 and the login page shows a clear message. Lockouts and blocked attempts are audited. Login logic is shared in `vault/auth/services.py`. Browser login and registration are now rate-limited, and sessions use Flask-Login `"strong"` protection with SameSite cookies.
- **Admin user management.** `/auth/admin/users` lets an administrator search, filter by role, paginate, and enable or disable users. Enabling an account also clears its lockout. Administrators cannot disable themselves, and every change is audited.
- **Faster reports.** The reports page and CSV export use one grouped query instead of three queries per institution.
- **Pagination and search.** The university workspace student list and the admin user list are searchable and paginated (20 per page).
- **Clearer admin screens.** University review cards show the institution name, code, and representative instead of "request #id". Review decisions give flash feedback. The admin and issuer dashboards link to every tool available to them.
- **Migration `d7a3e91c5b20`.** Adds the lockout columns and two indexes that were declared on the models but never migrated. Verified on a fresh database: upgrade, `flask db check` (no drift), downgrade, and `seed-demo`.

Tests: `tests/test_phase_p2_hardening.py` adds 16 tests. Full suite: **49 passed**.

## Phase P3 — UI foundation and design system

Status: complete (27 September 2026)

- **Design system** (`vault/static/css/app.css`). Colour, spacing, radius, and shadow tokens with full light and dark themes: the OS preference is followed by default, and a toggle in the header remembers the choice. Components: buttons, stat cards, credential cards, status badges (active, revoked, replaced, expired, pending, locked, and more), tables, pills, pagination, alerts, toasts, empty states, a drag-and-drop PDF picker, a password-strength meter, and copy-to-clipboard fields. There are also print styles and reduced-motion support.
- **Role-aware app shell** (`base.html`, `vault/ui.py`). Signed-in users get a sidebar showing only their role's tools. The admin reviews link shows a pending-count badge, the student notifications link shows an unread-count badge, and the student header has a notification bell. On phones the sidebar becomes a slide-in drawer. Visitors see a public top navigation. Navigation entries appear automatically once their route exists, so Phase P4 pages slot in without template edits.
- **Reusable macros** (`vault/templates/macros.html`). SVG icons (Lucide paths, ISC licence), badges, stat cards, empty states, pagination, the drop zone, and a CSRF field.
- **Every page redesigned.**
  - Public: landing page with a hero, "verify a credential" box, role cards, and how-it-works steps; login and registration with a strength meter; university registration; styled error pages.
  - Student: vault as certificate cards with filters, copy ID, PDF, QR, and verify actions; notifications with unread highlighting and "mark all as read".
  - Issuer: role dashboards with stats and recent activity; the workspace issue form now takes a description and expiry date, **templates prefill the form**, and student tables are searchable and paginated; templates page.
  - Admin: university review cards with Approve, Suspend, and Reject buttons; user management with avatars, status badges, and a disable confirmation; reports with SVG distribution bars.
- **Stricter CSP.** With all CSS and JavaScript in external files, the policy no longer allows `'unsafe-inline'`. It is now `default-src 'self'; style-src 'self'; script-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'`. Every page works without JavaScript; the scripts add convenience only.
- **Dev preview.** `.claude/launch.json` runs the app on port 5055 against a local SQLite database (`instance/dev.sqlite`, migrated and seeded).
- **Checked in the browser.** Desktop in dark mode (issuer and admin) and a 375 px phone in light mode (student). Bugs found and fixed during that check: the mobile scrim took up a grid column on desktop, the menu button showed on desktop, a lone credential card stretched full width, and the header overflowed on phones.

Tests: `tests/test_phase_p3_ui.py` adds 10 tests covering every page for every role, role-specific navigation, the unread badge, toasts, the CSP, a template scan that forbids inline styles, scripts, and event handlers, and static assets. Full suite: **59 passed**.

## Phase P4 — Bring existing backend features into the UI

Status: complete (27 September 2026)

- **Public verification portal.** `/verify` is a lookup page; IDs ignore case and spaces. `/credential/<id>` is a human-readable result page with:
  - a colour-coded verdict: valid, expired, revoked, superseded, or "document does not match";
  - the institution name with a "verified institution" badge;
  - the SHA-256 fingerprint with a copy button, and the signature algorithm;
  - a public timeline: issued, replaces or replaced by, revoked, expires;
  - the QR code;
  - an upload box that compares a PDF against the recorded fingerprint (the file is hashed, then discarded).

  **QR codes now open this page instead of raw JSON.** Revocation reasons and personal data are never shown publicly. The JSON API at `/verify/<id>` is unchanged.
- **Issuer credential management.**
  - `/university/credentials`: every institution credential, searchable by ID, title, programme, or student identifier, filterable by status (including computed "expired"), and paginated.
  - `/university/credentials/<id>`: full details, integrity-check history, a QR download, **Replace** (upload a corrected PDF; the old record becomes "replaced" and links to the new one), and **Revoke** (a private reason is required, with a confirmation prompt). Only the original issuer can revoke or replace.
  - Revocation is now a shared service (`revoke_credential`) used by both the API and the UI, and it notifies the student.
- **Bulk issuance page** (`/university/bulk`). Upload a CSV and a PDF, with default title and programme values for blank cells. A result report lists each created credential and every skipped row. A downloadable sample CSV is included.
- **Student share links** (`/student/shares`). Create a link to an active credential valid for 1 hour to 30 days, copy it, see whether each link is active, expired, or revoked, and revoke it. Links are audited. The public `/shared/<token>` page shows the holder's name and the credential without exposing their email or the PDF, and returns 410 once the link has expired or been revoked.
- **Admin console.**
  - `/integrity/monitor`: a "Run scan now" button, the latest result per document with incidents listed first, counts, and the last scan time. The new `flask integrity-scan` CLI is for cron and exits with status 1 when an incident is found.
  - `/audit/ledger`: paginated, filterable events showing each hash and the previous hash, a "Validate chain" button that reports the exact tampered event, "Anchor root", and anchor history.
- The sidebar picked up every new page automatically for the right role.
- **Checked in the browser.** Found and fixed a long fingerprint overflowing the result card (horizontal scroll) and misleading "compared locally" wording.

Tests: `tests/test_phase_p4_features.py` adds 18 tests covering portal lookup, match and mismatch, the QR target, revoke and replace (including privacy of the reason and blocking a colleague), bulk defaults and row errors, the share-link life cycle and expiry, tamper detection by the integrity monitor and CLI, audit tamper detection and anchor refusal, and role protection. Full suite: **77 passed**.

## Phase P5 — Real blockchain layer and public-key signatures

Status: complete (27 September 2026)

This resolves the mismatch between the "Blockchain-Based" title and the implementation. Design and setup: [docs/blockchain.md](docs/blockchain.md).

- **Ed25519 signatures** (`vault/chain/signing.py`). Every new credential is signed over a canonical JSON record: ID, institution code, title, programme, dates, and document SHA-256. The public key is published at `/.well-known/acv-signing-key.json`, so **anyone can verify offline**, unlike the old HMAC, which needed the server secret.
  - Legacy HMAC credentials are still recognised, and `flask upgrade-signatures` re-signs them when their HMAC is still valid.
  - `flask generate-signing-key` creates the key file (mode 600). Production refuses to start without a key.
- **Merkle batching** (`vault/chain/merkle.py`). Credentials are anchored in batches: one root per transaction, and each credential stores its own inclusion proof. Leaves and nodes use domain-separated hashing (0x00 and 0x01 prefixes) against second-preimage attacks.
- **Smart contract** (`blockchain/contracts/CredentialAnchor.sol`, Solidity 0.8.24). Owner-only `anchor(root, kind, count)`; roots are immutable (`AlreadyAnchored` revert) and zero roots are rejected; it emits an `Anchored` event and offers `isAnchored` and `anchoredAt` views. The compiled ABI and bytecode are committed, with a reproducible `blockchain/compile.js`. `blockchain/deploy.py` deploys to any EVM RPC (Polygon Amoy, Sepolia, Anvil).
- **Anchor providers** (`vault/chain/providers.py`). `local` is the offline default and is labelled honestly in the UI as "not a public blockchain". `ethereum` signs and sends transactions with web3.py and stores the transaction hash, block number, network, and explorer link. Provider failures roll back the whole batch.
- **Public verification page** has a new *Cryptographic proof* section: signature verified or invalid, and Merkle proof and anchor status with a link to the transaction. If the stored record was edited after signing or anchoring, the verdict becomes **"Record integrity failure"**. A **proof bundle** download is available at `/credential/<id>/proof.json`.
- **Standalone verifier** (`blockchain/verify_proof.py`). An examiner or employer can check the PDF hash, the Ed25519 signature, the Merkle path, and (with `--rpc`) the on-chain root, without the vault's code or trust in its operator. Checked end to end against the dev server: **VERIFIED**.
- **Admin controls.** The audit ledger has "Anchor credentials (n pending)" and "Anchor audit head" buttons, plus anchor history showing kind, network, and transaction. There is also `flask anchor-credentials` for cron.
- **Schema.** Migration `e5b8c2f4a901` adds signature key IDs, anchor receipt fields, and the `credential_anchor_proof` table. Verified with upgrade, `db check` (no drift), and downgrade. The unused `blockchain.py` prototype was removed.
- **Dependencies.** `cryptography` was added to `requirements.txt`. The optional `requirements-blockchain.txt` adds web3 and eth-tester.

Tests: `tests/test_phase_p5_blockchain.py` adds 25 tests.
- **Merkle:** proofs for every leaf across tree sizes 1–33, tamper rejection, and domain separation.
- **Signatures:** tampering with the database breaks the signature and shows publicly; legacy upgrade.
- **Local anchoring:** batching, tampering detected even after an attacker re-signs, the admin button and CLI.
- **Offline verifier:** accepts a genuine bundle and rejects forged payloads and edited PDFs.
- **Real contract on an in-process EVM:** on-chain anchoring with the transaction hash and explorer link, duplicate-root revert, owner-only access, rollback on provider failure, and audit-head anchoring.

Full suite: **103 passed**.

Not yet done: anchoring to a public testnet needs a funded testnet wallet and RPC URL, which only the project owner can provide. The code path is tested against a real EVM, and the steps are in `docs/blockchain.md`.

## Phase P6 — New product features

Status: complete (27 September 2026)

- **Student claim flow.** On `/student/claim` a student picks a verified university and enters their student ID. The university reviews requests at `/university/claims`, which shows a pending-count badge in the sidebar, the student's name, email-verification status, and whether the ID is already taken.
  - Approving links the profile, creating it if needed, and tells the student how many credentials are now in their vault.
  - Rejecting requires a note that is shown to the student.
  - Safeguards: claims need a verified email; IDs already linked to another account are refused; issuers only see their own institution's claims; every decision is audited.
- **Email.**
  - `vault/mail.py` supports console, memory (tests), and SMTP backends. Emails are **queued and sent only after the database commit succeeds**, so rolled-back actions never send mail.
  - `vault/notifications.py: notify()` replaces all direct notification writes: each in-app notification is mirrored by email to verified addresses.
- **Password reset** (`/auth/forgot` and `/auth/reset/<token>`). Signed tokens expire after one hour and are single-use, because they are bound to the current password hash. Responses are identical for unknown emails, so accounts cannot be enumerated. A reset also clears any lockout. The login page has a "Forgot password?" link.
- **Email verification.** Registration (student and university) sends a signed three-day link. Signed-in users with an unconfirmed address see a banner with a "Resend link" button.
- **Generated certificates** (`vault/credentials/certificates.py`). Issuers can choose **"Generate automatically"** instead of uploading a PDF. The result is a branded A4 landscape certificate with the institution name, logo, and accent colour, the recipient, title, programme, dates, credential ID, a signatory line, and an **embedded verification QR code**. Output is deterministic (reportlab invariant mode), so the same inputs reproduce the recorded SHA-256. Generated PDFs pass the same active-content screen as uploads.
- **Institution branding** (`/university/settings`). Accent colour (validated hex), official website (https only), and a logo upload (PNG or JPEG, checked by file signature, 512 KB maximum). These appear on generated certificates and public verification pages; colour is applied through an SVG attribute, so the CSP stays strict. The logo is served publicly at `/university/logo/<code>`.
- **Verifier receipt** (`/credential/<id>/receipt`). A printable page (with a "Print or save as PDF" button) recording the UTC time of the check, the status, the signature and anchor results, the document fingerprint, a reference code, and a QR code for re-checking.
- **Expiry reminders.** `flask send-expiry-reminders --days 30`, for cron, notifies students (in-app and by email) about credentials expiring soon, once per credential.
- **Migration `f81d0c7e3a12`.** Adds `claim_request`, institution branding columns, and `user.email_verified`. Verified with upgrade, `db check`, and downgrade. `reportlab` was added to `requirements.txt`.

Tests: `tests/test_phase_p6_features.py` adds 15 tests covering verification-email links and tampered tokens, a single-use password reset, no account enumeration, mail sent after commit only and never on rollback, claim approve and reject with a required note, the unverified-email and taken-ID guards, cross-institution isolation, deterministic generated certificates, the recipient-name requirement, branding validation and logo serving, the receipt, and one-time expiry reminders. The P3 page-render test now covers all 25 pages. Full suite: **118 passed**.

## Phase P7 — Testing, CI, and clean-up

Status: complete, with two items left for the project owner (27 September 2026)

- **Security regression tests** (`tests/test_phase_p7_security.py`, 20 tests).
  - Document-download IDOR matrix: owner student, own issuer, and admin are allowed; another student and a rival institution's issuer are refused; anonymous users get 401.
  - A rival issuer cannot view or revoke a credential.
  - API revoke validation; the public signature endpoint; bulk API CSV and UTF-8 errors.
  - Unapproved issuers are blocked on every route; non-students cannot be linked to profiles; templates are scoped to their institution.
  - **CSRF is enforced** when enabled.
  - Signing keys load from environment PEM text, and a missing key fails loudly.
  - `generate-signing-key` writes mode 600 and refuses to overwrite.
  - The SMTP backend uses TLS and login; `demo-reset` works.
- **Coverage.** 92% of `vault/` (up from 89%). CI fails if coverage drops below 85%.
- **GitHub Actions** (`.github/workflows/ci.yml`).
  - Test job on Python 3.12 and 3.13, with coverage and the real in-process EVM contract tests.
  - Migration job: upgrade, `db check` for drift, and downgrade to base.
  - A **PostgreSQL 16 job** that migrates, checks, seeds, anchors, and runs an integrity scan.
- **`flask demo-reset --yes`.** Erases all data and stored documents and reseeds deterministic demo data for rehearsals. It refuses to run in production or without `--yes`.
- **Requirements.** `requirements.txt` (runtime), `requirements-blockchain.txt` (web3 and eth-tester), and `requirements-dev.txt` (everything plus pytest-cov).
- **Legacy prototype.** The root `templates/` pages were moved to `docs/legacy-prototype/` with a README, kept only as evidence of how the project evolved for the report. `blockchain.py` was removed in P5.
- **Checked locally.** The full migration chain upgrades and downgrades to base on SQLite. Full suite: **138 passed**.

Left for the project owner:
- `uploads/` still contains **real personal PDFs** (e.g. a named student's coursework and an internship report), and `source/` is a stray virtualenv. Both are git-ignored, but they should be deleted by the owner before the project folder is zipped or shared. They were not deleted automatically because they are the owner's files.
- The PostgreSQL CI job could not be run locally (no PostgreSQL or Docker on this machine). It will first run on GitHub.

## Phase P8 — Documentation, report, and demo

Status: complete (27 September 2026)

- **README.md** rewritten: what each role can do, the five-layer trust model, a SQLite quick start, a table of CLI commands, tests and CI, project structure, and links to all docs.
- **docs/final-demo.md.** A 15-minute browser walkthrough across all four roles, finishing with live tamper demonstrations: database edit leading to "Record integrity failure", file edit caught by FIM, audit-log edit caught by chain validation, and `verify_proof.py` outputting **VERIFIED**.
- **docs/report-outline.md.** The report structure (architecture, trust layers, implementation highlights, a threat-to-evidence results table, honest limitations) and viva answers, including "Is it really blockchain-based?" and "What if an insider re-signs a record?".
- **docs/operations.md.** A deployment checklist covering secrets, the signing-key backup, the cron schedule for anchoring, integrity scans, and reminders, and SMTP; the full list of implemented security controls; and the remaining hardening before an internet-facing deployment.
- **docs/blockchain.md** (added in P5). Design, testnet setup, and independent verification.
- `production.md` §16 now marks every phase complete and lists the owner's open items.

Not done: screenshots for the report. Capture them while following `docs/final-demo.md`.

---

## Roadmap outcome

| | Before (27 Sep review) | After |
| --- | --- | --- |
| Confirmed bugs | 8, including a bulk-issuance crash and 429 errors after 50 page views | Fixed, with regression tests |
| Blockchain | In-memory list prototype; "local" anchor only | Ed25519 signatures, Merkle batching, Solidity contract tested on a real EVM, standalone verifier |
| UI | One inline-CSS line, JSON responses for key flows | Design system, role-aware shell, dark mode, mobile, 25+ pages, strict CSP |
| Features | JSON-only verify, share, revoke, integrity, and audit | Full UI for all of them, plus claims, generated certificates, branding, email, password reset, receipts, expiry reminders |
| Tests | 19 | **138 (92% coverage)**, with CI on SQLite and PostgreSQL |
