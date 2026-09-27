import hashlib
import json
from datetime import datetime, timezone

from sqlalchemy import text

from vault.extensions import db
from vault.timeutil import as_utc
from vault.models import AuditEvent


def _hash(event_type, actor_id, metadata, created_at, previous_hash):
    # Hash the instant in UTC: PostgreSQL returns timestamptz in the session time zone (e.g. +05:30), and
    # SQLite returns naive values, but the same moment must always produce the same hash.
    created_at = as_utc(created_at)
    payload = {"actor_user_id": actor_id, "created_at": created_at.isoformat(), "event_type": event_type, "metadata": metadata, "previous_event_hash": previous_hash}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


AUDIT_CHAIN_LOCK_ID = 724001


def append_event(event_type, actor_id, metadata):
    # Serialise writers so two concurrent events cannot chain to the same previous hash.
    # PostgreSQL: a transaction-scoped advisory lock; SQLite already allows only one writer.
    if db.session.get_bind().dialect.name == "postgresql":
        db.session.execute(text("SELECT pg_advisory_xact_lock(:lock_id)"), {"lock_id": AUDIT_CHAIN_LOCK_ID})
    previous = AuditEvent.query.order_by(AuditEvent.id.desc()).first()
    previous_hash = previous.event_hash if previous else None
    created_at = datetime.now(timezone.utc)
    digest = _hash(event_type, actor_id, metadata, created_at, previous_hash)
    db.session.add(AuditEvent(event_type=event_type, actor_user_id=actor_id, metadata_json=metadata, created_at=created_at, previous_event_hash=previous_hash, event_hash=digest))


def validate_chain():
    previous_hash = None
    for event in AuditEvent.query.order_by(AuditEvent.id).all():
        expected = _hash(event.event_type, event.actor_user_id, event.metadata_json, event.created_at, previous_hash)
        if event.previous_event_hash != previous_hash or event.event_hash != expected:
            return {"valid": False, "invalid_event_id": event.id}
        previous_hash = event.event_hash
    return {"valid": True, "events": AuditEvent.query.count()}
