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
            expires = time.monotonic() + ttl if ttl is not None else None
            self._kv[key] = (json.dumps(value, default=str), expires)

    def _get_json_locked(self, key):
        entry = self._kv.get(key)
        if entry is None:
            return None
        raw, expires = entry
        if expires is not None and time.monotonic() >= expires:
            del self._kv[key]
            return None
        return json.loads(raw)

    def get_json(self, key):
        with self._lock:
            return self._get_json_locked(key)

    def create_run_if_absent(self, cache_key, run_key, run_id, record, cache_ttl, run_ttl):
        with self._lock:
            if self._get_json_locked(cache_key) is not None:
                return False
            self._kv[cache_key] = (json.dumps(run_id), time.monotonic() + cache_ttl)
            self._kv[run_key] = (json.dumps(record, default=str), time.monotonic() + run_ttl)
            return True

    def replace_run_if_value(self, cache_key, expected, run_key, run_id, record, cache_ttl, run_ttl):
        with self._lock:
            if self._get_json_locked(cache_key) != expected:
                return False
            self._kv[cache_key] = (json.dumps(run_id), time.monotonic() + cache_ttl)
            self._kv[run_key] = (json.dumps(record, default=str), time.monotonic() + run_ttl)
            return True

    def delete_json_if_value(self, key, expected):
        with self._lock:
            if self._get_json_locked(key) != expected:
                return False
            self._kv.pop(key, None)
            return True

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

    def create_run_if_absent(self, cache_key, run_key, run_id, record, cache_ttl, run_ttl):
        script = """
        if redis.call('EXISTS', KEYS[1]) == 1 then return 0 end
        redis.call('SET', KEYS[1], ARGV[1], 'EX', ARGV[3])
        redis.call('SET', KEYS[2], ARGV[2], 'EX', ARGV[4])
        return 1
        """
        return bool(self.r.eval(script, 2, cache_key, run_key, json.dumps(run_id),
                                json.dumps(record, default=str), int(cache_ttl), int(run_ttl)))

    def replace_run_if_value(self, cache_key, expected, run_key, run_id, record, cache_ttl, run_ttl):
        script = """
        if redis.call('GET', KEYS[1]) ~= ARGV[1] then return 0 end
        redis.call('SET', KEYS[1], ARGV[2], 'EX', ARGV[4])
        redis.call('SET', KEYS[2], ARGV[3], 'EX', ARGV[5])
        return 1
        """
        return bool(self.r.eval(script, 2, cache_key, run_key, json.dumps(expected), json.dumps(run_id),
                                json.dumps(record, default=str), int(cache_ttl), int(run_ttl)))

    def delete_json_if_value(self, key, expected):
        script = "if redis.call('GET', KEYS[1]) == ARGV[1] then return redis.call('DEL', KEYS[1]) else return 0 end"
        return bool(self.r.eval(script, 1, key, json.dumps(expected)))

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
