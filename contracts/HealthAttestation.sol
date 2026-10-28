// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @title HealthAttestation
/// @notice Append-only log of potwatch health-report digests on the Portaldot EVM.
///         Anyone can verify a published report.json off-chain by recomputing
///         `potwatch digest --report report.json` and comparing it with the stored digest.
/// @dev No funds, no owner powers beyond managing the reporter list. Reports are never edited.
contract HealthAttestation {
    enum Severity { Ok, Info, Warn, Crit }

    struct Attestation {
        bytes32 digest;      // sha256 of the canonical report JSON
        bytes32 network;     // e.g. "portaldot-v3-testnet" packed into bytes32
        uint64 bestBlock;    // Substrate best block seen by the checker
        uint64 finalized;    // Substrate finalized block seen by the checker
        uint64 takenAt;      // checker timestamp (unix seconds)
        Severity severity;   // overall verdict
        address reporter;
    }

    address public owner;
    mapping(address => bool) public isReporter;
    Attestation[] private _log;
    mapping(bytes32 => uint256) public latestIndexPlusOne; // network => index+1 of latest attestation

    event ReporterSet(address indexed reporter, bool allowed);
    event Attested(uint256 indexed index, bytes32 indexed network, bytes32 digest,
                   Severity severity, uint64 bestBlock, uint64 finalized, uint64 takenAt);

    error NotOwner();
    error NotReporter();
    error StaleReport();

    constructor() {
        owner = msg.sender;
        isReporter[msg.sender] = true;
        emit ReporterSet(msg.sender, true);
    }

    function setReporter(address reporter, bool allowed) external {
        if (msg.sender != owner) revert NotOwner();
        isReporter[reporter] = allowed;
        emit ReporterSet(reporter, allowed);
    }

    function attest(bytes32 digest, bytes32 network, uint64 bestBlock, uint64 finalized,
                    uint64 takenAt, Severity severity) external returns (uint256 index) {
        if (!isReporter[msg.sender]) revert NotReporter();
        uint256 prev = latestIndexPlusOne[network];
        if (prev != 0 && takenAt <= _log[prev - 1].takenAt) revert StaleReport();
        index = _log.length;
        _log.push(Attestation(digest, network, bestBlock, finalized, takenAt, severity, msg.sender));
        latestIndexPlusOne[network] = index + 1;
        emit Attested(index, network, digest, severity, bestBlock, finalized, takenAt);
    }

    function count() external view returns (uint256) { return _log.length; }

    function get(uint256 index) external view returns (Attestation memory) { return _log[index]; }

    function latest(bytes32 network) external view returns (Attestation memory a, bool found) {
        uint256 p = latestIndexPlusOne[network];
        if (p == 0) return (a, false);
        return (_log[p - 1], true);
    }
}
