from vault.extensions import db
from vault.models import Institution, IssuerProfile, User


def _admin():
    user = User(email="admin@example.edu", full_name="Admin", role="admin")
    user.set_password("SecurePassword1")
    db.session.add(user); db.session.commit()
    return user


def test_registration_hashes_password(client, app):
    response = client.post("/auth/api/register", json={"email": "student@example.edu", "full_name": "Student", "password": "SecurePassword1"})
    assert response.status_code == 201
    with app.app_context():
        user = User.query.filter_by(email="student@example.edu").first()
        assert user.password_hash != "SecurePassword1"
        assert user.check_password("SecurePassword1")


def test_browser_signup_uses_form_route(client):
    response = client.get("/auth/register")
    token = response.data.decode().split('name="csrf_token" value="')[1].split('"')[0]
    response = client.post("/auth/register", data={"csrf_token": token, "email": "browser@example.edu", "full_name": "Browser Student", "password": "SecurePassword1"})
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/auth/dashboard")


def test_pending_issuer_cannot_self_approve(client, app):
    with app.app_context():
        institution = Institution(name="Example University", code="EXU")
        db.session.add(institution); db.session.commit(); institution_id = institution.id
    created = client.post("/auth/api/issuer-register", json={"email": "issuer@example.edu", "full_name": "Issuer", "password": "SecurePassword1", "institution_id": institution_id})
    assert created.status_code == 201
    assert client.post(f"/auth/api/issuers/{created.get_json()['id']}/approve").status_code == 401
    with app.app_context():
        profile = IssuerProfile.query.filter_by(user_id=created.get_json()["id"]).first()
        assert profile.approval_status == "pending"


def test_admin_can_approve_issuer(client, app):
    with app.app_context():
        institution = Institution(name="Example University", code="EXU")
        issuer = User(email="issuer@example.edu", full_name="Issuer", role="issuer"); issuer.set_password("SecurePassword1")
        db.session.add_all([institution, issuer]); db.session.flush()
        db.session.add(IssuerProfile(user_id=issuer.id, institution_id=institution.id)); issuer_id = issuer.id
        _admin(); db.session.commit()
    assert client.post("/auth/api/login", json={"email": "admin@example.edu", "password": "SecurePassword1"}).status_code == 200
    assert client.post(f"/auth/api/issuers/{issuer_id}/approve").status_code == 200
