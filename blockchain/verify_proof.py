#!/usr/bin/env python3
"""Independently verify an Academic Credential Vault proof bundle.

Deliberately standalone (it does not import the vault's code), so an employer or examiner can
check a credential without trusting the vault operator:

    python blockchain/verify_proof.py ACV-2026-XXXX-proof.json [certificate.pdf]
        [--public-key HEX] [--rpc URL --contract 0xADDRESS]

Checks:
  1. the PDF (if given) hashes to the document_sha256 inside the signed payload;
  2. the Ed25519 signature over the canonical payload is valid;
  3. the Merkle proof leads from the payload's leaf to the anchored root;
  4. (with --rpc/--contract) the root is recorded in the CredentialAnchor smart contract.
Pass --public-key with the key obtained from a trusted channel (e.g. the institution's website);
otherwise the key embedded in the bundle is used.
Requires: cryptography (and web3 for step 4).
"""
import argparse
import hashlib
import json
import sys


def canonical(payload):
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def merkle_root(leaf, proof):
    current = bytes.fromhex(leaf)
    for step in proof:
        sibling = bytes.fromhex(step["hash"])
        pair = sibling + current if step["side"] == "left" else current + sibling
        current = hashlib.sha256(b"\x01" + pair).digest()
    return current.hex()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("bundle"); parser.add_argument("pdf", nargs="?")
    parser.add_argument("--public-key", help="trusted Ed25519 public key (hex); defaults to the key in the bundle")
    parser.add_argument("--rpc", help="EVM JSON-RPC URL for the on-chain check"); parser.add_argument("--contract", help="CredentialAnchor address")
    args = parser.parse_args(argv)

    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    bundle = json.load(open(args.bundle))
    payload, results = bundle["payload"], []

    def report(name, ok, detail=""):
        results.append(ok)
        print(f"[{'PASS' if ok else 'FAIL'}] {name}{': ' + detail if detail else ''}")

    print(f"Credential {payload['credential_id']} — {payload['title']} ({payload['institution_code']})")
    if args.pdf:
        digest = hashlib.sha256(open(args.pdf, "rb").read()).hexdigest()
        report("Document matches signed fingerprint", digest == payload["document_sha256"], digest)

    signature = bundle.get("signature") or {}
    if signature.get("algorithm") == "Ed25519":
        key_hex = args.public_key or bundle["public_key"]["public_key_hex"]
        try:
            Ed25519PublicKey.from_public_bytes(bytes.fromhex(key_hex)).verify(bytes.fromhex(signature["value"]), canonical(payload))
            report("Ed25519 signature", True, f"key {hashlib.sha256(bytes.fromhex(key_hex)).hexdigest()[:16]}")
        except (InvalidSignature, ValueError):
            report("Ed25519 signature", False, "does not match payload")
    else:
        report("Ed25519 signature", False, f"unsupported or missing ({signature.get('algorithm')})")

    merkle = bundle.get("merkle")
    if merkle:
        leaf = hashlib.sha256(b"\x00" + canonical(payload)).hexdigest()
        report("Merkle leaf derived from payload", leaf == merkle["leaf"])
        root = merkle_root(leaf, merkle["proof"])
        report("Merkle proof reaches anchored root", root == merkle["root"], root)
        anchor = bundle.get("anchor") or {}
        print(f"       anchor: {anchor.get('network')} tx={anchor.get('tx_hash')} block={anchor.get('block_number')}")
        if args.rpc:
            from web3 import Web3
            w3 = Web3(Web3.HTTPProvider(args.rpc))
            address = args.contract or anchor.get("contract_address")
            abi = [{"name": "anchoredAt", "type": "function", "stateMutability": "view", "inputs": [{"name": "", "type": "bytes32"}], "outputs": [{"name": "", "type": "uint256"}]}]
            timestamp = w3.eth.contract(address=Web3.to_checksum_address(address), abi=abi).functions.anchoredAt(bytes.fromhex(merkle["root"])).call()
            report("Root recorded on-chain", timestamp > 0, f"contract {address}, timestamp {timestamp}")
    else:
        print("[SKIP] Not anchored yet")

    ok = all(results)
    print("\nRESULT:", "VERIFIED" if ok else "NOT VERIFIED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
