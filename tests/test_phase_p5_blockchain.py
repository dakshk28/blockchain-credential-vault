"""Phase P5: Ed25519 signatures, Merkle batching, and anchoring (local and a real in-process EVM chain)."""
import importlib.util
import json
import sys
from datetime import date
from io import BytesIO
from pathlib import Path

import pytest

from vault.chain import merkle, signing
from vault.chain.providers import AnchorError, EthereumProvider
from vault.chain.services import anchor_pending_credentials, anchor_status, proof_bundle, signature_status, upgrade_legacy_signatures
from vault.credentials.services import sign_credential
from vault.demo import DEMO_PASSWORD, DEMO_PDF
from vault.extensions import db
from vault.models import AuditAnchor, Credential, CredentialAnchorProof, CredentialSignature, IssuerProfile, User

HTML = {"Accept": "text/html"}
ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture()
def demo(app):
    with app.app_context():
        app.test_cli_runner().invoke(args=["seed-demo"])
        return Credential.query.one().credential_id


def issue_more(app, client, count):
    client.post("/auth/api/login", json={"email": "issuer@demo.local", "password": DEMO_PASSWORD})
    ids = []
    for index in range(count):
        response = client.post("/credentials", data={"title": f"Certificate {index}", "programme": "CS", "document": (BytesIO(DEMO_PDF + bytes([index])), "c.pdf")})
        ids.append(response.get_json()["credential_id"])
    client.post("/auth/api/logout")
    return ids


# ---------- Merkle tree ----------

@pytest.mark.parametrize("size", [1, 2, 3, 4, 5, 7, 8, 9, 16, 33])
def test_every_leaf_proves_inclusion(size):
    leaves = [merkle.leaf_hash(f"item-{i}".encode()) for i in range(size)]
    root, proofs = merkle.build(leaves)
    assert all(merkle.verify(leaf, proof, root) for leaf, proof in zip(leaves, proofs))


def test_tampered_leaf_or_proof_fails():
    leaves = [merkle.leaf_hash(f"item-{i}".encode()) for i in range(6)]
    root, proofs = merkle.build(leaves)
    assert not merkle.verify(merkle.leaf_hash(b"forged"), proofs[2], root)
    bad = [dict(step) for step in proofs[2]]; bad[0]["side"] = "left" if bad[0]["side"] == "right" else "right"
    assert not merkle.verify(leaves[2], bad, root)


def test_leaf_and_node_hashes_are_domain_separated():
    a, b = merkle.leaf_hash(b"a"), merkle.leaf_hash(b"b")
    assert merkle.leaf_hash(bytes.fromhex(a) + bytes.fromhex(b)) != merkle.node_hash(a, b)


# ---------- Ed25519 signatures ----------

def test_new_credentials_are_ed25519_signed_and_verifiable(client, app, demo):
    with app.app_context():
        credential = Credential.query.one()
        assert credential.signature_record.algorithm == "Ed25519"
        assert signature_status(credential)["state"] == "valid"
    key = client.get("/.well-known/acv-signing-key.json").get_json()
    assert key["algorithm"] == "Ed25519" and len(key["public_key_hex"]) == 64


def test_database_tampering_breaks_signature_and_is_shown_publicly(client, app, demo):
    with app.app_context():
        credential = Credential.query.one(); credential.title = "Doctor of Philosophy"; db.session.commit()
        assert signature_status(credential)["state"] == "invalid"
    page = client.get(f"/credential/{demo}", headers=HTML).data
    assert b"Record integrity failure" in page


def test_legacy_hmac_signatures_are_upgraded_only_when_valid(app, demo):
    with app.app_context():
        credential = Credential.query.one(); record = credential.signature_record
        record.algorithm, record.key_id = "HMAC-SHA256", None
        record.signature = sign_credential(credential.credential_id, credential.document_sha256, app.config["SIGNING_SECRET"])
        db.session.commit()
        assert signature_status(credential)["state"] == "legacy-valid"
        assert upgrade_legacy_signatures() == (1, [])
        assert signature_status(db.session.get(Credential, credential.id))["state"] == "valid"


# ---------- Local anchoring ----------

def test_local_anchoring_batches_pending_credentials(client, app, demo):
    issue_more(app, client, 4)
    with app.app_context():
        anchor = anchor_pending_credentials()
        assert anchor.kind == "credentials" and anchor.item_count == 5 and anchor.provider == "local"
        assert all(anchor_status(c)["state"] == "anchored" for c in Credential.query.all())
        assert anchor_pending_credentials() is None  # nothing left
    new_id = issue_more(app, client, 1)[0]
    with app.app_context():
        assert anchor_status(Credential.query.filter_by(credential_id=new_id).one())["state"] == "pending"


def test_tampering_after_anchoring_is_detected(app, demo):
    with app.app_context():
        anchor_pending_credentials()
        credential = Credential.query.one()
        credential.programme = "Forged Programme"
        record = credential.signature_record  # attacker even re-signs, but cannot change the anchored leaf
        record.signature, record.key_id = signing.sign(signing.credential_payload(credential))
        db.session.commit()
        assert signature_status(credential)["state"] == "valid"
        assert anchor_status(credential)["state"] == "altered"


def test_admin_anchor_credentials_button_and_cli(client, app, demo):
    client.post("/auth/api/login", json={"email": "admin@demo.local", "password": DEMO_PASSWORD})
    page = client.post("/audit/ledger/anchor-credentials", headers=HTML, follow_redirects=True).data
    assert b"Anchored 1 credential(s)" in page and b"data-anchor-row" in page
    assert "Nothing to anchor" in app.test_cli_runner().invoke(args=["anchor-credentials"]).output


def test_public_page_shows_signature_and_anchor(client, app, demo):
    with app.app_context():
        anchor_pending_credentials()
    page = client.get(f"/credential/{demo}", headers=HTML).data
    assert b"Ed25519 signature verified" in page and b"Merkle proof" in page


# ---------- Offline verification ----------

def load_verifier():
    spec = importlib.util.spec_from_file_location("verify_proof", ROOT / "blockchain" / "verify_proof.py")
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def test_offline_verifier_accepts_genuine_bundle_and_rejects_forgery(client, app, demo, tmp_path, capsys):
    with app.app_context():
        anchor_pending_credentials()
    bundle = client.get(f"/credential/{demo}/proof.json").get_json()
    genuine, pdf = tmp_path / "proof.json", tmp_path / "cert.pdf"
    genuine.write_text(json.dumps(bundle)); pdf.write_bytes(DEMO_PDF)
    verifier = load_verifier()
    assert verifier.main([str(genuine), str(pdf)]) == 0
    forged = dict(bundle, payload=dict(bundle["payload"], title="Master of Science"))
    (tmp_path / "forged.json").write_text(json.dumps(forged))
    assert verifier.main([str(tmp_path / "forged.json")]) == 1
    (tmp_path / "other.pdf").write_bytes(DEMO_PDF + b"edited")
    assert verifier.main([str(genuine), str(tmp_path / "other.pdf")]) == 1
    assert "NOT VERIFIED" in capsys.readouterr().out


# ---------- Real EVM chain (in-process eth-tester) ----------

@pytest.fixture()
def chain(app):
    """Deploy the compiled CredentialAnchor contract to a fresh in-process chain and plug it in."""
    pytest.importorskip("web3"); pytest.importorskip("eth_tester")
    from web3 import EthereumTesterProvider, Web3
    sys.path.insert(0, str(ROOT / "blockchain"))
    from deploy import deploy
    w3 = Web3(EthereumTesterProvider())
    address, _ = deploy(w3)
    provider = EthereumProvider(w3, address, network="eth-tester", explorer_tx_url="https://explorer.example/tx/{tx}")
    app.extensions["acv_anchor_provider"] = provider
    yield provider
    app.extensions.pop("acv_anchor_provider", None)


def test_credentials_are_anchored_on_chain(client, app, demo, chain):
    issue_more(app, client, 2)
    with app.app_context():
        anchor = anchor_pending_credentials()
        assert anchor.provider == "ethereum" and anchor.tx_hash.startswith("0x") and anchor.block_number >= 1
        assert anchor.explorer_url == f"https://explorer.example/tx/{anchor.tx_hash}"
        assert chain.is_anchored(anchor.audit_root) and chain.anchored_at(anchor.audit_root) > 0
        assert not chain.is_anchored("11" * 32)
    page = client.get(f"/credential/{demo}", headers=HTML).data
    assert b"View transaction" in page and b"on-chain" in page


def test_contract_rejects_duplicate_roots_and_nothing_is_saved(app, demo, chain):
    with app.app_context():
        root = "ab" * 32
        chain.anchor(root, "audit", 1)
        with pytest.raises(AnchorError):
            chain.anchor(root, "audit", 1)


def test_only_contract_owner_can_anchor(chain):
    other = chain.w3.eth.accounts[1]
    with pytest.raises(Exception):
        chain.contract.functions.anchor(bytes.fromhex("cd" * 32), "audit", 1).transact({"from": other})


def test_provider_failure_rolls_back_the_batch(client, app, demo, chain, monkeypatch):
    monkeypatch.setattr(chain, "anchor", lambda *a: (_ for _ in ()).throw(AnchorError("RPC unreachable")))
    client.post("/auth/api/login", json={"email": "admin@demo.local", "password": DEMO_PASSWORD})
    page = client.post("/audit/ledger/anchor-credentials", headers=HTML, follow_redirects=True).data
    assert b"RPC unreachable" in page
    with app.app_context():
        assert AuditAnchor.query.count() == 0 and CredentialAnchorProof.query.count() == 0


def test_audit_head_anchored_on_chain(client, app, demo, chain):
    client.post("/auth/api/login", json={"email": "admin@demo.local", "password": DEMO_PASSWORD})
    response = client.post("/audit/anchor")
    assert response.status_code == 201 and response.get_json()["tx_hash"].startswith("0x")
    with app.app_context():
        assert chain.is_anchored(AuditAnchor.query.one().audit_root)
