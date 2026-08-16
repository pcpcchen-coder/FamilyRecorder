from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from family_recorder.config import SmartHomeConfig, StorageConfig
from family_recorder.home.models import (
    ConnectionHealth,
    HomeAccount,
    HomeDevice,
    HomeStateEvent,
    HomeStateSnapshot,
    HomeSyncBatch,
    SyncCursor,
)
from family_recorder.home.normalization import is_numeric_measurement, normalize_state

HOME_SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS home_schema_meta (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS home_provider_accounts (
    account_id TEXT PRIMARY KEY,
    provider_key TEXT NOT NULL,
    display_name TEXT NOT NULL,
    transport TEXT NOT NULL,
    keychain_item_ref TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    is_active INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN (0, 1)),
    health_status TEXT NOT NULL DEFAULT 'disconnected',
    health_message TEXT NOT NULL DEFAULT '',
    requires_reauthorization INTEGER NOT NULL DEFAULT 0,
    last_checked_at TEXT,
    last_success_at TEXT,
    retry_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_home_provider_accounts_health
ON home_provider_accounts(health_status, updated_at);

CREATE TABLE IF NOT EXISTS home_structures (
    account_id TEXT NOT NULL REFERENCES home_provider_accounts(account_id),
    provider_structure_id TEXT NOT NULL,
    name TEXT NOT NULL,
    timezone TEXT NOT NULL,
    raw_json TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    PRIMARY KEY(account_id, provider_structure_id)
);

CREATE TABLE IF NOT EXISTS home_rooms (
    account_id TEXT NOT NULL REFERENCES home_provider_accounts(account_id),
    provider_room_id TEXT NOT NULL,
    provider_structure_id TEXT NOT NULL DEFAULT '',
    name TEXT NOT NULL,
    raw_json TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    PRIMARY KEY(account_id, provider_room_id)
);

CREATE INDEX IF NOT EXISTS idx_home_rooms_structure
ON home_rooms(account_id, provider_structure_id);

CREATE TABLE IF NOT EXISTS home_devices (
    account_id TEXT NOT NULL REFERENCES home_provider_accounts(account_id),
    provider_device_id TEXT NOT NULL,
    provider_structure_id TEXT NOT NULL DEFAULT '',
    provider_room_id TEXT NOT NULL DEFAULT '',
    name TEXT NOT NULL,
    device_type TEXT NOT NULL DEFAULT '',
    online INTEGER CHECK(online IN (0, 1)),
    raw_json TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    PRIMARY KEY(account_id, provider_device_id)
);

CREATE INDEX IF NOT EXISTS idx_home_devices_location
ON home_devices(account_id, provider_structure_id, provider_room_id);

CREATE TABLE IF NOT EXISTS home_capabilities (
    account_id TEXT NOT NULL,
    provider_device_id TEXT NOT NULL,
    provider_capability_key TEXT NOT NULL,
    display_name TEXT NOT NULL,
    normalized_capability_key TEXT,
    metadata_json TEXT NOT NULL,
    raw_json TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    PRIMARY KEY(account_id, provider_device_id, provider_capability_key),
    FOREIGN KEY(account_id, provider_device_id)
        REFERENCES home_devices(account_id, provider_device_id)
);

CREATE INDEX IF NOT EXISTS idx_home_capabilities_normalized
ON home_capabilities(normalized_capability_key);

CREATE TABLE IF NOT EXISTS home_state_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id TEXT NOT NULL,
    provider_device_id TEXT NOT NULL,
    provider_snapshot_id TEXT NOT NULL DEFAULT '',
    dedupe_key TEXT NOT NULL,
    provider_occurred_at TEXT,
    observed_at TEXT NOT NULL,
    effective_at TEXT NOT NULL,
    timezone TEXT NOT NULL,
    time_quality TEXT NOT NULL,
    clock_skew_ms INTEGER,
    source TEXT NOT NULL,
    raw_state_json TEXT NOT NULL,
    normalized_state_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(account_id, dedupe_key),
    FOREIGN KEY(account_id, provider_device_id)
        REFERENCES home_devices(account_id, provider_device_id)
);

CREATE INDEX IF NOT EXISTS idx_home_snapshots_device_time
ON home_state_snapshots(account_id, provider_device_id, effective_at);

CREATE TABLE IF NOT EXISTS home_state_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id TEXT NOT NULL,
    provider_device_id TEXT NOT NULL,
    provider_capability_key TEXT NOT NULL,
    normalized_capability_key TEXT,
    provider_event_id TEXT NOT NULL DEFAULT '',
    dedupe_key TEXT NOT NULL,
    event_kind TEXT NOT NULL DEFAULT 'state_change',
    raw_value_json TEXT NOT NULL,
    normalized_value_json TEXT NOT NULL,
    previous_value_json TEXT,
    display_value TEXT NOT NULL,
    provider_occurred_at TEXT,
    observed_at TEXT NOT NULL,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    timezone TEXT NOT NULL,
    time_quality TEXT NOT NULL,
    clock_skew_ms INTEGER,
    source TEXT NOT NULL,
    raw_payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(account_id, dedupe_key),
    FOREIGN KEY(account_id, provider_device_id)
        REFERENCES home_devices(account_id, provider_device_id)
);

CREATE INDEX IF NOT EXISTS idx_home_events_device_capability_time
ON home_state_events(account_id, provider_device_id, provider_capability_key, started_at);

CREATE INDEX IF NOT EXISTS idx_home_events_started_ended
ON home_state_events(started_at, ended_at);

CREATE TABLE IF NOT EXISTS home_sync_cursors (
    account_id TEXT NOT NULL REFERENCES home_provider_accounts(account_id),
    cursor_type TEXT NOT NULL,
    cursor_value TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY(account_id, cursor_type)
);

CREATE TABLE IF NOT EXISTS home_connection_errors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id TEXT NOT NULL REFERENCES home_provider_accounts(account_id),
    error_code TEXT NOT NULL DEFAULT '',
    message TEXT NOT NULL,
    retryable INTEGER NOT NULL CHECK(retryable IN (0, 1)),
    occurred_at TEXT NOT NULL,
    resolved_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_home_connection_errors_account_time
ON home_connection_errors(account_id, occurred_at);
"""

HOME_SCHEMA_VERSION = 2


@dataclass(frozen=True)
class IngestResult:
    snapshots_inserted: int = 0
    events_inserted: int = 0
    duplicates_skipped: int = 0
    policy_skipped: int = 0
    coalesced: int = 0


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash(*values: Any) -> str:
    payload = "\x1f".join(_json(value) for value in values)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _secret_metadata_key(key: str) -> bool:
    compact = key.casefold().replace("-", "_")
    return any(
        word in compact
        for word in (
            "api_key",
            "authorization",
            "credential",
            "password",
            "private_key",
            "secret",
            "token",
        )
    )


def _metadata_contains_secret(value: Any) -> bool:
    if isinstance(value, dict):
        return any(
            _secret_metadata_key(str(key)) or _metadata_contains_secret(child)
            for key, child in value.items()
        )
    if isinstance(value, (list, tuple)):
        return any(_metadata_contains_secret(child) for child in value)
    return False


def _validate_account_metadata(account: HomeAccount) -> None:
    if not all((account.id, account.provider, account.display_name, account.transport)):
        raise ValueError("provider account identity fields cannot be empty")
    if any(
        character in value
        for value in (
            account.id,
            account.provider,
            account.display_name,
            account.transport,
            account.keychain_item_ref,
        )
        for character in ("\n", "\r")
    ):
        raise ValueError("provider account identity fields cannot contain newlines")
    if _metadata_contains_secret(account.metadata):
        raise ValueError("provider account metadata cannot contain credentials")


def selection_key(account_id: str, device_id: str) -> str:
    return f"{account_id}/{device_id}"


def capability_is_allowed(
    allowlist: dict[str, tuple[str, ...]],
    account_id: str,
    device_id: str,
    capability_key: str,
) -> bool:
    keys = (selection_key(account_id, device_id), f"{account_id}/*", "*")
    return any(
        capability_key in allowlist.get(key, ()) or "*" in allowlist.get(key, ()) for key in keys
    )


class HomeStateStore:
    def __init__(self, storage: StorageConfig) -> None:
        self.root = storage.data_dir
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / ".familyrecorder-data").touch(mode=0o600, exist_ok=True)
        self.database_path = self.root / "listener.sqlite3"
        self.connection = sqlite3.connect(self.database_path)
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript(HOME_SCHEMA)
        with self.connection:
            account_columns = {
                str(row["name"])
                for row in self.connection.execute(
                    "PRAGMA table_info(home_provider_accounts)"
                ).fetchall()
            }
            if "is_active" not in account_columns:
                self.connection.execute(
                    """
                    ALTER TABLE home_provider_accounts
                    ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1
                    CHECK(is_active IN (0, 1))
                    """
                )
            self.connection.execute(
                "INSERT OR IGNORE INTO home_schema_meta(version, applied_at) VALUES (?, ?)",
                (
                    HOME_SCHEMA_VERSION,
                    datetime.now().astimezone().isoformat(),
                ),
            )

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> HomeStateStore:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def record_batch(self, batch: HomeSyncBatch, config: SmartHomeConfig) -> IngestResult:
        now = datetime.now().astimezone()
        _validate_account_metadata(batch.account)
        self._upsert_account(batch.account, now)
        for structure in batch.structures:
            self.connection.execute(
                """
                INSERT INTO home_structures(
                    account_id, provider_structure_id, name, timezone, raw_json, last_seen_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(account_id, provider_structure_id) DO UPDATE SET
                    name = excluded.name,
                    timezone = excluded.timezone,
                    raw_json = excluded.raw_json,
                    last_seen_at = excluded.last_seen_at
                """,
                (
                    structure.account_id,
                    structure.provider_id,
                    structure.name,
                    structure.timezone,
                    _json(structure.raw),
                    now.isoformat(),
                ),
            )
        for room in batch.rooms:
            self.connection.execute(
                """
                INSERT INTO home_rooms(
                    account_id, provider_room_id, provider_structure_id,
                    name, raw_json, last_seen_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(account_id, provider_room_id) DO UPDATE SET
                    provider_structure_id = excluded.provider_structure_id,
                    name = excluded.name,
                    raw_json = excluded.raw_json,
                    last_seen_at = excluded.last_seen_at
                """,
                (
                    room.account_id,
                    room.provider_id,
                    room.structure_id,
                    room.name,
                    _json(room.raw),
                    now.isoformat(),
                ),
            )
        device_map = {device.provider_id: device for device in batch.devices}
        for device in batch.devices:
            self._upsert_device(device, now)
        result = IngestResult()
        with self.connection:
            for snapshot in batch.snapshots:
                device = device_map.get(snapshot.device_id)
                if device is not None and not self._device_selected(device, config):
                    result = self._add_result(result, policy_skipped=1)
                    continue
                self._ensure_placeholder_device(batch.account.id, snapshot.device_id, now)
                outcome = self._record_snapshot(snapshot, config)
                result = self._add_result(result, **outcome)
            for event in batch.events:
                device = device_map.get(event.device_id)
                if device is not None and not self._device_selected(device, config):
                    result = self._add_result(result, policy_skipped=1)
                    continue
                self._ensure_placeholder_device(batch.account.id, event.device_id, now)
                outcome = self._record_event(event, config)
                result = self._add_result(result, **outcome)
            if batch.cursor:
                self._record_cursor(batch.cursor)
            if batch.health:
                self._record_health(batch.health)
        return result

    @staticmethod
    def _add_result(result: IngestResult, **changes: int) -> IngestResult:
        values = result.__dict__ | {
            key: getattr(result, key) + value for key, value in changes.items()
        }
        return IngestResult(**values)

    @staticmethod
    def _device_selected(device: HomeDevice, config: SmartHomeConfig) -> bool:
        structures = config.selected_structure_ids
        rooms = config.selected_room_ids
        structure_selected = not structures or any(
            value in structures
            for value in (device.structure_id, f"{device.account_id}/{device.structure_id}")
        )
        room_selected = not rooms or any(
            value in rooms for value in (device.room_id, f"{device.account_id}/{device.room_id}")
        )
        return structure_selected and room_selected

    def _upsert_account(self, account: HomeAccount, now: datetime) -> None:
        existing = self.connection.execute(
            "SELECT provider_key FROM home_provider_accounts WHERE account_id = ?",
            (account.id,),
        ).fetchone()
        if existing is not None and str(existing["provider_key"]) != account.provider:
            raise ValueError("provider account ID cannot change provider")
        self.connection.execute(
            """
            INSERT INTO home_provider_accounts(
                account_id, provider_key, display_name, transport, keychain_item_ref,
                metadata_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(account_id) DO UPDATE SET
                provider_key = excluded.provider_key,
                display_name = excluded.display_name,
                transport = excluded.transport,
                keychain_item_ref = CASE
                    WHEN excluded.keychain_item_ref = ''
                    THEN home_provider_accounts.keychain_item_ref
                    ELSE excluded.keychain_item_ref
                END,
                metadata_json = excluded.metadata_json,
                is_active = 1,
                updated_at = excluded.updated_at
            """,
            (
                account.id,
                account.provider,
                account.display_name,
                account.transport,
                account.keychain_item_ref,
                _json(account.metadata),
                now.isoformat(),
                now.isoformat(),
            ),
        )

    def _upsert_device(self, device: HomeDevice, now: datetime) -> None:
        self.connection.execute(
            """
            INSERT INTO home_devices(
                account_id, provider_device_id, provider_structure_id, provider_room_id,
                name, device_type, online, raw_json, last_seen_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(account_id, provider_device_id) DO UPDATE SET
                provider_structure_id = excluded.provider_structure_id,
                provider_room_id = excluded.provider_room_id,
                name = excluded.name,
                device_type = excluded.device_type,
                online = excluded.online,
                raw_json = excluded.raw_json,
                last_seen_at = excluded.last_seen_at
            """,
            (
                device.account_id,
                device.provider_id,
                device.structure_id,
                device.room_id,
                device.name,
                device.device_type,
                None if device.online is None else int(device.online),
                _json(device.raw),
                now.isoformat(),
            ),
        )
        for capability in device.capabilities:
            normalized = (
                capability.normalized_key or normalize_state(capability.provider_key, None).key
            )
            self.connection.execute(
                """
                INSERT INTO home_capabilities(
                    account_id, provider_device_id, provider_capability_key, display_name,
                    normalized_capability_key, metadata_json, raw_json, last_seen_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(account_id, provider_device_id, provider_capability_key) DO UPDATE SET
                    display_name = excluded.display_name,
                    normalized_capability_key = coalesce(
                        excluded.normalized_capability_key,
                        home_capabilities.normalized_capability_key
                    ),
                    metadata_json = excluded.metadata_json,
                    raw_json = excluded.raw_json,
                    last_seen_at = excluded.last_seen_at
                """,
                (
                    device.account_id,
                    device.provider_id,
                    capability.provider_key,
                    capability.display_name or capability.provider_key,
                    normalized,
                    _json(capability.metadata),
                    _json(capability.raw),
                    now.isoformat(),
                ),
            )

    def _ensure_placeholder_device(self, account_id: str, device_id: str, now: datetime) -> None:
        self.connection.execute(
            """
            INSERT OR IGNORE INTO home_devices(
                account_id, provider_device_id, name, raw_json, last_seen_at
            ) VALUES (?, ?, ?, '{}', ?)
            """,
            (account_id, device_id, device_id, now.isoformat()),
        )

    def _record_snapshot(
        self, snapshot: HomeStateSnapshot, config: SmartHomeConfig
    ) -> dict[str, int]:
        selected_raw = {
            key: value
            for key, value in snapshot.raw_state.items()
            if capability_is_allowed(
                config.record_allowlist, snapshot.account_id, snapshot.device_id, key
            )
        }
        if not selected_raw:
            return {"policy_skipped": 1}
        normalized = {key: normalize_state(key, value).value for key, value in selected_raw.items()}
        effective, quality, skew = self._event_time(
            snapshot.occurred_at,
            snapshot.observed_at,
            snapshot.source,
            config.max_clock_skew_seconds,
        )
        numeric_only = all(
            is_numeric_measurement(value, normalize_state(key, value).key)
            for key, value in selected_raw.items()
        )
        if numeric_only:
            bucket = int(effective.timestamp()) // config.high_frequency_min_interval_seconds
            dedupe = f"coalesced:{snapshot.device_id}:{bucket}"
        else:
            dedupe = snapshot.provider_snapshot_id or _hash(
                snapshot.device_id, effective.isoformat(), selected_raw
            )
        now = datetime.now().astimezone().isoformat()
        existed = self.connection.execute(
            "SELECT 1 FROM home_state_snapshots WHERE account_id = ? AND dedupe_key = ?",
            (snapshot.account_id, dedupe),
        ).fetchone()
        self.connection.execute(
            """
            INSERT INTO home_state_snapshots(
                account_id, provider_device_id, provider_snapshot_id, dedupe_key,
                provider_occurred_at, observed_at, effective_at, timezone, time_quality,
                clock_skew_ms, source, raw_state_json, normalized_state_json,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(account_id, dedupe_key) DO UPDATE SET
                provider_occurred_at = excluded.provider_occurred_at,
                observed_at = excluded.observed_at,
                effective_at = excluded.effective_at,
                raw_state_json = excluded.raw_state_json,
                normalized_state_json = excluded.normalized_state_json,
                updated_at = excluded.updated_at
            """,
            (
                snapshot.account_id,
                snapshot.device_id,
                snapshot.provider_snapshot_id,
                dedupe,
                snapshot.occurred_at.isoformat() if snapshot.occurred_at else None,
                snapshot.observed_at.isoformat(),
                effective.isoformat(),
                snapshot.timezone,
                quality,
                skew,
                snapshot.source,
                _json(selected_raw),
                _json(normalized),
                now,
                now,
            ),
        )
        return {"coalesced": 1} if existed else {"snapshots_inserted": 1}

    def _record_event(self, event: HomeStateEvent, config: SmartHomeConfig) -> dict[str, int]:
        if not capability_is_allowed(
            config.record_allowlist, event.account_id, event.device_id, event.capability_key
        ):
            return {"policy_skipped": 1}
        normalized = normalize_state(event.capability_key, event.value)
        effective, quality, skew = self._event_time(
            event.occurred_at,
            event.observed_at,
            event.source,
            config.max_clock_skew_seconds,
        )
        dedupe = event.provider_event_id or _hash(
            event.device_id,
            event.capability_key,
            effective.isoformat(),
            event.value,
        )
        if self.connection.execute(
            "SELECT 1 FROM home_state_events WHERE account_id = ? AND dedupe_key = ?",
            (event.account_id, dedupe),
        ).fetchone():
            return {"duplicates_skipped": 1}
        latest = self.connection.execute(
            """
            SELECT id, raw_value_json, normalized_value_json, started_at
            FROM home_state_events
            WHERE account_id = ? AND provider_device_id = ? AND provider_capability_key = ?
            ORDER BY started_at DESC, id DESC LIMIT 1
            """,
            (event.account_id, event.device_id, event.capability_key),
        ).fetchone()
        raw_json = _json(event.value)
        if latest and latest["raw_value_json"] == raw_json:
            previous_time = datetime.fromisoformat(latest["started_at"])
            if abs((effective - previous_time).total_seconds()) <= config.debounce_seconds:
                return {"duplicates_skipped": 1}
            return self._save_event_snapshot_only(
                event,
                normalized.key,
                effective,
                quality,
                skew,
                config.high_frequency_min_interval_seconds,
            )
        if latest and is_numeric_measurement(event.value, normalized.key):
            previous_time = datetime.fromisoformat(latest["started_at"])
            if abs((effective - previous_time).total_seconds()) < (
                config.high_frequency_min_interval_seconds
            ):
                return self._save_event_snapshot_only(
                    event,
                    normalized.key,
                    effective,
                    quality,
                    skew,
                    config.high_frequency_min_interval_seconds,
                )
        now = datetime.now().astimezone().isoformat()
        self.connection.execute(
            """
            INSERT INTO home_capabilities(
                account_id, provider_device_id, provider_capability_key, display_name,
                normalized_capability_key, metadata_json, raw_json, last_seen_at
            ) VALUES (?, ?, ?, ?, ?, '{}', '{}', ?)
            ON CONFLICT(account_id, provider_device_id, provider_capability_key) DO UPDATE SET
                normalized_capability_key = coalesce(
                    home_capabilities.normalized_capability_key,
                    excluded.normalized_capability_key
                ),
                last_seen_at = excluded.last_seen_at
            """,
            (
                event.account_id,
                event.device_id,
                event.capability_key,
                event.capability_key,
                normalized.key,
                now,
            ),
        )
        if latest:
            self.connection.execute(
                "UPDATE home_state_events SET ended_at = ?, updated_at = ? WHERE id = ?",
                (effective.isoformat(), now, int(latest["id"])),
            )
        self.connection.execute(
            """
            INSERT INTO home_state_events(
                account_id, provider_device_id, provider_capability_key,
                normalized_capability_key, provider_event_id, dedupe_key,
                raw_value_json, normalized_value_json, previous_value_json, display_value,
                provider_occurred_at, observed_at, started_at, timezone, time_quality,
                clock_skew_ms, source, raw_payload_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event.account_id,
                event.device_id,
                event.capability_key,
                normalized.key,
                event.provider_event_id,
                dedupe,
                raw_json,
                _json(normalized.value),
                _json(event.previous_value) if event.previous_value is not None else None,
                normalized.display_value,
                event.occurred_at.isoformat() if event.occurred_at else None,
                event.observed_at.isoformat(),
                effective.isoformat(),
                event.timezone,
                quality,
                skew,
                event.source,
                _json(event.raw),
                now,
                now,
            ),
        )
        return {"events_inserted": 1}

    def _save_event_snapshot_only(
        self,
        event: HomeStateEvent,
        normalized_key: str | None,
        effective: datetime,
        quality: str,
        skew: int | None,
        bucket_seconds: int,
    ) -> dict[str, int]:
        snapshot = HomeStateSnapshot(
            account_id=event.account_id,
            device_id=event.device_id,
            occurred_at=event.occurred_at,
            observed_at=event.observed_at,
            timezone=event.timezone,
            source=event.source,
            raw_state={event.capability_key: event.value},
            normalized_state={normalized_key or event.capability_key: event.value},
        )
        bucket = int(effective.timestamp()) // bucket_seconds
        dedupe = f"event-coalesced:{event.device_id}:{event.capability_key}:{bucket}"
        now = datetime.now().astimezone().isoformat()
        self.connection.execute(
            """
            INSERT INTO home_state_snapshots(
                account_id, provider_device_id, dedupe_key, provider_occurred_at,
                observed_at, effective_at, timezone, time_quality, clock_skew_ms, source,
                raw_state_json, normalized_state_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(account_id, dedupe_key) DO UPDATE SET
                provider_occurred_at = excluded.provider_occurred_at,
                observed_at = excluded.observed_at,
                effective_at = excluded.effective_at,
                raw_state_json = excluded.raw_state_json,
                normalized_state_json = excluded.normalized_state_json,
                updated_at = excluded.updated_at
            """,
            (
                event.account_id,
                event.device_id,
                dedupe,
                event.occurred_at.isoformat() if event.occurred_at else None,
                event.observed_at.isoformat(),
                effective.isoformat(),
                snapshot.timezone,
                quality,
                skew,
                snapshot.source,
                _json(snapshot.raw_state),
                _json(snapshot.normalized_state),
                now,
                now,
            ),
        )
        return {"coalesced": 1}

    @staticmethod
    def _event_time(
        occurred_at: datetime | None,
        observed_at: datetime,
        source: str,
        max_clock_skew_seconds: int,
    ) -> tuple[datetime, str, int | None]:
        if observed_at.tzinfo is None or (occurred_at is not None and occurred_at.tzinfo is None):
            raise ValueError("home state timestamps must include a UTC offset")
        if occurred_at is None:
            return observed_at, "observer", None
        skew = round((observed_at - occurred_at).total_seconds() * 1_000)
        if source == "history":
            return occurred_at, "provider_history", skew
        if abs(skew) <= max_clock_skew_seconds * 1_000:
            return occurred_at, "provider", skew
        return observed_at, "observer_clock_skew_fallback", skew

    def _record_cursor(self, cursor: SyncCursor) -> None:
        self.connection.execute(
            """
            INSERT INTO home_sync_cursors(account_id, cursor_type, cursor_value, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(account_id, cursor_type) DO UPDATE SET
                cursor_value = excluded.cursor_value,
                updated_at = excluded.updated_at
            """,
            (cursor.account_id, cursor.cursor_type, cursor.value, cursor.updated_at.isoformat()),
        )

    def _record_health(self, health: ConnectionHealth) -> None:
        self.connection.execute(
            """
            UPDATE home_provider_accounts SET
                health_status = ?, health_message = ?, requires_reauthorization = ?,
                last_checked_at = ?, last_success_at = ?, retry_at = ?, updated_at = ?
            WHERE account_id = ?
            """,
            (
                health.status,
                health.message,
                int(health.requires_reauthorization),
                health.checked_at.isoformat(),
                health.last_success_at.isoformat() if health.last_success_at else None,
                health.retry_at.isoformat() if health.retry_at else None,
                health.checked_at.isoformat(),
                health.account_id,
            ),
        )
        if health.status in {"error", "degraded", "reauthorization_required"} and health.message:
            self.connection.execute(
                """
                INSERT INTO home_connection_errors(
                    account_id, message, retryable, occurred_at
                ) VALUES (?, ?, ?, ?)
                """,
                (
                    health.account_id,
                    health.message,
                    int(not health.requires_reauthorization),
                    health.checked_at.isoformat(),
                ),
            )
        elif health.status == "connected":
            self.connection.execute(
                """
                UPDATE home_connection_errors SET resolved_at = ?
                WHERE account_id = ? AND resolved_at IS NULL
                """,
                (health.checked_at.isoformat(), health.account_id),
            )

    def record_connection_failure(
        self,
        account: HomeAccount,
        error: Exception,
        checked_at: datetime,
        retry_at: datetime,
    ) -> None:
        """Persist a safe provider failure without copying exception secrets."""
        _validate_account_metadata(account)
        error_code = type(error).__name__[:120]
        message = f"同步失敗（{error_code}）"
        with self.connection:
            self._upsert_account(account, checked_at)
            self.connection.execute(
                """
                UPDATE home_provider_accounts SET
                    health_status = 'error', health_message = ?,
                    requires_reauthorization = 0, last_checked_at = ?,
                    retry_at = ?, updated_at = ?
                WHERE account_id = ?
                """,
                (
                    message,
                    checked_at.isoformat(),
                    retry_at.isoformat(),
                    checked_at.isoformat(),
                    account.id,
                ),
            )
            self.connection.execute(
                """
                INSERT INTO home_connection_errors(
                    account_id, error_code, message, retryable, occurred_at
                ) VALUES (?, ?, ?, 1, ?)
                """,
                (account.id, error_code, message, checked_at.isoformat()),
            )

    def account_statuses(self) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            """
            SELECT account_id, provider_key, display_name, transport, health_status,
                   health_message, requires_reauthorization, last_checked_at,
                   last_success_at, retry_at
            FROM home_provider_accounts
            WHERE is_active = 1
            ORDER BY display_name, account_id
            """
        ).fetchall()
        return [
            {
                "id": str(row["account_id"]),
                "provider": str(row["provider_key"]),
                "display_name": str(row["display_name"]),
                "transport": str(row["transport"]),
                "status": str(row["health_status"]),
                "message": str(row["health_message"]),
                "requires_reauthorization": bool(row["requires_reauthorization"]),
                "last_checked_at": row["last_checked_at"],
                "last_success_at": row["last_success_at"],
                "retry_at": row["retry_at"],
            }
            for row in rows
        ]

    def cursor(self, account_id: str, cursor_type: str = "sync") -> SyncCursor | None:
        row = self.connection.execute(
            """
            SELECT cursor_value, updated_at FROM home_sync_cursors
            WHERE account_id = ? AND cursor_type = ?
            """,
            (account_id, cursor_type),
        ).fetchone()
        if row is None:
            return None
        return SyncCursor(
            account_id=account_id,
            cursor_type=cursor_type,
            value=str(row["cursor_value"]),
            updated_at=datetime.fromisoformat(str(row["updated_at"])),
        )

    def device_statuses(self, config: SmartHomeConfig) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            """
            SELECT d.account_id, d.provider_device_id, d.name, d.device_type, d.online,
                   d.last_seen_at, s.name AS structure_name, r.name AS room_name,
                   c.provider_capability_key, c.display_name AS capability_name,
                   c.normalized_capability_key
            FROM home_devices d
            JOIN home_provider_accounts a
              ON a.account_id = d.account_id
             AND a.is_active = 1
            LEFT JOIN home_structures s
              ON s.account_id = d.account_id
             AND s.provider_structure_id = d.provider_structure_id
            LEFT JOIN home_rooms r
              ON r.account_id = d.account_id
             AND r.provider_room_id = d.provider_room_id
            LEFT JOIN home_capabilities c
              ON c.account_id = d.account_id
             AND c.provider_device_id = d.provider_device_id
            ORDER BY s.name, r.name, d.name, c.display_name
            """
        ).fetchall()
        devices: dict[str, dict[str, Any]] = {}
        for row in rows:
            key = selection_key(str(row["account_id"]), str(row["provider_device_id"]))
            device = devices.setdefault(
                key,
                {
                    "selection_key": key,
                    "account_id": str(row["account_id"]),
                    "device_id": str(row["provider_device_id"]),
                    "name": str(row["name"]),
                    "device_type": str(row["device_type"]),
                    "online": None if row["online"] is None else bool(row["online"]),
                    "last_seen_at": str(row["last_seen_at"]),
                    "structure_name": str(row["structure_name"] or "未分類住家"),
                    "room_name": str(row["room_name"] or "未分類房間"),
                    "capabilities": [],
                },
            )
            capability_key = row["provider_capability_key"]
            if capability_key is None:
                continue
            capability = str(capability_key)
            device["capabilities"].append(
                {
                    "key": capability,
                    "name": str(row["capability_name"] or capability),
                    "normalized_key": row["normalized_capability_key"],
                    "record_enabled": capability_is_allowed(
                        config.record_allowlist,
                        str(row["account_id"]),
                        str(row["provider_device_id"]),
                        capability,
                    ),
                    "summary_enabled": capability_is_allowed(
                        config.summary_allowlist,
                        str(row["account_id"]),
                        str(row["provider_device_id"]),
                        capability,
                    ),
                }
            )
        return list(devices.values())

    def events_for_date(self, target: date) -> list[sqlite3.Row]:
        day = target.isoformat()
        return self.connection.execute(
            """
            SELECT e.*, d.name AS device_name, d.device_type,
                   r.name AS room_name, a.provider_key, a.display_name AS account_name
            FROM home_state_events e
            JOIN home_devices d
              ON d.account_id = e.account_id
             AND d.provider_device_id = e.provider_device_id
            JOIN home_provider_accounts a ON a.account_id = e.account_id
            LEFT JOIN home_rooms r
              ON r.account_id = d.account_id
             AND r.provider_room_id = d.provider_room_id
            WHERE substr(e.started_at, 1, 10) = ? OR substr(e.ended_at, 1, 10) = ?
            ORDER BY e.started_at, e.id
            """,
            (day, day),
        ).fetchall()

    def disconnect_account(self, account_id: str, when: datetime | None = None) -> bool:
        when = when or datetime.now().astimezone()
        with self.connection:
            cursor = self.connection.execute(
                """
                UPDATE home_provider_accounts SET
                    health_status = 'disconnected',
                    health_message = '已由使用者移除連線；本機歷史事件保留',
                    requires_reauthorization = 0,
                    is_active = 0,
                    keychain_item_ref = '',
                    updated_at = ?
                WHERE account_id = ?
                """,
                (when.isoformat(), account_id),
            )
        return cursor.rowcount == 1

    @property
    def schema_version(self) -> int:
        row = self.connection.execute("SELECT max(version) FROM home_schema_meta").fetchone()
        return int(row[0] or 0)
