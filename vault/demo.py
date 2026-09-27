"""Deterministic dummy data for demonstrations. Never use real student documents."""
from datetime import date
from io import BytesIO

from werkzeug.datastructures import FileStorage, MultiDict

from vault.extensions import db
from vault.models import Credential, Institution, InstitutionVerificationRequest, IssuerProfile, StudentProfile, User

DEMO_PASSWORD = "DemoPassword1"
DEMO_PDF = b"%PDF-1.4\n% Academic Credential Vault demo certificate (dummy data)\n1 0 obj << /Type /Catalog >> endobj\ntrailer << /Root 1 0 R >>\n%%EOF\n"


def _user(email, name, role):
    user = User.query.filter_by(email=email).first()
    if not user:
        user = User(email=email, full_name=name, role=role, email_verified=True); user.set_password(DEMO_PASSWORD)
        db.session.add(user); db.session.flush()
    return user


def seed_demo_data():
    from vault.credentials.services import issue_credential

    admin = _user("admin@demo.local", "Demo Administrator", "admin")
    issuer = _user("issuer@demo.local", "Demo Issuer", "issuer")
    student = _user("student@demo.local", "Demo Student", "student")
    institution = Institution.query.filter_by(code="DEMO").first()
    if not institution:
        institution = Institution(name="Demo Institute of Technology", code="DEMO", is_verified=True)
        db.session.add(institution); db.session.flush()
    profile = IssuerProfile.query.filter_by(user_id=issuer.id).first()
    if not profile:
        profile = IssuerProfile(user_id=issuer.id, institution_id=institution.id, approval_status="approved", approved_by=admin.id)
        db.session.add(profile)
    if not InstitutionVerificationRequest.query.filter_by(institution_id=institution.id).first():
        db.session.add(InstitutionVerificationRequest(institution_id=institution.id, representative_user_id=issuer.id, official_email_domain="demo.local", status="approved", reviewer_user_id=admin.id, review_note="Demo institution"))
    student_profile = StudentProfile.query.filter_by(institution_id=institution.id, student_identifier="DEMO-2026-001").first()
    if not student_profile:
        student_profile = StudentProfile(institution_id=institution.id, student_identifier="DEMO-2026-001", user_id=student.id)
        db.session.add(student_profile)
    db.session.commit()
    if not Credential.query.filter_by(student_profile_id=student_profile.id).first():
        form = MultiDict({"title": "Bachelor of Technology", "programme": "Computer Science and Engineering", "issue_date": date.today().isoformat(), "student_profile_id": str(student_profile.id)})
        issue_credential(profile, issuer.id, form, FileStorage(BytesIO(DEMO_PDF), filename="demo-degree.pdf"))
    return f"Demo accounts ready (admin@demo.local, issuer@demo.local, student@demo.local). Password: {DEMO_PASSWORD}"
