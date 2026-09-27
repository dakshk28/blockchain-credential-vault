from vault.audit.services import append_event, validate_chain
from vault.extensions import db
from vault.models import AuditEvent


def test_audit_chain_detects_tampering(app):
    with app.app_context():
        append_event("first", None, {"safe": True}); db.session.commit()
        append_event("second", None, {}); db.session.commit()
        assert validate_chain()["valid"] is True
        event = AuditEvent.query.first(); event.event_type = "altered"; db.session.commit()
        assert validate_chain() == {"valid": False, "invalid_event_id": event.id}
