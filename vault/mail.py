"""Outgoing email. Messages queued during a request are sent only after the database commit succeeds.

MAIL_BACKEND: "console" (log the message; development), "memory" (keep in app.extensions["outbox"]; tests),
or "smtp" (MAIL_SERVER, MAIL_PORT, MAIL_USERNAME, MAIL_PASSWORD, MAIL_USE_TLS, MAIL_DEFAULT_SENDER).
"""
import smtplib
from email.message import EmailMessage

from flask import current_app
from sqlalchemy import event

from vault.extensions import db


def queue_email(to, subject, body):
    db.session.info.setdefault("pending_emails", []).append((to, subject, body))


def send_email(to, subject, body):
    app = current_app._get_current_object()
    backend = app.config.get("MAIL_BACKEND", "console")
    message = EmailMessage()
    message["From"], message["To"], message["Subject"] = app.config["MAIL_DEFAULT_SENDER"], to, subject
    message.set_content(body)
    if backend == "memory":
        app.extensions.setdefault("outbox", []).append(message)
    elif backend == "smtp":
        with smtplib.SMTP(app.config["MAIL_SERVER"], app.config["MAIL_PORT"], timeout=20) as smtp:
            if app.config.get("MAIL_USE_TLS"):
                smtp.starttls()
            if app.config.get("MAIL_USERNAME"):
                smtp.login(app.config["MAIL_USERNAME"], app.config["MAIL_PASSWORD"])
            smtp.send_message(message)
    else:
        app.logger.info("EMAIL to %s | %s\n%s", to, subject, body)


def _flush_outbox(session):
    for to, subject, body in session.info.pop("pending_emails", []):
        try:
            send_email(to, subject, body)
        except Exception:  # email is best-effort; never break the request that triggered it
            current_app.logger.exception("Failed to send email to %s", to)


def _discard_outbox(session):
    session.info.pop("pending_emails", None)


def register_mail(app):
    # Listeners live on the shared scoped session, so register them once per process, not per app.
    if not event.contains(db.session, "after_commit", _flush_outbox):
        event.listen(db.session, "after_commit", _flush_outbox)
        event.listen(db.session, "after_rollback", _discard_outbox)
