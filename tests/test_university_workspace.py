from io import BytesIO

from vault.extensions import db
from vault.models import Institution, IssuerProfile, StudentProfile, User, Credential


def test_approved_university_can_create_and_list_scoped_students(client, app):
    with app.app_context():
        institution = Institution(name="North", code="NORTH", is_verified=True)
        issuer = User(email="north@example.edu", full_name="Issuer", role="issuer"); issuer.set_password("SecurePassword1")
        db.session.add_all([institution, issuer]); db.session.flush()
        db.session.add(IssuerProfile(user_id=issuer.id, institution_id=institution.id, approval_status="approved")); db.session.commit()
    client.post("/auth/api/login", json={"email": "north@example.edu", "password": "SecurePassword1"})
    created = client.post("/university/api/students", json={"student_identifier": "N-001"})
    assert created.status_code == 201
    assert client.get("/university/api/students?q=N-00").get_json()["students"][0]["student_identifier"] == "N-001"
    assert client.get("/university/workspace").status_code == 200


def test_university_issuance_assigns_credential_to_student(client, app):
    with app.app_context():
        institution = Institution(name="South", code="SOUTH", is_verified=True)
        issuer = User(email="south@example.edu", full_name="Issuer", role="issuer"); issuer.set_password("SecurePassword1")
        db.session.add_all([institution, issuer]); db.session.flush()
        db.session.add(IssuerProfile(user_id=issuer.id, institution_id=institution.id, approval_status="approved")); db.session.flush()
        student = StudentProfile(institution_id=institution.id, student_identifier="S-001"); db.session.add(student); db.session.commit(); student_id = student.id
    client.post("/auth/api/login", json={"email": "south@example.edu", "password": "SecurePassword1"})
    response = client.post("/credentials", data={"student_profile_id": str(student_id), "title": "BSc", "programme": "CS", "document": (BytesIO(b"%PDF-1.4 demo"), "degree.pdf")})
    assert response.status_code == 201
    with app.app_context():
        credential = Credential.query.one()
        assert credential.student_profile_id == student_id


def test_university_cannot_issue_to_another_institution(client, app):
    with app.app_context():
        first = Institution(name="First", code="FIRST", is_verified=True); second = Institution(name="Second", code="SECOND", is_verified=True)
        issuer = User(email="first@example.edu", full_name="Issuer", role="issuer"); issuer.set_password("SecurePassword1")
        db.session.add_all([first, second, issuer]); db.session.flush()
        db.session.add(IssuerProfile(user_id=issuer.id, institution_id=first.id, approval_status="approved")); other = StudentProfile(institution_id=second.id, student_identifier="X-001"); db.session.add(other); db.session.commit(); other_id = other.id
    client.post("/auth/api/login", json={"email": "first@example.edu", "password": "SecurePassword1"})
    response = client.post("/credentials", data={"student_profile_id": str(other_id), "title": "BSc", "programme": "CS", "document": (BytesIO(b"%PDF-1.4 demo"), "degree.pdf")})
    assert response.status_code == 404
