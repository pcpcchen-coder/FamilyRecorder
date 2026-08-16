from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class RetryPolicy:
    initial_seconds: float = 2.0
    maximum_seconds: float = 300.0
    max_attempts: int = 5

    def delay_for(self, failed_attempt: int) -> float:
        return min(self.maximum_seconds, self.initial_seconds * (2 ** (failed_attempt - 1)))


async def retry_async(
    operation: Callable[[], Awaitable[T]],
    policy: RetryPolicy,
    *,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> T:
    error: Exception | None = None
    for attempt in range(1, policy.max_attempts + 1):
        try:
            return await operation()
        except Exception as exc:  # provider errors are intentionally isolated here
            error = exc
            if attempt == policy.max_attempts:
                break
            await sleep(policy.delay_for(attempt))
    assert error is not None
    raise error
