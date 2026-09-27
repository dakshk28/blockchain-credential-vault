import csv
from io import StringIO
from flask import Blueprint, Response, abort, current_app, flash, jsonify, redirect, render_template, request, url_for
from sqlalchemy import func, or_
from flask_login import current_user, login_user, logout_user

from vault.auth.decorators import roles_required
from vault.extensions import db, limiter
from vault.models import AuditEvent, Credential, Institution, InstitutionVerificationRequest, IssuerProfile, Notification, StudentProfile, User
from vault.audit.services import append_event
from vault.auth.services import authenticate, password_error, queue_reset_email, queue_verification_email, user_from_reset_token, user_from_verify_token

bp = Blueprint("auth", __name__, url_prefix="/auth")


def audit(event_type, actor_id=None, **metadata):
    append_event(event_type, actor_id, metadata)


@bp.post("/api/register")
@limiter.limit("5 per hour")
def register():
    data = request.get_json() or {}
    email, password, full_name = data.get("email", "").strip().lower(), data.get("password", ""), data.get("full_name", "").strip()
    if not email or not full_name or len(password) < 12 or not any(c.isdigit() for c in password):
        return jsonify(error="invalid_registration", message="Name, email, and a 12-character password containing a digit are required."), 400
    if User.query.filter_by(email=email).first():
        return jsonify(error="email_exists"), 409
    user = User(email=email, full_name=full_name, role="student")
    user.set_password(password)
    db.session.add(user); db.session.flush(); audit("account_registered", user.id); queue_verification_email(user); db.session.commit()
    return jsonify(id=user.id, role=user.role), 201


@bp.post("/api/issuer-register")
@limiter.limit("3 per hour")
def register_issuer():
    data = request.get_json() or {}
    institution = db.session.get(Institution, data.get("institution_id"))
    if not institution:
        return jsonify(error="institution_not_found"), 404
    email, password, full_name = data.get("email", "").strip().lower(), data.get("password", ""), data.get("full_name", "").strip()
    if not email or not full_name or len(password) < 12 or User.query.filter_by(email=email).first():
        return jsonify(error="invalid_issuer_registration"), 400
    user = User(email=email, full_name=full_name, role="issuer"); user.set_password(password)
    db.session.add(user); db.session.flush()
    db.session.add(IssuerProfile(user_id=user.id, institution_id=institution.id)); audit("issuer_registration_requested", user.id); db.session.commit()
    return jsonify(id=user.id, approval_status="pending"), 201


@bp.post("/api/login")
@limiter.limit("5 per minute")
def login():
    data = request.get_json() or {}
    user, reason = authenticate(data.get("email", ""), data.get("password", ""))
    if not user:
        db.session.commit()
        if reason == "locked":
            return jsonify(error="account_locked", message="Too many failed attempts. Try again later."), 423
        return jsonify(error="invalid_credentials"), 401
    login_user(user); audit("login", user.id); db.session.commit()
    return jsonify(id=user.id, role=user.role)


@bp.post("/api/logout")
def logout():
    if current_user.is_authenticated: audit("logout", current_user.id); db.session.commit()
    logout_user(); return "", 204


@bp.post("/api/issuers/<int:user_id>/approve")
@roles_required("admin")
def approve_issuer(user_id):
    profile = IssuerProfile.query.filter_by(user_id=user_id).first_or_404()
    profile.approval_status = "approved"; profile.approved_by = current_user.id
    audit("issuer_approved", current_user.id, issuer_user_id=user_id); db.session.commit()
    return jsonify(user_id=user_id, approval_status="approved")


@bp.get("/api/users")
@roles_required("admin")
def list_users():
    users = User.query.order_by(User.email).all()
    return jsonify(users=[{"id": user.id, "email": user.email, "full_name": user.full_name, "role": user.role, "is_active": user.is_active} for user in users])


@bp.route("/register", methods=["GET", "POST"])
@limiter.limit("5 per hour", methods=["POST"])
def register_page():
    if request.method == "GET":
        return render_template("auth/register.html")
    data = request.form
    email, password, full_name = data.get("email", "").strip().lower(), data.get("password", ""), data.get("full_name", "").strip()
    if not email or not full_name or len(password) < 12 or not any(char.isdigit() for char in password):
        return render_template("auth/register.html", error="Enter a name, email, and a 12-character password containing a digit."), 400
    if User.query.filter_by(email=email).first():
        return render_template("auth/register.html", error="That email is already registered."), 409
    user = User(email=email, full_name=full_name, role="student"); user.set_password(password)
    db.session.add(user); db.session.flush(); audit("account_registered", user.id); queue_verification_email(user); db.session.commit(); login_user(user)
    flash("Welcome! We sent a link to confirm your email address.", "success")
    return redirect(url_for("auth.dashboard"))


@bp.route("/login", methods=["GET", "POST"])
@limiter.limit("10 per minute", methods=["POST"])
def login_page():
    if request.method == "GET":
        return render_template("auth/login.html")
    user, reason = authenticate(request.form.get("email", ""), request.form.get("password", ""))
    if not user:
        db.session.commit()
        if reason == "locked":
            return render_template("auth/login.html", error="Too many failed attempts. This account is temporarily locked; try again later."), 423
        return render_template("auth/login.html", error="Invalid email or password."), 401
    login_user(user); audit("login", user.id); db.session.commit()
    return redirect(url_for("auth.dashboard"))


@bp.route("/forgot", methods=["GET", "POST"])
@limiter.limit("5 per hour", methods=["POST"])
def forgot_password():
    if request.method == "POST":
        user = User.query.filter_by(email=request.form.get("email", "").strip().lower()).first()
        if user and user.is_active:
            queue_reset_email(user); audit("password_reset_requested", user.id); db.session.commit()
        # Same response whether or not the account exists, so emails cannot be enumerated.
        flash("If an account exists for that email, a reset link is on its way.", "success")
        return redirect(url_for("auth.login_page"))
    return render_template("auth/forgot.html")


@bp.route("/reset/<token>", methods=["GET", "POST"])
@limiter.limit("10 per hour", methods=["POST"])
def reset_password(token):
    user = user_from_reset_token(token)
    if not user:
        flash("That reset link is invalid or has expired. Request a new one.", "error")
        return redirect(url_for("auth.forgot_password"))
    if request.method == "POST":
        password = request.form.get("password", "")
        error = password_error(password) or (None if password == request.form.get("confirm", "") else "The passwords do not match.")
        if error:
            return render_template("auth/reset.html", error=error), 400
        user.set_password(password); user.failed_login_count, user.locked_until = 0, None
        audit("password_reset", user.id); db.session.commit()
        flash("Your password has been changed. Log in with the new password.", "success")
        return redirect(url_for("auth.login_page"))
    return render_template("auth/reset.html")


@bp.get("/verify-email/<token>")
def verify_email(token):
    user = user_from_verify_token(token)
    if not user:
        flash("That confirmation link is invalid or has expired.", "error")
    elif not user.email_verified:
        user.email_verified = True; audit("email_verified", user.id); db.session.commit()
        flash("Email address confirmed.", "success")
    return redirect(url_for("auth.dashboard") if current_user.is_authenticated else url_for("auth.login_page"))


@bp.post("/resend-verification")
@limiter.limit("3 per hour")
def resend_verification():
    if not current_user.is_authenticated:
        abort(401)
    if not current_user.email_verified:
        queue_verification_email(current_user); db.session.commit()
        flash(f"We sent a new confirmation link to {current_user.email}.", "success")
    return redirect(request.referrer or url_for("auth.dashboard"))


@bp.get("/dashboard")
def dashboard():
    if not current_user.is_authenticated:
        return redirect(url_for("auth.login_page"))
    profile = IssuerProfile.query.filter_by(user_id=current_user.id).first()
    data = {"issuer_status": profile.approval_status if profile else None}
    if current_user.role == "student":
        profile_ids = [p.id for p in StudentProfile.query.filter_by(user_id=current_user.id)]
        credentials = Credential.query.filter(Credential.student_profile_id.in_(profile_ids)).order_by(Credential.issue_date.desc()).all() if profile_ids else []
        data.update(credentials=credentials[:4], total=len(credentials), active=sum(c.effective_status == "active" for c in credentials), institutions=len({c.institution_id for c in credentials}),
                    notifications=Notification.query.filter_by(user_id=current_user.id).order_by(Notification.id.desc()).limit(5).all())
    elif current_user.role == "issuer" and profile and profile.approval_status == "approved":
        institution_id = profile.institution_id
        counts = dict(db.session.query(Credential.status, func.count(Credential.id)).filter_by(institution_id=institution_id).group_by(Credential.status).all())
        data.update(institution=db.session.get(Institution, institution_id), counts=counts, students=StudentProfile.query.filter_by(institution_id=institution_id).count(),
                    recent=Credential.query.filter_by(institution_id=institution_id).order_by(Credential.id.desc()).limit(5).all())
    elif current_user.role == "admin":
        counts = dict(db.session.query(Credential.status, func.count(Credential.id)).group_by(Credential.status).all())
        data.update(counts=counts, users=User.query.count(), institutions=Institution.query.filter_by(is_verified=True).count(),
                    pending=InstitutionVerificationRequest.query.filter_by(status="pending").count(),
                    events=AuditEvent.query.order_by(AuditEvent.id.desc()).limit(8).all())
    return render_template("auth/dashboard.html", **data)


@bp.post("/logout-page")
def logout_page():
    if current_user.is_authenticated:
        audit("logout", current_user.id); db.session.commit()
    logout_user()
    return redirect(url_for("verification.home"))


@bp.get("/admin/universities")
@roles_required("admin")
def university_reviews():
    requests = InstitutionVerificationRequest.query.order_by(InstitutionVerificationRequest.id.desc()).all()
    return render_template("admin/universities.html", requests=requests)

def credential_report_rows():
    """Per-institution credential counts in one grouped query (effective expiry is not stored, so it is not counted)."""
    counts = {}
    for institution_id, status, total in db.session.query(Credential.institution_id, Credential.status, func.count(Credential.id)).group_by(Credential.institution_id, Credential.status):
        counts[(institution_id, status)] = total
    return [{"institution": institution.name, "code": institution.code, **{status: counts.get((institution.id, status), 0) for status in REPORT_STATUSES}} for institution in Institution.query.order_by(Institution.name).all()]


REPORT_STATUSES = ("active", "revoked", "replaced")


@bp.get("/admin/reports")
@roles_required("admin")
def reports():
    return render_template("admin/reports.html", rows=credential_report_rows())

@bp.get("/admin/reports.csv")
@roles_required("admin")
def reports_csv():
    output = StringIO(); writer = csv.writer(output); writer.writerow(("institution", "code", *REPORT_STATUSES))
    for row in credential_report_rows():
        writer.writerow((row["institution"], row["code"], *(row[status] for status in REPORT_STATUSES)))
    return Response(output.getvalue(), mimetype="text/csv", headers={"Content-Disposition": "attachment; filename=credential-report.csv"})


@bp.get("/admin/users")
@roles_required("admin")
def users_page():
    query = User.query
    search, role = request.args.get("q", "").strip(), request.args.get("role", "")
    if search:
        query = query.filter(or_(User.email.ilike(f"%{search}%"), User.full_name.ilike(f"%{search}%")))
    if role in ("admin", "issuer", "student"):
        query = query.filter_by(role=role)
    page = query.order_by(User.email).paginate(per_page=current_app.config["PAGE_SIZE"], error_out=False)
    return render_template("admin/users.html", page=page, search=search, role=role)


@bp.post("/admin/users/<int:user_id>/status")
@roles_required("admin")
def set_user_status(user_id):
    user = db.session.get(User, user_id) or abort(404)
    if user.id == current_user.id:
        flash("You cannot disable your own account.", "error")
        return redirect(url_for("auth.users_page"))
    enable = request.form.get("action") == "enable"
    user.is_active = enable
    if enable:
        user.locked_until, user.failed_login_count = None, 0
    audit("user_enabled" if enable else "user_disabled", current_user.id, user_id=user.id); db.session.commit()
    flash(f"{user.email} has been {'enabled' if enable else 'disabled'}.", "success")
    return redirect(request.referrer or url_for("auth.users_page"))


@bp.post("/admin/universities/<int:request_id>/review")
@roles_required("admin")
def review_university(request_id):
    verification = db.session.get(InstitutionVerificationRequest, request_id)
    if not verification or verification.status != "pending":
        abort(404)
    decision = request.form.get("decision")
    note = request.form.get("review_note", "").strip()
    if decision not in ("approved", "rejected", "suspended") or not note:
        flash("Choose a decision and write a review note.", "error")
        return redirect(url_for("auth.university_reviews"))
    verification.status = decision; verification.reviewer_user_id = current_user.id; verification.review_note = note
    institution = db.session.get(Institution, verification.institution_id)
    profile = IssuerProfile.query.filter_by(user_id=verification.representative_user_id).first()
    institution.is_verified = decision == "approved"
    profile.approval_status = "approved" if decision == "approved" else decision
    audit(f"university_{decision}", current_user.id, institution_id=institution.id)
    db.session.commit()
    flash(f"{institution.name} was marked {decision}.", "success")
    return redirect(url_for("auth.university_reviews"))
