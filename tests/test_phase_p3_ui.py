"""Phase P3 UI checks: every page renders for its role, the shell is role-aware, and the CSP stays strict."""
import re
from pathlib import Path

import pytest

from vault.demo import DEMO_PASSWORD

HTML = {"Accept": "text/html"}
TEMPLATES = Path(__file__).resolve().parent.parent / "vault" / "templates"

PAGES = {
    None: ["/", "/auth/login", "/auth/register", "/auth/forgot", "/university/register", "/university/pending", "/verify"],
    "student@demo.local": ["/auth/dashboard", "/student/vault", "/student/vault?status=expired", "/student/notifications", "/student/shares", "/student/claim"],
    "issuer@demo.local": ["/auth/dashboard", "/university/workspace", "/university/workspace?q=DEMO", "/university/templates", "/university/credentials", "/university/bulk", "/university/claims", "/university/settings"],
    "admin@demo.local": ["/auth/dashboard", "/auth/admin/universities", "/auth/admin/users", "/auth/admin/reports", "/integrity/monitor", "/audit/ledger"],
}


@pytest.fixture()
def demo(app):
    with app.app_context():
        app.test_cli_runner().invoke(args=["seed-demo"])


@pytest.mark.parametrize("email", list(PAGES))
def test_every_page_renders_with_the_design_system(client, demo, email):
    if email:
        assert client.post("/auth/api/login", json={"email": email, "password": DEMO_PASSWORD}).status_code == 200
    for path in PAGES[email]:
        response = client.get(path, headers=HTML)
        assert response.status_code == 200, path
        assert b"css/app.css" in response.data, path
        assert (b'class="sidebar"' in response.data) == (email is not None and path != "/"), path
        assert b"css/app.css" in response.data


def test_navigation_is_role_specific(client, demo):
    client.post("/auth/api/login", json={"email": "student@demo.local", "password": DEMO_PASSWORD})
    page = client.get("/auth/dashboard", headers=HTML).data
    assert b"Certificates" in page and b"Workspace" not in page and b"University reviews" not in page


def test_unread_badge_counts_notifications(client, demo, app):
    from vault.extensions import db
    from vault.models import Notification, User
    with app.app_context():
        student = User.query.filter_by(email="student@demo.local").one()
        db.session.add_all([Notification(user_id=student.id, event_type="x", message="m") for _ in range(2)]); db.session.commit()
    client.post("/auth/api/login", json={"email": "student@demo.local", "password": DEMO_PASSWORD})
    assert b'<span class="count">3</span>' in client.get("/student/vault", headers=HTML).data


def test_flash_messages_render_as_toasts(client, demo):
    client.post("/auth/api/login", json={"email": "issuer@demo.local", "password": DEMO_PASSWORD})
    page = client.post("/university/students", data={"student_identifier": "UI-001"}, headers=HTML, follow_redirects=True).data
    assert b'class="toast toast-success"' in page and b"Student UI-001 added" in page


def test_csp_forbids_inline_styles_and_scripts(client):
    policy = client.get("/").headers["Content-Security-Policy"]
    assert "'unsafe-inline'" not in policy and "script-src 'self'" in policy and "frame-ancestors 'none'" in policy


def test_templates_contain_no_inline_styles_or_scripts():
    offenders = []
    for template in TEMPLATES.rglob("*.html"):
        text = template.read_text()
        if re.search(r"\sstyle=|<style|<script(?![^>]*\ssrc=)|\son[a-z]+=", text):
            offenders.append(template.name)
    assert offenders == []


def test_static_assets_are_served(client):
    for asset in ("css/app.css", "js/app.js", "js/theme.js", "img/favicon.svg"):
        assert client.get(f"/static/{asset}").status_code == 200
