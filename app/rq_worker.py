"""RQ worker entry point used in Docker.

Imports the agent graph once at startup, so each job (which RQ runs in a forked child
process) starts with LangGraph, the prompts and, later, B's embedding model already loaded.
"""

import logging
import os

from redis import Redis
from rq import Queue, Worker

import app.agents  # noqa: F401  preload

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))

if __name__ == "__main__":
    conn = Redis.from_url(os.getenv("REDIS_URL", "redis://redis:6379/0"))
    Worker([Queue("claims", connection=conn)], connection=conn).work(with_scheduler=False)