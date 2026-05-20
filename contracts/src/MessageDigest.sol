// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

contract MessageDigest {
    struct Record {
        uint256 timestamp;   // block.timestamp at record time
        address recorder;    // who submitted (server wallet)
    }

    address public immutable owner;             // deployer
    mapping(address => bool) public recorders;  // allowed writers (the backend's hot wallet)
    mapping(bytes32 => Record) private _records;

    event HashRecorded(bytes32 indexed digest, uint256 timestamp, address indexed recorder);
    event RecorderUpdated(address indexed recorder, bool allowed);

    error NotOwner();
    error NotRecorder();
    error AlreadyRecorded(bytes32 digest);

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

    function recordHash(bytes32 digest) external onlyRecorder {
        if (_records[digest].timestamp != 0) revert AlreadyRecorded(digest);
        _records[digest] = Record({ timestamp: block.timestamp, recorder: msg.sender });
        emit HashRecorded(digest, block.timestamp, msg.sender);
    }

    function getRecord(bytes32 digest) external view returns (uint256 timestamp, address recorder) {
        Record memory r = _records[digest];
        return (r.timestamp, r.recorder);
    }
}

