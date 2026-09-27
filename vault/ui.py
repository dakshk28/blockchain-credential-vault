"""Template helpers: role-aware navigation, unread counts, and date formatting."""
from flask import current_app, request
from flask_login import current_user

from vault.models import InstitutionVerificationRequest, Notification
from vault.timeutil import as_utc

# (section, label, endpoint, icon). Entries whose endpoint is not registered are skipped,
# so navigation grows automatically as features are added.
NAVIGATION = {
    "student": [
        ("Overview", "Dashboard", "auth.dashboard", "home"),
        ("My vault", "Certificates", "student.vault_page", "award"),
        ("My vault", "Share links", "student.shares_page", "link"),
        ("My vault", "Claim a credential", "student.claim_page", "user-plus"),
        ("My vault", "Notifications", "student.notifications_page", "bell"),
    ],
    "issuer": [
        ("Overview", "Dashboard", "auth.dashboard", "home"),
        ("University", "Workspace", "university.workspace", "building"),
        ("University", "Credentials", "university.credentials_page", "award"),
        ("University", "Bulk issuance", "university.bulk_page", "upload"),
        ("University", "Templates", "university.templates_page", "layers"),
        ("University", "Claim requests", "university.claims_page", "user-plus"),
        ("University", "Branding", "university.settings_page", "sun"),
    ],
    "admin": [
        ("Overview", "Dashboard", "auth.dashboard", "home"),
        ("Governance", "University reviews", "auth.university_reviews", "building"),
        ("Governance", "Users", "auth.users_page", "users"),
        ("Monitoring", "Integrity monitor", "integrity.monitor_page", "activity"),
        ("Monitoring", "Audit ledger", "audit.ledger_page", "blocks"),
        ("Monitoring", "Reports", "auth.reports", "chart"),
    ],
}
PUBLIC_LINKS = [("Verify a credential", "verification.portal", "search")]


def navigation_for(role):
    sections = []
    for section, label, endpoint, icon in NAVIGATION.get(role, []):
        if endpoint not in current_app.view_functions:
            continue
        if not sections or sections[-1][0] != section:
            sections.append((section, []))
        sections[-1][1].append({"label": label, "endpoint": endpoint, "icon": icon, "active": request.endpoint == endpoint})
    return sections


def register_ui(app):
    app.jinja_env.add_extension("jinja2.ext.do")

    @app.context_processor
    def ui_context():
        context = {"pending_claims": 0, "has_endpoint": lambda endpoint: endpoint in current_app.view_functions, "public_links": [link for link in PUBLIC_LINKS if link[1] in current_app.view_functions], "nav_sections": [], "unread_count": 0, "pending_reviews": 0}
        if current_user.is_authenticated:
            context["nav_sections"] = navigation_for(current_user.role)
            context["unread_count"] = Notification.query.filter_by(user_id=current_user.id, is_read=False).count()
            if current_user.role == "issuer":
                from vault.models import ClaimRequest, IssuerProfile
                profile = IssuerProfile.query.filter_by(user_id=current_user.id, approval_status="approved").first()
                if profile:
                    context["pending_claims"] = ClaimRequest.query.filter_by(institution_id=profile.institution_id, status="pending").count()
            if current_user.role == "admin":
                context["pending_reviews"] = InstitutionVerificationRequest.query.filter_by(status="pending").count()
        return context

    @app.template_filter("datetime")
    def format_datetime(value, fmt="%d %b %Y, %H:%M UTC"):
        return as_utc(value).strftime(fmt) if value else "—"

    @app.template_filter("date")
    def format_date(value, fmt="%d %b %Y"):
        return value.strftime(fmt) if value else "—"

    @app.template_filter("initials")
    def initials(name):
        parts = [part for part in (name or "?").split() if part]
        return "".join(part[0] for part in parts[:2]).upper() or "?"
