import re
import secrets
from datetime import date, datetime, timezone

from flask import Blueprint, Response, abort, current_app, flash, jsonify, redirect, render_template, request, send_from_directory, url_for
from flask_login import current_user
from sqlalchemy import or_

from vault.auth.decorators import roles_required
from vault.auth.routes import audit
from vault.auth.services import queue_verification_email
from vault.credentials.routes import read_csv_rows
from vault.credentials.services import IssuanceError, bulk_issue_credentials, issue_credential, revoke_credential
from vault.extensions import db, limiter
from vault.models import ClaimRequest, Credential, CredentialTemplate, IntegrityCheck, Institution, InstitutionVerificationRequest, IssuerProfile, StudentProfile, User
from vault.notifications import notify

bp = Blueprint("university", __name__, url_prefix="/university")

def approved_profile():
    return IssuerProfile.query.filter_by(user_id=current_user.id, approval_status="approved").first()

@bp.get("/workspace")
@roles_required("issuer")
def workspace():
    profile = approved_profile()
    if not profile:
        return render_template("university/pending.html"), 403
    search = request.args.get("q", "").strip()
    student_query = StudentProfile.query.filter_by(institution_id=profile.institution_id)
    if search:
        student_query = student_query.filter(StudentProfile.student_identifier.ilike(f"%{search}%"))
    student_page = student_query.order_by(StudentProfile.student_identifier).paginate(per_page=current_app.config["PAGE_SIZE"], error_out=False)
    all_students = StudentProfile.query.filter_by(institution_id=profile.institution_id).order_by(StudentProfile.student_identifier).all()
    credentials = Credential.query.filter_by(institution_id=profile.institution_id).order_by(Credential.id.desc()).limit(10).all()
    counts = {status: Credential.query.filter_by(institution_id=profile.institution_id, status=status).count() for status in ("active", "revoked", "replaced")}
    templates = CredentialTemplate.query.filter_by(institution_id=profile.institution_id, archived=False).order_by(CredentialTemplate.name).all()
    institution = db.session.get(Institution, profile.institution_id)
    return render_template("university/workspace.html", institution=institution, student_page=student_page, students=all_students, search=search, credentials=credentials, counts=counts, templates=templates)

@bp.get("/api/students")
@roles_required("issuer")
def students():
    profile = approved_profile()
    if not profile: return jsonify(error="issuer_not_approved"), 403
    query = request.args.get("q", "").strip()
    records = StudentProfile.query.filter_by(institution_id=profile.institution_id)
    if query:
        records = records.filter(StudentProfile.student_identifier.ilike(f"%{query}%"))
    return jsonify(students=[{"id": s.id, "student_identifier": s.student_identifier, "user_id": s.user_id} for s in records.order_by(StudentProfile.student_identifier).all()])

@bp.get("/api/templates")
@roles_required("issuer")
def templates():
    profile = approved_profile()
    if not profile: return jsonify(error="issuer_not_approved"), 403
    rows = CredentialTemplate.query.filter_by(institution_id=profile.institution_id, archived=False).order_by(CredentialTemplate.name).all()
    return jsonify(templates=[{"id": t.id, "name": t.name, "title": t.title, "programme": t.programme, "description": t.description} for t in rows])

@bp.post("/api/templates")
@roles_required("issuer")
def create_template():
    profile = approved_profile(); data = request.get_json() or {}
    if not profile: return jsonify(error="issuer_not_approved"), 403
    required = ("name", "title", "programme")
    if any(not str(data.get(key, "")).strip() for key in required): return jsonify(error="template_fields_required"), 400
    template = CredentialTemplate(institution_id=profile.institution_id, created_by_user_id=current_user.id, name=data["name"].strip(), title=data["title"].strip(), programme=data["programme"].strip(), description=str(data.get("description", "")).strip())
    db.session.add(template); db.session.commit()
    return jsonify(id=template.id, name=template.name), 201

@bp.route("/templates", methods=["GET", "POST"])
@roles_required("issuer")
def templates_page():
    profile = approved_profile()
    if not profile: abort(403)
    if request.method == "POST":
        data = request.form
        if data.get("name", "").strip() and data.get("title", "").strip() and data.get("programme", "").strip():
            db.session.add(CredentialTemplate(institution_id=profile.institution_id, created_by_user_id=current_user.id, name=data["name"].strip(), title=data["title"].strip(), programme=data["programme"].strip(), description=data.get("description", "").strip()))
            db.session.commit()
        return redirect(url_for("university.templates_page"))
    rows = CredentialTemplate.query.filter_by(institution_id=profile.institution_id, archived=False).order_by(CredentialTemplate.name).all()
    return render_template("university/templates.html", templates=rows)

@bp.post("/api/students")
@roles_required("issuer")
def create_student():
    profile = approved_profile()
    if not profile: return jsonify(error="issuer_not_approved"), 403
    data = request.get_json() or {}
    identifier = data.get("student_identifier", "").strip()
    if not identifier: return jsonify(error="student_identifier_required"), 400
    if StudentProfile.query.filter_by(institution_id=profile.institution_id, student_identifier=identifier).first():
        return jsonify(error="student_exists"), 409
    user_id = data.get("user_id")
    if user_id:
        user = db.session.get(User, user_id)
        if not user or user.role != "student": return jsonify(error="student_user_required"), 400
    student = StudentProfile(institution_id=profile.institution_id, student_identifier=identifier, user_id=user_id)
    db.session.add(student); db.session.flush(); audit("student_profile_created", current_user.id, student_profile_id=student.id, institution_id=profile.institution_id); db.session.commit()
    return jsonify(id=student.id, student_identifier=identifier, user_id=user_id), 201

def _student_user(email):
    """Return the student account for an email, or None; raises ValueError if the email belongs to a non-student."""
    if not email:
        return None
    user = User.query.filter_by(email=email.strip().lower()).first()
    if not user or user.role != "student":
        raise ValueError("No student account is registered with that email.")
    return user

@bp.post("/students")
@roles_required("issuer")
def create_student_page():
    profile = approved_profile()
    if not profile: abort(403)
    identifier = request.form.get("student_identifier", "").strip()
    if not identifier:
        flash("Enter a student identifier.", "error"); return redirect(url_for("university.workspace"))
    if StudentProfile.query.filter_by(institution_id=profile.institution_id, student_identifier=identifier).first():
        flash(f"Student {identifier} already exists.", "error"); return redirect(url_for("university.workspace"))
    try:
        user = _student_user(request.form.get("student_email", ""))
    except ValueError as error:
        flash(str(error), "error"); return redirect(url_for("university.workspace"))
    student = StudentProfile(institution_id=profile.institution_id, student_identifier=identifier, user_id=user.id if user else None)
    db.session.add(student); db.session.flush(); audit("student_profile_created", current_user.id, student_profile_id=student.id, institution_id=profile.institution_id); db.session.commit()
    flash(f"Student {identifier} added" + (f" and linked to {user.email}." if user else "."), "success")
    return redirect(url_for("university.workspace"))

@bp.post("/students/<int:student_id>/link")
@roles_required("issuer")
def link_student_page(student_id):
    profile = approved_profile()
    if not profile: abort(403)
    student = StudentProfile.query.filter_by(id=student_id, institution_id=profile.institution_id).first_or_404()
    try:
        user = _student_user(request.form.get("student_email", ""))
    except ValueError as error:
        flash(str(error), "error"); return redirect(url_for("university.workspace"))
    if not user:
        flash("Enter the student's account email.", "error"); return redirect(url_for("university.workspace"))
    student.user_id = user.id
    for credential in Credential.query.filter_by(student_profile_id=student.id).all():
        notify(user.id, "credential_linked", f"{credential.title} is now available in your vault.")
    audit("student_profile_linked", current_user.id, student_profile_id=student.id, user_id=user.id); db.session.commit()
    flash(f"{student.student_identifier} is now linked to {user.email}.", "success")
    return redirect(url_for("university.workspace"))

@bp.post("/credentials")
@roles_required("issuer")
@limiter.limit("10 per hour")
def issue_page():
    profile = approved_profile()
    if not profile: abort(403)
    try:
        credential, duplicate = issue_credential(profile, current_user.id, request.form, request.files.get("document"))
    except IssuanceError as error:
        flash(str(error), "error"); return redirect(url_for("university.workspace"))
    flash(f"Issued {credential.title} as {credential.credential_id}.", "success")
    if duplicate:
        flash("Warning: an identical document was already issued under another credential.", "warning")
    return redirect(url_for("university.workspace"))


CREDENTIAL_FILTERS = ("active", "expired", "revoked", "replaced")


@bp.get("/credentials")
@roles_required("issuer")
def credentials_page():
    profile = approved_profile()
    if not profile: abort(403)
    search, status = request.args.get("q", "").strip(), request.args.get("status", "")
    query = Credential.query.filter_by(institution_id=profile.institution_id).outerjoin(StudentProfile, Credential.student_profile_id == StudentProfile.id)
    if search:
        like = f"%{search}%"
        query = query.filter(or_(Credential.credential_id.ilike(like), Credential.title.ilike(like), Credential.programme.ilike(like), StudentProfile.student_identifier.ilike(like)))
    today = date.today()
    if status == "expired":
        query = query.filter(Credential.status == "active", Credential.expiry_date < today)
    elif status == "active":
        query = query.filter(Credential.status == "active", or_(Credential.expiry_date.is_(None), Credential.expiry_date >= today))
    elif status in CREDENTIAL_FILTERS:
        query = query.filter(Credential.status == status)
    page = query.order_by(Credential.id.desc()).paginate(per_page=current_app.config["PAGE_SIZE"], error_out=False)
    return render_template("university/credentials.html", page=page, search=search, status=status)


def _owned_credential(profile, credential_id):
    return Credential.query.filter_by(credential_id=credential_id, institution_id=profile.institution_id).first_or_404()


@bp.get("/credentials/<credential_id>")
@roles_required("issuer")
def credential_detail(credential_id):
    profile = approved_profile()
    if not profile: abort(403)
    credential = _owned_credential(profile, credential_id)
    checks = IntegrityCheck.query.filter_by(credential_id=credential.id).order_by(IntegrityCheck.id.desc()).limit(5).all()
    can_manage = credential.issued_by_user_id == current_user.id and credential.status == "active"
    return render_template("university/credential_detail.html", credential=credential, checks=checks, can_manage=can_manage)


@bp.post("/credentials/<credential_id>/revoke")
@roles_required("issuer")
def revoke_page(credential_id):
    profile = approved_profile()
    if not profile: abort(403)
    credential = _owned_credential(profile, credential_id)
    try:
        revoke_credential(profile, current_user.id, credential, request.form.get("reason", ""))
    except IssuanceError as error:
        flash(str(error), "error")
    else:
        flash(f"{credential.credential_id} has been revoked.", "success")
    return redirect(url_for("university.credential_detail", credential_id=credential_id))


@bp.post("/credentials/<credential_id>/replace")
@roles_required("issuer")
@limiter.limit("10 per hour")
def replace_page(credential_id):
    profile = approved_profile()
    if not profile: abort(403)
    old = _owned_credential(profile, credential_id)
    form = request.form.copy()
    form["replacement_of_id"] = str(old.id)
    form["student_profile_id"] = str(old.student_profile_id or "")
    try:
        credential, _ = issue_credential(profile, current_user.id, form, request.files.get("document"))
    except IssuanceError as error:
        flash(str(error), "error")
        return redirect(url_for("university.credential_detail", credential_id=credential_id))
    flash(f"Issued {credential.credential_id} to replace {old.credential_id}.", "success")
    return redirect(url_for("university.credential_detail", credential_id=credential.credential_id))


@bp.route("/bulk", methods=["GET", "POST"])
@roles_required("issuer")
def bulk_page():
    profile = approved_profile()
    if not profile: abort(403)
    result = None
    if request.method == "POST":
        csv_file = request.files.get("students_csv")
        try:
            if not csv_file or not csv_file.filename:
                raise IssuanceError("students_csv_required", "Choose a CSV file listing the students.")
            rows = read_csv_rows(csv_file)
            defaults = {"title": request.form.get("title", "").strip(), "programme": request.form.get("programme", "").strip()}
            rows = [{**row, **{key: row.get(key) or value for key, value in defaults.items()}} for row in rows]
            created, errors = bulk_issue_credentials(profile, current_user.id, request.files.get("document"), rows)
        except IssuanceError as error:
            flash(str(error), "error")
        else:
            result = {"created": Credential.query.filter(Credential.credential_id.in_(created)).all() if created else [], "errors": errors}
            flash(f"Issued {len(created)} credential(s)" + (f"; {len(errors)} row(s) skipped." if errors else "."), "success" if not errors else "warning")
    return render_template("university/bulk.html", result=result)


BULK_SAMPLE = "student_identifier,title,programme\nCS-2026-001,Bachelor of Technology,Computer Science\nCS-2026-002,,\n"


@bp.get("/bulk/sample.csv")
@roles_required("issuer")
def bulk_sample():
    return Response(BULK_SAMPLE, mimetype="text/csv", headers={"Content-Disposition": "attachment; filename=bulk-issuance-sample.csv"})


@bp.get("/claims")
@roles_required("issuer")
def claims_page():
    profile = approved_profile()
    if not profile: abort(403)
    status = request.args.get("status", "pending")
    query = ClaimRequest.query.filter_by(institution_id=profile.institution_id)
    if status in ("pending", "approved", "rejected"):
        query = query.filter_by(status=status)
    claims = query.order_by(ClaimRequest.id.desc()).all()
    for claim in claims:
        claim.profile = StudentProfile.query.filter_by(institution_id=profile.institution_id, student_identifier=claim.student_identifier).first()
    return render_template("university/claims.html", claims=claims, status=status)


@bp.post("/claims/<int:claim_id>")
@roles_required("issuer")
def review_claim(claim_id):
    profile = approved_profile()
    if not profile: abort(403)
    claim = ClaimRequest.query.filter_by(id=claim_id, institution_id=profile.institution_id, status="pending").first_or_404()
    decision, note = request.form.get("decision"), request.form.get("review_note", "").strip()[:500]
    if decision not in ("approved", "rejected") or (decision == "rejected" and not note):
        flash("Choose a decision; a note is required when rejecting.", "error")
        return redirect(url_for("university.claims_page"))
    institution = db.session.get(Institution, profile.institution_id)
    if decision == "approved":
        student = StudentProfile.query.filter_by(institution_id=profile.institution_id, student_identifier=claim.student_identifier).first()
        if student and student.user_id and student.user_id != claim.user_id:
            flash("That student ID is already linked to another account; reject this claim instead.", "error")
            return redirect(url_for("university.claims_page"))
        if not student:
            student = StudentProfile(institution_id=profile.institution_id, student_identifier=claim.student_identifier); db.session.add(student)
        student.user_id = claim.user_id; db.session.flush()
        count = Credential.query.filter_by(student_profile_id=student.id).count()
        notify(claim.user_id, "claim_approved", f"{institution.name} linked student ID {claim.student_identifier} to your account. {count} credential(s) are now in your vault.")
    else:
        notify(claim.user_id, "claim_rejected", f"{institution.name} did not approve your claim for {claim.student_identifier}: {note}")
    claim.status, claim.review_note, claim.reviewed_by_user_id, claim.reviewed_at = decision, note or None, current_user.id, datetime.now(timezone.utc)
    audit(f"claim_{decision}", current_user.id, claim_id=claim.id, institution_id=profile.institution_id); db.session.commit()
    flash(f"Claim for {claim.student_identifier} {decision}.", "success")
    return redirect(url_for("university.claims_page"))


HEX_COLOUR = re.compile(r"^#[0-9a-fA-F]{6}$")
LOGO_TYPES = {b"\x89PNG\r\n\x1a\n": "png", b"\xff\xd8\xff": "jpg"}
MAX_LOGO_BYTES = 512 * 1024


@bp.route("/settings", methods=["GET", "POST"])
@roles_required("issuer")
def settings_page():
    profile = approved_profile()
    if not profile: abort(403)
    institution = db.session.get(Institution, profile.institution_id)
    if request.method == "POST":
        colour, website = request.form.get("accent_color", "").strip(), request.form.get("website", "").strip()
        if colour and not HEX_COLOUR.match(colour):
            flash("Accent colour must be a hex value such as #3b5bdb.", "error"); return redirect(url_for("university.settings_page"))
        if website and not website.startswith("https://"):
            flash("Website must start with https://.", "error"); return redirect(url_for("university.settings_page"))
        logo = request.files.get("logo")
        if logo and logo.filename:
            content = logo.read(MAX_LOGO_BYTES + 1)
            extension = next((ext for magic, ext in LOGO_TYPES.items() if content.startswith(magic)), None)
            if not extension or len(content) > MAX_LOGO_BYTES:
                flash("The logo must be a PNG or JPEG under 512 KB.", "error"); return redirect(url_for("university.settings_page"))
            folder = current_app.config["UPLOAD_DIRECTORY"] / "logos"; folder.mkdir(exist_ok=True)
            if institution.logo_key:
                (folder / institution.logo_key).unlink(missing_ok=True)
            institution.logo_key = f"{secrets.token_urlsafe(16)}.{extension}"
            (folder / institution.logo_key).write_bytes(content)
        institution.accent_color, institution.website = colour or None, website or None
        audit("institution_branding_updated", current_user.id, institution_id=institution.id); db.session.commit()
        flash("Branding saved. New generated certificates will use it.", "success")
        return redirect(url_for("university.settings_page"))
    return render_template("university/settings.html", institution=institution)


@bp.get("/logo/<code>")
def logo(code):
    institution = Institution.query.filter_by(code=code.upper(), is_verified=True).first_or_404()
    if not institution.logo_key:
        abort(404)
    return send_from_directory(current_app.config["UPLOAD_DIRECTORY"] / "logos", institution.logo_key, max_age=3600)


@bp.route("/register", methods=["GET", "POST"])
@limiter.limit("3 per hour", methods=["POST"])
def register():
    if request.method == "GET":
        return render_template("university/register.html")
    name = request.form.get("institution_name", "").strip()
    code = request.form.get("institution_code", "").strip().upper()
    email = request.form.get("email", "").strip().lower()
    full_name = request.form.get("full_name", "").strip()
    password = request.form.get("password", "")
    if not name or not code or not email or "@" not in email or not full_name or len(password) < 12 or not any(char.isdigit() for char in password):
        return render_template("university/register.html", error="Complete every field and use a 12-character password containing a digit."), 400
    if Institution.query.filter_by(code=code).first() or User.query.filter_by(email=email).first():
        return render_template("university/register.html", error="That institution code or representative email is already registered."), 409
    institution = Institution(name=name, code=code, is_verified=False)
    representative = User(email=email, full_name=full_name, role="issuer"); representative.set_password(password)
    db.session.add_all([institution, representative]); db.session.flush()
    db.session.add(IssuerProfile(user_id=representative.id, institution_id=institution.id, approval_status="pending"))
    db.session.add(InstitutionVerificationRequest(institution_id=institution.id, representative_user_id=representative.id, official_email_domain=email.rsplit("@", 1)[1]))
    audit("university_registration_requested", representative.id, institution_id=institution.id)
    queue_verification_email(representative)
    db.session.commit()
    return redirect(url_for("university.pending"))


@bp.get("/pending")
def pending():
    return render_template("university/pending.html")


@bp.get("/login")
def login():
    return redirect(url_for("auth.login_page"))
