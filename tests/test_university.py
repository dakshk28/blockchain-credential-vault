from vault.extensions import db
from vault.models import Institution, InstitutionVerificationRequest, IssuerProfile, User


def test_university_registration_creates_pending_institution(client, app):
    page = client.get("/university/register")
    token = page.data.decode().split('name="csrf_token" value="')[1].split('"')[0]
    response = client.post("/university/register", data={"csrf_token": token, "institution_name": "Example University", "institution_code": "EXU", "full_name": "University Rep", "email": "rep@example.edu", "password": "SecurePassword1"})
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/university/pending")
    with app.app_context():
        institution = Institution.query.filter_by(code="EXU").first()
        representative = User.query.filter_by(email="rep@example.edu").first()
        assert institution.is_verified is False
        assert IssuerProfile.query.filter_by(user_id=representative.id).first().approval_status == "pending"
        assert InstitutionVerificationRequest.query.filter_by(institution_id=institution.id).first().status == "pending"
