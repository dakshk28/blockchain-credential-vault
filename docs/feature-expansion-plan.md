# Feature Expansion Plan: Student Vault and University Portal

## Goal

Extend the existing Academic Credential Vault so that students can view their own issued certificates and universities can register, be authenticated, and issue certificates through a dedicated portal. This plan builds on the existing login, role checks, private storage, SHA-256 verification, FIM, and audit chain.

## Product decisions

- **Student users** have a personal vault containing only credentials assigned to them. They can view status, download documents they are authorized to access, view verification IDs/QR codes, and see revocation or expiry information.
- **University users** use a separate university sign-up and login entry point. A university account is not trusted immediately: it remains pending until a platform administrator verifies it.
- **University authentication** has two levels: account authentication (secure password login) and institution verification (administrator checks the university identity before issuer accounts can issue credentials).
- A credential is assigned to a student profile using an institution-specific student identifier and, where available, the linked student account.
- Students cannot issue, edit, revoke, or access other students' credentials. University issuers can access only their own institution's records.

## Phase A — Data model and access boundaries

**Goal:** establish reliable relationships before creating screens.

1. Add `student_profiles` with `user_id`, `institution_id`, and `student_identifier`.
2. Add `institution_verification_requests` with legal name, institution code, official email domain, address, submitted evidence reference, status, reviewer, and timestamps.
3. Add `student_profile_id` to credentials and make it the source of ownership for the student vault.
4. Add institution contact fields and an institution verification status/history.
5. Define authorization helpers for student ownership, approved issuer scope, and administrator actions.
6. Create and apply a migration plus tests that prove cross-student and cross-institution access is denied.

**Completion criteria:** each credential has one student owner; all ownership checks are server-side; migrations run on a fresh database.

## Phase B — Student certificate vault

**Goal:** replace the empty student dashboard with useful, privacy-safe information.

1. Create `/student/certificates` to list the logged-in student's credentials.
2. Display certificate title, institution, programme, issue date, status, availability, public ID, and QR link.
3. Add a credential-detail page with a protected document download action.
4. Add status filters: active, revoked, expired, replaced, and document issue/integrity state.
5. Add an empty-state view explaining that certificates appear after an approved university issues one.
6. Record secure document-download audit events.
7. Add tests for list isolation, detail isolation, and download authorization.

**Completion criteria:** a student sees every credential assigned to them and never sees another student's record or document.

## Phase C — University onboarding and authentication

**Goal:** create a distinct, reviewable university path.

1. Add a dedicated `/university/register` page for an institution administrator/representative.
2. Capture institution identity, official contact email, address, requested institution code, and representative account details.
3. Validate email, password strength, unique institution code, and allowed evidence metadata; do not expose uploaded evidence publicly.
4. Create the representative as an issuer with `pending` approval and create a pending university verification request.
5. Add `/university/login` as a clear entry point that uses the same secure session system as normal login.
6. Add a pending-review screen which explains that issuance remains blocked until verification.
7. Rate-limit onboarding/login endpoints and audit registration, login, and review events.

**Completion criteria:** an unverified university cannot issue; no public visitor can use a university dashboard; each request is traceable to a representative and institution.

## Phase D — Administrator university-verification console

**Goal:** make institutional trust a controlled admin workflow.

1. Add an administrator page listing pending university requests.
2. Allow an administrator to approve, reject, or suspend a university with a required safe review note.
3. On approval, mark the institution verified and approve the representative issuer profile.
4. Allow administrators to create/approve additional issuers for a verified university.
5. Preserve review history and record every action in the audit chain.
6. Add tests for approval, rejection, suspension, and no cross-institution administration.

**Completion criteria:** issuing is enabled only after an administrator approval, and the audit chain records all trust decisions.

## Phase E — University issuance workspace

**Goal:** give authenticated universities a usable issuance workflow.

1. Add an issuer dashboard with institution-scoped counts, recent credentials, pending student matches, and integrity incidents.
2. Add student lookup/create within the issuer's institution using the student identifier.
3. Update issuance form to select or create the student profile, then attach the credential to it.
4. Keep the existing PDF validation, randomized private storage, SHA-256 baseline, duplicate warning, QR generation, and audit event.
5. Add issuer-only credential search, revocation, and controlled replacement UI.
6. Add tests confirming a university cannot issue to or view another institution's students/credentials.

**Completion criteria:** an approved university can issue a credential that immediately appears in the intended student's vault.

## Phase F — User experience and notification records

**Goal:** make workflow status understandable without adding unsafe external dependencies.

1. Improve landing page navigation with separate Student, University, and Administrator entry points.
2. Show role-specific dashboards after login rather than a generic message.
3. Create in-app notification records for university approval, credential issuance, revocation, and integrity incidents.
4. Add accessibility labels, helpful validation errors, responsive layouts, and consistent empty/error states.
5. Add end-to-end browser tests for student and university journeys.

**Completion criteria:** a new user can understand the correct path without knowing internal roles or API URLs.

## Phase G — Final security review and demo evidence

**Goal:** verify the expanded workflow is safe and easy to demonstrate.

1. Test unauthorized student access, cross-institution access, unapproved issuer issuance, unsafe upload, brute-force login, and CSRF failures.
2. Review all public pages for private data exposure.
3. Update the demo script: university registration → admin verification → issuer login → student record/credential issuance → student vault → public verification → revocation/FIM/audit validation.
4. Capture test evidence and update report diagrams/screenshots.

**Completion criteria:** all critical tests pass and the full scenario can be demonstrated with deterministic dummy accounts and documents.

## Recommended implementation order

`Phase A → Phase B → Phase C → Phase D → Phase E → Phase F → Phase G`

Start with Phases A and B. They make the student dashboard genuinely useful while putting the ownership model in place before university-facing issuance screens are added.

## Extended achievable-feature backlog

The following features are approved for incremental implementation after the core student/university workflow. They are grouped by dependency and can be demonstrated locally without third-party services.

| Delivery group | Features |
| --- | --- |
| Foundation | Student profiles, university verification requests, in-app notifications, credential ownership and claim codes. |
| Student experience | Certificate vault, status/history, QR download, protected document download, time-limited share links, claim-certificate workflow. |
| University experience | Separate onboarding/login, verification console, issuer dashboard, student lookup, templates, bulk CSV issuance, replacement workflow. |
| Trust and verification | Digital-signature design, verifier reports, verification history, QR/mobile verification, public privacy controls. |
| Security operations | Scheduled FIM command, incident acknowledgement, audit explorer, backup/restore runbook, security dashboards. |
| Integrations | Scoped API tokens, documented REST API, outbound webhook event records, ERP adapter boundary. |
| Advanced deployment | Email delivery provider, malware scanner, Redis rate limits, object storage, blockchain audit-root anchoring. |

### Delivery rule

External-provider features are implemented first as safe local interfaces and records. They are only connected to email, scanning, cloud storage, Redis, or a blockchain testnet after credentials and deployment authority are available.
