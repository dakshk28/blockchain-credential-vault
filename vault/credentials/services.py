import hashlib
import hmac
import re
import secrets
import shlex
import subprocess
from datetime import date
from pathlib import Path

from flask import current_app

from vault.audit.services import append_event
from vault.chain import signing
from vault.extensions import db
from vault.models import Credential, CredentialSignature, Revocation, StudentProfile
from vault.notifications import notify


MAX_PDF_BYTES = 10 * 1024 * 1024
EICAR_MARKER = b"EICAR-STANDARD-ANTIVIRUS-TEST-FILE"
# PDF name objects that run code, launch programs, or carry embedded payloads. A name ends at a PDF delimiter.
ACTIVE_CONTENT = re.compile(rb"/(JavaScript|JS|Launch|EmbeddedFiles?|RichMedia|SubmitForm|ImportData)(?=[\s/<>\[\]()%]|$)")
NAME_ESCAPE = re.compile(rb"#([0-9A-Fa-f]{2})")


class IssuanceError(ValueError):
    """A credential could not be issued; `code` is a stable machine-readable reason."""

    def __init__(self, code, message, status=400):
        super().__init__(message)
        self.code, self.status = code, status


def read_pdf(upload):
    """Validate an uploaded PDF and return its bytes without writing anything to disk."""
    if not upload or not getattr(upload, "filename", None) or not upload.filename.lower().endswith(".pdf"):
        raise ValueError("A PDF document is required.")
    content = upload.read(MAX_PDF_BYTES + 1)
    if len(content) > MAX_PDF_BYTES or not content.startswith(b"%PDF-"):
        raise ValueError("The upload must be a PDF no larger than 10 MB.")
    screen_pdf(content)
    return content


def screen_pdf(content):
    """Reject PDFs with active content, then run the optional external antivirus command."""
    if EICAR_MARKER in content:
        raise ValueError("The upload failed malware screening.")
    # Decode "#xx" escapes so obfuscated names such as /J#61vaScript are caught too.
    normalised = NAME_ESCAPE.sub(lambda match: bytes([int(match.group(1), 16)]), content)
    found = ACTIVE_CONTENT.search(normalised)
    if found:
        raise ValueError(f"PDFs containing active content ({found.group(1).decode()}) are not accepted.")
    command = current_app.config.get("MALWARE_SCAN_COMMAND") if current_app else ""
    if command:
        try:
            scan = subprocess.run(shlex.split(command), input=content, capture_output=True, timeout=60)
        except (OSError, subprocess.TimeoutExpired):
            raise ValueError("The malware scanner is unavailable; please try again later.")
        if scan.returncode != 0:
            raise ValueError("The upload failed malware screening.")


def store_pdf(content, directory: Path):
    storage_key = f"{secrets.token_urlsafe(24)}.pdf"
    (directory / storage_key).write_bytes(content)
    return storage_key


def save_pdf(upload, directory: Path):
    content = read_pdf(upload)
    return store_pdf(content, directory), hashlib.sha256(content).hexdigest()


def credential_public_id():
    return f"ACV-{date.today():%Y}-{secrets.token_hex(5).upper()}"


def sign_credential(credential_id, digest, secret):
    """Legacy HMAC-SHA256 signature (kept only to verify credentials issued before Ed25519)."""
    return hmac.new(secret.encode(), f"{credential_id}:{digest}".encode(), hashlib.sha256).hexdigest()


def add_signature(credential):
    """Sign the credential's canonical record with the platform Ed25519 key (after flush)."""
    signature, key_id = signing.sign(signing.credential_payload(credential))
    db.session.add(CredentialSignature(credential_id=credential.id, algorithm=signing.ALGORITHM, signature=signature, key_id=key_id))


def generate_certificate(institution_id, public_id, recipient, title, programme, issue_date, expiry_date):
    from vault.credentials.certificates import render_certificate
    from vault.models import Institution
    from vault.urls import external_url
    institution = db.session.get(Institution, institution_id)
    verify_url = external_url("verification.credential_page", credential_id=public_id)
    logo = current_app.config["UPLOAD_DIRECTORY"] / "logos" / institution.logo_key if institution.logo_key else None
    content = render_certificate(institution=institution, recipient=recipient, title=title, programme=programme, issue_date=issue_date, expiry_date=expiry_date, credential_id=public_id, verify_url=verify_url, logo_path=logo)
    screen_pdf(content)
    return content


def parse_date(value, field, default=None):
    if not value:
        return default
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise IssuanceError("invalid_date", f"{field} must be a valid date (YYYY-MM-DD).")


def issue_credential(profile, issuer_id, form, upload):
    """Issue one credential atomically: nothing is committed or left on disk if any step fails."""
    title, programme = form.get("title", "").strip(), form.get("programme", "").strip()
    if not title or not programme:
        raise IssuanceError("invalid_credential", "Title and programme are required.")
    student = None
    student_profile_id = form.get("student_profile_id", type=int)
    if student_profile_id:
        student = StudentProfile.query.filter_by(id=student_profile_id, institution_id=profile.institution_id).first()
        if not student:
            raise IssuanceError("student_not_found", "The selected student profile was not found.", 404)
    replaced = None
    replacement_of_id = form.get("replacement_of_id", type=int)
    if replacement_of_id:
        replaced = Credential.query.filter_by(id=replacement_of_id, institution_id=profile.institution_id, issued_by_user_id=issuer_id).first()
        if not replaced or replaced.status in ("replaced", "revoked"):
            raise IssuanceError("invalid_replacement", "Only an active credential you issued can be replaced.")
    issue_date = parse_date(form.get("issue_date"), "Issue date", date.today())
    expiry_date = parse_date(form.get("expiry_date"), "Expiry date")
    if expiry_date and expiry_date <= issue_date:
        raise IssuanceError("invalid_date", "Expiry date must be after the issue date.")
    public_id = credential_public_id()
    if form.get("document_mode") == "generate":
        recipient = form.get("recipient_name", "").strip() or (student.user.full_name if student and student.user else "")
        if not recipient:
            raise IssuanceError("recipient_required", "Enter the recipient's name to generate a certificate (or link the student's account).")
        content, filename = generate_certificate(profile.institution_id, public_id, recipient, title, programme, issue_date, expiry_date), f"{public_id}.pdf"
    else:
        try:
            content = read_pdf(upload)
        except ValueError as error:
            raise IssuanceError("invalid_document", str(error))
        filename = upload.filename
    digest = hashlib.sha256(content).hexdigest()
    duplicate = Credential.query.filter_by(document_sha256=digest).first() is not None
    directory = current_app.config["UPLOAD_DIRECTORY"]
    storage_key = store_pdf(content, directory)
    try:
        credential = Credential(credential_id=public_id, institution_id=profile.institution_id, issued_by_user_id=issuer_id, student_profile_id=student.id if student else None, replacement_of_id=replaced.id if replaced else None, title=title, programme=programme, description=form.get("description", "").strip() or None, issue_date=issue_date, expiry_date=expiry_date, status="active", document_sha256=digest, storage_key=storage_key, original_filename=filename)
        db.session.add(credential); db.session.flush()
        add_signature(credential)
        append_event("credential_issued", issuer_id, {"credential_id": credential.id})
        if replaced:
            replaced.status = "replaced"
            append_event("credential_replaced", issuer_id, {"old_credential_id": replaced.id, "new_credential_id": credential.id})
        if student and student.user_id:
            notify(student.user_id, "credential_issued", f"A new credential, {title}, was issued to your student profile.")
        db.session.commit()
    except Exception:
        db.session.rollback()
        (directory / storage_key).unlink(missing_ok=True)
        raise
    return credential, duplicate


def bulk_issue_credentials(profile, issuer_id, upload, csv_rows):
    """Issue the same PDF to every CSV row in one transaction; returns (created_ids, row_errors)."""
    try:
        content = read_pdf(upload)
    except ValueError as error:
        raise IssuanceError("invalid_document", str(error))
    if not csv_rows or "student_identifier" not in csv_rows[0]:
        raise IssuanceError("invalid_bulk_upload", "CSV must contain a student_identifier column.")
    digest = hashlib.sha256(content).hexdigest()
    directory = current_app.config["UPLOAD_DIRECTORY"]
    created, errors, written = [], [], []
    try:
        for line, row in enumerate(csv_rows, start=2):
            identifier = (row.get("student_identifier") or "").strip()
            if not identifier:
                errors.append({"row": line, "error": "student_identifier is blank"})
                continue
            student = StudentProfile.query.filter_by(institution_id=profile.institution_id, student_identifier=identifier).first()
            if not student:
                student = StudentProfile(institution_id=profile.institution_id, student_identifier=identifier); db.session.add(student); db.session.flush()
            storage_key = store_pdf(content, directory); written.append(storage_key)
            title = (row.get("title") or "").strip() or "Academic Credential"
            credential = Credential(credential_id=credential_public_id(), institution_id=profile.institution_id, issued_by_user_id=issuer_id, student_profile_id=student.id, title=title, programme=(row.get("programme") or "").strip() or "General", issue_date=date.today(), status="active", document_sha256=digest, storage_key=storage_key, original_filename=upload.filename)
            db.session.add(credential); db.session.flush()
            add_signature(credential)
            if student.user_id:
                notify(student.user_id, "credential_issued", f"A new credential, {title}, was issued to your student profile.")
            created.append(credential.credential_id)
        if created:
            append_event("credentials_bulk_issued", issuer_id, {"count": len(created), "institution_id": profile.institution_id})
        db.session.commit()
    except Exception:
        db.session.rollback()
        for key in written:
            (directory / key).unlink(missing_ok=True)
        raise
    return created, errors


def revoke_credential(profile, issuer_id, credential, reason):
    """Revoke a credential the issuer created; records the reason, audits it, and notifies the student."""
    reason = (reason or "").strip()
    if credential.institution_id != profile.institution_id or credential.issued_by_user_id != issuer_id:
        raise IssuanceError("forbidden", "You can only revoke credentials you issued.", 403)
    if credential.status != "active" or credential.revocation:
        raise IssuanceError("invalid_revocation", "Only an active credential can be revoked.")
    if not reason:
        raise IssuanceError("invalid_revocation", "A reason is required to revoke a credential.")
    credential.status = "revoked"
    db.session.add(Revocation(credential_id=credential.id, reason=reason[:500], revoked_by_user_id=issuer_id))
    append_event("credential_revoked", issuer_id, {"credential_id": credential.id})
    student = credential.student_profile
    if student and student.user_id:
        notify(student.user_id, "credential_revoked", f"{credential.title} ({credential.credential_id}) was revoked by the issuing institution.")
    db.session.commit()
