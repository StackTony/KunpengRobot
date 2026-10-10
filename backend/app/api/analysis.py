"""解析结果 API: 事件分页筛选 / 聚合统计 / 按需 LLM (触发 + SSE) / 报告查看.

对应 witty TaskResultView 五个 Tab:
KPI 横幅 / 时序堆叠图 / 类别饼图 / 错误码排行 / IP 聚合 / 原始日志多维筛选 / LLM 报告.
"""
import asyncio
import json
import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import Text, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import (AnalyzeEvent, EventsPage, LlmStartResponse, ReportInfo,
                             StatsResponse)
from app.core.audit import log_audit
from app.core.database import get_db
from app.core.deps import (ensure_team_perm, get_current_user, get_current_user_or_query,
                           get_redis, is_platform_admin)
from app.events.event_bus import EventBus
from app.models.analyze import ParsedEventRecord
from app.models.asset import AssetLibrary
from app.models.task import Report, Task
from app.models.user import User
from app.modules.analyze import ANALYZE_PARSERS
from app.modules.analyze.aggregate import (bucket_by_time, by_category, by_error_code,
                                           by_ip, kpi_of)
from app.modules.analyze.parsers import ParsedEvent
from app.queue.task_queue import TaskQueue

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/tasks", tags=["analysis"])

MAX_EVENTS_FOR_STATS = 100_000


async def _load_visible_task(db: AsyncSession, user: User, task_id: uuid.UUID) -> Task:
    """加载任务并校验可见性: 任务创建者 / 平台管理员 / 同团队成员 (task:view)."""
    task = (await db.execute(select(Task).where(Task.id == task_id))).scalar_one_or_none()
    if task is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "任务不存在")
    if task.user_id == user.id or is_platform_admin(user):
        return task
    if task.asset_id is not None:
        asset = (await db.execute(select(AssetLibrary)
                                  .where(AssetLibrary.id == task.asset_id))).scalar_one_or_none()
        if asset is not None:
            try:
                await ensure_team_perm(db, user, asset.team_id, "task:view")
                return task
            except HTTPException:
                pass
    raise HTTPException(status.HTTP_403_FORBIDDEN, "无权访问该任务")


async def _ensure_task_perm(db: AsyncSession, user: User, task: Task, perm: str) -> None:
    """任务级权限: 创建者/管理员直通, 否则走资产所属团队的团队角色判定."""
    if task.user_id == user.id or is_platform_admin(user):
        return
    if task.asset_id is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "无权操作该任务")
    asset = (await db.execute(select(AssetLibrary)
                              .where(AssetLibrary.id == task.asset_id))).scalar_one()
    await ensure_team_perm(db, user, asset.team_id, perm)


# ---------- 原始日志分页筛选 ----------
@router.get("/{task_id}/logs", response_model=EventsPage)
async def list_events(
    task_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    severity: str | None = None,
    category: str | None = None,
    error_code: str | None = None,
    source_ip: str | None = None,
    kw: str | None = None,
    page: int = 1,
    page_size: int = 50,
):
    """原始日志分页: kw 对 raw + fields 文本 ILIKE, SQL 侧过滤 (不全量加载)."""
    await _load_visible_task(db, user, task_id)
    conds = [ParsedEventRecord.task_id == task_id]
    if severity:
        conds.append(ParsedEventRecord.severity == severity)
    if category:
        conds.append(ParsedEventRecord.category == category)
    if error_code:
        conds.append(ParsedEventRecord.error_code == error_code)
    if source_ip:
        conds.append(ParsedEventRecord.source_ip == source_ip)
    if kw:
        like = f"%{kw}%"
        conds.append(or_(ParsedEventRecord.raw.ilike(like),
                         ParsedEventRecord.fields.cast(Text).ilike(like)))

    total = (await db.execute(select(func.count()).select_from(ParsedEventRecord)
                              .where(*conds))).scalar_one()
    rows = (await db.execute(
        select(ParsedEventRecord).where(*conds)
        .order_by(ParsedEventRecord.ts.asc(), ParsedEventRecord.id.asc())
        .offset((page - 1) * page_size).limit(page_size))).scalars().all()
    items = [AnalyzeEvent(
        id=r.id, ts=r.ts, source_ip=r.source_ip, severity=r.severity,
        category=r.category, error_code=r.error_code, raw=r.raw,
        fields=r.fields or {}) for r in rows]
    return EventsPage(total=total, items=items)


# ---------- 聚合统计 ----------
@router.get("/{task_id}/stats", response_model=StatsResponse)
async def task_stats(
    task_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
):
    """结果页聚合: 瘦身列内存聚合 (1:1 witty 语义) + Top 错误码样例 SQL 补齐."""
    await _load_visible_task(db, user, task_id)
    rows = (await db.execute(
        select(ParsedEventRecord.ts, ParsedEventRecord.source_ip,
               ParsedEventRecord.severity, ParsedEventRecord.category,
               ParsedEventRecord.error_code)
        .where(ParsedEventRecord.task_id == task_id)
        .order_by(ParsedEventRecord.ts.asc())
        .limit(MAX_EVENTS_FOR_STATS))).all()
    events = [ParsedEvent(timestamp=r[0], source_ip=r[1], severity=r[2],
                          category=r[3], error_code=r[4]) for r in rows]
    if not events:
        return StatsResponse(kpi=kpi_of(events), time_buckets=[], categories=[],
                             codes=[], ips=[])

    codes = by_error_code(events, 15)  # 内存聚合 (sample 为空, 下方 SQL 补样例)
    if codes:
        samples = dict((await db.execute(
            select(ParsedEventRecord.error_code, func.min(ParsedEventRecord.raw))
            .where(ParsedEventRecord.task_id == task_id,
                   ParsedEventRecord.error_code.in_([c["name"] for c in codes]))
            .group_by(ParsedEventRecord.error_code))).all())
        for c in codes:
            c["sample"] = (samples.get(c["name"]) or "")[:160]

    return StatsResponse(
        kpi=kpi_of(events),
        time_buckets=bucket_by_time(events, 20),
        categories=by_category(events),
        codes=codes,
        ips=by_ip(events)[:20],
    )


# ---------- 报告查看 (兜底五段 / LLM 覆盖后) ----------
@router.get("/{task_id}/report", response_model=ReportInfo)
async def task_report(
    task_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
):
    await _load_visible_task(db, user, task_id)
    report = (await db.execute(select(Report).where(Report.task_id == task_id))).scalar_one_or_none()
    if report is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "报告尚未生成")
    content = report.content or {}
    return ReportInfo(
        task_id=report.task_id, health_score=report.health_score,
        summary=report.summary, sections=content.get("sections") or [],
        findings=report.findings or [], llm=bool(content.get("llm")),
        created_at=report.created_at)


# ---------- 按需 LLM ----------
@router.post("/{task_id}/llm", response_model=LlmStartResponse)
async def start_llm(
    task_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    redis: Annotated[object, Depends(get_redis)],
):
    """触发 LLM 报告生成: 抢锁 → INCR run_id → 入队 llm 消息 → 前端订阅 SSE."""
    task = (await db.execute(select(Task).where(Task.id == task_id))).scalar_one_or_none()
    if task is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "任务不存在")
    if task.status != "done" or not task.event_count:
        raise HTTPException(status.HTTP_409_CONFLICT, "任务未完成解析, 无法生成报告")
    await _ensure_task_perm(db, user, task, "task:llm")

    if await redis.exists(f"llm:lock:{task_id}"):
        raise HTTPException(status.HTTP_409_CONFLICT, "已有报告生成中, 请稍候")
    run_id = str(await redis.incr("llm:run:seq"))
    queue = TaskQueue(redis)
    await queue.enqueue(str(task_id), "llm", {"run_id": run_id})
    log_audit(db, user, "使用 LLM 分析", task.name or task.filename,
              team_id=(await _team_id_of_task(db, task)), detail={"run_id": run_id})
    await db.commit()
    return LlmStartResponse(run_id=run_id)


async def _team_id_of_task(db: AsyncSession, task: Task) -> int | None:
    if task.asset_id is None:
        return None
    return (await db.execute(select(AssetLibrary.team_id)
                             .where(AssetLibrary.id == task.asset_id))).scalar_one_or_none()


@router.get("/{task_id}/llm/events")
async def llm_events(
    task_id: str,
    request: Request,
    run_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user_or_query)],
    redis: Annotated[object, Depends(get_redis)],
):
    """LLM 报告流式 SSE: 订阅 {task_id}:llm:{run_id} 独立通道 (?token= 认证)."""
    try:
        tid = uuid.UUID(task_id)
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "任务 ID 非法")
    await _load_visible_task(db, user, tid)

    key = f"{task_id}:llm:{run_id}"
    bus = EventBus(redis)
    stop = asyncio.Event()

    async def event_generator():
        for event in await bus.replay(key):
            yield {"event": event.get("type", "message"),
                   "data": json.dumps(event, ensure_ascii=False)}
            if event.get("type") in ("done", "error"):
                stop.set()
        if stop.is_set():
            return

        live: asyncio.Queue = asyncio.Queue()

        def on_event(event: dict):
            live.put_nowait(event)
            if event.get("type") in ("done", "error"):
                stop.set()

        subscribe_task = asyncio.create_task(bus.subscribe(key, on_event, stop))
        try:
            while not stop.is_set():
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(live.get(), timeout=5.0)
                except asyncio.TimeoutError:
                    yield {"event": "ping", "data": ""}
                    continue
                yield {"event": event.get("type", "message"),
                       "data": json.dumps(event, ensure_ascii=False)}
        finally:
            stop.set()
            subscribe_task.cancel()
            try:
                await subscribe_task
            except (asyncio.CancelledError, Exception):
                pass

    from sse_starlette.sse import EventSourceResponse
    return EventSourceResponse(event_generator())
