from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from family_recorder.home.fake import batch_from_document
from family_recorder.home.models import HomeSyncBatch

BRIDGE_SCHEMA_VERSION = 1
_CREDENTIAL_KEYS = {
    "access_token",
    "api_key",
    "authorization",
    "client_key",
    "client_secret",
    "credential",
    "password",
    "private_key",
    "refresh_token",
    "secret",
    "token",
}


class CompanionBridgeError(ValueError):
    """Raised when a companion payload fails the local bridge contract."""


def _contains_credentials(value: Any) -> bool:
    if isinstance(value, dict):
        for key, child in value.items():
            compact = str(key).casefold().replace("-", "_")
            if compact in _CREDENTIAL_KEYS or compact.endswith("_secret"):
                return True
            if _contains_credentials(child):
                return True
    elif isinstance(value, list):
        return any(_contains_credentials(child) for child in value)
    return False


def parse_companion_payload(payload: str | bytes | dict[str, Any]) -> HomeSyncBatch:
    if isinstance(payload, bytes):
        payload = payload.decode("utf-8")
    document = json.loads(payload) if isinstance(payload, str) else payload
    if not isinstance(document, dict):
        raise CompanionBridgeError("companion payload must be a JSON object")
    if document.get("schema_version") != BRIDGE_SCHEMA_VERSION:
        raise CompanionBridgeError("unsupported companion bridge schema version")
    account = document.get("account")
    if not isinstance(account, dict):
        raise CompanionBridgeError("companion payload requires account metadata")
    if account.get("transport") != "companion_bridge":
        raise CompanionBridgeError("companion payload must declare companion_bridge transport")
    if account.get("provider") not in {"google_home", "apple_home"}:
        raise CompanionBridgeError("unsupported companion bridge provider")
    if _contains_credentials(document):
        raise CompanionBridgeError("companion payload must not contain credentials")
    if account.get("keychain_item_ref"):
        raise CompanionBridgeError("companion payload cannot choose a Mac Keychain item")
    return batch_from_document(document)


def load_companion_payload(path: Path) -> HomeSyncBatch:
    return parse_companion_payload(path.read_text(encoding="utf-8"))
