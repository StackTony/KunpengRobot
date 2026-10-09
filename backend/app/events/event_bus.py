"""事件通道: Pub/Sub 实时推送 + Stream 留存 (SSE 断线补发).

事件流: Worker 发布 → Redis
  - XADD events:{task_id} (带 TTL)  ← 断线重连时 XRANGE 补发历史
  - PUBLISH ch:{task_id}            ← 在线订阅者实时收到
API 侧 SSE 端点: 先读 Stream 历史, 再订阅 Pub/Sub 续流.
"""
import asyncio
import json
import logging
import time

from redis.asyncio import Redis

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class EventBus:
    def __init__(self, redis: Redis):
        self.redis = redis

    async def publish(self, task_id: str, event_type: str, data: dict | None = None) -> None:
        """发布一条事件 (进度/日志行/LLM token/结论)."""
        event = json.dumps({
            "type": event_type,       # e.g. progress / log / llm_token / finding / done / error
            "data": data or {},
            "ts": time.time(),
        }, ensure_ascii=False)
        stream_key = f"{settings.EVENT_STREAM_PREFIX}:{task_id}"
        channel = f"{settings.EVENT_CHANNEL_PREFIX}:{task_id}"
        pipe = self.redis.pipeline()
        pipe.xadd(stream_key, {"e": event}, maxlen=10000, approximate=True)
        pipe.expire(stream_key, settings.EVENT_TTL_SECONDS)
        pipe.publish(channel, event)
        await pipe.execute()

    async def replay(self, task_id: str) -> list[dict]:
        """读取该任务的全部留存事件 (断线补发)."""
        stream_key = f"{settings.EVENT_STREAM_PREFIX}:{task_id}"
        entries = await self.redis.xrange(stream_key)
        return [json.loads(fields["e"]) for _msg_id, fields in entries]

    async def subscribe(self, task_id: str, on_event, stop: asyncio.Event):
        """订阅实时事件, 直到 stop 被置位; on_event(event_dict) 为回调."""
        pubsub = self.redis.pubsub()
        await pubsub.subscribe(f"{settings.EVENT_CHANNEL_PREFIX}:{task_id}")
        try:
            while not stop.is_set():
                msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if msg and msg["type"] == "message":
                    try:
                        on_event(json.loads(msg["data"]))
                    except Exception:
                        logger.exception("事件回调异常")
        finally:
            await pubsub.unsubscribe(f"{settings.EVENT_CHANNEL_PREFIX}:{task_id}")
            await pubsub.aclose()
