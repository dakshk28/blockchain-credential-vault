"""Phase P6: claims, email, password reset, generated certificates, branding, receipts, expiry reminders."""
import hashlib
import re
from datetime import date, timedelta
from io import BytesIO

import pytest

from vault.demo import DEMO_PASSWORD
from vault.extensions import db
from vault.models import ClaimRequest, Credential, Institution, Notification, StudentProfile, User

HTML = {"Accept": "text/html"}
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


@pytest.fixture()
def demo(app):
    with app.app_context():
        app.test_cli_runner().invoke(args=["seed-demo"])
    app.extensions["outbox"] = []
    return app


def login(client, email, password=DEMO_PASSWORD):
    client.post("/auth/api/logout")
    return client.post("/auth/api/login", json={"email": email, "password": password})


def outbox(app):
    return app.extensions.get("outbox", [])


def link_in(message):
    return re.search(r"http://localhost(/\S+)", message.get_content()).group(1)


# ---------- Email verification & password reset ----------

def test_registration_sends_verification_email_and_link_verifies(client, app, demo):
    client.post("/auth/register", data={"full_name": "New Student", "email": "new@x.edu", "password": "LongPassword123"}, headers=HTML)
    assert outbox(app)[-1]["To"] == "new@x.edu"
    client.get(link_in(outbox(app)[-1]), headers=HTML)
    with app.app_context():
        assert User.query.filter_by(email="new@x.edu").one().email_verified


def test_tampered_verification_token_is_rejected(client, app, demo):
    client.post("/auth/register", data={"full_name": "N", "email": "n2@x.edu", "password": "LongPassword123"}, headers=HTML)
    client.get(link_in(outbox(app)[-1]) + "x", headers=HTML)
    with app.app_context():
        assert not User.query.filter_by(email="n2@x.edu").one().email_verified


def test_password_reset_flow_is_single_use(client, app, demo):
    assert b"a reset link is on its way" in client.post("/auth/forgot", data={"email": "student@demo.local"}, headers=HTML, follow_redirects=True).data
    path = link_in(outbox(app)[-1])
    assert client.post(path, data={"password": "short", "confirm": "short"}, headers=HTML).status_code == 400
    client.post(path, data={"password": "BrandNewPassword9", "confirm": "BrandNewPassword9"}, headers=HTML)
    assert login(client, "student@demo.local", "BrandNewPassword9").status_code == 200
    reused = client.get(path, headers=HTML, follow_redirects=True).data
    assert b"invalid or has expired" in reused


def test_forgot_password_does_not_reveal_unknown_accounts(client, app, demo):
    before = len(outbox(app))
    page = client.post("/auth/forgot", data={"email": "nobody@x.edu"}, headers=HTML, follow_redirects=True).data
    assert b"a reset link is on its way" in page and len(outbox(app)) == before


def test_notifications_are_emailed_after_commit_only_to_verified_users(client, app, demo):
    login(client, "issuer@demo.local")
    with app.app_context():
        profile_id = StudentProfile.query.filter_by(student_identifier="DEMO-2026-001").one().id
    client.post("/credentials", data={"student_profile_id": str(profile_id), "title": "Diploma", "programme": "Maths", "document": (BytesIO(b"%PDF-1.4 mail"), "d.pdf")})
    assert outbox(app)[-1]["To"] == "student@demo.local" and "new credential" in outbox(app)[-1]["Subject"].lower()


def test_rolled_back_actions_send_no_email(client, app, demo, monkeypatch):
    login(client, "issuer@demo.local")
    with app.app_context():
        profile_id = StudentProfile.query.filter_by(student_identifier="DEMO-2026-001").one().id
    before = len(outbox(app))
    monkeypatch.setattr("vault.credentials.services.add_signature", lambda c: (_ for _ in ()).throw(RuntimeError("fail")))
    with pytest.raises(RuntimeError):
        client.post("/credentials", data={"student_profile_id": str(profile_id), "title": "X", "programme": "Y", "document": (BytesIO(b"%PDF-1.4 rb"), "d.pdf")})
    assert len(outbox(app)) == before


# ---------- Claims ----------

def make_student(app, email, verified=True):
    with app.app_context():
        user = User(email=email, full_name="Claiming Student", role="student", email_verified=verified); user.set_password(DEMO_PASSWORD)
        db.session.add(user); db.session.commit()
        return user.id


def demo_institution_id(app):
    with app.app_context():
        return Institution.query.filter_by(code="DEMO").one().id


def test_claim_approval_links_profile_and_notifies(client, app, demo):
    user_id = make_student(app, "claimer@x.edu")
    login(client, "issuer@demo.local")
    client.post("/university/students", data={"student_identifier": "CL-001"}, headers=HTML)
    login(client, "claimer@x.edu")
    client.post("/student/claim", data={"institution_id": demo_institution_id(app), "student_identifier": "CL-001"}, headers=HTML)
    with app.app_context():
        claim_id = ClaimRequest.query.one().id
    login(client, "issuer@demo.local")
    assert b"Claiming Student" in client.get("/university/claims", headers=HTML).data
    client.post(f"/university/claims/{claim_id}", data={"decision": "approved"}, headers=HTML)
    with app.app_context():
        assert StudentProfile.query.filter_by(student_identifier="CL-001").one().user_id == user_id
        assert Notification.query.filter_by(user_id=user_id, event_type="claim_approved").count() == 1


def test_claim_rejection_requires_note(client, app, demo):
    make_student(app, "rej@x.edu")
    login(client, "rej@x.edu")
    client.post("/student/claim", data={"institution_id": demo_institution_id(app), "student_identifier": "RJ-1"}, headers=HTML)
    with app.app_context():
        claim_id = ClaimRequest.query.one().id
    login(client, "issuer@demo.local")
    client.post(f"/university/claims/{claim_id}", data={"decision": "rejected"}, headers=HTML)
    with app.app_context():
        assert db.session.get(ClaimRequest, claim_id).status == "pending"
    client.post(f"/university/claims/{claim_id}", data={"decision": "rejected", "review_note": "No such student"}, headers=HTML)
    with app.app_context():
        assert db.session.get(ClaimRequest, claim_id).status == "rejected"


def test_claims_blocked_for_unverified_email_and_for_taken_ids(client, app, demo):
    make_student(app, "unverified@x.edu", verified=False)
    login(client, "unverified@x.edu")
    assert b"Confirm your email" in client.post("/student/claim", data={"institution_id": demo_institution_id(app), "student_identifier": "X"}, headers=HTML, follow_redirects=True).data
    make_student(app, "thief@x.edu")
    login(client, "thief@x.edu")
    page = client.post("/student/claim", data={"institution_id": demo_institution_id(app), "student_identifier": "DEMO-2026-001"}, headers=HTML, follow_redirects=True).data
    assert b"already linked to another account" in page
    with app.app_context():
        assert ClaimRequest.query.count() == 0


def test_issuer_cannot_review_other_institutions_claims(client, app, demo):
    make_student(app, "c2@x.edu")
    with app.app_context():
        other = Institution(name="Other U", code="OTH", is_verified=True); db.session.add(other); db.session.commit(); other_id = other.id
    login(client, "c2@x.edu")
    client.post("/student/claim", data={"institution_id": other_id, "student_identifier": "O-1"}, headers=HTML)
    with app.app_context():
        claim_id = ClaimRequest.query.one().id
    login(client, "issuer@demo.local")
    assert client.post(f"/university/claims/{claim_id}", data={"decision": "approved"}, headers=HTML).status_code == 404


# ---------- Generated certificates & branding ----------

def test_generated_certificate_is_a_valid_deterministic_pdf(client, app, demo):
    login(client, "issuer@demo.local")
    with app.app_context():
        profile_id = StudentProfile.query.filter_by(student_identifier="DEMO-2026-001").one().id
    response = client.post("/university/credentials", data={"student_profile_id": str(profile_id), "title": "Master of Technology", "programme": "Data Science", "document_mode": "generate"}, headers=HTML, follow_redirects=True)
    assert b"Issued Master of Technology" in response.data
    with app.app_context():
        credential = Credential.query.filter_by(title="Master of Technology").one()
        content = (app.config["UPLOAD_DIRECTORY"] / credential.storage_key).read_bytes()
        assert content.startswith(b"%PDF-") and hashlib.sha256(content).hexdigest() == credential.document_sha256
        assert credential.original_filename == f"{credential.credential_id}.pdf"
        from vault.credentials.services import generate_certificate
        with app.test_request_context():
            again = generate_certificate(credential.institution_id, credential.credential_id, "Demo Student", credential.title, credential.programme, credential.issue_date, None)
        assert again == content  # invariant rendering reproduces the fingerprint


def test_generation_requires_a_recipient_name_for_unlinked_students(client, app, demo):
    login(client, "issuer@demo.local")
    client.post("/university/students", data={"student_identifier": "UNL-1"}, headers=HTML)
    with app.app_context():
        profile_id = StudentProfile.query.filter_by(student_identifier="UNL-1").one().id
    page = client.post("/university/credentials", data={"student_profile_id": str(profile_id), "title": "T", "programme": "P", "document_mode": "generate"}, headers=HTML, follow_redirects=True).data
    assert b"recipient&#39;s name" in page or b"recipient's name" in page


def test_branding_settings_validate_and_logo_is_served(client, app, demo):
    login(client, "issuer@demo.local")
    bad = client.post("/university/settings", data={"accent_color": "red;background:url(x)"}, headers=HTML, follow_redirects=True).data
    assert b"hex value" in bad
    assert b"PNG or JPEG" in client.post("/university/settings", data={"logo": (BytesIO(b"GIF89a"), "l.gif")}, headers=HTML, follow_redirects=True).data
    client.post("/university/settings", data={"accent_color": "#aa3355", "website": "https://demo.example.edu", "logo": (BytesIO(PNG), "logo.png")}, headers=HTML)
    with app.app_context():
        institution = Institution.query.filter_by(code="DEMO").one()
        assert institution.accent_color == "#aa3355" and institution.logo_key.endswith(".png")
        credential_id = Credential.query.first().credential_id
    assert client.get("/university/logo/DEMO").data == PNG
    page = client.get(f"/credential/{credential_id}", headers=HTML).data
    assert b'fill="#aa3355"' in page and b"https://demo.example.edu" in page


# ---------- Receipt & expiry reminders ----------

def test_receipt_records_check_time_and_status(client, app, demo):
    with app.app_context():
        credential_id = Credential.query.first().credential_id
    page = client.get(f"/credential/{credential_id}/receipt", headers=HTML).data
    assert b"Credential verified" in page and b"UTC" in page and b"Verification receipt" in page


def test_expiry_reminders_are_sent_once(app, demo):
    with app.app_context():
        credential = Credential.query.first(); credential.expiry_date = date.today() + timedelta(days=10); db.session.commit()
    runner = app.test_cli_runner()
    assert "Sent 1" in runner.invoke(args=["send-expiry-reminders"]).output
    assert "Sent 0" in runner.invoke(args=["send-expiry-reminders"]).output
    assert outbox(app)[-1]["Subject"] == "A credential is about to expire"
