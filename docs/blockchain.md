# Blockchain layer

The vault keeps documents and personal data **off-chain**. It publishes only 32-byte hashes, so anyone can prove a credential record has not changed since issuance without trusting the vault operator.

```text
issue ─► canonical JSON payload ─► Ed25519 signature (platform key)
                          │
                          └─► Merkle leaf = sha256(0x00 ‖ payload)
batch of leaves ─► Merkle root ─► CredentialAnchor.anchor(root) on an EVM chain
verifier ─► signature ✓ + Merkle proof ✓ + root on-chain ✓ (+ PDF hash ✓)
```

| Layer | What it proves | Where |
| --- | --- | --- |
| SHA-256 document fingerprint | The PDF is byte-for-byte the issued one. | `credential.document_sha256` |
| Ed25519 signature | The platform issued exactly these fields (title, programme, dates, fingerprint). | `vault/chain/signing.py`, key published at `/.well-known/acv-signing-key.json` |
| Merkle proof | This record is one of the leaves committed by an anchored root. | `vault/chain/merkle.py`, `credential_anchor_proof` table |
| On-chain anchor | The root existed at a given block time and cannot be rewritten, even by the vault operator. | `blockchain/contracts/CredentialAnchor.sol` |
| Hash-chained audit ledger | Internal actions cannot be silently edited; the chain head can also be anchored. | `vault/audit/services.py` |

**Why a Merkle batch instead of one transaction per credential?** A single transaction anchors any number of credentials, so the cost is constant. Each credential still gets its own short inclusion proof.

## Providers

- `local` (default): roots are stored only in the vault database. This is good for offline demos, and the UI says clearly that it is **not a public blockchain**.
- `ethereum`: any EVM network, such as the Polygon Amoy or Sepolia testnet, or a local Anvil or Hardhat node.

## Using a testnet (Polygon Amoy)

1. Install the extras: `pip install -r requirements-blockchain.txt`.
2. Create a **new testnet-only wallet** and get free test POL from the Polygon faucet. Never use a wallet that holds real funds.
3. Deploy the contract:
   ```bash
   ETH_RPC_URL=https://rpc-amoy.polygon.technology ETH_PRIVATE_KEY=0x... python blockchain/deploy.py
   ```
4. Copy the printed settings into `.env`, and add `ETH_PRIVATE_KEY`, `ETH_NETWORK_NAME=Polygon Amoy testnet`, and `ETH_EXPLORER_TX_URL=https://amoy.polygonscan.com/tx/{tx}`.
5. Anchor credentials from **Admin → Audit ledger → Anchor credentials**, or on a schedule:
   ```bash
   flask --app app anchor-credentials
   ```

For a fully local chain, run `anvil` (Foundry), then use `ETH_RPC_URL=http://127.0.0.1:8545` and one of Anvil's development keys.

## Verifying independently

Download the proof bundle from a credential's public page (the **Proof bundle** button, which serves `/credential/<id>/proof.json`), then run:

```bash
python blockchain/verify_proof.py ACV-2026-XXXX-proof.json certificate.pdf \
    --public-key <key from the institution's website> --rpc https://rpc-amoy.polygon.technology --contract 0x...
```

The script is standalone and does not import the vault's code. It checks the PDF hash, the Ed25519 signature, the Merkle path, and (with `--rpc`) the on-chain record.

## Keys and operations

- `flask generate-signing-key` creates the Ed25519 key (`SIGNING_KEY_FILE`, mode 600). Production refuses to start without a key. Back it up: losing it means new credentials get a new key ID.
- `flask upgrade-signatures` re-signs legacy HMAC credentials with Ed25519, but only when their HMAC still verifies.
- The contract is compiled with solc 0.8.24 (`blockchain/compile.js`). The ABI and bytecode are committed in `blockchain/build/CredentialAnchor.json`.

## Tests

`tests/test_phase_p5_blockchain.py` deploys the compiled contract to an in-process EVM (eth-tester and py-evm) and exercises:

- real anchoring transactions;
- rejection of duplicate roots;
- owner-only access;
- rollback when the provider fails;
- detection of tampering both before and after anchoring;
- the offline verifier.
