from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol


@dataclass(frozen=True)
class HomeAccount:
    id: str
    provider: str
    display_name: str
    transport: str
    keychain_item_ref: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class HomeStructure:
    account_id: str
    provider_id: str
    name: str
    timezone: str
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class HomeRoom:
    account_id: str
    provider_id: str
    structure_id: str
    name: str
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class HomeCapability:
    provider_key: str
    display_name: str = ""
    normalized_key: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class HomeDevice:
    account_id: str
    provider_id: str
    name: str
    structure_id: str = ""
    room_id: str = ""
    device_type: str = ""
    online: bool | None = None
    capabilities: tuple[HomeCapability, ...] = ()
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def selection_key(self) -> str:
        return f"{self.account_id}/{self.provider_id}"


@dataclass(frozen=True)
class HomeStateSnapshot:
    account_id: str
    device_id: str
    occurred_at: datetime | None
    observed_at: datetime
    timezone: str
    source: str
    raw_state: dict[str, Any]
    normalized_state: dict[str, Any] = field(default_factory=dict)
    provider_snapshot_id: str = ""


@dataclass(frozen=True)
class HomeStateEvent:
    account_id: str
    device_id: str
    capability_key: str
    value: Any
    occurred_at: datetime | None
    observed_at: datetime
    timezone: str
    source: str
    provider_event_id: str = ""
    previous_value: Any = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SyncCursor:
    account_id: str
    cursor_type: str
    value: str
    updated_at: datetime


@dataclass(frozen=True)
class ConnectionHealth:
    account_id: str
    status: str
    checked_at: datetime
    last_success_at: datetime | None = None
    message: str = ""
    retry_at: datetime | None = None
    requires_reauthorization: bool = False


@dataclass(frozen=True)
class HomeSyncBatch:
    account: HomeAccount
    structures: tuple[HomeStructure, ...] = ()
    rooms: tuple[HomeRoom, ...] = ()
    devices: tuple[HomeDevice, ...] = ()
    snapshots: tuple[HomeStateSnapshot, ...] = ()
    events: tuple[HomeStateEvent, ...] = ()
    cursor: SyncCursor | None = None
    health: ConnectionHealth | None = None


class HomeProvider(Protocol):
    """Read-only provider contract. Implementations must never expose control commands."""

    @property
    def account(self) -> HomeAccount: ...

    @property
    def supported_transports(self) -> frozenset[str]: ...

    async def sync(self, cursor: SyncCursor | None = None) -> HomeSyncBatch: ...

    def subscribe(self, cursor: SyncCursor | None = None) -> AsyncIterator[HomeSyncBatch]: ...
