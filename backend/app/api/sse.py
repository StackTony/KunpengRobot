"""SSE 端点: 任务事件实时流式输出 (先补发历史, 再实时续流)."""
import asyncio
import json
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from redis.asyncio import Redis
from sse_starlette.sse import EventSourceResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user, get_redis
from app.events.event_bus import EventBus
from app.models.task import Task
from app.models.user import User

router = APIRouter(prefix="/tasks", tags=["sse"])


@router.get("/{task_id}/events")
async def task_events(
    task_id: str,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    redis: Annotated[Redis, Depends(get_redis)],
):
    """订阅任务事件流: 分析进度 / 解析日志行 / LLM token / 结论.

    断线重连: 客户端带 Last-Event-ID 重连时, 服务端从 Stream 补发历史后续流.
    """
    task = (await db.execute(select(Task).where(Task.id == task_id))).scalar_one_or_none()
    if task is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "任务不存在")
    if task.user_id != user.id and "admin" not in {r.name for r in user.roles}:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "无权访问该任务")

    bus = EventBus(redis)
    stop = asyncio.Event()

    async def event_generator():
        # 1) 补发留存历史
        for event in await bus.replay(task_id):
            yield {"event": event.get("type", "message"), "data": json.dumps(event, ensure_ascii=False)}
            if event.get("type") in ("done", "error"):
                stop.set()
        if stop.is_set():
            return

        # 2) 实时续流: Pub/Sub 回调写入队列, 协程逐条推送
        live: asyncio.Queue = asyncio.Queue()

        def on_event(event: dict):
            live.put_nowait(event)
            if event.get("type") in ("done", "error"):
                stop.set()

        subscribe_task = asyncio.create_task(bus.subscribe(task_id, on_event, stop))
        try:
            while not stop.is_set():
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(live.get(), timeout=5.0)
                except asyncio.TimeoutError:
                    yield {"event": "ping", "data": ""}  # 保活
                    continue
                yield {"event": event.get("type", "message"), "data": json.dumps(event, ensure_ascii=False)}
        finally:
            stop.set()
            subscribe_task.cancel()
            try:
                await subscribe_task
            except (asyncio.CancelledError, Exception):
                pass

    return EventSourceResponse(event_generator())
