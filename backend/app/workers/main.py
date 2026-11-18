"""arq worker entrypoint: `arq app.workers.main.WorkerSettings`.

Scale horizontally by running more replicas; the relay and every cron job use row locks
(SKIP LOCKED) so replicas never step on each other.
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import Any, ClassVar

from arq import cron
from arq.connections import RedisSettings
from prometheus_client import start_http_server

from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.workers import tasks
from app.workers.relay import relay_forever

log = get_logger(__name__)


async def startup(ctx: dict[str, Any]) -> None:
    s = get_settings()
    configure_logging(s.log_level, json=s.is_production)
    with contextlib.suppress(OSError):  # port taken when running several workers on one host
        start_http_server(9100)
    ctx["relay_task"] = asyncio.create_task(relay_forever(ctx))
    log.info("worker_started", embeddings=s.embedding_provider)


async def shutdown(ctx: dict[str, Any]) -> None:
    task: asyncio.Task[None] | None = ctx.get("relay_task")
    if task:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


class WorkerSettings:
    functions: ClassVar = [tasks.process_found_item, tasks.match_lost_report,
                           tasks.send_notification_email]
    cron_jobs: ClassVar = [
        cron(tasks.expire_items, minute={5}, unique=True),
        cron(tasks.expire_watches, minute={10}, unique=True),
        cron(tasks.requeue_stuck_items, minute={0, 15, 30, 45}, unique=True),
        cron(tasks.cleanup_outbox, hour={3}, minute={30}, unique=True),
    ]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    max_jobs = 20
    job_timeout = 120
    max_tries = 6
    keep_result = 3600
