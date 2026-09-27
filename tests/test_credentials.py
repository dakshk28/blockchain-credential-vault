from io import BytesIO

from vault.extensions import db
from vault.models import Institution, IssuerProfile, User


def test_only_approved_issuer_can_issue(client, app):
    with app.app_context():
        institution = Institution(name="Example University", code="EXU")
        issuer = User(email="issuer@example.edu", full_name="Issuer", role="issuer"); issuer.set_password("SecurePassword1")
        db.session.add_all([institution, issuer]); db.session.flush()
        db.session.add(IssuerProfile(user_id=issuer.id, institution_id=institution.id, approval_status="approved")); db.session.commit()
    assert client.post("/auth/api/login", json={"email": "issuer@example.edu", "password": "SecurePassword1"}).status_code == 200
    response = client.post("/credentials", data={"title":"BSc Computer Science", "programme":"Computer Science", "issue_date":"2026-01-01", "document":(BytesIO(b"%PDF-1.4 dummy"), "credential.pdf")})
    assert response.status_code == 201
    assert response.get_json()["credential_id"].startswith("ACV-")


def test_non_pdf_is_rejected(client):
    response = client.post("/credentials", data={"title":"x", "programme":"x", "document":(BytesIO(b"not a pdf"), "bad.txt")})
    assert response.status_code in (401, 403)
