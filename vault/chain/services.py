"""Signing, batching, anchoring, and verification of credential records."""
import hashlib

from flask import current_app

from vault.audit.services import append_event, validate_chain
from vault.chain import merkle, signing
from vault.chain.providers import AnchorError, get_provider
from vault.credentials.services import sign_credential
from vault.extensions import db
from vault.models import AuditAnchor, AuditEvent, Credential, CredentialAnchorProof, CredentialSignature


def signature_status(credential):
    """valid | invalid | legacy-valid | legacy-invalid | missing, checked against the *current* database record."""
    record = credential.signature_record
    if not record:
        return {"state": "missing"}
    if record.algorithm == signing.ALGORITHM:
        info = signing.public_key_info()
        if record.key_id != info["key_id"]:
            return {"state": "unknown-key", "algorithm": record.algorithm, "key_id": record.key_id}
        valid = signing.verify(signing.credential_payload(credential), record.signature, info["public_key_hex"])
        return {"state": "valid" if valid else "invalid", "algorithm": record.algorithm, "key_id": record.key_id}
    expected = sign_credential(credential.credential_id, credential.document_sha256, current_app.config["SIGNING_SECRET"])
    return {"state": "legacy-valid" if expected == record.signature else "legacy-invalid", "algorithm": record.algorithm, "key_id": None}


def upgrade_legacy_signatures():
    """Re-sign HMAC-only credentials with Ed25519 after confirming their HMAC is still valid."""
    upgraded, skipped = 0, []
    for record in CredentialSignature.query.filter(CredentialSignature.algorithm != signing.ALGORITHM).all():
        credential = db.session.get(Credential, record.credential_id)
        if signature_status(credential)["state"] != "legacy-valid":
            skipped.append(credential.credential_id)
            continue
        record.signature, record.key_id = signing.sign(signing.credential_payload(credential))
        record.algorithm = signing.ALGORITHM
        upgraded += 1
    if upgraded:
        append_event("signatures_upgraded", None, {"count": upgraded})
    db.session.commit()
    return upgraded, skipped


def credential_leaf(credential):
    return merkle.leaf_hash(signing.canonical(signing.credential_payload(credential)))


def anchor_pending_credentials(actor_id=None):
    """Batch every signed, not-yet-anchored credential into one Merkle tree and anchor its root.

    Returns the AuditAnchor, or None when nothing is pending. Raises AnchorError if the provider
    fails; in that case nothing is written, so the batch can simply be retried.
    """
    pending = (Credential.query.join(CredentialSignature, CredentialSignature.credential_id == Credential.id)
               .outerjoin(CredentialAnchorProof, CredentialAnchorProof.credential_id == Credential.id)
               .filter(CredentialAnchorProof.id.is_(None), CredentialSignature.algorithm == signing.ALGORITHM)
               .order_by(Credential.id).all())
    pending = [credential for credential in pending if signature_status(credential)["state"] == "valid"]
    if not pending:
        return None
    leaves = [credential_leaf(credential) for credential in pending]
    root, proofs = merkle.build(leaves)
    receipt = get_provider().anchor(root, "credentials", len(pending))
    anchor = AuditAnchor(audit_root=root, kind="credentials", item_count=len(pending), provider=receipt.provider, network=receipt.network,
                         tx_hash=receipt.tx_hash, block_number=receipt.block_number, explorer_url=receipt.explorer_url)
    db.session.add(anchor); db.session.flush()
    for credential, leaf, proof in zip(pending, leaves, proofs):
        db.session.add(CredentialAnchorProof(credential_id=credential.id, anchor_id=anchor.id, leaf_hash=leaf, proof=proof))
    append_event("credentials_anchored", actor_id, {"anchor_id": anchor.id, "root": root, "count": len(pending), "provider": receipt.provider, "tx_hash": receipt.tx_hash})
    db.session.commit()
    return anchor


def anchor_audit_head(actor_id=None):
    """Anchor the latest audit-chain hash. Returns None if the chain is invalid (tampered)."""
    if not validate_chain().get("valid"):
        return None
    last = AuditEvent.query.order_by(AuditEvent.id.desc()).first()
    root = last.event_hash if last else hashlib.sha256(b"empty-audit-chain").hexdigest()
    receipt = get_provider().anchor(root, "audit", AuditEvent.query.count())
    anchor = AuditAnchor(audit_root=root, kind="audit", item_count=AuditEvent.query.count(), provider=receipt.provider, network=receipt.network,
                         tx_hash=receipt.tx_hash, block_number=receipt.block_number, explorer_url=receipt.explorer_url)
    db.session.add(anchor); db.session.commit()
    return anchor


def anchor_status(credential):
    """anchored (proof checks out against the current record) | altered | pending."""
    proof = credential.anchor_proof
    if not proof:
        return {"state": "pending"}
    current_leaf = credential_leaf(credential)
    included = current_leaf == proof.leaf_hash and merkle.verify(proof.leaf_hash, proof.proof, proof.anchor.audit_root)
    return {"state": "anchored" if included else "altered", "anchor": proof.anchor, "leaf": proof.leaf_hash, "steps": len(proof.proof)}


def proof_bundle(credential):
    """Everything a third party needs to verify this credential without trusting the vault."""
    signature = credential.signature_record
    proof = credential.anchor_proof
    bundle = {
        "format": "acv-credential-proof/1",
        "payload": signing.credential_payload(credential),
        "signature": {"algorithm": signature.algorithm, "key_id": signature.key_id, "value": signature.signature} if signature else None,
        "public_key": {key: value for key, value in signing.public_key_info().items() if key != "public_key_pem"},
        "merkle": None,
        "anchor": None,
    }
    if proof:
        anchor = proof.anchor
        bundle["merkle"] = {"leaf": proof.leaf_hash, "proof": proof.proof, "root": anchor.audit_root, "leaf_rule": "sha256(0x00 || canonical_json(payload))", "node_rule": "sha256(0x01 || left || right)"}
        bundle["anchor"] = {"provider": anchor.provider, "network": anchor.network, "tx_hash": anchor.tx_hash, "block_number": anchor.block_number,
                            "explorer_url": anchor.explorer_url, "anchored_at": anchor.anchored_at.isoformat() if anchor.anchored_at else None,
                            "contract_address": current_app.config.get("ETH_CONTRACT_ADDRESS") or None if anchor.provider == "ethereum" else None}
    return bundle


__all__ = ["AnchorError", "anchor_audit_head", "anchor_pending_credentials", "anchor_status", "proof_bundle", "signature_status", "upgrade_legacy_signatures"]
