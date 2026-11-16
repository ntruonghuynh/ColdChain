// SPDX-License-Identifier: MIT
pragma solidity ^0.8.26;

/// @notice Minimal local-demo evidence registry. No readings, names, or documents are stored here.
contract ColdChainRegistry {
    bytes32 public constant ADMIN = keccak256("ADMIN");
    bytes32 public constant SHIPPER = keccak256("SHIPPER");
    bytes32 public constant CARRIER = keccak256("CARRIER");
    bytes32 public constant QUALITY = keccak256("QUALITY");
    bytes32 public constant WAREHOUSE = keccak256("WAREHOUSE");
    bytes32 public constant MONITOR = keccak256("MONITOR");

    enum State { NONE, CREATED, IN_TRANSIT, DELIVERED, RELEASE_APPROVED, QUARANTINED, RELEASED }
    enum Disposition { NONE, RELEASE, QUARANTINE }

    struct Shipment {
        State state;
        Disposition disposition;
        bytes32 policyVersionHash;
        uint64 incidentCount;
        uint64 reviewedIncidentCount;
        bool hasDisposition;
    }

    mapping(bytes32 => mapping(address => bool)) public hasRole;
    mapping(bytes32 => bool) public isReferenceUsed;
    mapping(bytes32 => bytes32) public referencePayloadHash;
    mapping(bytes32 => bytes32) public referenceShipment;
    mapping(bytes32 => Shipment) public shipments;
    mapping(bytes32 => bool) public isIncidentOpen;
    mapping(bytes32 => bytes32[]) private shipmentIncidents;

    error Unauthorized();
    error DuplicateReference(bytes32 referenceHash);
    error InvalidTransition();
    error ShipmentMismatch();
    error MissingOpenIncident(bytes32 incidentRefHash);

    event BusinessAction(bytes32 indexed referenceHash, bytes32 indexed shipmentKey, bytes32 indexed action,
                         bytes32 payloadHash, address actor, uint64 occurredAt);
    event RoleGranted(bytes32 indexed role, address indexed account);

    constructor(address admin, address shipper, address carrier, address quality, address warehouse, address monitor) {
        if (admin == address(0) || shipper == address(0) || carrier == address(0) ||
            quality == address(0) || warehouse == address(0) || monitor == address(0)) revert Unauthorized();
        if (admin == shipper || admin == carrier || admin == quality || admin == warehouse || admin == monitor ||
            shipper == carrier || shipper == quality || shipper == warehouse || shipper == monitor ||
            carrier == quality || carrier == warehouse || carrier == monitor ||
            quality == warehouse || quality == monitor || warehouse == monitor) revert Unauthorized();
        _grant(ADMIN, admin);
        _grant(SHIPPER, shipper);
        _grant(CARRIER, carrier);
        _grant(QUALITY, quality);
        _grant(WAREHOUSE, warehouse);
        _grant(MONITOR, monitor);
    }

    modifier onlyRole(bytes32 role) { if (!hasRole[role][msg.sender]) revert Unauthorized(); _; }

    function grantRole(bytes32 role, address account) external onlyRole(ADMIN) {
        if (!_validRole(role) || account == address(0)) revert Unauthorized();
        _grant(role, account);
    }

    function registerShipment(bytes32 ref, bytes32 shipmentKey, bytes32 payloadHash, bytes32 policyHash)
        external onlyRole(SHIPPER)
    {
        _requireUnused(ref);
        if (shipments[shipmentKey].state != State.NONE) revert InvalidTransition();
        _consume(ref, shipmentKey, payloadHash);
        shipments[shipmentKey] = Shipment(State.CREATED, Disposition.NONE, policyHash, 0, 0, false);
        _emit(ref, shipmentKey, keccak256("SHIPMENT_REGISTERED"), payloadHash);
    }

    function acceptCustody(bytes32 ref, bytes32 shipmentKey, bytes32 payloadHash, bool delivery)
        external
    {
        Shipment storage s = shipments[shipmentKey];
        if (delivery) {
            if (!hasRole[WAREHOUSE][msg.sender]) revert Unauthorized();
            _requireUnused(ref);
            if (s.state != State.IN_TRANSIT) revert InvalidTransition();
            s.state = State.DELIVERED;
        } else {
            if (!hasRole[CARRIER][msg.sender]) revert Unauthorized();
            _requireUnused(ref);
            if (s.state != State.CREATED) revert InvalidTransition();
            s.state = State.IN_TRANSIT;
        }
        _consume(ref, shipmentKey, payloadHash);
        _emit(ref, shipmentKey, keccak256(bytes(delivery ? "CUSTODY_DELIVERY" : "CUSTODY_PICKUP")), payloadHash);
    }

    function anchorSensorBatch(bytes32 ref, bytes32 shipmentKey, bytes32 payloadHash) external onlyRole(CARRIER) {
        _requireUnused(ref);
        if (shipments[shipmentKey].state == State.NONE || shipments[shipmentKey].state == State.RELEASED) revert InvalidTransition();
        _consume(ref, shipmentKey, payloadHash);
        _emit(ref, shipmentKey, keccak256("SENSOR_BATCH_ANCHORED"), payloadHash);
    }

    function openIncident(bytes32 ref, bytes32 shipmentKey, bytes32 payloadHash) external onlyRole(MONITOR) {
        _requireUnused(ref);
        Shipment storage s = shipments[shipmentKey];
        if (s.state == State.NONE) revert InvalidTransition();
        _consume(ref, shipmentKey, payloadHash);
        isIncidentOpen[ref] = true;
        shipmentIncidents[shipmentKey].push(ref);
        s.incidentCount += 1;
        if (s.hasDisposition && s.state != State.RELEASED) s.state = State.DELIVERED;
        _emit(ref, shipmentKey, keccak256("INCIDENT_OPENED"), payloadHash);
    }

    function recordDisposition(bytes32 ref, bytes32 shipmentKey, bytes32 payloadHash, bytes32 policyHash,
                               bool release, bytes32[] calldata addressedIncidents) external onlyRole(QUALITY) {
        _requireUnused(ref);
        Shipment storage s = shipments[shipmentKey];
        if (s.state != State.DELIVERED) revert InvalidTransition();
        if (s.hasDisposition && s.incidentCount <= s.reviewedIncidentCount) revert InvalidTransition();
        if (s.policyVersionHash != policyHash) revert ShipmentMismatch();
        for (uint256 i = 0; i < addressedIncidents.length; i++) {
            bool belongsToShipment = false;
            for (uint256 j = 0; j < shipmentIncidents[shipmentKey].length; j++) {
                if (addressedIncidents[i] == shipmentIncidents[shipmentKey][j]) {
                    belongsToShipment = true;
                    break;
                }
            }
            if (!belongsToShipment) revert ShipmentMismatch();
            for (uint256 k = i + 1; k < addressedIncidents.length; k++) {
                if (addressedIncidents[i] == addressedIncidents[k]) revert ShipmentMismatch();
            }
        }
        for (uint256 i = 0; i < shipmentIncidents[shipmentKey].length; i++) {
            bytes32 incidentRef = shipmentIncidents[shipmentKey][i];
            if (isIncidentOpen[incidentRef] && !_contains(addressedIncidents, incidentRef)) revert MissingOpenIncident(incidentRef);
        }
        _consume(ref, shipmentKey, payloadHash);
        if (release) { s.disposition = Disposition.RELEASE; s.state = State.RELEASE_APPROVED; }
        else { s.disposition = Disposition.QUARANTINE; s.state = State.QUARANTINED; }
        s.hasDisposition = true;
        s.reviewedIncidentCount = s.incidentCount;
        _emit(ref, shipmentKey, keccak256(bytes(release ? "DISPOSITION_RELEASE" : "DISPOSITION_QUARANTINE")), payloadHash);
    }

    function recordWarehouseRelease(bytes32 ref, bytes32 shipmentKey, bytes32 payloadHash) external onlyRole(WAREHOUSE) {
        _requireUnused(ref);
        Shipment storage s = shipments[shipmentKey];
        if (s.state != State.RELEASE_APPROVED || s.disposition != Disposition.RELEASE) revert InvalidTransition();
        _consume(ref, shipmentKey, payloadHash);
        s.state = State.RELEASED;
        _emit(ref, shipmentKey, keccak256("WAREHOUSE_RELEASED"), payloadHash);
    }

    function getIncidentReferences(bytes32 shipmentKey) external view returns (bytes32[] memory) {
        return shipmentIncidents[shipmentKey];
    }

    function _contains(bytes32[] calldata list, bytes32 value) private pure returns (bool) {
        for (uint256 i = 0; i < list.length; i++) if (list[i] == value) return true;
        return false;
    }
    function _consume(bytes32 ref, bytes32 shipmentKey, bytes32 payloadHash) private {
        _requireUnused(ref);
        isReferenceUsed[ref] = true;
        referencePayloadHash[ref] = payloadHash;
        referenceShipment[ref] = shipmentKey;
    }
    function _requireUnused(bytes32 ref) private view {
        if (isReferenceUsed[ref]) revert DuplicateReference(ref);
    }
    function _emit(bytes32 ref, bytes32 shipmentKey, bytes32 action, bytes32 payloadHash) private {
        emit BusinessAction(ref, shipmentKey, action, payloadHash, msg.sender, uint64(block.timestamp));
    }
    function _grant(bytes32 role, address account) private {
        if (hasRole[role][account]) revert Unauthorized();
        hasRole[role][account] = true;
        emit RoleGranted(role, account);
    }
    function _validRole(bytes32 role) private pure returns (bool) {
        return role == SHIPPER || role == CARRIER || role == QUALITY || role == WAREHOUSE || role == MONITOR;
    }
}
