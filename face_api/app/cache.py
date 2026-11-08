"""A tiny in-memory cache with a time limit, so repeated page views do not each wake the Databricks warehouse
(the free tier has a daily compute limit). One copy per server instance; entries expire on their own."""
from __future__ import annotations

import time
from typing import Callable


class TTLCache:
    def __init__(self, ttl: float, max_items: int = 256, clock: Callable[[], float] = time.monotonic):
        self.ttl, self.max_items, self.clock = ttl, max_items, clock
        self._data: dict = {}

    def get(self, key, make: Callable[[], object]):
        """The cached value for `key`, or `make()` stored for `ttl` seconds. Errors from `make()` are never cached."""
        now = self.clock()
        hit = self._data.get(key)
        if hit is not None and now < hit[0]:
            return hit[1]
        value = make()
        if len(self._data) >= self.max_items:
            self._data = {k: v for k, v in self._data.items() if v[0] > now}
            if len(self._data) >= self.max_items:
                self._data.clear()
        self._data[key] = (now + self.ttl, value)
        return value

    def clear(self) -> None:
        self._data.clear()
