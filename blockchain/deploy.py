#!/usr/bin/env python3
"""Deploy CredentialAnchor to an EVM network and print the settings to put in .env.

    ETH_RPC_URL=https://rpc-amoy.polygon.technology ETH_PRIVATE_KEY=0x... python blockchain/deploy.py

For a local chain run `anvil` (Foundry) or `npx hardhat node` and use ETH_RPC_URL=http://127.0.0.1:8545
with one of the printed development private keys. Never use a key that holds real funds.
"""
import json
import os
import sys
from pathlib import Path

from web3 import Web3

ARTIFACT = Path(__file__).resolve().parent / "build" / "CredentialAnchor.json"


def deploy(w3, private_key=None):
    artifact = json.loads(ARTIFACT.read_text())
    contract = w3.eth.contract(abi=artifact["abi"], bytecode=artifact["bytecode"])
    if private_key:
        account = w3.eth.account.from_key(private_key)
        tx = contract.constructor().build_transaction({"from": account.address, "nonce": w3.eth.get_transaction_count(account.address), "chainId": w3.eth.chain_id})
        tx_hash = w3.eth.send_raw_transaction(account.sign_transaction(tx).raw_transaction)
    else:
        tx_hash = contract.constructor().transact({"from": w3.eth.accounts[0]})
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=300)
    return receipt["contractAddress"], receipt


def main():
    rpc = os.environ.get("ETH_RPC_URL")
    if not rpc:
        sys.exit("Set ETH_RPC_URL (and ETH_PRIVATE_KEY for public networks).")
    w3 = Web3(Web3.HTTPProvider(rpc))
    address, receipt = deploy(w3, os.environ.get("ETH_PRIVATE_KEY") or None)
    print(f"CredentialAnchor deployed at {address} (block {receipt['blockNumber']}, chain {w3.eth.chain_id})\n")
    print("Add to .env:\nBLOCKCHAIN_ANCHOR_PROVIDER=ethereum")
    print(f"ETH_RPC_URL={rpc}\nETH_CONTRACT_ADDRESS={address}\nETH_CHAIN_ID={w3.eth.chain_id}")


if __name__ == "__main__":
    main()
