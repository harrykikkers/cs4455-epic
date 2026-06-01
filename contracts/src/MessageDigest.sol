// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

contract MessageDigest {
    struct Record {
        bytes32 digest;      // keccak256(plaintext) committed by the client
        uint256 timestamp;   // block.timestamp at record time
        address recorder;    // who submitted (server wallet)
    }

    address public immutable owner;             // deployer
    mapping(address => bool) public recorders;  // allowed writers (the backend's hot wallet)
    // Keyed by messageId, NOT by digest. Two messages with identical plaintext
    // (hence identical digest) must each anchor independently, so uniqueness is
    // enforced per message rather than per content. Re-recording the SAME
    // messageId still reverts, which makes a retry of an already-anchored
    // message idempotent rather than a duplicate write.
    mapping(bytes32 => Record) private _records;

    event HashRecorded(bytes32 indexed digest, uint256 timestamp, address indexed recorder);
    event RecorderUpdated(address indexed recorder, bool allowed);

    error NotOwner();
    error NotRecorder();
    error AlreadyRecorded(bytes32 messageId);

    modifier onlyOwner() { if (msg.sender != owner) revert NotOwner(); _; }
    modifier onlyRecorder() { if (!recorders[msg.sender]) revert NotRecorder(); _; }

    constructor() {
        owner = msg.sender;
        recorders[msg.sender] = true; // deployer can record by default
    }

    function setRecorder(address r, bool allowed) external onlyOwner {
        recorders[r] = allowed;
        emit RecorderUpdated(r, allowed);
    }

    // `digest` is keccak256(plaintext) (the client's commitment, emitted so the
    // verification page can compare it); `messageId` is the per-message
    // uniqueness key. The HashRecorded event signature is unchanged, so the
    // verification page keeps reading `digest` from the event exactly as before.
    function recordHash(bytes32 digest, bytes32 messageId) external onlyRecorder {
        if (_records[messageId].timestamp != 0) revert AlreadyRecorded(messageId);
        _records[messageId] = Record({ digest: digest, timestamp: block.timestamp, recorder: msg.sender });
        emit HashRecorded(digest, block.timestamp, msg.sender);
    }

    function getRecord(bytes32 messageId) external view returns (bytes32 digest, uint256 timestamp, address recorder) {
        Record memory r = _records[messageId];
        return (r.digest, r.timestamp, r.recorder);
    }
}

