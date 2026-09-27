from flask import Blueprint, current_app, flash, jsonify, redirect, render_template, request, url_for

from flask_login import current_user

from vault.audit.services import validate_chain
from vault.chain.providers import AnchorError
from vault.chain.services import anchor_audit_head, anchor_pending_credentials
from vault.auth.decorators import roles_required
from vault.extensions import db
from vault.models import AuditAnchor, AuditEvent, Credential, CredentialAnchorProof

bp = Blueprint("audit", __name__, url_prefix="/audit")


@bp.get("/validate")
@roles_required("admin")
def validate():
    return jsonify(validate_chain())


@bp.post("/anchor")
@roles_required("admin")
def anchor():
    try:
        record = anchor_audit_head(current_user.id)
    except AnchorError as error:
        return jsonify(error="anchor_failed", message=str(error)), 502
    if not record: return jsonify(error="invalid_audit_chain"), 409
    return jsonify(anchor_id=record.id, audit_root=record.audit_root, provider=record.provider, tx_hash=record.tx_hash), 201


@bp.get("/ledger")
@roles_required("admin")
def ledger_page():
    event_type = request.args.get("type", "")
    query = AuditEvent.query
    if event_type:
        query = query.filter_by(event_type=event_type)
    page = query.order_by(AuditEvent.id.desc()).paginate(per_page=current_app.config["PAGE_SIZE"], error_out=False)
    types = [row[0] for row in db.session.query(AuditEvent.event_type).distinct().order_by(AuditEvent.event_type)]
    anchors = AuditAnchor.query.order_by(AuditAnchor.id.desc()).limit(8).all()
    pending = Credential.query.outerjoin(CredentialAnchorProof, CredentialAnchorProof.credential_id == Credential.id).filter(CredentialAnchorProof.id.is_(None)).count()
    return render_template("admin/ledger.html", page=page, types=types, event_type=event_type, anchors=anchors, total=AuditEvent.query.count(), pending=pending, provider=current_app.config["BLOCKCHAIN_ANCHOR_PROVIDER"])


@bp.post("/ledger/validate")
@roles_required("admin")
def validate_page():
    result = validate_chain()
    if result["valid"]:
        flash(f"Audit chain is intact: all {result['events']} events verified.", "success")
    else:
        flash(f"Tampering detected: event #{result['invalid_event_id']} does not match its hash chain.", "error")
    return redirect(url_for("audit.ledger_page"))


def _receipt(record):
    where = f"transaction {record.tx_hash[:18]}… on {record.network}" if record.tx_hash else record.network
    return f"root {record.audit_root[:16]}… ({where})"


@bp.post("/ledger/anchor")
@roles_required("admin")
def anchor_page():
    try:
        record = anchor_audit_head(current_user.id)
    except AnchorError as error:
        flash(str(error), "error")
        return redirect(url_for("audit.ledger_page"))
    if record:
        flash(f"Anchored audit {_receipt(record)}.", "success")
    else:
        flash("The audit chain is invalid, so it cannot be anchored. Validate it first.", "error")
    return redirect(url_for("audit.ledger_page"))


@bp.post("/ledger/anchor-credentials")
@roles_required("admin")
def anchor_credentials_page():
    try:
        record = anchor_pending_credentials(current_user.id)
    except AnchorError as error:
        flash(str(error), "error")
        return redirect(url_for("audit.ledger_page"))
    if record:
        flash(f"Anchored {record.item_count} credential(s): Merkle {_receipt(record)}.", "success")
    else:
        flash("No credentials are waiting to be anchored.", "info")
    return redirect(url_for("audit.ledger_page"))
