"""Tests for Phase P2 security and code-quality hardening."""
from io import BytesIO

import pytest

from config import DEFAULT_SECRET, ProductionConfig
from vault.audit.services import validate_chain
from vault.credentials.services import screen_pdf
from vault.extensions import db
from vault.models import Credential, Institution, IssuerProfile, User

PASSWORD = "SecurePassword1"
HTML = {"Accept": "text/html"}


def make_user(app, email, role="student", password=PASSWORD):
    with app.app_context():
        user = User(email=email, full_name=email.split("@")[0], role=role); user.set_password(password)
        db.session.add(user); db.session.commit()
        return user.id


def login(client, email, password=PASSWORD):
    return client.post("/auth/api/login", json={"email": email, "password": password})


@pytest.mark.parametrize("secret", [DEFAULT_SECRET, "short"])
def test_production_refuses_weak_secrets(secret):
    with pytest.raises(RuntimeError):
        ProductionConfig.validate({"SECRET_KEY": secret, "SIGNING_SECRET": "x" * 40})


def test_production_accepts_strong_secrets_with_signing_key():
    ProductionConfig.validate({"SECRET_KEY": "k" * 40, "SIGNING_SECRET": "s" * 40, "SIGNING_PRIVATE_KEY": "-----BEGIN PRIVATE KEY-----"})


def test_production_requires_ed25519_signing_key(tmp_path):
    with pytest.raises(RuntimeError, match="Ed25519"):
        ProductionConfig.validate({"SECRET_KEY": "k" * 40, "SIGNING_SECRET": "s" * 40, "SIGNING_PRIVATE_KEY": "", "SIGNING_KEY_FILE": tmp_path / "missing.pem"})


@pytest.mark.parametrize("payload", [b"/JavaScript (app.alert(1))", b"/OpenAction << /S /JS /JS (x) >>", b"/Launch << /F (cmd.exe) >>", b"/EmbeddedFiles <<>>", b"/J#61vaScript (x)"])
def test_active_pdf_content_is_rejected(app, payload):
    with app.app_context(), pytest.raises(ValueError):
        screen_pdf(b"%PDF-1.7\n" + payload)


def test_plain_pdf_with_similar_words_is_accepted(app):
    with app.app_context():
        screen_pdf(b"%PDF-1.7\n(A course on JavaScript and <script> tags) /JSONData /Type /Page")


def test_external_scanner_hook_blocks_on_nonzero_exit(app):
    app.config["MALWARE_SCAN_COMMAND"] = "false"
    with app.app_context(), pytest.raises(ValueError):
        screen_pdf(b"%PDF-1.7 clean")
    app.config["MALWARE_SCAN_COMMAND"] = "true"
    with app.app_context():
        screen_pdf(b"%PDF-1.7 clean")


def test_account_locks_after_repeated_failures_and_admin_can_unlock(client, app):
    make_user(app, "victim@example.edu")
    admin_id = make_user(app, "admin@example.edu", role="admin")
    for _ in range(app.config["LOGIN_LOCKOUT_THRESHOLD"]):
        assert login(client, "victim@example.edu", "wrong-password1").status_code == 401
    locked = login(client, "victim@example.edu")
    assert locked.status_code == 423 and locked.get_json()["error"] == "account_locked"
    with app.app_context():
        victim_id = User.query.filter_by(email="victim@example.edu").one().id
    login(client, "admin@example.edu")
    client.post(f"/auth/admin/users/{victim_id}/status", data={"action": "enable"}, headers=HTML)
    client.post("/auth/api/logout")
    assert login(client, "victim@example.edu").status_code == 200
    with app.app_context():
        assert validate_chain()["valid"] is True


def test_successful_login_resets_failure_count(client, app):
    make_user(app, "reset@example.edu")
    login(client, "reset@example.edu", "wrong-password1")
    assert login(client, "reset@example.edu").status_code == 200
    with app.app_context():
        assert User.query.filter_by(email="reset@example.edu").one().failed_login_count == 0


def test_admin_can_disable_user_but_not_self(client, app):
    target = make_user(app, "target@example.edu")
    admin_id = make_user(app, "boss@example.edu", role="admin")
    login(client, "boss@example.edu")
    assert b"target@example.edu" in client.get("/auth/admin/users?q=target").data
    client.post(f"/auth/admin/users/{target}/status", data={"action": "disable"}, headers=HTML)
    client.post(f"/auth/admin/users/{admin_id}/status", data={"action": "disable"}, headers=HTML)
    with app.app_context():
        assert db.session.get(User, target).is_active is False
        assert db.session.get(User, admin_id).is_active is True


def test_non_admin_cannot_manage_users(client, app):
    target = make_user(app, "t2@example.edu")
    make_user(app, "s2@example.edu")
    login(client, "s2@example.edu")
    assert client.post(f"/auth/admin/users/{target}/status", data={"action": "disable"}).status_code == 403


def test_reports_use_grouped_counts(client, app):
    make_user(app, "rep-admin@example.edu", role="admin")
    with app.app_context():
        institution = Institution(name="Count U", code="CNT"); issuer = User(email="i@c.edu", full_name="I", role="issuer"); issuer.set_password(PASSWORD)
        db.session.add_all([institution, issuer]); db.session.flush()
        for index, status in enumerate(("active", "active", "revoked")):
            db.session.add(Credential(credential_id=f"ACV-C{index}", institution_id=institution.id, issued_by_user_id=issuer.id, title="T", programme="P", issue_date=__import__("datetime").date.today(), status=status, document_sha256="c" * 64, storage_key=f"c{index}.pdf", original_filename="c.pdf"))
        db.session.commit()
    login(client, "rep-admin@example.edu")
    csv = client.get("/auth/admin/reports.csv").data.decode()
    assert "Count U,CNT,2,1,0" in csv


def test_workspace_student_search_and_pagination(client, app):
    with app.app_context():
        institution = Institution(name="Page U", code="PGU", is_verified=True); issuer = User(email="p@u.edu", full_name="P", role="issuer"); issuer.set_password(PASSWORD)
        db.session.add_all([institution, issuer]); db.session.flush()
        db.session.add(IssuerProfile(user_id=issuer.id, institution_id=institution.id, approval_status="approved")); db.session.commit()
    login(client, "p@u.edu")
    for index in range(25):
        client.post("/university/api/students", json={"student_identifier": f"PG-{index:03d}"})
    first = client.get("/university/workspace").data
    assert b"Page 1 of 2" in first and first.count(b"data-student-row") == 20
    second = client.get("/university/workspace?page=2").data
    assert second.count(b"data-student-row") == 5 and b">PG-024<" in second
    searched = client.get("/university/workspace?q=007").data
    assert searched.count(b"data-student-row") == 1 and b">PG-007<" in searched
