import csv
from io import StringIO

from flask import Blueprint, abort, current_app, jsonify, request, send_from_directory
from flask_login import current_user

from vault.auth.decorators import roles_required
from vault.credentials.services import IssuanceError, bulk_issue_credentials, issue_credential, revoke_credential
from vault.extensions import db, limiter
from vault.models import Credential, CredentialSignature, IssuerProfile, StudentProfile

bp = Blueprint("credentials", __name__, url_prefix="/credentials")


@bp.post("")
@roles_required("issuer")
@limiter.limit("10 per hour")
def issue():
    profile = IssuerProfile.query.filter_by(user_id=current_user.id, approval_status="approved").first()
    if not profile:
        return jsonify(error="issuer_not_approved"), 403
    try:
        credential, duplicate = issue_credential(profile, current_user.id, request.form, request.files.get("document"))
    except IssuanceError as error:
        return jsonify(error=error.code, message=str(error)), error.status
    return jsonify(credential_id=credential.credential_id, sha256=credential.document_sha256, duplicate_content=duplicate), 201


def read_csv_rows(csv_file):
    try:
        return list(csv.DictReader(StringIO(csv_file.read().decode("utf-8-sig"))))
    except UnicodeDecodeError:
        raise IssuanceError("invalid_bulk_upload", "The CSV file must be UTF-8 encoded.")


@bp.post("/bulk")
@roles_required("issuer")
@limiter.limit("5 per hour")
def bulk_issue():
    """Issue the same PDF-backed credential metadata to CSV-listed students."""
    profile = IssuerProfile.query.filter_by(user_id=current_user.id, approval_status="approved").first()
    if not profile: return jsonify(error="issuer_not_approved"), 403
    csv_file = request.files.get("students_csv")
    if not csv_file: return jsonify(error="students_csv_required"), 400
    try:
        created, errors = bulk_issue_credentials(profile, current_user.id, request.files.get("document"), read_csv_rows(csv_file))
    except IssuanceError as error:
        return jsonify(error=error.code, message=str(error)), error.status
    return jsonify(credential_ids=created, count=len(created), errors=errors), 201

@bp.get("/<credential_id>/signature")
def signature(credential_id):
    credential = Credential.query.filter_by(credential_id=credential_id).first_or_404()
    record = CredentialSignature.query.filter_by(credential_id=credential.id).first()
    return jsonify(credential_id=credential_id, algorithm=record.algorithm if record else None, signature=record.signature if record else None)


@bp.get("/<credential_id>/document")
@roles_required("admin", "issuer", "student")
def download(credential_id):
    credential = Credential.query.filter_by(credential_id=credential_id).first_or_404()
    if current_user.role == "student":
        profile = StudentProfile.query.filter_by(id=credential.student_profile_id, user_id=current_user.id).first()
        if not profile:
            abort(403)
    elif current_user.role != "admin":
        profile = IssuerProfile.query.filter_by(user_id=current_user.id, approval_status="approved").first()
        if not profile or profile.institution_id != credential.institution_id:
            abort(403)
    if not credential.document_available:
        abort(404)
    return send_from_directory(current_app.config["UPLOAD_DIRECTORY"], credential.storage_key, as_attachment=True, download_name=credential.original_filename)


@bp.post("/<credential_id>/revoke")
@roles_required("issuer")
def revoke(credential_id):
    credential = Credential.query.filter_by(credential_id=credential_id).first_or_404()
    profile = IssuerProfile.query.filter_by(user_id=current_user.id, approval_status="approved").first()
    if not profile:
        abort(403)
    try:
        revoke_credential(profile, current_user.id, credential, (request.get_json(silent=True) or {}).get("reason", ""))
    except IssuanceError as error:
        if error.status == 403:
            abort(403)
        return jsonify(error=error.code, message=str(error)), error.status
    return jsonify(credential_id=credential_id, status="revoked")
