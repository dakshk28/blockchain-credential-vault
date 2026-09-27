"""Regression tests for the Phase P1 bug fixes listed in production.md section 16."""
from datetime import date, timedelta
from io import BytesIO

import pytest

import config
from vault import create_app
from vault.extensions import db
from vault.models import AuditEvent, Credential, Institution, IssuerProfile, Notification, StudentProfile, User

PASSWORD = "SecurePassword1"
PDF = b"%PDF-1.4 regression"
HTML = {"Accept": "text/html"}


@pytest.fixture()
def issuer(app, client):
    with app.app_context():
        institution = Institution(name="Regression University", code="REG", is_verified=True)
        user = User(email="issuer@reg.edu", full_name="Issuer", role="issuer"); user.set_password(PASSWORD)
        db.session.add_all([institution, user]); db.session.flush()
        db.session.add(IssuerProfile(user_id=user.id, institution_id=institution.id, approval_status="approved")); db.session.commit()
        ids = {"institution_id": institution.id, "user_id": user.id}
    client.post("/auth/api/login", json={"email": "issuer@reg.edu", "password": PASSWORD})
    return ids


def upload_count(app):
    return len(list(app.config["UPLOAD_DIRECTORY"].glob("*.pdf")))


def test_bulk_issuance_creates_one_credential_per_row_and_reports_blank_rows(client, app, issuer):
    csv = b"student_identifier,title\nB-001,Degree\n,Blank\nB-002,\n"
    response = client.post("/credentials/bulk", data={"document": (BytesIO(PDF), "bulk.pdf"), "students_csv": (BytesIO(csv), "s.csv")}, content_type="multipart/form-data")
    assert response.status_code == 201
    body = response.get_json()
    assert body["count"] == 2
    assert body["errors"] == [{"row": 3, "error": "student_identifier is blank"}]
    with app.app_context():
        assert {s.student_identifier for s in StudentProfile.query.all()} == {"B-001", "B-002"}
        assert Credential.query.filter_by(title="Academic Credential").count() == 1


def test_bulk_issuance_without_pdf_is_a_clean_400(client, issuer):
    response = client.post("/credentials/bulk", data={"students_csv": (BytesIO(b"student_identifier\nX\n"), "s.csv")}, content_type="multipart/form-data")
    assert response.status_code == 400
    assert response.get_json()["error"] == "invalid_document"


def test_ordinary_browsing_is_not_rate_limited(monkeypatch):
    monkeypatch.setattr(config.TestConfig, "RATELIMIT_ENABLED", True)
    client = create_app("test").test_client()
    assert all(client.get("/").status_code == 200 for _ in range(60))


def test_seed_demo_creates_a_working_issuer_and_linked_student(app):
    runner = app.test_cli_runner()
    with app.app_context():
        assert "Demo accounts ready" in runner.invoke(args=["seed-demo"]).output
        runner.invoke(args=["seed-demo"])  # idempotent
        issuer = User.query.filter_by(email="issuer@demo.local").one()
        assert IssuerProfile.query.filter_by(user_id=issuer.id, approval_status="approved").one()
        student = User.query.filter_by(email="student@demo.local").one()
        profile = StudentProfile.query.filter_by(user_id=student.id).one()
        assert Credential.query.filter_by(student_profile_id=profile.id).count() == 1


def test_university_can_link_student_account_from_browser_form(client, app, issuer):
    with app.app_context():
        student = User(email="linked@reg.edu", full_name="Linked", role="student"); student.set_password(PASSWORD)
        db.session.add(student); db.session.commit(); student_id = student.id
    response = client.post("/university/students", data={"student_identifier": "L-001", "student_email": "linked@reg.edu"}, headers=HTML)
    assert response.status_code == 302
    with app.app_context():
        assert StudentProfile.query.filter_by(student_identifier="L-001").one().user_id == student_id


def test_linking_existing_profile_notifies_student_of_existing_credentials(client, app, issuer):
    with app.app_context():
        student = User(email="late@reg.edu", full_name="Late", role="student"); student.set_password(PASSWORD)
        profile = StudentProfile(institution_id=issuer["institution_id"], student_identifier="L-002")
        db.session.add_all([student, profile]); db.session.commit(); profile_id = profile.id
    client.post("/credentials", data={"student_profile_id": str(profile_id), "title": "Diploma", "programme": "Maths", "document": (BytesIO(PDF), "d.pdf")})
    client.post(f"/university/students/{profile_id}/link", data={"student_email": "late@reg.edu"}, headers=HTML)
    with app.app_context():
        assert db.session.get(StudentProfile, profile_id).user_id is not None
        assert Notification.query.filter_by(event_type="credential_linked").count() == 1


def test_linking_rejects_non_student_accounts(client, app, issuer):
    client.post("/university/students", data={"student_identifier": "L-003", "student_email": "issuer@reg.edu"}, headers=HTML)
    with app.app_context():
        assert StudentProfile.query.filter_by(student_identifier="L-003").first() is None


def test_browser_issuance_error_shows_message_not_json(client, issuer):
    response = client.post("/university/credentials", data={"title": "BSc", "programme": "CS", "document": (BytesIO(b"not a pdf"), "bad.txt")}, headers=HTML, follow_redirects=True)
    assert response.status_code == 200
    assert b"A PDF document is required." in response.data
    assert not response.is_json


def test_browser_error_pages_are_html_and_api_errors_are_json(client):
    assert b"Page not found" in client.get("/missing", headers=HTML).data
    assert client.get("/api/missing").get_json()["error"] == "not_found"
    assert client.get("/student/vault", headers=HTML).status_code == 302


def test_expiry_is_reported_by_verification_and_blocks_authenticity(client, app, issuer):
    yesterday, last_year = date.today() - timedelta(days=1), date.today() - timedelta(days=365)
    created = client.post("/credentials", data={"title": "Cert", "programme": "CS", "issue_date": last_year.isoformat(), "expiry_date": yesterday.isoformat(), "document": (BytesIO(PDF), "c.pdf")})
    credential_id = created.get_json()["credential_id"]
    verified = client.get(f"/verify/{credential_id}").get_json()
    assert verified["status"] == "expired"
    assert verified["institution_name"] == "Regression University"
    compared = client.post(f"/verify/{credential_id}/compare", data={"document": (BytesIO(PDF), "c.pdf")}).get_json()
    assert compared["document_result"] == "unchanged"
    assert compared["authentic"] is False


def test_expiry_must_follow_issue_date(client, issuer):
    response = client.post("/credentials", data={"title": "Cert", "programme": "CS", "issue_date": "2026-01-10", "expiry_date": "2026-01-01", "document": (BytesIO(PDF), "c.pdf")})
    assert response.status_code == 400
    assert response.get_json()["error"] == "invalid_date"


def test_student_vault_expired_filter(client, app, issuer):
    with app.app_context():
        student = User(email="exp@reg.edu", full_name="Exp", role="student"); student.set_password(PASSWORD)
        db.session.add(student); db.session.flush()
        profile = StudentProfile(institution_id=issuer["institution_id"], student_identifier="E-1", user_id=student.id); db.session.add(profile); db.session.flush()
        for public_id, expiry in (("ACV-EXPIRED", date.today() - timedelta(days=1)), ("ACV-CURRENT", None)):
            db.session.add(Credential(credential_id=public_id, institution_id=issuer["institution_id"], issued_by_user_id=issuer["user_id"], student_profile_id=profile.id, title=public_id, programme="CS", issue_date=date.today() - timedelta(days=30), expiry_date=expiry, document_sha256="b" * 64, storage_key=f"{public_id}.pdf", original_filename="x.pdf"))
        db.session.commit()
    client.post("/auth/api/login", json={"email": "exp@reg.edu", "password": PASSWORD})
    expired = client.get("/student/vault?status=expired").data
    assert b"ACV-EXPIRED" in expired and b"ACV-CURRENT" not in expired
    active = client.get("/student/vault?status=active").data
    assert b"ACV-CURRENT" in active and b"ACV-EXPIRED" not in active


def test_failed_issuance_leaves_no_file_or_rows(client, app, issuer, monkeypatch):
    before = upload_count(app)
    monkeypatch.setattr("vault.credentials.services.append_event", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    with pytest.raises(RuntimeError):
        client.post("/credentials", data={"title": "Cert", "programme": "CS", "document": (BytesIO(PDF), "c.pdf")})
    assert upload_count(app) == before
    with app.app_context():
        assert Credential.query.count() == 0


def test_replacement_and_notification_commit_with_issuance(client, app, issuer):
    with app.app_context():
        student = User(email="rep@reg.edu", full_name="Rep", role="student"); student.set_password(PASSWORD)
        db.session.add(student); db.session.flush()
        profile = StudentProfile(institution_id=issuer["institution_id"], student_identifier="R-1", user_id=student.id); db.session.add(profile); db.session.commit(); profile_id = profile.id
    first = client.post("/credentials", data={"student_profile_id": str(profile_id), "title": "V1", "programme": "CS", "document": (BytesIO(PDF), "a.pdf")}).get_json()["credential_id"]
    with app.app_context():
        old_id = Credential.query.filter_by(credential_id=first).one().id
    client.post("/credentials", data={"student_profile_id": str(profile_id), "replacement_of_id": str(old_id), "title": "V2", "programme": "CS", "document": (BytesIO(PDF + b"v2"), "b.pdf")})
    with app.app_context():
        assert db.session.get(Credential, old_id).status == "replaced"
        assert Notification.query.count() == 2
        assert AuditEvent.query.filter_by(event_type="credential_replaced").count() == 1
