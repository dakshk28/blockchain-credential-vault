from datetime import datetime, timedelta, timezone
import secrets
from flask import Blueprint, abort, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user

from vault.audit.services import append_event
from vault.auth.decorators import roles_required
from vault.extensions import db
from vault.models import ClaimRequest, Credential, Institution, Notification, ShareLink, StudentProfile

bp = Blueprint("student", __name__, url_prefix="/student")


@bp.get("/certificates")
@roles_required("student")
def certificates():
    profiles = StudentProfile.query.filter_by(user_id=current_user.id).all()
    profile_ids = [profile.id for profile in profiles]
    credentials = Credential.query.filter(Credential.student_profile_id.in_(profile_ids)).order_by(Credential.issue_date.desc()).all() if profile_ids else []
    return jsonify(certificates=[{"credential_id": item.credential_id, "title": item.title, "programme": item.programme, "issue_date": item.issue_date.isoformat(), "status": item.effective_status, "document_available": item.document_available} for item in credentials])


@bp.get("/vault")
@roles_required("student")
def vault_page():
    profiles = StudentProfile.query.filter_by(user_id=current_user.id).all()
    profile_ids = [profile.id for profile in profiles]
    query = Credential.query.filter(Credential.student_profile_id.in_(profile_ids)) if profile_ids else Credential.query.filter(False)
    status = request.args.get("status", "")
    items = query.order_by(Credential.issue_date.desc()).all()
    if status in {"active", "revoked", "expired", "replaced"}:
        items = [item for item in items if item.effective_status == status]
    return render_template("student/vault.html", certificates=items, status=status)

@bp.get("/notifications")
@roles_required("student")
def notifications_page():
    items = Notification.query.filter_by(user_id=current_user.id).order_by(Notification.id.desc()).all()
    return render_template("student/notifications.html", notifications=items)

@bp.post("/notifications/read-all")
@roles_required("student")
def notifications_read_all():
    Notification.query.filter_by(user_id=current_user.id, is_read=False).update({"is_read": True})
    db.session.commit()
    return redirect(request.referrer or url_for("student.notifications_page"))

@bp.post("/share/<credential_id>")
@roles_required("student")
def create_share(credential_id):
    profile_ids = [p.id for p in StudentProfile.query.filter_by(user_id=current_user.id).all()]
    credential = Credential.query.filter(Credential.credential_id == credential_id, Credential.student_profile_id.in_(profile_ids)).first_or_404()
    link = ShareLink(token=secrets.token_urlsafe(32), credential_id=credential.id, student_user_id=current_user.id, expires_at=datetime.now(timezone.utc) + timedelta(hours=24))
    db.session.add(link); db.session.commit()
    return jsonify(token=link.token, expires_at=link.expires_at.isoformat()), 201

@bp.post("/share/<token>/revoke")
@roles_required("student")
def revoke_share(token):
    link = ShareLink.query.filter_by(token=token, student_user_id=current_user.id).first_or_404(); link.revoked = True
    db.session.commit(); return jsonify(status="revoked")

@bp.get("/shared/<token>")
def shared_credential(token):
    link = ShareLink.query.filter_by(token=token, revoked=False).first_or_404()
    if link.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc): abort(410)
    credential = db.session.get(Credential, link.credential_id)
    return jsonify(credential_id=credential.credential_id, title=credential.title, programme=credential.programme, issue_date=credential.issue_date.isoformat(), status=credential.effective_status, expires_at=link.expires_at.isoformat())


SHARE_DURATIONS = {1: "1 hour", 24: "24 hours", 72: "3 days", 168: "7 days", 720: "30 days"}


def _student_credentials():
    profile_ids = [p.id for p in StudentProfile.query.filter_by(user_id=current_user.id).all()]
    return Credential.query.filter(Credential.student_profile_id.in_(profile_ids)).order_by(Credential.issue_date.desc()).all() if profile_ids else []


@bp.get("/shares")
@roles_required("student")
def shares_page():
    links = ShareLink.query.filter_by(student_user_id=current_user.id).order_by(ShareLink.id.desc()).all()
    now = datetime.now(timezone.utc)
    for link in links:
        link.state = "revoked" if link.revoked else ("expired" if link.expires_at.replace(tzinfo=timezone.utc) < now else "active")
        link.credential = db.session.get(Credential, link.credential_id)
    credentials = [c for c in _student_credentials() if c.effective_status == "active"]
    return render_template("student/shares.html", links=links, credentials=credentials, durations=SHARE_DURATIONS, selected=request.args.get("credential", ""))


@bp.post("/shares")
@roles_required("student")
def create_share_page():
    credential = next((c for c in _student_credentials() if c.credential_id == request.form.get("credential_id")), None)
    hours = request.form.get("hours", type=int)
    if not credential or credential.effective_status != "active" or hours not in SHARE_DURATIONS:
        flash("Choose one of your active credentials and a valid duration.", "error")
        return redirect(url_for("student.shares_page"))
    link = ShareLink(token=secrets.token_urlsafe(32), credential_id=credential.id, student_user_id=current_user.id, expires_at=datetime.now(timezone.utc) + timedelta(hours=hours))
    db.session.add(link); append_event("share_link_created", current_user.id, {"credential_id": credential.id, "hours": hours}); db.session.commit()
    flash(f"Share link created for {credential.title}. It expires in {SHARE_DURATIONS[hours]}.", "success")
    return redirect(url_for("student.shares_page"))


@bp.post("/shares/<int:link_id>/revoke")
@roles_required("student")
def revoke_share_page(link_id):
    link = ShareLink.query.filter_by(id=link_id, student_user_id=current_user.id).first_or_404()
    link.revoked = True; append_event("share_link_revoked", current_user.id, {"share_link_id": link.id}); db.session.commit()
    flash("Share link revoked. It no longer works.", "success")
    return redirect(url_for("student.shares_page"))


@bp.route("/claim", methods=["GET", "POST"])
@roles_required("student")
def claim_page():
    if request.method == "POST":
        institution = Institution.query.filter_by(id=request.form.get("institution_id", type=int), is_verified=True).first()
        identifier = request.form.get("student_identifier", "").strip()
        error = None
        if not current_user.email_verified:
            error = "Confirm your email address before submitting a claim."
        elif not institution or not identifier:
            error = "Choose your university and enter your student ID."
        elif ClaimRequest.query.filter_by(user_id=current_user.id, institution_id=institution.id, student_identifier=identifier, status="pending").first():
            error = "You already have a pending claim for that student ID."
        else:
            profile = StudentProfile.query.filter_by(institution_id=institution.id, student_identifier=identifier).first()
            if profile and profile.user_id == current_user.id:
                error = "That student ID is already linked to your account."
            elif profile and profile.user_id:
                error = "That student ID is already linked to another account. Contact your university."
        if error:
            flash(error, "error")
        else:
            claim = ClaimRequest(user_id=current_user.id, institution_id=institution.id, student_identifier=identifier[:100], message=request.form.get("message", "").strip()[:500] or None)
            db.session.add(claim); db.session.flush()
            append_event("claim_submitted", current_user.id, {"claim_id": claim.id, "institution_id": institution.id}); db.session.commit()
            flash(f"Claim sent to {institution.name}. You'll be notified when it is reviewed.", "success")
        return redirect(url_for("student.claim_page"))
    claims = ClaimRequest.query.filter_by(user_id=current_user.id).order_by(ClaimRequest.id.desc()).all()
    institutions = Institution.query.filter_by(is_verified=True).order_by(Institution.name).all()
    return render_template("student/claim.html", claims=claims, institutions=institutions)
