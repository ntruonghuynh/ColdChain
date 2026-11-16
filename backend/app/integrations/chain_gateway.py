"""Local Hardhat gateway. Only the outbox worker can submit writes."""

import json
import re
from pathlib import Path
from typing import Any

from eth_account import Account
from sqlalchemy.orm import Session
from web3 import Web3

from app.core.config import get_settings
from app.db.models import OrganizationChainRole
from app.db.models.enums import Role

ABI: list[dict[str, Any]] = [
    {"type": "function", "name": "isReferenceUsed", "stateMutability": "view", "inputs": [{"name": "", "type": "bytes32"}], "outputs": [{"type": "bool"}]},
    {"type": "function", "name": "referencePayloadHash", "stateMutability": "view", "inputs": [{"name": "", "type": "bytes32"}], "outputs": [{"type": "bytes32"}]},
    {"type": "function", "name": "referenceShipment", "stateMutability": "view", "inputs": [{"name": "", "type": "bytes32"}], "outputs": [{"type": "bytes32"}]},
    {"type": "function", "name": "registerShipment", "stateMutability": "nonpayable", "inputs": [{"name": "ref", "type": "bytes32"}, {"name": "shipmentKey", "type": "bytes32"}, {"name": "payloadHash", "type": "bytes32"}, {"name": "policyHash", "type": "bytes32"}], "outputs": []},
    {"type": "function", "name": "acceptCustody", "stateMutability": "nonpayable", "inputs": [{"name": "ref", "type": "bytes32"}, {"name": "shipmentKey", "type": "bytes32"}, {"name": "payloadHash", "type": "bytes32"}, {"name": "delivery", "type": "bool"}], "outputs": []},
    {"type": "function", "name": "anchorSensorBatch", "stateMutability": "nonpayable", "inputs": [{"name": "ref", "type": "bytes32"}, {"name": "shipmentKey", "type": "bytes32"}, {"name": "payloadHash", "type": "bytes32"}], "outputs": []},
    {"type": "function", "name": "openIncident", "stateMutability": "nonpayable", "inputs": [{"name": "ref", "type": "bytes32"}, {"name": "shipmentKey", "type": "bytes32"}, {"name": "payloadHash", "type": "bytes32"}], "outputs": []},
    {"type": "function", "name": "recordDisposition", "stateMutability": "nonpayable", "inputs": [{"name": "ref", "type": "bytes32"}, {"name": "shipmentKey", "type": "bytes32"}, {"name": "payloadHash", "type": "bytes32"}, {"name": "policyHash", "type": "bytes32"}, {"name": "release", "type": "bool"}, {"name": "addressedIncidents", "type": "bytes32[]"}], "outputs": []},
    {"type": "function", "name": "recordWarehouseRelease", "stateMutability": "nonpayable", "inputs": [{"name": "ref", "type": "bytes32"}, {"name": "shipmentKey", "type": "bytes32"}, {"name": "payloadHash", "type": "bytes32"}], "outputs": []},
    {"type": "event", "name": "BusinessAction", "anonymous": False, "inputs": [{"indexed": True, "name": "referenceHash", "type": "bytes32"}, {"indexed": True, "name": "shipmentKey", "type": "bytes32"}, {"indexed": True, "name": "action", "type": "bytes32"}, {"indexed": False, "name": "payloadHash", "type": "bytes32"}, {"indexed": False, "name": "actor", "type": "address"}, {"indexed": False, "name": "occurredAt", "type": "uint64"}]},
]


def normalize_tx_hash(value: Any) -> str:
    """Return a canonical 0x-prefixed transaction hash for PostgreSQL/API storage."""
    result = value.hex() if hasattr(value, "hex") else str(value)
    return result if result.startswith("0x") else f"0x{result}"


def normalize_data_hex(value: Any) -> str:
    """Return canonical 0x-prefixed hex for Web3 byte values."""
    return Web3.to_hex(value)


class ChainUnavailable(RuntimeError):
    pass


class ContractRevert(RuntimeError):
    """Deterministic contract rejection; retrying cannot make it succeed."""

    def __init__(self, operation: str, code: str, message: str) -> None:
        self.operation = operation
        self.code = code
        self.detail = message[:240]
        super().__init__(f"{operation}:{code}:{self.detail}")


_CONTRACT_ERRORS = {
    "0x82b42900": ("Unauthorized", "contract rejected the configured signer role"),
    "0x9a89aa1d": ("DuplicateReference", "business reference is already used"),
    "0xa6532e5d": ("InvalidTransition", "contract rejected the shipment state transition"),
    "0x0ed0c9e6": ("ShipmentMismatch", "business reference belongs to another shipment"),
    "0x73126577": ("MissingOpenIncident", "disposition references no open incident"),
}


def _revert_data(exc: Exception) -> str | None:
    """Extract only a custom-error selector from common web3/JSON-RPC exceptions."""
    for arg in getattr(exc, "args", ()):
        candidates = [arg] if isinstance(arg, str) else []
        if isinstance(arg, dict):
            candidates.extend(str(value) for value in arg.values())
        for candidate in candidates:
            match = re.search(r"0x[0-9a-fA-F]{8,}", candidate)
            if match:
                return match.group(0)[:10].lower()
    return None


def _rpc_summary(exc: Exception, operation: str) -> str:
    selector = _revert_data(exc)
    if selector in _CONTRACT_ERRORS:
        name, detail = _CONTRACT_ERRORS[selector]
        raise ContractRevert(operation, name, detail) from exc
    args = getattr(exc, "args", ())
    # Keep an RPC error code/message, but never include request payloads or signed tx data.
    message = next((str(arg.get("message")) for arg in args if isinstance(arg, dict) and arg.get("message")), "")
    code = next((str(arg.get("code")) for arg in args if isinstance(arg, dict) and arg.get("code") is not None), type(exc).__name__)
    if not message:
        message = type(exc).__name__
    return f"{operation}:{code}:{message[:180]}"


class ChainGateway:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.web3 = Web3(Web3.HTTPProvider(self.settings.chain_rpc_url, request_kwargs={"timeout": 8}))
        path = Path(self.settings.chain_deployment_file)
        if not path.is_absolute():
            path = Path(__file__).resolve().parents[3] / path
        try:
            self.deployment = json.loads(path.read_text(encoding="utf-8"))
            self.address = Web3.to_checksum_address(self.deployment["contract_address"])
            deployment_abi = self.deployment.get("abi", ABI)
        except (OSError, ValueError, KeyError) as exc:
            raise ChainUnavailable("Local contract deployment metadata is unavailable") from exc
        self.contract = self.web3.eth.contract(address=self.address, abi=deployment_abi)
        Account.enable_unaudited_hdwallet_features()

    def _account(self, role: str):
        index = {
            "SHIPPER": self.settings.chain_account_index_shipper,
            "CARRIER": self.settings.chain_account_index_carrier,
            "QUALITY": self.settings.chain_account_index_quality,
            "WAREHOUSE": self.settings.chain_account_index_warehouse,
            "MONITOR": self.settings.chain_account_index_monitor,
        }[role]
        return Account.from_mnemonic(
            self.settings.chain_mnemonic.get_secret_value(), account_path=f"m/44'/60'/0'/0/{index}"
        )

    @staticmethod
    def hash_ref(value: str) -> bytes:
        return Web3.keccak(text=value)

    @staticmethod
    def _hash(value: str) -> bytes:
        if value.startswith("0x") and len(value) == 66:
            return bytes.fromhex(value[2:])
        if len(value) == 64:
            try:
                return bytes.fromhex(value)
            except ValueError:
                pass
        return Web3.keccak(text=value)

    @staticmethod
    def payload_hash_for(event: Any) -> bytes:
        if event.event_type.value == "SENSOR_BATCH_ANCHORED":
            return bytes.fromhex(event.payload["content_sha256"])
        return bytes.fromhex(event.payload_sha256)

    def is_reference_used(self, business_ref: str) -> bool:
        return bool(self.contract.functions.isReferenceUsed(self.hash_ref(business_ref)).call())

    def get_reference(self, business_ref: str) -> dict[str, str] | None:
        ref = self.hash_ref(business_ref)
        if not self.contract.functions.isReferenceUsed(ref).call():
            return None
        return {
            "payload_hash": normalize_data_hex(self.contract.functions.referencePayloadHash(ref).call()),
            "shipment_key": normalize_data_hex(self.contract.functions.referenceShipment(ref).call()),
        }

    def find_reference_log(self, business_ref: str) -> dict[str, Any] | None:
        logs = self.contract.events.BusinessAction().get_logs(
            from_block=0, to_block="latest",
            argument_filters={"referenceHash": self.hash_ref(business_ref)},
        )
        if not logs:
            return None
        log = logs[-1]
        return {"tx_hash": normalize_tx_hash(log["transactionHash"]), "block_number": log["blockNumber"],
                "log_index": log["logIndex"]}

    def business_function(self, event: Any, session: Session):
        p = event.payload
        ref = self.hash_ref(event.business_ref)
        shipment = self._hash(event.shipment_id)
        payload_hash = self.payload_hash_for(event)
        if event.event_type.value == "SHIPMENT_REGISTERED":
            role, call = "SHIPPER", self.contract.functions.registerShipment(
                ref, shipment, payload_hash, self._hash(p["policy_hash"])
            )
        elif event.event_type.value == "CUSTODY_ACCEPTED":
            role, call = p["signing_role"], self.contract.functions.acceptCustody(
                ref, shipment, payload_hash, p["stage"] == "DELIVERY"
            )
        elif event.event_type.value == "SENSOR_BATCH_ANCHORED":
            role, call = "CARRIER", self.contract.functions.anchorSensorBatch(ref, shipment, payload_hash)
        elif event.event_type.value == "INCIDENT_OPENED":
            role, call = "MONITOR", self.contract.functions.openIncident(ref, shipment, payload_hash)
        elif event.event_type.value == "DISPOSITION_RECORDED":
            role, call = "QUALITY", self.contract.functions.recordDisposition(
                ref, shipment, payload_hash, self._hash(p["policy_hash"]), p["decision"] == "RELEASE",
                [self.hash_ref(value) for value in p["incident_refs"]],
            )
        elif event.event_type.value == "WAREHOUSE_RELEASED":
            role, call = "WAREHOUSE", self.contract.functions.recordWarehouseRelease(ref, shipment, payload_hash)
        else:
            raise ValueError(f"Unsupported blockchain event type {event.event_type}")
        return self._validate_role_mapping(event, role, session), call

    def _validate_role_mapping(self, event: Any, role: str, session: Session) -> str:
        expected_org = {
            "SHIPPER": "ORG-SHIPPER", "CARRIER": "ORG-CARRIER",
            "QUALITY": "ORG-RECEIVER", "WAREHOUSE": "ORG-RECEIVER", "MONITOR": "ORG-RECEIVER",
        }[role]
        if event.actor_org_id != expected_org:
            raise ValueError(f"event actor organization is not authorized for {role}")
        mapping = session.get(OrganizationChainRole, (event.actor_org_id, Role(role)))
        account = self._account(role)
        deployed = self.deployment.get("roles", {}).get(role)
        if (mapping is None or mapping.chain_address.lower() != account.address.lower()
                or not deployed or deployed.lower() != account.address.lower()):
            raise ValueError(f"database and deployed contract role mapping differ for {role}")
        return role

    def submit(self, event: Any, session: Session) -> tuple[str, int, int, int]:
        try:
            connected = self.web3.is_connected()
        except Exception as exc:
            raise ChainUnavailable(_rpc_summary(exc, "eth_chainId")) from exc
        if not connected:
            raise ChainUnavailable("Local blockchain RPC is unavailable")
        try:
            runtime_chain_id = self.web3.eth.chain_id
            bytecode = self.web3.eth.get_code(self.address)
        except Exception as exc:
            raise ChainUnavailable(_rpc_summary(exc, "eth_chainId/getCode")) from exc
        if (runtime_chain_id != self.settings.chain_id
                or int(self.deployment.get("chain_id", -1)) != self.settings.chain_id):
            raise ChainUnavailable("Local blockchain chain ID differs from deployment configuration")
        if not bytecode:
            raise ChainUnavailable("Configured contract address has no deployed bytecode")
        role, call = self.business_function(event, session)
        account = self._account(role)
        try:
            # Execute the same business transition as a read-only call first. Contract reverts
            # are deterministic and should be recorded once, not retried as RPC outages.
            call.call({"from": account.address})
        except ContractRevert:
            raise
        except Exception as exc:
            summary = _rpc_summary(exc, "eth_call:preflight")
            if summary.startswith("eth_call:preflight:") and "Revert" not in summary:
                raise ChainUnavailable(summary) from exc
            if _revert_data(exc) is not None or "revert" in str(exc).lower():
                raise ContractRevert("eth_call:preflight", "ContractRevert", summary) from exc
            raise ChainUnavailable(summary) from exc
        tx = call.build_transaction({
            "from": account.address,
            "nonce": self.web3.eth.get_transaction_count(account.address, "pending"),
            "chainId": self.settings.chain_id,
            "gas": 900_000,
            "gasPrice": self.web3.eth.gas_price,
        })
        signed = account.sign_transaction(tx)
        try:
            tx_hash = self.web3.eth.send_raw_transaction(signed.raw_transaction)
        except Exception as exc:
            summary = _rpc_summary(exc, "eth_sendRawTransaction")
            if _revert_data(exc) is not None or "revert" in str(exc).lower():
                raise ContractRevert("eth_sendRawTransaction", "ContractRevert", summary) from exc
            raise ChainUnavailable(summary) from exc
        try:
            receipt = self.web3.eth.wait_for_transaction_receipt(tx_hash, timeout=60, poll_latency=0.2)
        except Exception as exc:
            raise ChainUnavailable(f"eth_getTransactionReceipt:{type(exc).__name__}:transaction outcome uncertain") from exc
        if receipt.status != 1:
            raise RuntimeError("Blockchain transaction reverted")
        target = receipt.blockNumber + max(1, self.settings.chain_confirmations) - 1
        while self.web3.eth.block_number < target:
            import time
            time.sleep(0.2)
        if self.web3.eth.block_number < target:
            raise TimeoutError("Confirmation depth was not reached")
        logs = self.contract.events.BusinessAction().process_receipt(receipt)
        match = next((log for log in logs if log["args"]["referenceHash"] == self.hash_ref(event.business_ref)), None)
        if match is None:
            raise RuntimeError("Confirmed transaction has no matching business event log")
        return normalize_tx_hash(tx_hash), receipt.blockNumber, match["logIndex"], target + 1
