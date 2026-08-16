from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta

from family_recorder.config import SmartHomeConfig, StorageConfig
from family_recorder.home.models import HomeProvider, HomeSyncBatch
from family_recorder.home.retry import RetryPolicy, retry_async
from family_recorder.home.store import HomeStateStore, IngestResult


class HomeSyncService:
    """Shared polling/subscription ingestion with retry and provider fault isolation."""

    def __init__(self, storage: StorageConfig, config: SmartHomeConfig) -> None:
        self.storage = storage
        self.config = config
        self.retry_policy = RetryPolicy(
            initial_seconds=config.retry_initial_seconds,
            maximum_seconds=config.retry_max_seconds,
            max_attempts=config.retry_max_attempts,
        )

    async def sync_once(
        self,
        provider: HomeProvider,
        *,
        sleep: Callable[[float], Awaitable[None]] | None = None,
    ) -> IngestResult:
        with HomeStateStore(self.storage) as store:
            cursor = store.cursor(provider.account.id)

        async def operation() -> HomeSyncBatch:
            return await provider.sync(cursor)

        try:
            if sleep is None:
                batch = await retry_async(operation, self.retry_policy)
            else:
                batch = await retry_async(operation, self.retry_policy, sleep=sleep)
        except Exception as exc:
            checked_at = datetime.now().astimezone()
            retry_at = checked_at + timedelta(seconds=self.config.retry_max_seconds)
            with HomeStateStore(self.storage) as store:
                store.record_connection_failure(
                    provider.account,
                    exc,
                    checked_at,
                    retry_at,
                )
            raise
        with HomeStateStore(self.storage) as store:
            return store.record_batch(batch, self.config)

    async def consume(
        self,
        provider: HomeProvider,
        *,
        maximum_batches: int | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> int:
        count = 0
        failed_attempts = 0
        while maximum_batches is None or count < maximum_batches:
            with HomeStateStore(self.storage) as store:
                cursor = store.cursor(provider.account.id)
            try:
                async for batch in provider.subscribe(cursor):
                    with HomeStateStore(self.storage) as store:
                        store.record_batch(batch, self.config)
                    count += 1
                    failed_attempts = 0
                    if maximum_batches is not None and count >= maximum_batches:
                        return count
                return count
            except Exception as exc:
                failed_attempts += 1
                delay = self.retry_policy.delay_for(failed_attempts)
                checked_at = datetime.now().astimezone()
                with HomeStateStore(self.storage) as store:
                    store.record_connection_failure(
                        provider.account,
                        exc,
                        checked_at,
                        checked_at + timedelta(seconds=delay),
                    )
                if failed_attempts >= self.retry_policy.max_attempts:
                    raise
                await sleep(delay)
        return count
