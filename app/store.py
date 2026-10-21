"""Storage for runs, quarantined requests, feedback and rate-limit counters.

STORE_BACKEND=memory  - one process only (local development on Windows, no Docker)
STORE_BACKEND=redis   - shared between the API and any number of workers (Docker)
"""

from __future__ import annotations

import json
import os
import threading
import time


class MemoryStore:
    def __init__(self):
        self._kv, self._lists, self._counters, self._lock = {}, {}, {}, threading.Lock()

    def set_json(self, key, value, ttl=None):
        with self._lock:
            self._kv[key] = json.dumps(value, default=str)

    def get_json(self, key):
        v = self._kv.get(key)
        return json.loads(v) if v else None

    def push(self, key, value, max_len=1000):
        with self._lock:
            lst = self._lists.setdefault(key, [])
            lst.insert(0, json.dumps(value, default=str))
            del lst[max_len:]

    def list(self, key, n=50):
        return [json.loads(x) for x in self._lists.get(key, [])[:n]]

    def incr(self, key, ttl):
        with self._lock:
            count, expires = self._counters.get(key, (0, 0.0))
            if time.time() > expires:
                count, expires = 0, time.time() + ttl
            self._counters[key] = (count + 1, expires)
            return count + 1

    def ping(self):
        return True


class RedisStore:
    def __init__(self, url):
        import redis
        self.r = redis.Redis.from_url(url, decode_responses=True)

    def set_json(self, key, value, ttl=None):
        self.r.set(key, json.dumps(value, default=str), ex=ttl)

    def get_json(self, key):
        v = self.r.get(key)
        return json.loads(v) if v else None

    def push(self, key, value, max_len=1000):
        p = self.r.pipeline()
        p.lpush(key, json.dumps(value, default=str))
        p.ltrim(key, 0, max_len - 1)
        p.execute()

    def list(self, key, n=50):
        return [json.loads(x) for x in self.r.lrange(key, 0, n - 1)]

    def incr(self, key, ttl):
        p = self.r.pipeline()
        p.incr(key)
        p.expire(key, ttl, nx=True)
        return p.execute()[0]

    def ping(self):
        return self.r.ping()


def make_store():
    backend = os.getenv("STORE_BACKEND", "memory")
    if backend == "redis":
        return RedisStore(os.getenv("REDIS_URL", "redis://localhost:6379/0"))
    return MemoryStore()


STORE = make_store()
RUN_TTL_S = int(os.getenv("RUN_TTL_S", str(7 * 24 * 3600)))