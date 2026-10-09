"""Worker 内嵌调度器: 巡检定时触发 (入队) + 指标分区维护."""
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from redis.asyncio import Redis

from app.core.config import get_settings
from app.core.database import AsyncSessionLocal
from app.metrics.store import drop_expired_partitions, ensure_partitions

logger = logging.getLogger(__name__)
settings = get_settings()
scheduler = AsyncIOScheduler()


async def trigger_scheduled_inspections(redis: Redis) -> None:
    """扫描到期的周期巡检任务并入队 (骨架: 预留, 巡检模板功能展开时实现)."""
    # TODO: 从巡检模板表读取 crontab, 对每模板创建 Task 并 enqueue
    pass


async def maintain_metric_partitions() -> None:
    async with AsyncSessionLocal() as db:
        await ensure_partitions(db)
        dropped = await drop_expired_partitions(db, settings.METRIC_RETENTION_DAYS)
        if dropped:
            logger.info("清理 %d 个过期指标分区", dropped)


async def start_scheduler(redis: Redis) -> None:
    from app.queue.task_queue import TaskQueue
    queue = TaskQueue(redis)

    async def _trigger():
        await trigger_scheduled_inspections(redis)

    scheduler.add_job(_trigger, "interval", minutes=5, id="inspection_trigger")
    scheduler.add_job(maintain_metric_partitions, "cron", hour=3, id="metric_partitions")
    scheduler.start()
    logger.info("调度器已启动 (巡检触发 + 指标分区维护)")
