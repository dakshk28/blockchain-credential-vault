"""Anchor providers publish a 32-byte Merkle root somewhere the vault operator cannot rewrite.

* ``local``    – records the root in the vault's own database. Works offline for demos, but gives
                 no independent guarantee; the UI labels it as such.
* ``ethereum`` – calls ``CredentialAnchor.anchor(root, kind, count)`` on any EVM chain (Polygon Amoy,
                 Sepolia, or a local Anvil/Hardhat node). The transaction is public and permanent.
"""
import json
from dataclasses import dataclass
from pathlib import Path

from flask import current_app

ARTIFACT = Path(__file__).resolve().parents[2] / "blockchain" / "build" / "CredentialAnchor.json"


class AnchorError(RuntimeError):
    pass


@dataclass
class AnchorReceipt:
    provider: str
    network: str
    tx_hash: str | None = None
    block_number: int | None = None
    explorer_url: str | None = None


def load_artifact():
    return json.loads(ARTIFACT.read_text())


class LocalProvider:
    name = "local"
    network = "Local ledger (not a public blockchain)"

    def anchor(self, root: str, kind: str, item_count: int) -> AnchorReceipt:
        return AnchorReceipt(provider=self.name, network=self.network)

    def is_anchored(self, root: str) -> bool | None:
        return None  # nothing independent to check against


class EthereumProvider:
    name = "ethereum"

    def __init__(self, w3, contract_address, private_key=None, sender=None, chain_id=None, network="Ethereum", explorer_tx_url=None):
        self.w3 = w3
        self.contract = w3.eth.contract(address=w3.to_checksum_address(contract_address), abi=load_artifact()["abi"])
        self.account = w3.eth.account.from_key(private_key) if private_key else None
        self.sender = self.account.address if self.account else (sender or w3.eth.accounts[0])
        self.chain_id = chain_id
        self.network = network
        self.explorer_tx_url = explorer_tx_url

    @classmethod
    def from_config(cls, config):
        from web3 import Web3  # optional dependency: only needed when this provider is selected
        missing = [key for key in ("ETH_RPC_URL", "ETH_CONTRACT_ADDRESS") if not config.get(key)]
        if missing:
            raise AnchorError(f"Ethereum anchoring needs {', '.join(missing)}.")
        w3 = Web3(Web3.HTTPProvider(config["ETH_RPC_URL"], request_kwargs={"timeout": 30}))
        return cls(w3, config["ETH_CONTRACT_ADDRESS"], private_key=config.get("ETH_PRIVATE_KEY") or None, chain_id=config.get("ETH_CHAIN_ID"),
                   network=config.get("ETH_NETWORK_NAME") or "Ethereum", explorer_tx_url=config.get("ETH_EXPLORER_TX_URL") or None)

    def anchor(self, root: str, kind: str, item_count: int) -> AnchorReceipt:
        root_bytes = bytes.fromhex(root)
        try:
            call = self.contract.functions.anchor(root_bytes, kind, item_count)
            if self.account:
                tx = call.build_transaction({"from": self.sender, "nonce": self.w3.eth.get_transaction_count(self.sender), "chainId": self.chain_id or self.w3.eth.chain_id})
                signed = self.account.sign_transaction(tx)
                tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
            else:
                tx_hash = call.transact({"from": self.sender})  # unlocked account (local dev node / tests)
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=180)
        except Exception as error:  # network, gas, revert (e.g. AlreadyAnchored)
            raise AnchorError(f"Blockchain transaction failed: {error}") from error
        if receipt["status"] != 1:
            raise AnchorError("Blockchain transaction was reverted.")
        tx_hex = "0x" + bytes(receipt["transactionHash"]).hex().removeprefix("0x")
        explorer = self.explorer_tx_url.format(tx=tx_hex) if self.explorer_tx_url else None
        return AnchorReceipt(provider=self.name, network=self.network, tx_hash=tx_hex, block_number=receipt["blockNumber"], explorer_url=explorer)

    def is_anchored(self, root: str) -> bool:
        return bool(self.contract.functions.isAnchored(bytes.fromhex(root)).call())

    def anchored_at(self, root: str) -> int:
        return int(self.contract.functions.anchoredAt(bytes.fromhex(root)).call())


def get_provider():
    app = current_app._get_current_object()
    if "acv_anchor_provider" in app.extensions:  # tests and demos may inject a provider
        return app.extensions["acv_anchor_provider"]
    selected = app.config.get("BLOCKCHAIN_ANCHOR_PROVIDER", "local")
    if selected == "ethereum":
        provider = EthereumProvider.from_config(app.config)
    elif selected == "local":
        provider = LocalProvider()
    else:
        raise AnchorError(f"Unknown anchor provider '{selected}'.")
    app.extensions["acv_anchor_provider"] = provider
    return provider
