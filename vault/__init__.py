import os
import click

from flask import Flask, jsonify, redirect, render_template, request, url_for

from config import CONFIG_BY_NAME
from vault.extensions import csrf, db, limiter, login_manager, migrate


def create_app(config_name=None):
    app = Flask(__name__, instance_relative_config=True)
    selected = config_name or os.environ.get("FLASK_ENV", "development")
    config_class = CONFIG_BY_NAME.get(selected, CONFIG_BY_NAME["development"])
    app.config.from_object(config_class)
    app.config["ENV_NAME"] = selected if selected in CONFIG_BY_NAME else "development"
    if hasattr(config_class, "validate"):
        config_class.validate(app.config)
    app.config["UPLOAD_DIRECTORY"].mkdir(parents=True, exist_ok=True)
    db.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)
    limiter.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login_page"
    login_manager.session_protection = "strong"
    from vault import models  # noqa: F401
    from vault.models import User
    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))
    from vault.auth.routes import bp as auth_bp
    from vault.api import bp as api_bp
    from vault.audit.routes import bp as audit_bp
    from vault.credentials.routes import bp as credentials_bp
    from vault.integrity.routes import bp as integrity_bp
    from vault.student.routes import bp as student_bp
    from vault.university.routes import bp as university_bp
    from vault.verification.routes import bp as verification_bp
    for blueprint in (auth_bp, api_bp, credentials_bp, verification_bp, integrity_bp, audit_bp, student_bp, university_bp):
        app.register_blueprint(blueprint)
    @app.after_request
    def security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Content-Security-Policy"] = "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
        return response
    _register_errors(app)
    from vault.ui import register_ui
    register_ui(app)
    from vault.mail import register_mail
    register_mail(app)
    @app.cli.command("seed-demo")
    def seed_demo():
        """Create a demo administrator, verified university issuer, and linked student with one credential."""
        from vault.demo import seed_demo_data
        click.echo(seed_demo_data())

    @app.cli.command("generate-signing-key")
    @click.option("--force", is_flag=True, help="Overwrite an existing key (invalidates existing signatures).")
    def generate_signing_key(force):
        """Create the Ed25519 signing key file (SIGNING_KEY_FILE)."""
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        from vault.chain.signing import key_id, write_private_key
        path = app.config["SIGNING_KEY_FILE"]
        if path.exists() and not force:
            raise click.ClickException(f"{path} already exists; use --force to replace it.")
        key = Ed25519PrivateKey.generate(); write_private_key(key, path)
        click.echo(f"Wrote {path} (key id {key_id(key.public_key())}). Back it up securely.")

    @app.cli.command("anchor-credentials")
    def anchor_credentials():
        """Anchor all signed, not-yet-anchored credentials as one Merkle batch (schedule with cron)."""
        from vault.chain.services import anchor_pending_credentials
        record = anchor_pending_credentials()
        click.echo(f"Anchored {record.item_count} credential(s): root {record.audit_root} via {record.provider}" + (f", tx {record.tx_hash}" if record.tx_hash else "") if record else "Nothing to anchor.")

    @app.cli.command("upgrade-signatures")
    def upgrade_signatures():
        """Re-sign legacy HMAC credentials with Ed25519 (only those whose HMAC still verifies)."""
        from vault.chain.services import upgrade_legacy_signatures
        upgraded, skipped = upgrade_legacy_signatures()
        click.echo(f"Upgraded {upgraded} signature(s)." + (f" Skipped (HMAC invalid): {', '.join(skipped)}" if skipped else ""))

    @app.cli.command("send-expiry-reminders")
    @click.option("--days", default=30, show_default=True, help="Remind about credentials expiring within this many days.")
    def send_expiry_reminders(days):
        """Notify students whose active credentials expire soon (once per credential). Schedule daily."""
        from datetime import date, timedelta
        from vault.models import Credential, Notification
        from vault.notifications import notify
        sent = 0
        for credential in Credential.query.filter(Credential.status == "active", Credential.expiry_date.isnot(None), Credential.expiry_date >= date.today(), Credential.expiry_date <= date.today() + timedelta(days=days)).all():
            student = credential.student_profile
            marker = f"[{credential.credential_id}]"
            if not student or not student.user_id or Notification.query.filter(Notification.user_id == student.user_id, Notification.event_type == "credential_expiring", Notification.message.contains(marker)).first():
                continue
            notify(student.user_id, "credential_expiring", f"{credential.title} {marker} expires on {credential.expiry_date:%d %B %Y}. Contact {credential.institution.name} if you need a renewal.")
            sent += 1
        db.session.commit()
        click.echo(f"Sent {sent} expiry reminder(s).")

    @app.cli.command("demo-reset")
    @click.option("--yes", is_flag=True, help="Confirm that ALL data and stored documents will be erased.")
    def demo_reset(yes):
        """Erase every record and stored document, then reseed the demo (never in production)."""
        if app.config.get("ENV_NAME") == "production" or not (app.debug or app.testing):
            raise click.ClickException("demo-reset is only available in development or test.")
        if not yes:
            raise click.ClickException("This erases all data. Re-run with --yes to confirm.")
        db.session.remove(); db.drop_all(); db.create_all()
        upload_dir = app.config["UPLOAD_DIRECTORY"]
        for pattern in ("*.pdf", "logos/*"):
            for path in upload_dir.glob(pattern):
                path.unlink()
        from vault.demo import seed_demo_data
        click.echo("Database and stored documents cleared. " + seed_demo_data())

    @app.cli.command("integrity-scan")
    def integrity_scan():
        """Re-hash all active stored documents (schedule with cron). Exits 1 if any incident is found."""
        from vault.integrity.services import INCIDENT_RESULTS, run_all
        results = run_all()
        incidents = {cid: result for cid, result in results.items() if result in INCIDENT_RESULTS}
        click.echo(f"Scanned {len(results)} document(s); {len(incidents)} incident(s).")
        for cid, result in incidents.items():
            click.echo(f"  {cid}: {result}")
        raise SystemExit(1 if incidents else 0)
    return app


ERROR_MESSAGES = {
    400: ("bad_request", "Bad request", "The request was incomplete or invalid."),
    401: ("unauthorized", "Please log in", "You need to log in to view this page."),
    403: ("forbidden", "Access denied", "Your account does not have permission to do that."),
    404: ("not_found", "Page not found", "The requested resource was not found."),
    410: ("gone", "Link expired", "This link has expired or been revoked."),
    413: ("payload_too_large", "File too large", "The uploaded file is too large."),
    429: ("rate_limited", "Too many requests", "You have made too many requests. Please wait and try again."),
    500: ("server_error", "Something went wrong", "An unexpected error occurred. Please try again."),
}


def _wants_json():
    """API clients get JSON errors; browsers get HTML error pages."""
    if "/api/" in request.path or request.is_json:
        return True
    return not request.accept_mimetypes.accept_html


def _register_errors(app):
    def handler(error):
        status = getattr(error, "code", 500) or 500
        code, title, message = ERROR_MESSAGES.get(status, ERROR_MESSAGES[500])
        if status == 500:
            db.session.rollback()
        if _wants_json():
            return jsonify(error=code, message=message), status
        if status == 401:
            return redirect(url_for("auth.login_page"))
        return render_template("errors/error.html", status=status, title=title, message=message), status

    for status in ERROR_MESSAGES:
        app.register_error_handler(status, handler)
