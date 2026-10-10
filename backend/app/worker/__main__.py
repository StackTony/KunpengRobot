"""分析 Worker 入口: 消费 Redis Stream 队列, 并发执行诊断/巡检流水线.

启动: python -m app.worker  (或 uvicorn 不适用, 这是独立进程)
"""
import asyncio
import logging
import signal
import uuid

from redis.asyncio import Redis
from sqlalchemy import select, update

from app.core.config import get_settings
from app.core.database import AsyncSessionLocal, Base, engine
from app.events.event_bus import EventBus
from app.models.task import Task, TaskStatus
from app.modules.analyze.llm_report import run_llm_report
from app.modules.analyze.pipeline import run_analyze
from app.modules.diagnosis.pipeline import run_diagnosis
from app.modules.inspection.pipeline import run_inspection
from app.queue.task_queue import TaskQueue

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("worker")
settings = get_settings()

PIPELINES = {
    "diagnosis": run_diagnosis,
    "inspection": run_inspection,
    "analyze": run_analyze,
}

shutdown = asyncio.Event()


async def recover_interrupted(redis: Redis) -> None:
    """进程重启后, 将上次遗留的 running 任务标记为 interrupted."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Task).where(Task.status == TaskStatus.running))
        stale = result.scalars().all()
        for task in stale:
            task.status = TaskStatus.interrupted
        if stale:
            await db.commit()
            logger.warning("标记 %d 个中断任务为 interrupted (可重新下发)", len(stale))


async def make_cancel_checker(redis: Redis, task_id: str):
    async def is_cancelled() -> bool:
        return bool(await redis.exists(f"cancel:{task_id}"))
    return is_cancelled


async def handle_message(queue: TaskQueue, bus: EventBus, redis: Redis, msg_id: str,
                         task_id: str, task_type: str, payload: dict) -> None:
    try:
        cancelled = await make_cancel_checker(redis, task_id)
        if task_type == "llm":
            # 按需 LLM 报告: 独立签名, run_id 取自消息 payload
            run_id = str(payload.get("run_id") or uuid.uuid4())
            await run_llm_report(uuid.UUID(task_id), run_id, bus, cancelled)
        else:
            pipeline = PIPELINES.get(task_type)
            if pipeline is None:
                raise RuntimeError(f"未知任务类型: {task_type}")
            await pipeline(uuid.UUID(task_id), bus, cancelled)
        await redis.delete(f"cancel:{task_id}")
    except Exception:
        logger.exception("任务 %s 处理异常", task_id)
    finally:
        await queue.ack(msg_id)


async def main() -> None:
    redis = Redis.from_url(settings.REDIS_URL, decode_responses=True)
    queue = TaskQueue(redis)
    bus = EventBus(redis)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await queue.ensure_group()
    await queue.reclaim_stale()
    await recover_interrupted(redis)

    semaphore = asyncio.Semaphore(settings.WORKER_CONCURRENCY)
    logger.info("Worker 启动: consumer=%s, 并发=%d", settings.WORKER_CONSUMER_NAME, settings.WORKER_CONCURRENCY)

    # 调度器: 巡检定时触发 + 指标分区维护
    from app.worker.scheduler import start_scheduler
    await start_scheduler(redis)

    async def consume_loop():
        while not shutdown.is_set():
            messages = await queue.consume(settings.WORKER_CONSUMER_NAME, count=1, block_ms=2000)
            for msg_id, task_id, task_type, payload in messages:
                async def run(m_id=msg_id, t_id=task_id, t_type=task_type, p=payload):
                    async with semaphore:
                        await handle_message(queue, bus, redis, m_id, t_id, t_type, p)
                asyncio.create_task(run())

    loop_task = asyncio.create_task(consume_loop())
    await shutdown.wait()
    loop_task.cancel()
    try:
        await loop_task
    except asyncio.CancelledError:
        pass
    await redis.aclose()


if __name__ == "__main__":
    def _stop(*_):
        shutdown.set()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            import asyncio as _a
            loop = asyncio.get_event_loop()
            loop.add_signal_handler(sig, _stop)
        except (NotImplementedError, RuntimeError):
            signal.signal(sig, _stop)  # Windows
    asyncio.run(main())
