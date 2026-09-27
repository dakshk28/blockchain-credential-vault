from pathlib import Path

from vault.extensions import db
from vault.integrity.services import check_credential
from vault.models import Credential, Institution, User


def test_integrity_detects_modified_file(app):
    with app.app_context():
        institution = Institution(name="Example", code="EX")
        user = User(email="issuer@ex.edu", full_name="Issuer", role="issuer"); user.set_password("SecurePassword1")
        db.session.add_all([institution, user]); db.session.flush()
        path = app.config["UPLOAD_DIRECTORY"] / "test.pdf"; path.write_bytes(b"original")
        credential = Credential(credential_id="ACV-TEST", institution_id=institution.id, issued_by_user_id=user.id, title="Test", programme="Test", issue_date=__import__("datetime").date.today(), document_sha256=__import__("hashlib").sha256(b"original").hexdigest(), storage_key="test.pdf", original_filename="test.pdf")
        db.session.add(credential); db.session.commit()
        assert check_credential(credential) == "unchanged"
        path.write_bytes(b"changed")
        assert check_credential(credential) == "modified"
