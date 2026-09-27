import hashlib

from vault.auth.routes import audit
from vault.extensions import db
from vault.models import Credential, IntegrityCheck


def check_credential(credential):
    path = credential.storage_key
    from flask import current_app
    file_path = current_app.config["UPLOAD_DIRECTORY"] / path
    try:
        if not file_path.exists():
            result, digest, details = "missing", None, "Stored document was not found."
        else:
            digest = hashlib.sha256(file_path.read_bytes()).hexdigest()
            result, details = ("unchanged", "Baseline matches.") if digest == credential.document_sha256 else ("modified", "Baseline hash differs.")
    except PermissionError:
        result, digest, details = "inaccessible", None, "Stored document cannot be read."
    except OSError:
        result, digest, details = "error", None, "Integrity check failed."
    previous = IntegrityCheck.query.filter_by(credential_id=credential.id).order_by(IntegrityCheck.id.desc()).first()
    db.session.add(IntegrityCheck(credential_id=credential.id, current_sha256=digest, result=result, details=details))
    if result in ("modified", "missing") and (not previous or previous.result != result):
        audit(f"integrity_{result}", None, credential_id=credential.id)
    return result


INCIDENT_RESULTS = ("modified", "missing", "inaccessible", "error")


def latest_checks():
    """Most recent integrity check per credential, keyed by credential primary key."""
    latest = {}
    for check in IntegrityCheck.query.order_by(IntegrityCheck.id.desc()).all():
        latest.setdefault(check.credential_id, check)
    return latest


def run_all():
    results = {}
    for credential in Credential.query.filter_by(status="active").all():
        results[credential.credential_id] = check_credential(credential)
    db.session.commit()
    return results
