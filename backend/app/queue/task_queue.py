"""Redis Stream 任务队列封装: 入队 / 消费组消费 / ACK / pending 重投."""
import asyncio
import json
import logging
import time
import uuid

from redis.asyncio import Redis

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class TaskQueue:
    """基于 Redis Stream + 消费组的可靠任务队列.

    - XADD 入队 (MAXLEN 防膨胀)
    - XREADGROUP 消费组消费, 处理成功后 XACK
    - 启动时 XAUTOCLAIM 回收超时 pending 任务 (Worker 崩溃遗留)
    """

    def __init__(self, redis: Redis):
        self.redis = redis

    async def ensure_group(self) -> None:
        try:
            await self.redis.xgroup_create(settings.QUEUE_STREAM, settings.QUEUE_GROUP, id="0", mkstream=True)
        except Exception as e:  # BUSYGROUP: 组已存在
            if "BUSYGROUP" not in str(e):
                raise

    async def enqueue(self, task_id: str, task_type: str, payload: dict | None = None) -> str:
        msg_id = await self.redis.xadd(
            settings.QUEUE_STREAM,
            {
                "task_id": task_id,
                "type": task_type,
                "payload": json.dumps(payload or {}, ensure_ascii=False),
                "enqueued_at": str(time.time()),
            },
            maxlen=settings.QUEUE_MAX_LEN,
            approximate=True,
        )
        return msg_id

    async def consume(self, consumer: str, count: int = 1, block_ms: int = 5000):
        """读取一批消息: 返回 [(msg_id, task_id, type, payload)], 处理方须显式 ack."""
        result = await self.redis.xreadgroup(
            settings.QUEUE_GROUP, consumer, {settings.QUEUE_STREAM: ">"},
            count=count, block=block_ms,
        )
        tasks = []
        for _stream, messages in result or []:
            for msg_id, fields in messages:
                tasks.append((
                    msg_id,
                    fields["task_id"],
                    fields["type"],
                    json.loads(fields.get("payload", "{}")),
                ))
        return tasks

    async def ack(self, *msg_ids: str) -> None:
        if msg_ids:
            await self.redis.xack(settings.QUEUE_STREAM, settings.QUEUE_GROUP, *msg_ids)

    async def reclaim_stale(self) -> int:
        """回收崩溃 Worker 遗留的 pending 消息, 返回回收数."""
        reclaimed, next_cursor = 0, "0"
        while True:
            next_cursor, msgs, _ = await self.redis.xautoclaim(
                settings.QUEUE_STREAM, settings.QUEUE_GROUP,
                settings.WORKER_CONSUMER_NAME + "-reclaim",
                min_idle_time=settings.WORKER_PENDING_TIMEOUT_MS,
                start_id=next_cursor, count=50,
            )
            reclaimed += len(msgs or [])
            if not msgs or next_cursor == "0":
                break
        if reclaimed:
            logger.warning("回收 %d 条超时 pending 任务", reclaimed)
        return reclaimed
