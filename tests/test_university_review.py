from vault.extensions import db
from vault.models import Institution, InstitutionVerificationRequest, IssuerProfile, User


def test_admin_can_approve_university(client, app):
    with app.app_context():
        institution = Institution(name="Example University", code="EXU")
        representative = User(email="rep@example.edu", full_name="Rep", role="issuer"); representative.set_password("SecurePassword1")
        admin = User(email="admin@example.edu", full_name="Admin", role="admin"); admin.set_password("SecurePassword1")
        db.session.add_all([institution, representative, admin]); db.session.flush()
        db.session.add(IssuerProfile(user_id=representative.id, institution_id=institution.id, approval_status="pending"))
        review = InstitutionVerificationRequest(institution_id=institution.id, representative_user_id=representative.id, official_email_domain="example.edu")
        db.session.add(review); db.session.flush(); review_id, representative_id = review.id, representative.id; db.session.commit()
    assert client.post("/auth/api/login", json={"email": "admin@example.edu", "password": "SecurePassword1"}).status_code == 200
    page = client.get("/auth/admin/universities")
    token = page.data.decode().split('name="csrf_token" value="')[1].split('"')[0]
    assert client.post(f"/auth/admin/universities/{review_id}/review", data={"csrf_token": token, "decision": "approved", "review_note": "Official domain confirmed."}).status_code == 302
    with app.app_context():
        assert Institution.query.filter_by(code="EXU").first().is_verified is True
        assert IssuerProfile.query.filter_by(user_id=representative_id).first().approval_status == "approved"
