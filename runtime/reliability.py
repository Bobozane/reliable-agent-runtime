from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from dataclasses import dataclass
from typing import Callable, TypeVar


T = TypeVar("T")


class ToolCallError(RuntimeError):
    pass


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 3
    timeout_seconds: float = 0.25
    backoff_seconds: float = 0.01


@dataclass
class RetryResult:
    value: T | None
    attempts: int
    used_fallback: bool = False
    error: str | None = None


def call_with_retry(
    operation: Callable[[], T],
    policy: RetryPolicy,
    *,
    fallback: Callable[[Exception], T] | None = None,
) -> RetryResult[T]:
    last_error: Exception | None = None
    for attempt in range(1, policy.max_attempts + 1):
        try:
            pool = ThreadPoolExecutor(max_workers=1)
            future = pool.submit(operation)
            try:
                return RetryResult(value=future.result(timeout=policy.timeout_seconds), attempts=attempt)
            finally:
                # A timed-out tool must not hold the workflow hostage while its
                # worker finishes. The tool boundary is already considered failed.
                pool.shutdown(wait=False, cancel_futures=True)
        except (FutureTimeoutError, TimeoutError) as exc:
            last_error = TimeoutError(f"operation timed out after {policy.timeout_seconds:.2f}s")
        except Exception as exc:  # tool boundaries must convert failures into data
            last_error = exc
        if attempt < policy.max_attempts:
            time.sleep(policy.backoff_seconds * (2 ** (attempt - 1)))
    if fallback is not None and last_error is not None:
        try:
            return RetryResult(value=fallback(last_error), attempts=policy.max_attempts, used_fallback=True, error=str(last_error))
        except Exception as fallback_error:
            last_error = fallback_error
    return RetryResult(value=None, attempts=policy.max_attempts, error=str(last_error) if last_error else "unknown failure")
