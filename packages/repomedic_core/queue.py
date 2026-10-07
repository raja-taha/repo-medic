from __future__ import annotations

from arq import create_pool
from arq.connections import RedisSettings

from repomedic_core.config import get_settings


def redis_settings() -> RedisSettings:
    settings = get_settings()
    return RedisSettings.from_dsn(settings.redis_url)


async def enqueue_repair_task(task_id: str) -> str:
    redis = await create_pool(redis_settings())
    try:
        job = await redis.enqueue_job("run_repair_job", task_id)
        return job.job_id if job else task_id
    finally:
        await redis.close()