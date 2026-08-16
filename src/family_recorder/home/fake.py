from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import datetime
from pathlib import Path
from typing import Any

from family_recorder.home.models import (
    ConnectionHealth,
    HomeAccount,
    HomeCapability,
    HomeDevice,
    HomeRoom,
    HomeStateEvent,
    HomeStateSnapshot,
    HomeStructure,
    HomeSyncBatch,
    SyncCursor,
)


def _timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("fixture timestamps must include a UTC offset")
    return parsed


def batch_from_document(document: dict[str, Any]) -> HomeSyncBatch:
    account_raw = document["account"]
    account = HomeAccount(
        id=str(account_raw["id"]),
        provider=str(account_raw.get("provider", "fake")),
        display_name=str(account_raw.get("display_name", account_raw["id"])),
        transport=str(account_raw.get("transport", "fake")),
        keychain_item_ref=str(account_raw.get("keychain_item_ref", "")),
        metadata=dict(account_raw.get("metadata", {})),
    )
    structures = tuple(
        HomeStructure(
            account.id,
            str(item["id"]),
            str(item.get("name", item["id"])),
            str(item.get("timezone", "UTC")),
            dict(item),
        )
        for item in document.get("structures", [])
    )
    rooms = tuple(
        HomeRoom(
            account.id,
            str(item["id"]),
            str(item.get("structure_id", "")),
            str(item.get("name", item["id"])),
            dict(item),
        )
        for item in document.get("rooms", [])
    )
    devices = tuple(
        HomeDevice(
            account_id=account.id,
            provider_id=str(item["id"]),
            name=str(item.get("name", item["id"])),
            structure_id=str(item.get("structure_id", "")),
            room_id=str(item.get("room_id", "")),
            device_type=str(item.get("device_type", "")),
            online=item.get("online"),
            capabilities=tuple(
                HomeCapability(
                    provider_key=str(capability["key"]),
                    display_name=str(capability.get("display_name", capability["key"])),
                    normalized_key=capability.get("normalized_key"),
                    metadata=dict(capability.get("metadata", {})),
                    raw=dict(capability),
                )
                for capability in item.get("capabilities", [])
            ),
            raw=dict(item),
        )
        for item in document.get("devices", [])
    )
    snapshots = tuple(
        HomeStateSnapshot(
            account_id=account.id,
            device_id=str(item["device_id"]),
            occurred_at=_timestamp(item.get("occurred_at")),
            observed_at=_timestamp(item.get("observed_at")) or datetime.now().astimezone(),
            timezone=str(item.get("timezone", "UTC")),
            source=str(item.get("source", "fake")),
            raw_state=dict(item.get("state", {})),
            normalized_state=dict(item.get("normalized_state", {})),
            provider_snapshot_id=str(item.get("snapshot_id", "")),
        )
        for item in document.get("snapshots", [])
    )
    events = tuple(
        HomeStateEvent(
            account_id=account.id,
            device_id=str(item["device_id"]),
            capability_key=str(item["capability"]),
            value=item.get("value"),
            occurred_at=_timestamp(item.get("occurred_at")),
            observed_at=_timestamp(item.get("observed_at")) or datetime.now().astimezone(),
            timezone=str(item.get("timezone", "UTC")),
            source=str(item.get("source", "fake")),
            provider_event_id=str(item.get("event_id", "")),
            previous_value=item.get("previous_value"),
            raw=dict(item),
        )
        for item in document.get("events", [])
    )
    cursor_raw = document.get("cursor")
    cursor = (
        SyncCursor(
            account.id,
            str(cursor_raw.get("type", "sync")),
            str(cursor_raw.get("value", "")),
            _timestamp(cursor_raw.get("updated_at")) or datetime.now().astimezone(),
        )
        if isinstance(cursor_raw, dict)
        else None
    )
    health_raw = document.get("health", {})
    checked_at = _timestamp(health_raw.get("checked_at")) or datetime.now().astimezone()
    health = ConnectionHealth(
        account_id=account.id,
        status=str(health_raw.get("status", "connected")),
        checked_at=checked_at,
        last_success_at=_timestamp(health_raw.get("last_success_at")) or checked_at,
        message=str(health_raw.get("message", "")),
        retry_at=_timestamp(health_raw.get("retry_at")),
        requires_reauthorization=bool(health_raw.get("requires_reauthorization", False)),
    )
    return HomeSyncBatch(account, structures, rooms, devices, snapshots, events, cursor, health)


class FakeHomeProvider:
    def __init__(self, document: dict[str, Any]) -> None:
        self._batch = batch_from_document(document)

    @classmethod
    def from_path(cls, path: Path) -> FakeHomeProvider:
        return cls(json.loads(path.read_text(encoding="utf-8")))

    @property
    def account(self) -> HomeAccount:
        return self._batch.account

    @property
    def supported_transports(self) -> frozenset[str]:
        return frozenset({"poll", "subscription", "fake"})

    async def sync(self, cursor: SyncCursor | None = None) -> HomeSyncBatch:
        del cursor
        return self._batch

    async def subscribe(self, cursor: SyncCursor | None = None) -> AsyncIterator[HomeSyncBatch]:
        del cursor
        for event in self._batch.events:
            yield HomeSyncBatch(
                account=self._batch.account,
                structures=self._batch.structures,
                rooms=self._batch.rooms,
                devices=self._batch.devices,
                events=(event,),
                health=self._batch.health,
            )
