"""Binary Merkle tree over SHA-256 with domain separation.

leaf = SHA256(0x00 || data), node = SHA256(0x01 || left || right). The prefixes stop an
interior node from being passed off as a leaf (second-preimage attack). An odd node at
any level is carried up unchanged rather than duplicated.
"""
import hashlib

LEAF_PREFIX, NODE_PREFIX = b"\x00", b"\x01"


def leaf_hash(data: bytes) -> str:
    return hashlib.sha256(LEAF_PREFIX + data).hexdigest()


def node_hash(left: str, right: str) -> str:
    return hashlib.sha256(NODE_PREFIX + bytes.fromhex(left) + bytes.fromhex(right)).hexdigest()


def build(leaves):
    """Return (root, proofs) where proofs[i] is a list of {"side", "hash"} steps for leaves[i]."""
    if not leaves:
        raise ValueError("A Merkle tree needs at least one leaf.")
    proofs = [[] for _ in leaves]
    positions = list(range(len(leaves)))  # positions[i] = index of leaf i's ancestor at the current level
    level = list(leaves)
    while len(level) > 1:
        next_level = []
        for index in range(0, len(level), 2):
            if index + 1 < len(level):
                next_level.append(node_hash(level[index], level[index + 1]))
            else:
                next_level.append(level[index])
        for leaf_index, position in enumerate(positions):
            sibling = position ^ 1
            if sibling < len(level):
                proofs[leaf_index].append({"side": "left" if sibling < position else "right", "hash": level[sibling]})
            positions[leaf_index] = position // 2
        level = next_level
    return level[0], proofs


def verify(leaf: str, proof, root: str) -> bool:
    current = leaf
    for step in proof:
        current = node_hash(step["hash"], current) if step["side"] == "left" else node_hash(current, step["hash"])
    return current == root
