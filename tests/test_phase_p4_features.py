"""Phase P4: backend features exposed in the browser UI."""
from datetime import datetime, timedelta, timezone
from io import BytesIO

import pytest

from vault.demo import DEMO_PASSWORD, DEMO_PDF
from vault.extensions import db
from vault.models import AuditEvent, Credential, IssuerProfile, Notification, ShareLink, StudentProfile, User

HTML = {"Accept": "text/html"}


@pytest.fixture()
def demo(app):
    with app.app_context():
        app.test_cli_runner().invoke(args=["seed-demo"])
        return Credential.query.one().credential_id


def login(client, who):
    client.post("/auth/api/logout")
    assert client.post("/auth/api/login", json={"email": f"{who}@demo.local", "password": DEMO_PASSWORD}).status_code == 200


# ---------- Public verification portal ----------

def test_portal_redirects_id_lookup_case_insensitively(client, demo):
    response = client.get(f"/verify?id= {demo.lower()} ", headers=HTML)
    assert response.status_code == 302 and response.headers["Location"].endswith(f"/credential/{demo}")


def test_result_page_shows_verdict_institution_and_timeline(client, demo):
    page = client.get(f"/credential/{demo}", headers=HTML).data
    assert b"Valid credential" in page and b"Demo Institute of Technology" in page and b"timeline" in page


def test_unknown_credential_page_is_404(client):
    response = client.get("/credential/ACV-NOPE", headers=HTML)
    assert response.status_code == 404 and b"No credential found" in response.data


def test_document_comparison_page_reports_match_and_mismatch(client, demo):
    match = client.post(f"/credential/{demo}", data={"document": (BytesIO(DEMO_PDF), "c.pdf")}, headers=HTML).data
    assert b"matches the original exactly" in match
    mismatch = client.post(f"/credential/{demo}", data={"document": (BytesIO(DEMO_PDF + b"x"), "c.pdf")}, headers=HTML).data
    assert b"Document does not match" in mismatch


def test_qr_code_points_to_human_verification_page(client, demo, monkeypatch):
    captured = {}
    import vault.verification.routes as routes
    real = routes.qrcode.make
    monkeypatch.setattr(routes.qrcode, "make", lambda target: captured.setdefault("target", target) and real(target))
    assert client.get(f"/verify/{demo}/qr").status_code == 200
    assert captured["target"].endswith(f"/credential/{demo}")


# ---------- Issuer tools ----------

def test_issuer_credential_list_search_and_filter(client, demo):
    login(client, "issuer")
    assert client.get("/university/credentials", headers=HTML).data.count(b"data-credential-row") == 1
    assert client.get("/university/credentials?q=DEMO-2026-001", headers=HTML).data.count(b"data-credential-row") == 1
    assert client.get("/university/credentials?status=revoked", headers=HTML).data.count(b"data-credential-row") == 0


def test_issuer_revokes_from_ui_and_student_is_notified(client, app, demo):
    login(client, "issuer")
    client.post(f"/university/credentials/{demo}/revoke", data={"reason": ""}, headers=HTML)
    with app.app_context():
        assert Credential.query.filter_by(credential_id=demo).one().status == "active"
    client.post(f"/university/credentials/{demo}/revoke", data={"reason": "Issued in error"}, headers=HTML)
    with app.app_context():
        assert Credential.query.filter_by(credential_id=demo).one().status == "revoked"
        assert Notification.query.filter_by(event_type="credential_revoked").count() == 1
    public = client.get(f"/credential/{demo}", headers=HTML).data
    assert b"Credential revoked" in public and b"Issued in error" not in public  # reason stays private


def test_issuer_replaces_from_ui(client, app, demo):
    login(client, "issuer")
    response = client.post(f"/university/credentials/{demo}/replace", data={"title": "Bachelor of Technology (corrected)", "programme": "CSE", "document": (BytesIO(DEMO_PDF + b"v2"), "v2.pdf")}, headers=HTML)
    assert response.status_code == 302
    with app.app_context():
        old = Credential.query.filter_by(credential_id=demo).one()
        new = Credential.query.filter_by(replacement_of_id=old.id).one()
        assert old.status == "replaced" and new.student_profile_id == old.student_profile_id
        new_id = new.credential_id
    page = client.get(f"/credential/{demo}", headers=HTML).data
    assert b"Credential superseded" in page and new_id.encode() in page


def test_other_issuer_cannot_manage_credential(client, app, demo):
    with app.app_context():
        colleague = User(email="colleague@demo.local", full_name="Colleague", role="issuer"); colleague.set_password(DEMO_PASSWORD)
        db.session.add(colleague); db.session.flush()
        institution_id = Credential.query.one().institution_id
        db.session.add(IssuerProfile(user_id=colleague.id, institution_id=institution_id, approval_status="approved")); db.session.commit()
    login(client, "colleague")
    assert b"Only the issuer who created" in client.get(f"/university/credentials/{demo}", headers=HTML).data
    client.post(f"/university/credentials/{demo}/revoke", data={"reason": "x"}, headers=HTML)
    with app.app_context():
        assert Credential.query.filter_by(credential_id=demo).one().status == "active"


def test_bulk_page_issues_with_defaults_and_reports_rows(client, app, demo):
    login(client, "issuer")
    csv = b"student_identifier,title\nBK-1,\nBK-2,Custom\n,\n"
    page = client.post("/university/bulk", data={"title": "Default Title", "programme": "Default Programme", "students_csv": (BytesIO(csv), "s.csv"), "document": (BytesIO(DEMO_PDF), "b.pdf")}, headers=HTML).data
    assert page.count(b"data-bulk-row") == 2 and b"Row 4" in page
    with app.app_context():
        assert {c.title for c in Credential.query.filter(Credential.programme == "Default Programme")} == {"Default Title", "Custom"}
    assert client.get("/university/bulk/sample.csv").data.startswith(b"student_identifier")


# ---------- Student sharing ----------

def test_student_creates_uses_and_revokes_share_link(client, app, demo):
    login(client, "student")
    client.post("/student/shares", data={"credential_id": demo, "hours": "24"}, headers=HTML)
    with app.app_context():
        link = ShareLink.query.one(); token, link_id = link.token, link.id
    assert client.get("/student/shares", headers=HTML).data.count(b"data-share-row") == 1
    shared = client.get(f"/shared/{token}", headers=HTML)
    assert shared.status_code == 200 and b"Demo Student shared a valid credential" in shared.data and b"student@demo.local" not in shared.data
    client.post(f"/student/shares/{link_id}/revoke", headers=HTML)
    assert client.get(f"/shared/{token}", headers=HTML).status_code == 410


def test_share_link_rejects_foreign_credentials_and_bad_durations(client, app, demo):
    login(client, "student")
    client.post("/student/shares", data={"credential_id": "ACV-OTHER", "hours": "24"}, headers=HTML)
    client.post("/student/shares", data={"credential_id": demo, "hours": "99999"}, headers=HTML)
    with app.app_context():
        assert ShareLink.query.count() == 0


def test_expired_share_link_is_gone(client, app, demo):
    with app.app_context():
        credential = Credential.query.one(); student = User.query.filter_by(email="student@demo.local").one()
        db.session.add(ShareLink(token="old-token", credential_id=credential.id, student_user_id=student.id, expires_at=datetime.now(timezone.utc) - timedelta(minutes=1))); db.session.commit()
    assert client.get("/shared/old-token", headers=HTML).status_code == 410


# ---------- Admin console ----------

def test_integrity_monitor_detects_tampering(client, app, demo):
    login(client, "admin")
    client.post("/integrity/monitor/run", headers=HTML)
    assert b"Unchanged" in client.get("/integrity/monitor", headers=HTML).data
    with app.app_context():
        path = app.config["UPLOAD_DIRECTORY"] / Credential.query.one().storage_key
    path.write_bytes(b"%PDF-1.4 tampered")
    page = client.post("/integrity/monitor/run", headers=HTML, follow_redirects=True).data
    assert b"1 incident(s)" in page and b"badge-modified" in page


def test_integrity_cli_exit_code(app, demo):
    runner = app.test_cli_runner()
    assert runner.invoke(args=["integrity-scan"]).exit_code == 0
    with app.app_context():
        (app.config["UPLOAD_DIRECTORY"] / Credential.query.one().storage_key).unlink()
    result = runner.invoke(args=["integrity-scan"])
    assert result.exit_code == 1 and "missing" in result.output


def test_audit_ledger_validate_and_anchor(client, app, demo):
    login(client, "admin")
    assert b"data-event-row" in client.get("/audit/ledger", headers=HTML).data
    assert b"Audit chain is intact" in client.post("/audit/ledger/validate", headers=HTML, follow_redirects=True).data
    assert b"Anchored audit root" in client.post("/audit/ledger/anchor", headers=HTML, follow_redirects=True).data
    with app.app_context():
        event = AuditEvent.query.order_by(AuditEvent.id).first(); event.metadata_json = {"forged": True}; db.session.commit()
    assert b"Tampering detected" in client.post("/audit/ledger/validate", headers=HTML, follow_redirects=True).data
    assert b"cannot be anchored" in client.post("/audit/ledger/anchor", headers=HTML, follow_redirects=True).data


def test_new_pages_are_role_protected(client, demo):
    login(client, "student")
    for path in ("/university/credentials", "/university/bulk", "/integrity/monitor", "/audit/ledger"):
        assert client.get(path, headers=HTML).status_code == 403, path
    login(client, "issuer")
    assert client.get("/student/shares", headers=HTML).status_code == 403


def test_navigation_includes_new_pages(client, demo):
    login(client, "admin")
    page = client.get("/auth/dashboard", headers=HTML).data
    assert b"Integrity monitor" in page and b"Audit ledger" in page and b"Verify a credential" in page
