from datetime import date

from vault.extensions import db
from vault.models import Credential, Institution, StudentProfile, User


def test_student_sees_only_own_certificates(client, app):
    with app.app_context():
        institution = Institution(name="Example University", code="EXU")
        owner = User(email="owner@example.edu", full_name="Owner", role="student"); owner.set_password("SecurePassword1")
        other = User(email="other@example.edu", full_name="Other", role="student"); other.set_password("SecurePassword1")
        issuer = User(email="issuer@example.edu", full_name="Issuer", role="issuer"); issuer.set_password("SecurePassword1")
        db.session.add_all([institution, owner, other, issuer]); db.session.flush()
        owner_profile = StudentProfile(user_id=owner.id, institution_id=institution.id, student_identifier="STU-1")
        other_profile = StudentProfile(user_id=other.id, institution_id=institution.id, student_identifier="STU-2")
        db.session.add_all([owner_profile, other_profile]); db.session.flush()
        for public_id, profile in (("ACV-OWN", owner_profile), ("ACV-OTHER", other_profile)):
            db.session.add(Credential(credential_id=public_id, institution_id=institution.id, issued_by_user_id=issuer.id, student_profile_id=profile.id, title="Degree", programme="CS", issue_date=date.today(), document_sha256="a" * 64, storage_key=f"{public_id}.pdf", original_filename="degree.pdf"))
        db.session.commit()
    assert client.post("/auth/api/login", json={"email": "owner@example.edu", "password": "SecurePassword1"}).status_code == 200
    response = client.get("/student/certificates")
    assert response.status_code == 200
    assert [item["credential_id"] for item in response.get_json()["certificates"]] == ["ACV-OWN"]


def test_student_vault_browser_page_has_empty_state(client, app):
    with app.app_context():
        student = User(email="empty@example.edu", full_name="Empty Student", role="student")
        student.set_password("SecurePassword1")
        db.session.add(student); db.session.commit()
    assert client.post("/auth/api/login", json={"email": "empty@example.edu", "password": "SecurePassword1"}).status_code == 200
    response = client.get("/student/vault")
    assert response.status_code == 200
    assert b"No certificates yet" in response.data
