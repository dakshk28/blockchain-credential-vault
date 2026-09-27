from datetime import datetime, timedelta, timezone

from flask import current_app

from vault.audit.services import append_event
from vault.models import User


def _as_utc(moment):
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def authenticate(email, password):
    """Return (user, None) on success or (None, reason) where reason is "invalid" or "locked".

    Repeated failures lock the account for LOGIN_LOCKOUT_MINUTES. The caller commits the session.
    """
    email = (email or "").strip().lower()
    user = User.query.filter_by(email=email).first()
    now = datetime.now(timezone.utc)
    if user and user.locked_until and _as_utc(user.locked_until) > now:
        append_event("login_blocked_locked", user.id, {})
        return None, "locked"
    if not user or not user.is_active or not user.check_password(password or ""):
        append_event("login_failed", None, {"email": email[:320]})
        if user:
            user.failed_login_count = (user.failed_login_count or 0) + 1
            if user.failed_login_count >= current_app.config["LOGIN_LOCKOUT_THRESHOLD"]:
                user.locked_until = now + timedelta(minutes=current_app.config["LOGIN_LOCKOUT_MINUTES"])
                user.failed_login_count = 0
                append_event("account_locked", user.id, {})
        return None, "invalid"
    user.failed_login_count, user.locked_until = 0, None
    return user, None


# ---------- Password rules and signed email tokens ----------

from flask import url_for
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from vault.extensions import db
from vault.mail import queue_email


def password_error(password):
    if len(password or "") < 12 or not any(char.isdigit() for char in password):
        return "Use at least 12 characters, including a digit."
    return None


def _serializer(purpose):
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt=f"acv-{purpose}")


def make_reset_token(user):
    # Binding part of the password hash makes the token single-use: it dies once the password changes.
    return _serializer("reset").dumps({"uid": user.id, "h": user.password_hash[-16:]})


def user_from_reset_token(token):
    try:
        data = _serializer("reset").loads(token, max_age=current_app.config["PASSWORD_RESET_MAX_AGE"])
    except (BadSignature, SignatureExpired):
        return None
    user = db.session.get(User, data.get("uid"))
    return user if user and user.is_active and user.password_hash[-16:] == data.get("h") else None


def make_verify_token(user):
    return _serializer("verify").dumps({"uid": user.id, "email": user.email})


def user_from_verify_token(token):
    try:
        data = _serializer("verify").loads(token, max_age=current_app.config["EMAIL_VERIFY_MAX_AGE"])
    except (BadSignature, SignatureExpired):
        return None
    user = db.session.get(User, data.get("uid"))
    return user if user and user.email == data.get("email") else None


def queue_verification_email(user):
    link = url_for("auth.verify_email", token=make_verify_token(user), _external=True)
    queue_email(user.email, "Confirm your email address", f"Hello {user.full_name},\n\nConfirm your email address to receive credential notifications and submit claims:\n{link}\n\nThis link expires in 3 days.\n")


def queue_reset_email(user):
    link = url_for("auth.reset_password", token=make_reset_token(user), _external=True)
    queue_email(user.email, "Reset your password", f"Hello {user.full_name},\n\nUse this link within one hour to choose a new password:\n{link}\n\nIf you did not ask for this, ignore this email; your password is unchanged.\n")
