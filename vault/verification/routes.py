import hashlib
from datetime import datetime, timezone
from io import BytesIO
import qrcode

from flask import Blueprint, abort, current_app, jsonify, redirect, render_template, request, send_file, url_for

from vault.chain.services import anchor_status, proof_bundle, signature_status
from vault.chain.signing import public_key_info
from vault.extensions import db, limiter
from vault.models import Credential, Institution, ShareLink, User

bp = Blueprint("verification", __name__)


@bp.get("/")
def home():
    return render_template("home.html")


@bp.get("/health")
def health():
    return jsonify(status="ok"), 200


@bp.get("/verify/<credential_id>")
@limiter.limit("30 per minute")
def verify(credential_id):
    credential = Credential.query.filter_by(credential_id=credential_id).first()
    if not credential:
        return jsonify(result="unknown"), 404
    institution = db.session.get(Institution, credential.institution_id)
    return jsonify(credential_id=credential.credential_id, institution_id=credential.institution_id, institution_name=institution.name if institution else None, title=credential.title, programme=credential.programme, issue_date=credential.issue_date.isoformat(), expiry_date=credential.expiry_date.isoformat() if credential.expiry_date else None, status=credential.effective_status)


@bp.post("/verify/<credential_id>/compare")
@limiter.limit("10 per hour")
def compare(credential_id):
    credential = Credential.query.filter_by(credential_id=credential_id).first_or_404()
    uploaded = request.files.get("document")
    if not uploaded:
        return jsonify(error="document_required"), 400
    digest = hashlib.sha256(uploaded.read()).hexdigest()
    result = "unchanged" if digest == credential.document_sha256 else "modified"
    status = credential.effective_status
    return jsonify(credential_id=credential_id, status=status, document_result=result, authentic=status == "active" and result == "unchanged")


@bp.get("/verify/<credential_id>/qr")
def qr_code(credential_id):
    Credential.query.filter_by(credential_id=credential_id).first_or_404()
    target = url_for("verification.credential_page", credential_id=credential_id, _external=True)
    image = qrcode.make(target); output = BytesIO(); image.save(output, "PNG"); output.seek(0)
    return send_file(output, mimetype="image/png", download_name=f"{credential_id}.png")


# ---------- Human-facing verification portal ----------

def normalise_id(value):
    return (value or "").strip().upper().replace(" ", "")


def credential_timeline(credential):
    """Public lifecycle events for a credential, oldest first. Private data (reasons, people) is omitted."""
    events = [{"label": "Issued", "detail": f"by {credential.institution.name}", "date": credential.issue_date, "tone": "active"}]
    if credential.replacement_of:
        events.append({"label": "Replaces an earlier credential", "detail": credential.replacement_of.credential_id, "date": credential.issue_date, "tone": "replaced"})
    if credential.replaced_by:
        events.append({"label": "Replaced", "detail": f"superseded by {credential.replaced_by.credential_id}", "date": credential.replaced_by.issue_date, "tone": "replaced"})
    if credential.revocation:
        events.append({"label": "Revoked", "detail": "by the issuing institution", "date": credential.revocation.revoked_at.date(), "tone": "revoked"})
    if credential.expiry_date:
        events.append({"label": "Expired" if credential.is_expired else "Expires", "detail": "", "date": credential.expiry_date, "tone": "expired" if credential.is_expired else "pending"})
    return events


def trust_context(credential):
    return {"signature": signature_status(credential), "anchoring": anchor_status(credential)}


@bp.get("/.well-known/acv-signing-key.json")
def signing_key():
    """The platform's Ed25519 public key, for offline signature verification."""
    return jsonify(public_key_info())


@bp.get("/credential/<credential_id>/proof.json")
@limiter.limit("60 per minute")
def proof(credential_id):
    """Self-contained proof bundle: signed payload, signature, public key, Merkle proof, and anchor receipt."""
    credential = Credential.query.filter_by(credential_id=normalise_id(credential_id)).first_or_404()
    response = jsonify(proof_bundle(credential))
    response.headers["Content-Disposition"] = f"attachment; filename={credential.credential_id}-proof.json"
    return response


@bp.get("/verify")
@limiter.limit("60 per minute")
def portal():
    credential_id = normalise_id(request.args.get("id"))
    if credential_id:
        return redirect(url_for("verification.credential_page", credential_id=credential_id))
    return render_template("verification/portal.html")


@bp.get("/credential/<credential_id>")
@limiter.limit("60 per minute")
def credential_page(credential_id):
    credential = Credential.query.filter_by(credential_id=normalise_id(credential_id)).first()
    if not credential:
        return render_template("verification/not_found.html", credential_id=credential_id), 404
    return render_template("verification/result.html", credential=credential, status=credential.effective_status, timeline=credential_timeline(credential), comparison=None, **trust_context(credential))


@bp.post("/credential/<credential_id>")
@limiter.limit("10 per hour")
def credential_compare_page(credential_id):
    credential = Credential.query.filter_by(credential_id=normalise_id(credential_id)).first_or_404()
    uploaded = request.files.get("document")
    comparison = None
    if uploaded and uploaded.filename:
        digest = hashlib.sha256(uploaded.read()).hexdigest()
        comparison = {"filename": uploaded.filename, "sha256": digest, "matches": digest == credential.document_sha256}
    status = credential.effective_status
    return render_template("verification/result.html", credential=credential, status=status, timeline=credential_timeline(credential), comparison=comparison, **trust_context(credential))


@bp.get("/shared/<token>")
@limiter.limit("60 per minute")
def shared_page(token):
    link = ShareLink.query.filter_by(token=token).first()
    if not link or link.revoked or link.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        abort(410)
    credential = db.session.get(Credential, link.credential_id)
    holder = db.session.get(User, link.student_user_id)
    return render_template("verification/shared.html", credential=credential, status=credential.effective_status, holder=holder, link=link, timeline=credential_timeline(credential))


@bp.get("/credential/<credential_id>/receipt")
@limiter.limit("30 per minute")
def receipt(credential_id):
    """Printable verification receipt: what was checked, the result, and when (UTC)."""
    credential = Credential.query.filter_by(credential_id=normalise_id(credential_id)).first_or_404()
    checked_at = datetime.now(timezone.utc)
    context = trust_context(credential)
    status = credential.effective_status
    reference = hashlib.sha256(f"{credential.credential_id}|{status}|{context['signature']['state']}|{context['anchoring']['state']}|{checked_at.isoformat()}".encode()).hexdigest()[:20].upper()
    return render_template("verification/receipt.html", credential=credential, status=status, checked_at=checked_at, reference=reference, **context)
