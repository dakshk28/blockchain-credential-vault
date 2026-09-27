# Production Plan: Academic Credential Vault with File Integrity Monitoring

## 1. Project purpose

Build a secure web application for issuing, storing, verifying, revoking, and monitoring academic credentials. The system combines:

- credential verification through SHA-256 hashes;
- persistent records in PostgreSQL;
- role-based access control for institutions, students, verifiers, and administrators;
- QR-code based public verification;
- File Integrity Monitoring (FIM) for stored documents; and
- a tamper-evident audit chain for important actions.

The project must be presented honestly: the first version uses a **tamper-evident internal audit ledger**, not a decentralized public blockchain. Anchoring audit roots to a blockchain testnet is optional advanced work.

## 2. Problem statement

Paper and digital academic credentials can be forged, altered, lost, or difficult for employers to validate. Institutions also need an auditable history of credential issuance and a way to detect changes to stored documents.

This system enables an authorized institution to issue a credential, create a cryptographic baseline for its document, and give the credential a unique ID and QR code. A verifier can check its status publicly, while authorized users can compare an uploaded document against its baseline. The FIM module identifies stored documents that are unchanged, modified, missing, or inaccessible.

## 3. Scope

### In scope

- Secure login and role-based authorization.
- Persistent credential data in PostgreSQL.
- Authorized credential issuance and document upload.
- SHA-256 hashing and baseline persistence.
- Certificate ID and QR-code verification.
- Optional file upload during verification to detect modification.
- Credential revocation, expiry, and replacement.
- Integrity monitoring of stored credential files.
- Tamper-evident audit log.
- Security testing, documentation, and a repeatable demo.

### Out of scope for the core submission

- Real university ERP integration.
- Government identity verification.
- A production public blockchain deployment involving real funds.
- Full antivirus scanning implementation; the architecture should allow it later.
- Sending real email or SMS notifications; a local notification record is sufficient initially.

## 4. Users and permissions

| Role | Main permissions |
| --- | --- |
| Administrator | Approves/rejects issuer accounts, manages users, views all incidents and audit logs, configures the system. |
| Institution issuer | Creates credentials for their institution, uploads documents, revokes or replaces credentials they issued, views institution reports. |
| Student | Views their own credentials and status; downloads only credentials they are permitted to access. |
| Public verifier | Verifies by credential ID or QR code; may upload a file for hash comparison; never sees unnecessary private data. |

**Permission rule:** a user must never be able to issue, edit, revoke, view, or download a credential outside their role and institution scope.

## 5. Target architecture

```text
Browser
  |
  +-- Flask application
       |
       +-- Authentication and authorization service
       +-- Credential service
       +-- Verification service
       +-- File integrity monitoring service
       +-- Audit-chain service
       |
       +-- PostgreSQL database
       +-- Private credential-file storage
       +-- Scheduled integrity-check worker
```

### Recommended stack

| Area | Recommendation |
| --- | --- |
| Backend | Python 3.11+ and Flask |
| Database | PostgreSQL |
| ORM and migrations | SQLAlchemy and Alembic/Flask-Migrate |
| Authentication | Flask-Login or JWT with secure password hashing via Werkzeug/Argon2 |
| Frontend | Server-rendered Jinja templates, Bootstrap or a small custom CSS layer |
| QR generation | Python `qrcode` library |
| File storage | A private local storage directory for development; object storage in a future deployment |
| Background work | APScheduler for the college-project version; Celery/RQ later if required |
| Testing | pytest and Flask test client |
| Deployment | Docker Compose with Flask/Gunicorn, PostgreSQL, and Nginx (optional final deployment) |

## 6. Core data model

These tables are the minimum design. Final column names can change, but relationships and security boundaries must remain.

### users

- `id` (UUID or integer primary key)
- `email` (unique)
- `password_hash`
- `full_name`
- `role` (`admin`, `issuer`, `student`)
- `is_active`
- `created_at`, `last_login_at`

### institutions

- `id`
- `name`
- `code` (unique short identifier)
- `address`
- `is_verified`
- `created_at`

### issuer_profiles

- `user_id` (linked to users)
- `institution_id`
- `approval_status` (`pending`, `approved`, `rejected`, `suspended`)
- `approved_by`, `approved_at`

### student_profiles

- `user_id` (linked to users; nullable if a student account has not been created)
- `institution_id`
- `student_identifier` (institution-specific ID)

### credentials

- `id`
- `credential_id` (public unique value, for example `ACV-2026-...`)
- `institution_id`
- `student_profile_id`
- `issued_by_user_id`
- `title`, `programme`, `description`
- `issue_date`, `expiry_date`
- `status` (`active`, `revoked`, `expired`, `replaced`)
- `document_sha256`
- `storage_key` (private randomized filename/key, never the original browser filename)
- `original_filename` (display metadata only)
- `document_available`
- `replaced_by_credential_id` (nullable)
- `created_at`, `updated_at`

### integrity_checks

- `id`
- `credential_id`
- `checked_at`
- `current_sha256` (nullable when missing)
- `result` (`unchanged`, `modified`, `missing`, `inaccessible`, `error`)
- `details`

### audit_events

- `id`
- `event_type` (for example `credential_issued`, `credential_verified`, `credential_revoked`)
- `actor_user_id` (nullable for public checks)
- `credential_id` (nullable for account events)
- `metadata_json` (never place passwords, tokens, or unnecessary PII here)
- `created_at`
- `previous_event_hash`
- `event_hash`

### revocations

- `id`
- `credential_id`
- `reason`
- `revoked_by_user_id`
- `revoked_at`

## 7. Security baseline

Implement these rules before calling the application production-ready.

1. Store passwords only as secure password hashes; never store plaintext passwords.
2. Use environment variables for secrets, database URLs, and deployment configuration. Do not commit a `.env` file.
3. Disable Flask debug mode outside local development.
4. Enforce authentication and server-side authorization on every protected route.
5. Use CSRF protection for browser forms that change server state.
6. Accept only approved document types, initially PDF; enforce a conservative size limit.
7. Generate randomized storage keys with `secrets` or UUIDs. Do not save directly using user-provided filenames.
8. Keep credential files outside the public static directory and serve them only after authorization.
9. Validate and normalize all input on the server.
10. Use parameterized queries through the ORM; never build SQL using string concatenation.
11. Add rate limiting to login, upload, and public verification endpoints.
12. Add secure response headers: Content-Security-Policy, X-Content-Type-Options, Referrer-Policy, and frame protection.
13. Log security-relevant events without logging passwords, session tokens, or full confidential documents.
14. Back up PostgreSQL and verify that restoration works.
15. Use HTTPS for any deployed environment.

## 8. Phase-by-phase implementation plan

## Phase 0: Requirements, research, and design

**Goal:** agree on exactly what will be built before adding features.

### Tasks

1. Write the problem statement, objectives, scope, and limitations.
2. Finalize the four user roles and their permissions.
3. Create use-case, ER, data-flow, and deployment diagrams.
4. List public fields allowed on a verification page and private fields that must remain hidden.
5. Define credential states: active, revoked, expired, and replaced.
6. Define integrity states: unchanged, modified, missing, inaccessible, and error.
7. Create a threat model covering forged credentials, malicious uploads, stolen accounts, unauthorized file access, database tampering, and denial-of-service abuse.

### Completion criteria

- Guide approves the feature scope.
- Database entities and role-permission matrix are documented.
- At least five threats and corresponding mitigations are recorded.

## Phase 1: Foundation and project cleanup

**Goal:** convert the current prototype into a maintainable application foundation.

### Tasks

1. Initialize Git and add `.gitignore` rules for virtual environments, `.env`, uploads, caches, and database dumps.
2. Create `README.md`, `requirements.txt` or `pyproject.toml`, and `.env.example`.
3. Refactor the application into modules: `auth`, `credentials`, `verification`, `integrity`, `audit`, and `models`.
4. Add application configuration classes for development, test, and production.
5. Connect PostgreSQL and add migration support.
6. Implement structured error pages and JSON API error responses with appropriate HTTP status codes.
7. Establish pytest and add tests for application startup and health endpoints.
8. Remove real sample credentials from source control; use generated dummy documents for demos.

### Completion criteria

- The app starts from documented setup steps.
- A fresh database can be created through migrations.
- No secrets, uploaded files, virtual environments, or generated cache files are tracked.
- Automated tests run successfully.

## Phase 2: Identity, authentication, and role access

**Goal:** ensure only authorized users can perform sensitive actions.

### Tasks

1. Create user registration and login/logout flows.
2. Implement password hashing and password-strength validation.
3. Add role checks for administrator, issuer, and student actions.
4. Build issuer registration with an administrator approval workflow.
5. Restrict issuers to their assigned institution.
6. Create an admin user-management page.
7. Record login, logout, failed-login, account approval, and role-change audit events.
8. Add rate limiting and CSRF protection.

### Completion criteria

- A public visitor cannot access issuer or admin pages.
- An unapproved issuer cannot issue credentials.
- An issuer cannot access another institution's credentials.
- Passwords never appear in the database or logs in plaintext.

## Phase 3: Secure credential issuance and storage

**Goal:** create complete, persistent credential records safely.

### Tasks

1. Build an issuer-only credential creation form.
2. Validate student identifier, credential title, programme, dates, and optional expiry date.
3. Restrict uploads to PDF initially and enforce a file-size limit.
4. Calculate SHA-256 directly from the upload stream or controlled temporary storage.
5. Generate a public unique credential ID.
6. Store the document with a randomized storage key, outside publicly accessible paths.
7. Save credential metadata, baseline hash, storage key, issuer identity, and status in PostgreSQL as one controlled workflow.
8. Detect duplicate content hashes and decide whether to reject duplicates or allow them with a visible warning.
9. Write a `credential_issued` audit event.

### Completion criteria

- Only approved issuers can issue a credential.
- The original document can be retrieved only by authorized users.
- A credential survives application restart.
- Each newly issued credential has a unique ID and baseline SHA-256 hash.

## Phase 4: Public verification, QR code, and credential lifecycle

**Goal:** make credentials easy to verify without exposing private information.

### Tasks

1. Generate a QR code for a public URL such as `/verify/<credential_id>`.
2. Build a public verification page that displays only safe fields: institution, credential title, issue date, current status, and a limited student identifier or name according to the privacy decision.
3. Support searching by credential ID.
4. Add an optional upload comparison flow: hash the supplied document and compare it with the credential baseline.
5. Clearly distinguish results: authentic and unchanged, authentic but document differs, revoked, expired, replaced, and unknown credential.
6. Build issuer workflows to revoke or replace credentials with a required reason.
7. Write audit events for verification, revocation, and replacement.

### Completion criteria

- Scanning a generated QR code opens the correct public verification page.
- An exact document verifies as unchanged.
- A one-byte-modified document is marked modified.
- Revoked and expired credentials are never shown as valid.

## Phase 5: File Integrity Monitoring

**Goal:** apply cybersecurity File Integrity Monitoring concepts to stored credentials.

### Tasks

1. Create an integrity-check service that reads each active credential's stored file.
2. Recalculate the SHA-256 hash and compare it with `document_sha256`.
3. Store an integrity-check record for each result.
4. Mark outcomes as unchanged, modified, missing, inaccessible, or error.
5. Create a scheduled job to run checks regularly; use a manually triggered route or command during development.
6. Add an integrity dashboard showing latest status, incident counts, last check time, and affected credentials.
7. Record `integrity_modified` and `integrity_missing` audit events only when a new incident is detected, to avoid noisy duplicates.
8. Add a simple incident acknowledgement workflow for administrators.

### Completion criteria

- Editing a stored test file causes a `modified` incident.
- Deleting a stored test file causes a `missing` incident.
- An unchanged stored file remains `unchanged`.
- Prior incident records remain visible after restart.

## Phase 6: Tamper-evident audit chain

**Goal:** prove whether the application audit history has been altered.

### Tasks

1. Define canonical audit-event content: event type, timestamp, actor, target credential, and safe metadata.
2. Calculate each event hash from its canonical content plus the previous event hash.
3. Save the prior event hash and new event hash atomically with each audit event.
4. Build an administrator-only chain-validation operation.
5. Report the first invalid event if an event is altered, removed, or relinked.
6. Add audit search/filtering by credential, user, event type, and date.
7. Optionally compute a daily audit-root hash and store it separately; this can later be anchored on a blockchain testnet.

### Completion criteria

- Normal audit history validates successfully.
- Changing an event directly in a test database causes validation to fail.
- The validation report identifies the broken event or chain link.

## Phase 7: Security hardening, quality assurance, and deployment

**Goal:** test the system as a cybersecurity project, not only as a functional web app.

### Tasks

1. Add unit tests for hashing, credential state rules, FIM classification, permissions, and audit-chain validation.
2. Add integration tests for issue, verify, revoke, and integrity-monitoring workflows.
3. Test negative cases: invalid uploads, oversized files, unsafe filenames, SQL injection payloads, XSS payloads, brute-force login attempts, cross-institution access, and invalid QR IDs.
4. Review logs to ensure secrets and sensitive documents are absent.
5. Configure production environment variables, disable debug mode, and enable secure cookies and security headers.
6. Add Docker Compose for the application and PostgreSQL.
7. Create database backup and restore instructions.
8. Run a final vulnerability scan or manual OWASP Top 10 review and record findings/remediations.

### Completion criteria

- Critical user flows and security controls have passing tests.
- The project can be run from clean setup instructions.
- The demo deployment does not expose debug tools, database credentials, private uploads, or secret keys.

## Phase 8: Report, presentation, and final demonstration

**Goal:** make the technical work easy to assess in a final-year-project viva.

### Tasks

1. Write the report: abstract, problem, literature review, methodology, architecture, implementation, testing, results, limitations, and future work.
2. Include diagrams: use case, ER, data flow, sequence diagrams for issuance/verification/FIM, and deployment diagram.
3. Prepare test evidence with screenshots and expected/actual results.
4. Create a 10- to 15-slide presentation.
5. Prepare dummy credentials and deterministic demo accounts.
6. Rehearse the demo flow below.
7. Prepare answers for common viva questions: why SHA-256, why PostgreSQL, why this is tamper-evident rather than decentralized blockchain, how FIM works, and what privacy protections exist.

### Completion criteria

- The project can be demonstrated without relying on real student data or external services.
- All primary scenarios are documented and rehearsed.
- Limitations and future enhancements are explicitly stated.

## 9. Final demonstration script

1. Administrator approves an institution issuer account.
2. Approved issuer signs in and creates a credential using a dummy PDF.
3. The system produces a credential ID, baseline hash, and QR code.
4. A public verifier opens the QR link and sees an active credential status.
5. The verifier uploads the untouched document and receives `authentic / unchanged`.
6. The verifier uploads a modified copy and receives `modified / hash mismatch`.
7. The issuer revokes the credential; the public page changes to `revoked`.
8. An administrator runs an integrity check after a stored test file is modified or deleted; the dashboard shows the incident.
9. An administrator validates the audit chain successfully.
10. For a controlled test, alter an audit record in a disposable test database and show that audit validation detects the broken chain.

## 10. Acceptance checklist

### Functional

- [ ] Users can authenticate and are restricted by role.
- [ ] Only approved issuers can create credentials.
- [ ] Credentials persist in PostgreSQL after restart.
- [ ] A credential has a public ID, QR code, baseline hash, and lifecycle status.
- [ ] Public verification works by QR/ID.
- [ ] Upload comparison detects altered files.
- [ ] Revocation, expiry, and replacement are handled correctly.
- [ ] Integrity monitoring detects unchanged, modified, and missing files.
- [ ] Audit-chain validation detects modified audit history.

### Security

- [ ] Passwords are securely hashed.
- [ ] Secrets are configured outside source control.
- [ ] Uploads have type, size, and safe-storage protections.
- [ ] Private documents are not public URLs.
- [ ] Sensitive actions use authorization and CSRF protection.
- [ ] Debug mode is disabled in deployment.
- [ ] Rate limiting protects login, upload, and verification endpoints.
- [ ] Security tests cover unauthorized access and malicious input.

### Submission

- [ ] README and setup instructions are complete.
- [ ] Database schema and architecture diagrams are included.
- [ ] Tests and test evidence are included.
- [ ] The presentation and demo use dummy data.
- [ ] Known limitations and future work are documented.

## 11. Prioritization: MVP versus advanced work

### Must have for final submission

- PostgreSQL persistence.
- Login, issuer approval, and role authorization.
- Secure credential issuance with SHA-256 baseline.
- QR/credential-ID public verification.
- Modified-file detection through upload comparison.
- Revocation.
- FIM checks for unchanged, modified, and missing states.
- Tamper-evident internal audit chain.
- Tests, report, and demo.

### Build only after the must-have list works

- Expiry and replacement workflows.
- Email notifications.
- Encryption at rest using managed keys.
- Advanced reporting and visual analytics.
- Object-storage integration.
- Blockchain-testnet anchoring of daily audit roots.
- Digital signatures issued by institutions.

## 12. Important implementation decisions

1. **Use SHA-256 for credential integrity.** MD5 may be discussed academically as a legacy comparison but must not be used as the trust decision.
2. **Hash content, not filenames.** Renaming a file should not affect authenticity; changing even one byte must.
3. **Do not expose the raw hash as the only proof.** The verification page must also check credential status and issuer authorization.
4. **Do not delete an issuance record when its file is missing.** Preserve the credential and show document availability separately.
5. **Keep public verification privacy-minimal.** Reveal only the fields needed for a verifier to trust the credential.
6. **Treat the audit chain as evidence, not magic.** If an attacker can alter the database and all application secrets, a local chain alone is insufficient; backups, access controls, and optional external anchoring provide stronger protection.

## 13. Immediate next steps

1. Confirm the final roles, public verification fields, and document types.
2. Create the Phase 0 diagrams and threat model.
3. Start Phase 1: clean the current Flask project and establish PostgreSQL, configuration, migrations, Git rules, and tests.
4. Do not add public-blockchain integration until the core MVP is fully working and tested.

## 14. Feature expansion phases: student vault and university portal

The core MVP is extended through these phases. Each phase must preserve server-side role and institution boundaries.

1. **Expansion Phase A — Ownership foundation:** add student profiles, credential-to-student ownership, university verification requests, and notification records.
2. **Expansion Phase B — Student vault:** show each student only their credentials, protected downloads, QR/public-ID details, statuses, and a clear empty state.
3. **Expansion Phase C — University onboarding:** create a distinct university registration/login experience; representatives and institutions remain pending until administrator verification.
4. **Expansion Phase D — Administrator verification:** let administrators approve/reject/suspend institutions and issuer representatives with audit records.
5. **Expansion Phase E — University workspace:** complete for the MVP: approved universities can create/search institution-scoped students, issue assigned credentials, view counts/recent credentials, and preserve lifecycle controls. Templates and bulk issuance remain backlog items.
6. **Expansion Phase F — Trust and operations:** complete for the local MVP: student notifications, status filters, role-specific workspace views, and institution-scoped dashboards are available. Scheduled operations and external delivery remain deployment enhancements.
7. **Expansion Phase G — Integrations and advanced deployment:** core security review and demo flow are complete; external integrations (object storage, malware scanning, Redis, signatures, blockchain anchoring) remain optional production hardening.

## 15. Achievable engineering-project feature roadmap

The following phases extend the working MVP with features that can be implemented and demonstrated locally using dummy data. Each phase should preserve role, institution, ownership, privacy, and audit boundaries.

### Phase H — Credential lifecycle management

**Goal:** make credentials manageable after initial issuance.

- Add issuer-facing credential search and filters by student, programme, status, and date.
- Add expiry dates and automatic expired-status evaluation.
- Add a controlled replacement workflow that links the old and new credentials.
- Add mandatory reason fields for replacement and revocation.
- Display credential history to students, issuers, and administrators according to role.

**Completion criteria:** every lifecycle transition is authorized, auditable, visible in public verification, and covered by tests.

### Phase I — Credential templates and institution branding

**Goal:** reduce repetitive data entry while keeping issuance controlled.

- Let approved issuers create, edit, archive, and select institution-scoped templates.
- Store title, programme, description, default expiry period, and metadata fields in each template.
- Add institution name/logo and a printable credential view.
- Prevent one institution from viewing or editing another institution's templates.

**Completion criteria:** an issuer can create a template, use it for issuance, and demonstrate institution isolation.

### Phase J — Bulk issuance and import quality

**Goal:** support realistic university batch workflows.

- Add CSV upload preview before issuing credentials.
- Validate required columns, duplicate identifiers, invalid dates, and missing students.
- Provide row-level success and error reports.
- Add an idempotency key so retrying a batch does not duplicate credentials.
- Record one batch audit event with links to each issued credential.

**Completion criteria:** a valid sample CSV issues multiple credentials, while invalid rows are reported without partial unauthorized issuance.

### Phase K — Student sharing and verifier reports

**Goal:** make credentials useful outside the application.

- Add time-limited, revocable sharing links for student-selected credentials.
- Allow students to revoke an active share link.
- Add a privacy-safe verification report containing status, issuer, issue date, and integrity result.
- Add downloadable PDF or printable HTML verification reports.
- Record share creation, access, and revocation events.

**Completion criteria:** a verifier can validate a shared credential without receiving private document access.

### Phase L — Notifications and operational workflows

**Goal:** make important events visible and actionable.

- Add notification read/unread state and bulk mark-as-read actions.
- Notify students about issuance, revocation, replacement, and expiry.
- Notify administrators about pending university reviews and integrity incidents.
- Add an administrator incident page with acknowledgement, notes, and status.
- Add a local scheduled-command entry point for recurring integrity checks.

**Completion criteria:** every notification is permission-safe, linked to its source event, and testable without an email provider.

### Phase M — Administration and reporting

**Goal:** provide evidence for university and project evaluation.

- Add institution and issuer management screens for administrators.
- Add dashboard charts for issued, active, revoked, expired, and replaced credentials.
- Add CSV export of privacy-safe credential and audit summaries.
- Add audit-event filters by actor, institution, event type, and date range.
- Add a system health page for database, storage, audit-chain, and integrity-check status.

**Completion criteria:** administrators can produce a scoped report without exposing private documents or passwords.

### Phase N — Engineering quality and final evaluation

**Goal:** make the project presentation-ready and maintainable.

- Add OpenAPI documentation for supported APIs.
- Add end-to-end browser tests for student, university, administrator, and verifier journeys.
- Add security tests for CSRF, IDOR, unsafe uploads, rate limits, and cross-institution access.
- Add deterministic demo seed data and a reset command for rehearsals.
- Add CI test execution, migration checks, and coverage reporting.
- Add architecture, threat-model, test-evidence, and deployment diagrams to the report.

**Completion criteria:** a clean checkout can migrate, seed, test, and run the complete demonstration using dummy data.

### Recommended order

`Phase H → Phase I → Phase J → Phase K → Phase L → Phase M → Phase N`

Refer to `docs/feature-expansion-plan.md` for detailed acceptance criteria and sequencing.

---

## 16. Improvement roadmap (code review, 27 September 2026)

A full review of the codebase found confirmed bugs, backend features with no user interface, a mismatch between the project title ("Blockchain-Based") and the implementation, and a minimal UI. Every item is listed below in the phase that fixes it. Phases are ordered by dependency and by viva impact. Progress is recorded in `WORK_SUMMARY.md`.

Legend: **[BUG]** confirmed defect · **[GAP]** shortcoming or missing UI · **[NEW]** new feature · **[UI]** interface work

### Phase P1 — Critical bug fixes ✅

**Goal:** everything that already exists works correctly and cannot break during a demo.

- [BUG] Bulk issuance always crashes: `save_pdf()` receives a `BytesIO` with no `.filename` (`vault/credentials/routes.py`). It also writes an orphan file for the digest and crashes when the PDF is missing.
- [BUG] The global default rate limit ("50 per hour") applies to every page, so ordinary browsing returns HTTP 429 after about 50 views. Remove global limits and keep the targeted limits on login, registration, issuance, and verification.
- [BUG] `seed-demo` creates an issuer with no institution or issuer profile, so the demo issuer cannot do anything. It also creates no student profile or credentials.
- [BUG] A student account registered in the UI can never be linked to a university student profile, so the student vault is always empty unless the JSON API is used.
- [BUG] Browser issuance errors show raw JSON. 400, 403, and 413 errors have no HTML pages.
- [BUG] The "expired" status is never computed. Expiry cannot be set when issuing, and the vault filter for expired credentials never matches.
- [BUG] Document comparison reports an expired credential as authentic.
- [BUG] Issuance writes the file before the database commit and splits replacement and notification into separate commits. A failure leaves orphan files or half-saved data.
- [BUG] Bulk rows with a blank `student_identifier` create empty student profiles.

**Completion criteria:** regression tests exist for every bug above and the full suite passes.

### Phase P2 — Security and code-quality hardening ✅

- [GAP] Production must refuse to start with the default `SECRET_KEY` or `SIGNING_SECRET`.
- [GAP] Replace the byte-substring "malware scan" with structural PDF checks (reject `/JavaScript`, `/JS`, `/Launch`, `/EmbeddedFile`, and `/OpenAction` with a script). Keep an antivirus hook for ClamAV.
- [GAP] Audit-chain race condition: serialise `append_event` (row lock on PostgreSQL, single writer on SQLite).
- [GAP] Account lockout after repeated failed logins, and session protection set to "strong".
- [GAP] Admin user management: list, disable, and enable users from the UI.
- [GAP] Remove N+1 queries from the reports (use grouped counts) and add pagination to large lists.
- [GAP] Consistent JSON versus HTML error handling for API and browser routes.

### Phase P3 — UI foundation and design system ✅

- [UI] A shared stylesheet (`static/css/app.css`) with design tokens, light and dark themes, and a responsive layout. There is no inline CSS, which keeps the CSP strict.
- [UI] A role-aware app shell: top bar, sidebar navigation for each role (student, issuer, admin), and an unread-notification badge.
- [UI] Flash-message toasts for every action (success and error).
- [UI] Components: stat cards, status badges (active, revoked, replaced, expired), styled tables, empty states, form validation hints, and a drag-and-drop file input.
- [UI] A redesigned landing page and styled 400, 403, 404, 413, 429, and 500 error pages.

### Phase P4 — Bring existing backend features into the UI ✅

- [GAP] **Public verification portal:** look up a credential by ID or QR code and get a human-readable result page (institution name, title, status, timeline) plus an option to drop in a PDF for hash comparison. The QR code points to this page, not to JSON.
- [GAP] **Issuer tools:** revoke and replace from the UI, pick a template in the issue form, a bulk CSV issuance page with a per-row result report, expiry dates, a searchable and paginated credential list, and a QR download.
- [GAP] **Student sharing:** create a share link (choose its expiry), list active links, revoke them, and a public shared-credential page.
- [GAP] **Admin console:** integrity monitor (run a scan and view incidents), an audit-chain viewer with validation, anchor history, reports with charts, and university review cards that show institution names.
- [GAP] Dashboards for each role link to every feature available to that role.

### Phase P5 — Real blockchain layer and public-key signatures ✅

This resolves the mismatch between the "Blockchain-Based" title and the implementation.

- [NEW] Ed25519 credential signatures, with the institution or platform public key published at `/.well-known/acv-public-key`. Anyone can verify a signature offline. HMAC is kept only for older records.
- [NEW] A Merkle tree over credential hashes. Each credential stores its Merkle proof, and the root is anchored.
- [NEW] An `AnchorProvider` interface: `local` (the default, for offline demos) and `ethereum` (web3.py plus a small Solidity `CredentialAnchor` contract on the Polygon Amoy or Sepolia testnet). Anchors store the transaction hash and explorer URL.
- [NEW] The verification page shows signature validity, the Merkle proof, and a link to the on-chain anchor transaction.
- [NEW] Contract source, a deployment script, and documentation under `blockchain/`. The unused `blockchain.py` prototype is removed.

### Phase P6 — New product features ✅

- [NEW] Student claim flow: a student enters an institution and student ID, and the university approves or rejects the link.
- [NEW] Generated certificate PDFs: produce a branded certificate from a template with an embedded QR code (optional alternative to uploading a PDF).
- [NEW] Institution branding: logo and accent colour on certificates and public verification pages.
- [NEW] Email notifications (console backend in development, SMTP in production), password reset by signed token, and email verification.
- [NEW] Verifier report: a downloadable PDF or JSON verification receipt with a timestamp.
- [NEW] Expiry reminders and a scheduled integrity-check CLI (`flask integrity-scan`) for cron.

### Phase P7 — Testing, CI, and clean-up ✅

- [GAP] Tests for bulk issuance, share links, templates, signatures, anchoring, expiry, lockout, and error pages.
- [GAP] GitHub Actions: run the tests, check migrations, and report coverage.
- [GAP] Remove the legacy prototype (`templates/`, `blockchain.py`) and the stray `source/` virtualenv. Delete the `uploads/` folder, which holds real personal PDFs.
- [GAP] `flask demo-reset` to create deterministic dummy data for rehearsals.

### Phase P8 — Documentation, report, and demo ✅

- Update the README, architecture diagrams, threat model, demo script, and viva outline for the new blockchain layer and UI.
- Add screenshots of each role's journey and test evidence.

### Order

`P1 → P2 → P3 → P4 → P5 → P6 → P7 → P8` (tests are added in every phase, and P7 closes the remaining gaps).

**Status (27 September 2026):** all eight phases are implemented; see `WORK_SUMMARY.md`. Open items for the project owner: deploy the contract to a public testnet with a funded testnet wallet, delete the personal PDFs in `uploads/` and the stray `source/` virtualenv, and capture screenshots for the report.
