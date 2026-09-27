"""Ed25519 signatures over a canonical credential record.

The public key is published at /.well-known/acv-signing-key.json, so anyone can check a
credential's signature offline without trusting (or contacting) the vault.
"""
import hashlib
import json
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from flask import current_app

ALGORITHM = "Ed25519"
PAYLOAD_VERSION = 1


def credential_payload(credential):
    """The exact fields that are signed and anchored. Changing any of them invalidates the signature."""
    return {
        "v": PAYLOAD_VERSION,
        "credential_id": credential.credential_id,
        "institution_code": credential.institution.code,
        "title": credential.title,
        "programme": credential.programme,
        "issue_date": credential.issue_date.isoformat(),
        "expiry_date": credential.expiry_date.isoformat() if credential.expiry_date else None,
        "document_sha256": credential.document_sha256,
    }


def canonical(payload) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def _load_or_create(app):
    pem = app.config.get("SIGNING_PRIVATE_KEY")
    if pem:
        return serialization.load_pem_private_key(pem.encode(), password=None)
    path = Path(app.config["SIGNING_KEY_FILE"])
    if path.exists():
        return serialization.load_pem_private_key(path.read_bytes(), password=None)
    if not app.config.get("SIGNING_KEY_AUTOGENERATE", False):
        raise RuntimeError(f"No Ed25519 signing key: set SIGNING_PRIVATE_KEY or create {path} with `flask generate-signing-key`.")
    key = Ed25519PrivateKey.generate()
    write_private_key(key, path)
    return key


def write_private_key(key, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    path.chmod(0o600)


def private_key():
    app = current_app._get_current_object()
    if "acv_signing_key" not in app.extensions:
        app.extensions["acv_signing_key"] = _load_or_create(app)
    return app.extensions["acv_signing_key"]


def public_key_raw(public_key: Ed25519PublicKey) -> bytes:
    return public_key.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)


def key_id(public_key: Ed25519PublicKey) -> str:
    return hashlib.sha256(public_key_raw(public_key)).hexdigest()[:16]


def public_key_info():
    public = private_key().public_key()
    return {
        "algorithm": ALGORITHM,
        "key_id": key_id(public),
        "public_key_hex": public_key_raw(public).hex(),
        "public_key_pem": public.public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode(),
    }


def sign(payload) -> tuple[str, str]:
    """Return (signature_hex, key_id)."""
    key = private_key()
    return key.sign(canonical(payload)).hex(), key_id(key.public_key())


def verify(payload, signature_hex: str, public_key_hex: str) -> bool:
    try:
        Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_key_hex)).verify(bytes.fromhex(signature_hex), canonical(payload))
        return True
    except (InvalidSignature, ValueError):
        return False
