import asyncio
import json
import sqlite3
from datetime import date
from pathlib import Path

import pytest

from family_recorder.config import SmartHomeConfig, StorageConfig
from family_recorder.home.bridge import CompanionBridgeError, parse_companion_payload
from family_recorder.home.fake import FakeHomeProvider
from family_recorder.home.models import HomeAccount, HomeSyncBatch
from family_recorder.home.normalization import normalize_state
from family_recorder.home.retry import RetryPolicy, retry_async
from family_recorder.home.service import HomeSyncService
from family_recorder.home.store import HomeStateStore
from family_recorder.home.timeline import render_home_timeline

FIXTURE = Path(__file__).parent / "fixtures" / "home" / "fake_home.json"


def _config() -> SmartHomeConfig:
    return SmartHomeConfig(
        enabled=True,
        record_allowlist={
            "fake-home/coffee-maker": ("on_off.on", "vendor.secret_mode"),
            "fake-home/extractor-hood": (
                "on_off.on",
                "fan_control.percent_current",
            ),
        },
        summary_allowlist={
            "fake-home/coffee-maker": ("on_off.on",),
            "fake-home/extractor-hood": ("on_off.on",),
        },
    )


def test_normalization_preserves_unknown_provider_value() -> None:
    raw = {"provider_code": 91, "mode": "turbo_secret"}

    normalized = normalize_state("vendor.secret_mode", raw)

    assert normalized.key is None
    assert normalized.value == raw


def test_home_schema_migrates_an_existing_listener_database(tmp_path: Path) -> None:
    database = tmp_path / "listener.sqlite3"
    connection = sqlite3.connect(database)
    connection.execute("CREATE TABLE segments(id INTEGER PRIMARY KEY)")
    connection.commit()
    connection.close()

    with HomeStateStore(StorageConfig(data_dir=tmp_path)) as store:
        tables = {
            row[0]
            for row in store.connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        indexes = {
            row[0]
            for row in store.connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index'"
            ).fetchall()
        }
        assert store.schema_version == 2

    assert "segments" in tables
    assert {
        "home_provider_accounts",
        "home_devices",
        "home_capabilities",
        "home_state_snapshots",
        "home_state_events",
        "home_sync_cursors",
        "home_connection_errors",
    }.issubset(tables)
    assert "idx_home_events_device_capability_time" in indexes


def test_home_schema_v1_account_table_upgrades_without_losing_rows(tmp_path: Path) -> None:
    database = tmp_path / "listener.sqlite3"
    connection = sqlite3.connect(database)
    connection.executescript(
        """
        CREATE TABLE home_schema_meta(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL);
        INSERT INTO home_schema_meta VALUES (1, '2026-08-16T00:00:00+08:00');
        CREATE TABLE home_provider_accounts (
            account_id TEXT PRIMARY KEY,
            provider_key TEXT NOT NULL,
            display_name TEXT NOT NULL,
            transport TEXT NOT NULL,
            keychain_item_ref TEXT NOT NULL DEFAULT '',
            metadata_json TEXT NOT NULL DEFAULT '{}',
            health_status TEXT NOT NULL DEFAULT 'disconnected',
            health_message TEXT NOT NULL DEFAULT '',
            requires_reauthorization INTEGER NOT NULL DEFAULT 0,
            last_checked_at TEXT,
            last_success_at TEXT,
            retry_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        INSERT INTO home_provider_accounts(
            account_id, provider_key, display_name, transport, created_at, updated_at
        ) VALUES ('existing', 'fake', '既有連線', 'fake', 'old', 'old');
        """
    )
    connection.commit()
    connection.close()

    with HomeStateStore(StorageConfig(data_dir=tmp_path)) as store:
        row = store.connection.execute(
            "SELECT account_id, is_active FROM home_provider_accounts"
        ).fetchone()
        version = store.schema_version

    assert tuple(row) == ("existing", 1)
    assert version == 2


def test_fake_provider_ingests_dedupes_merges_and_retains_raw_unknown_state(
    tmp_path: Path,
) -> None:
    provider = FakeHomeProvider.from_path(FIXTURE)
    storage = StorageConfig(data_dir=tmp_path)
    service = HomeSyncService(storage, _config())

    first = asyncio.run(service.sync_once(provider))
    second = asyncio.run(service.sync_once(provider))

    assert first.events_inserted == 6
    assert first.coalesced == 2
    assert second.duplicates_skipped == 6
    with HomeStateStore(storage) as store:
        unknown = store.connection.execute(
            """
            SELECT normalized_capability_key, raw_value_json, raw_payload_json
            FROM home_state_events
            WHERE provider_capability_key = 'vendor.secret_mode'
            """
        ).fetchone()
        coffee = store.connection.execute(
            """
            SELECT started_at, ended_at, time_quality
            FROM home_state_events
            WHERE provider_device_id = 'coffee-maker'
              AND normalized_capability_key = 'on_off'
              AND normalized_value_json = 'true'
            """
        ).fetchone()
        snapshots = store.connection.execute(
            "SELECT count(*) FROM home_state_snapshots"
        ).fetchone()[0]
        cursor = store.cursor("fake-home")
        account = store.account_statuses()[0]
    assert unknown[0] is None
    assert json.loads(unknown[1]) == {"mode": "turbo_secret", "provider_code": 91}
    assert "vendor.secret_mode" in unknown[2]
    assert coffee[0] == "2026-08-16T07:31:00+08:00"
    assert coffee[1] == "2026-08-16T07:36:00+08:00"
    assert coffee[2] == "provider"
    assert snapshots == 1
    assert cursor is not None and cursor.value == "fixture-cursor-1"
    assert account["status"] == "connected"


def test_summary_timeline_uses_only_summary_allowlist(tmp_path: Path) -> None:
    provider = FakeHomeProvider.from_path(FIXTURE)
    storage = StorageConfig(data_dir=tmp_path)
    asyncio.run(HomeSyncService(storage, _config()).sync_once(provider))

    timeline = render_home_timeline(storage, _config(), date(2026, 8, 16))

    assert "07:31–07:36｜廚房／咖啡機運作" in timeline
    assert "19:08–19:26｜廚房／抽油煙機運作" in timeline
    assert "turbo_secret" not in timeline
    assert "provider_code" not in timeline
    assert "風速" not in timeline


def test_disconnect_hides_active_account_but_retains_local_history(tmp_path: Path) -> None:
    storage = StorageConfig(data_dir=tmp_path)
    asyncio.run(HomeSyncService(storage, _config()).sync_once(FakeHomeProvider.from_path(FIXTURE)))

    with HomeStateStore(storage) as store:
        assert store.disconnect_account("fake-home") is True
        accounts = store.account_statuses()
        event_count = store.connection.execute("SELECT count(*) FROM home_state_events").fetchone()[
            0
        ]

    assert accounts == []
    assert event_count == 6


def test_clock_skew_falls_back_to_observer_time(tmp_path: Path) -> None:
    document = json.loads(FIXTURE.read_text(encoding="utf-8"))
    document["events"] = [dict(document["events"][0])]
    document["events"][0]["event_id"] = "skewed"
    document["events"][0]["observed_at"] = "2026-08-16T08:31:00+08:00"
    provider = FakeHomeProvider(document)
    storage = StorageConfig(data_dir=tmp_path)

    asyncio.run(HomeSyncService(storage, _config()).sync_once(provider))

    with HomeStateStore(storage) as store:
        event = store.connection.execute(
            "SELECT started_at, time_quality, clock_skew_ms FROM home_state_events"
        ).fetchone()
    assert event[0] == "2026-08-16T08:31:00+08:00"
    assert event[1] == "observer_clock_skew_fallback"
    assert event[2] == 3_600_000


def test_retry_uses_exponential_backoff_without_network() -> None:
    attempts = 0
    delays: list[float] = []

    async def operation() -> str:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise RuntimeError("temporary")
        return "ok"

    async def fake_sleep(delay: float) -> None:
        delays.append(delay)

    result = asyncio.run(
        retry_async(
            operation,
            RetryPolicy(initial_seconds=1, maximum_seconds=10, max_attempts=4),
            sleep=fake_sleep,
        )
    )

    assert result == "ok"
    assert delays == [1, 2]


def test_sync_failure_is_retried_and_stored_without_exception_secrets(tmp_path: Path) -> None:
    provider = FakeHomeProvider.from_path(FIXTURE)
    attempts = 0
    delays: list[float] = []

    async def failing_sync(_cursor: object = None) -> object:
        nonlocal attempts
        attempts += 1
        raise RuntimeError("Bearer secret-token-must-not-be-stored")

    async def fake_sleep(delay: float) -> None:
        delays.append(delay)

    provider.sync = failing_sync  # type: ignore[method-assign]
    config = SmartHomeConfig(
        enabled=True,
        retry_initial_seconds=1,
        retry_max_seconds=4,
        retry_max_attempts=3,
    )

    with pytest.raises(RuntimeError, match="must-not-be-stored"):
        asyncio.run(
            HomeSyncService(StorageConfig(data_dir=tmp_path), config).sync_once(
                provider,
                sleep=fake_sleep,
            )
        )

    with HomeStateStore(StorageConfig(data_dir=tmp_path)) as store:
        account = store.account_statuses()[0]
        error = store.connection.execute(
            "SELECT error_code, message, retryable FROM home_connection_errors"
        ).fetchone()
    assert attempts == 3
    assert delays == [1, 2]
    assert account["status"] == "error"
    assert account["retry_at"]
    assert "secret-token" not in account["message"]
    assert tuple(error) == (
        "RuntimeError",
        "同步失敗（RuntimeError）",
        1,
    )


def test_subscription_reconnects_with_exponential_backoff(tmp_path: Path) -> None:
    class FlakySubscriptionProvider(FakeHomeProvider):
        calls = 0

        async def subscribe(self, cursor=None):
            del cursor
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("temporary subscription failure")
            yield self._batch

    provider = FlakySubscriptionProvider(json.loads(FIXTURE.read_text(encoding="utf-8")))
    delays: list[float] = []

    async def fake_sleep(delay: float) -> None:
        delays.append(delay)

    count = asyncio.run(
        HomeSyncService(StorageConfig(data_dir=tmp_path), _config()).consume(
            provider,
            maximum_batches=1,
            sleep=fake_sleep,
        )
    )

    with HomeStateStore(StorageConfig(data_dir=tmp_path)) as store:
        status = store.account_statuses()[0]
        unresolved = store.connection.execute(
            "SELECT count(*) FROM home_connection_errors WHERE resolved_at IS NULL"
        ).fetchone()[0]
    assert count == 1
    assert provider.calls == 2
    assert delays == [2.0]
    assert status["status"] == "connected"
    assert unresolved == 0


def test_companion_contract_rejects_credentials() -> None:
    document = json.loads(FIXTURE.read_text(encoding="utf-8"))
    document["schema_version"] = 1
    document["account"]["provider"] = "google_home"
    document["account"]["transport"] = "companion_bridge"
    document["access_token"] = "must-not-cross-bridge"

    with pytest.raises(CompanionBridgeError, match="credentials"):
        parse_companion_payload(document)


def test_companion_contract_rejects_nested_credentials() -> None:
    document = json.loads(FIXTURE.read_text(encoding="utf-8"))
    document["schema_version"] = 1
    document["account"]["provider"] = "google_home"
    document["account"]["transport"] = "companion_bridge"
    document["account"]["metadata"]["oauth"] = {"refresh-token": "must-not-cross-bridge"}

    with pytest.raises(CompanionBridgeError, match="credentials"):
        parse_companion_payload(document)


def test_companion_contract_cannot_choose_mac_keychain_item() -> None:
    document = json.loads(FIXTURE.read_text(encoding="utf-8"))
    document["schema_version"] = 1
    document["account"]["provider"] = "google_home"
    document["account"]["transport"] = "companion_bridge"
    document["account"]["keychain_item_ref"] = "attacker-selected-item"

    with pytest.raises(CompanionBridgeError, match="Keychain"):
        parse_companion_payload(document)


def test_store_rejects_secrets_hidden_in_account_metadata(tmp_path: Path) -> None:
    account = HomeAccount(
        id="unsafe",
        provider="fake",
        display_name="Unsafe",
        transport="fake",
        metadata={"nested": {"client_secret": "must-use-keychain"}},
    )

    with (
        HomeStateStore(StorageConfig(data_dir=tmp_path)) as store,
        pytest.raises(ValueError, match="credentials"),
    ):
        store.record_batch(HomeSyncBatch(account=account), SmartHomeConfig(enabled=True))


def test_account_id_cannot_silently_change_provider(tmp_path: Path) -> None:
    config = SmartHomeConfig(enabled=True)
    first = HomeAccount("same-id", "google_home", "Google", "companion_bridge")
    conflicting = HomeAccount("same-id", "apple_home", "Apple", "companion_bridge")

    with (
        HomeStateStore(StorageConfig(data_dir=tmp_path)) as store,
        pytest.raises(ValueError, match="cannot change provider"),
    ):
        store.record_batch(HomeSyncBatch(account=first), config)
        store.record_batch(HomeSyncBatch(account=conflicting), config)
