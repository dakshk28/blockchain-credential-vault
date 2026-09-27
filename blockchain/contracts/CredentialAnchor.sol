// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @title CredentialAnchor
/// @notice Stores Merkle roots of academic-credential batches and audit-ledger heads.
///         Only hashes are published: no personal data or documents ever touch the chain.
///         Anyone can check that a root was anchored, and when, without trusting the vault operator.
contract CredentialAnchor {
    address public owner;

    /// root => block timestamp at which it was first anchored (0 = never anchored)
    mapping(bytes32 => uint256) public anchoredAt;
    /// root => kind of data it commits to ("credentials" or "audit")
    mapping(bytes32 => string) public kindOf;
    uint256 public anchorCount;

    event Anchored(bytes32 indexed root, string kind, uint256 itemCount, uint256 timestamp, address indexed by);
    event OwnershipTransferred(address indexed previousOwner, address indexed newOwner);

    error NotOwner();
    error AlreadyAnchored(bytes32 root);
    error ZeroRoot();

    modifier onlyOwner() {
        if (msg.sender != owner) revert NotOwner();
        _;
    }

    constructor() {
        owner = msg.sender;
        emit OwnershipTransferred(address(0), msg.sender);
    }

    /// @notice Anchor a Merkle root. Roots are immutable once anchored.
    function anchor(bytes32 root, string calldata kind, uint256 itemCount) external onlyOwner {
        if (root == bytes32(0)) revert ZeroRoot();
        if (anchoredAt[root] != 0) revert AlreadyAnchored(root);
        anchoredAt[root] = block.timestamp;
        kindOf[root] = kind;
        anchorCount += 1;
        emit Anchored(root, kind, itemCount, block.timestamp, msg.sender);
    }

    /// @notice True if the root has been anchored.
    function isAnchored(bytes32 root) external view returns (bool) {
        return anchoredAt[root] != 0;
    }

    function transferOwnership(address newOwner) external onlyOwner {
        emit OwnershipTransferred(owner, newOwner);
        owner = newOwner;
    }
}
