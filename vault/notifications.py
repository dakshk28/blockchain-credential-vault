"""In-app notifications, mirrored to email when the recipient has a verified address."""
from flask import url_for

from vault.extensions import db
from vault.mail import queue_email
from vault.models import Notification, User

SUBJECTS = {
    "credential_issued": "A new credential is in your vault",
    "credential_linked": "A credential was added to your vault",
    "credential_revoked": "One of your credentials was revoked",
    "claim_approved": "Your credential claim was approved",
    "claim_rejected": "Your credential claim was not approved",
    "credential_expiring": "A credential is about to expire",
}


def notify(user_id, event_type, message):
    db.session.add(Notification(user_id=user_id, event_type=event_type, message=message))
    user = db.session.get(User, user_id)
    if user and user.email_verified:
        link = url_for("student.vault_page", _external=True)
        queue_email(user.email, SUBJECTS.get(event_type, "Academic Credential Vault update"), f"Hello {user.full_name},\n\n{message}\n\nOpen your vault: {link}\n")
