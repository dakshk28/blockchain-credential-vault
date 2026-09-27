"""Phase P7: security regression tests (IDOR, CSRF, API boundaries) and remaining coverage gaps."""
import smtplib
from io import BytesIO

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from vault import create_app
from vault.demo import DEMO_PASSWORD
from vault.extensions import db
from vault.models import Credential, Institution, IssuerProfile, StudentProfile, User

HTML = {"Accept": "text/html"}


@pytest.fixture()
def demo(app):
    with app.app_context():
        app.test_cli_runner().invoke(args=["seed-demo"])
        other = Institution(name="Rival University", code="RIVAL", is_verified=True)
        rival = User(email="rival@rival.edu", full_name="Rival Issuer", role="issuer", email_verified=True); rival.set_password(DEMO_PASSWORD)
        stranger = User(email="stranger@x.edu", full_name="Stranger", role="student", email_verified=True); stranger.set_password(DEMO_PASSWORD)
        db.session.add_all([other, rival, stranger]); db.session.flush()
        db.session.add(IssuerProfile(user_id=rival.id, institution_id=other.id, approval_status="approved")); db.session.commit()
        return Credential.query.one().credential_id


def login(client, email):
    client.post("/auth/api/logout")
    assert client.post("/auth/api/login", json={"email": email, "password": DEMO_PASSWORD}).status_code == 200


# ---------- Document download authorisation (IDOR) ----------

@pytest.mark.parametrize("email,expected", [("student@demo.local", 200), ("issuer@demo.local", 200), ("admin@demo.local", 200), ("stranger@x.edu", 403), ("rival@rival.edu", 403)])
def test_document_download_is_scoped(client, demo, email, expected):
    login(client, email)
    assert client.get(f"/credentials/{demo}/document").status_code == expected


def test_anonymous_cannot_download(client, demo):
    assert client.get(f"/credentials/{demo}/document").status_code == 401


def test_rival_issuer_cannot_view_or_revoke_credential(client, app, demo):
    login(client, "rival@rival.edu")
    assert client.get(f"/university/credentials/{demo}", headers=HTML).status_code == 404
    assert client.post(f"/credentials/{demo}/revoke", json={"reason": "hostile"}).status_code == 403
    with app.app_context():
        assert Credential.query.one().status == "active"


def test_api_revoke_validates_reason_and_state(client, demo):
    login(client, "issuer@demo.local")
    assert client.post(f"/credentials/{demo}/revoke", json={}).status_code == 400
    assert client.post(f"/credentials/{demo}/revoke", json={"reason": "error"}).get_json()["status"] == "revoked"
    assert client.post(f"/credentials/{demo}/revoke", json={"reason": "again"}).status_code == 400


def test_signature_endpoint_is_public_and_reports_ed25519(client, demo):
    body = client.get(f"/credentials/{demo}/signature").get_json()
    assert body["algorithm"] == "Ed25519" and len(body["signature"]) == 128


def test_bulk_api_requires_csv_and_utf8(client, demo):
    login(client, "issuer@demo.local")
    assert client.post("/credentials/bulk", data={}).status_code == 400
    bad = client.post("/credentials/bulk", data={"students_csv": (BytesIO(b"\xff\xfe\x00bad"), "s.csv"), "document": (BytesIO(b"%PDF-1.4"), "d.pdf")}, content_type="multipart/form-data")
    assert bad.status_code == 400 and "UTF-8" in bad.get_json()["message"]


def test_unapproved_issuer_is_blocked_everywhere(client, app, demo):
    with app.app_context():
        profile = IssuerProfile.query.join(User, User.id == IssuerProfile.user_id).filter(User.email == "rival@rival.edu").one()
        profile.approval_status = "pending"; db.session.commit()
    login(client, "rival@rival.edu")
    assert client.post("/credentials", data={"title": "x", "programme": "y"}).status_code == 403
    assert client.post("/credentials/bulk", data={}).status_code == 403
    assert client.get("/university/workspace", headers=HTML).status_code == 403
    assert client.get("/university/credentials", headers=HTML).status_code == 403


def test_student_profile_api_cannot_link_non_students(client, app, demo):
    login(client, "issuer@demo.local")
    with app.app_context():
        admin_id = User.query.filter_by(email="admin@demo.local").one().id
    assert client.post("/university/api/students", json={"student_identifier": "Z-1", "user_id": admin_id}).status_code == 400


def test_template_api_is_institution_scoped(client, demo):
    login(client, "issuer@demo.local")
    assert client.post("/university/api/templates", json={"name": "B.Tech"}).status_code == 400
    assert client.post("/university/api/templates", json={"name": "B.Tech", "title": "Bachelor of Technology", "programme": "CSE"}).status_code == 201
    login(client, "rival@rival.edu")
    assert client.get("/university/api/templates").get_json()["templates"] == []


def test_openapi_document_is_served(client):
    assert client.get("/api/openapi.json").get_json()["openapi"].startswith("3.")


# ---------- CSRF (enabled outside tests) ----------

def test_browser_forms_require_csrf_token(monkeypatch):
    import config
    monkeypatch.setattr(config.TestConfig, "WTF_CSRF_ENABLED", True)
    app = create_app("test")
    with app.app_context():
        db.create_all()
        client = app.test_client()
        assert client.post("/auth/login", data={"email": "a@b.c", "password": "x"}, headers=HTML).status_code == 400
        db.drop_all()


# ---------- Signing keys ----------

def test_signing_key_from_environment_pem(app):
    key = Ed25519PrivateKey.generate()
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()
    app.config["SIGNING_PRIVATE_KEY"] = pem
    app.extensions.pop("acv_signing_key", None)
    from vault.chain.signing import public_key_info, public_key_raw
    with app.app_context():
        assert public_key_info()["public_key_hex"] == public_key_raw(key.public_key()).hex()
    app.extensions.pop("acv_signing_key", None)


def test_missing_signing_key_fails_loudly_when_autogeneration_is_off(app, tmp_path):
    app.config.update(SIGNING_PRIVATE_KEY="", SIGNING_KEY_FILE=tmp_path / "none.pem", SIGNING_KEY_AUTOGENERATE=False)
    app.extensions.pop("acv_signing_key", None)
    from vault.chain.signing import private_key
    with app.app_context(), pytest.raises(RuntimeError, match="generate-signing-key"):
        private_key()
    app.extensions.pop("acv_signing_key", None)


def test_generate_signing_key_cli_refuses_to_overwrite(app, tmp_path):
    app.config["SIGNING_KEY_FILE"] = tmp_path / "k.pem"
    runner = app.test_cli_runner()
    assert "Wrote" in runner.invoke(args=["generate-signing-key"]).output
    assert (tmp_path / "k.pem").stat().st_mode & 0o777 == 0o600
    assert runner.invoke(args=["generate-signing-key"]).exit_code != 0


# ---------- SMTP backend ----------

def test_smtp_backend_uses_tls_and_login(app, monkeypatch):
    sent = {}

    class FakeSMTP:
        def __init__(self, host, port, timeout): sent["host"] = (host, port)
        def __enter__(self): return self
        def __exit__(self, *exc): return False
        def starttls(self): sent["tls"] = True
        def login(self, user, password): sent["login"] = user
        def send_message(self, message): sent["to"] = message["To"]

    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    app.config.update(MAIL_BACKEND="smtp", MAIL_SERVER="smtp.example.edu", MAIL_PORT=587, MAIL_USE_TLS=True, MAIL_USERNAME="vault", MAIL_PASSWORD="pw")
    from vault.mail import send_email
    with app.app_context():
        send_email("someone@example.edu", "Hi", "Body")
    assert sent == {"host": ("smtp.example.edu", 587), "tls": True, "login": "vault", "to": "someone@example.edu"}


# ---------- Demo reset ----------

def test_demo_reset_rebuilds_demo_data(app, demo):
    runner = app.test_cli_runner()
    assert runner.invoke(args=["demo-reset"]).exit_code != 0  # needs --yes
    result = runner.invoke(args=["demo-reset", "--yes"])
    assert result.exit_code == 0, result.output
    with app.app_context():
        assert User.query.filter_by(email="rival@rival.edu").first() is None
        assert Credential.query.count() == 1 and StudentProfile.query.count() == 1


def test_cli_commands_build_absolute_links_without_a_request(app, tmp_path):
    """seed-demo and cron jobs send emails with links outside any request (regression: crashed on PostgreSQL CI)."""
    app.config.update(SERVER_NAME=None, PUBLIC_BASE_URL="https://vault.example.edu")
    assert app.test_cli_runner().invoke(args=["seed-demo"]).exit_code == 0
    with app.app_context():
        credential = Credential.query.one(); credential.expiry_date = __import__("datetime").date.today(); db.session.commit()
    assert "Sent 1" in app.test_cli_runner().invoke(args=["send-expiry-reminders"]).output
    assert "https://vault.example.edu/student/vault" in app.extensions["outbox"][-1].get_content()
