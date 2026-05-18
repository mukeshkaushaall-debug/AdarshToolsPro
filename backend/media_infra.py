"""Small production helpers for public media API traffic.

The backend intentionally avoids external queue dependencies so it can run on a
single VPS or Railway container. These primitives keep failures bounded and make
the service degrade predictably under load.
"""

from __future__ import annotations

import logging
import os
import threading
import time
import uuid
from collections import OrderedDict, deque
from dataclasses import dataclass
from typing import Any, Callable

try:
    from flask import g, has_request_context
except Exception:  # pragma: no cover - helpers also work outside Flask
    g = None

    def has_request_context() -> bool:
        return False


def env_int(name: str, default: int, minimum: int = 0, maximum: int | None = None) -> int:
    try:
        value = int(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        value = default
    value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return value


def configure_logging(app: Any) -> None:
    level_name = os.environ.get("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s request_id=%(request_id)s %(message)s",
    )

    class RequestIdFilter(logging.Filter):
        def filter(self, record: logging.LogRecord) -> bool:
            if not hasattr(record, "request_id"):
                record.request_id = getattr(g, "request_id", "-") if has_request_context() else "-"
            return True

    for handler in logging.getLogger().handlers:
        handler.addFilter(RequestIdFilter())
    app.logger.setLevel(level)


def make_request_id() -> str:
    return uuid.uuid4().hex[:16]


class TTLCache:
    def __init__(self, ttl_seconds: int, max_items: int = 512):
        self.ttl_seconds = ttl_seconds
        self.max_items = max(1, max_items)
        self._items: OrderedDict[str, tuple[float, Any]] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: str) -> Any:
        now = time.time()
        with self._lock:
            item = self._items.get(key)
            if not item:
                return None
            created_at, value = item
            if now - created_at > self.ttl_seconds:
                self._items.pop(key, None)
                return None
            self._items.move_to_end(key)
            return value

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self._items[key] = (time.time(), value)
            self._items.move_to_end(key)
            while len(self._items) > self.max_items:
                self._items.popitem(last=False)


class SlidingWindowRateLimiter:
    def __init__(self, limit: int, window_seconds: int = 60):
        self.limit = max(1, limit)
        self.window_seconds = max(1, window_seconds)
        self._events: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str, cost: int = 1) -> tuple[bool, int]:
        now = time.time()
        cutoff = now - self.window_seconds
        with self._lock:
            events = self._events.setdefault(key, deque())
            while events and events[0] < cutoff:
                events.popleft()
            if len(events) + cost > self.limit:
                retry_after = max(1, int(events[0] + self.window_seconds - now)) if events else self.window_seconds
                return False, retry_after
            for _ in range(cost):
                events.append(now)
            return True, 0


class WorkGate:
    def __init__(self, capacity: int, wait_seconds: float):
        self.capacity = max(1, capacity)
        self.wait_seconds = max(0.0, wait_seconds)
        self._semaphore = threading.BoundedSemaphore(self.capacity)

    def acquire(self) -> bool:
        return self._semaphore.acquire(timeout=self.wait_seconds)

    def release(self) -> None:
        try:
            self._semaphore.release()
        except ValueError:
            pass


@dataclass
class CircuitState:
    failures: int = 0
    opened_at: float = 0.0


class CircuitBreaker:
    def __init__(self, failure_threshold: int = 3, cooldown_seconds: int = 120):
        self.failure_threshold = max(1, failure_threshold)
        self.cooldown_seconds = max(1, cooldown_seconds)
        self._states: dict[str, CircuitState] = {}
        self._lock = threading.Lock()

    def available(self, key: str) -> bool:
        with self._lock:
            state = self._states.get(key)
            if not state or state.failures < self.failure_threshold:
                return True
            if time.time() - state.opened_at >= self.cooldown_seconds:
                self._states.pop(key, None)
                return True
            return False

    def success(self, key: str) -> None:
        with self._lock:
            self._states.pop(key, None)

    def failure(self, key: str) -> None:
        with self._lock:
            state = self._states.setdefault(key, CircuitState())
            state.failures += 1
            if state.failures >= self.failure_threshold:
                state.opened_at = time.time()


def retry_call(
    func: Callable[[], Any],
    *,
    attempts: int = 3,
    base_delay: float = 0.35,
    retryable: tuple[type[BaseException], ...] = (Exception,),
) -> Any:
    last_error: BaseException | None = None
    for index in range(max(1, attempts)):
        try:
            return func()
        except retryable as error:
            last_error = error
            if index == attempts - 1:
                break
            time.sleep(base_delay * (2**index))
    if last_error:
        raise last_error
    return None
