"""按需 LLM 报告: 前端在结果页点击「生成诊断报告」后入队 llm 任务, 流式输出.

- 事件通道独立: {task_id}:llm:{run_id} (run_id 每次触发生成, 互不串流)
- 并发去重: Redis 锁 llm:lock:{task_id}, 同任务同时只允许一个生成
- LLM 已配置: llm.stream_summary 逐 token 推送 llm_token
- LLM 未配置: 五段规则报告逐段推送 llm_section + 逐行 llm_token (打字机节奏)
- 完成后覆盖任务的 Report (保留 health_score/findings)
"""
import asyncio
import logging
import uuid

from sqlalchemy import delete, select

from app.core.database import AsyncSessionLocal
from app.events.event_bus import EventBus
from app.models.analyze import ParsedEventRecord
from app.models.task import Report, Task
from app.modules.analyze import ANALYZE_PARSERS
from app.modules.analyze.parsers import ParsedEvent
from app.modules.analyze.report_builder import build_llm_context, build_llm_report
from app.modules.diagnosis import llm

logger = logging.getLogger(__name__)

LOCK_TTL_SECONDS = 600        # 生成锁 TTL (防进程崩溃后死锁)
MAX_EVENTS_FOR_LLM = 50000    # 送入 LLM 上下文的事件上限
TYPEWRITER_INTERVAL = 0.11    # 规则报告打字机节奏 (秒/行)


class _Cancelled(Exception):
    pass


async def run_llm_report(task_id: uuid.UUID, run_id: str, bus: EventBus, is_cancelled) -> None:
    """对已完成解析任务按需生成 LLM 诊断报告, 事件流输出到 {task_id}:llm:{run_id}."""
    key = f"{task_id}:llm:{run_id}"
    lock_key = f"llm:lock:{task_id}"
    redis = bus.redis

    got_lock = await redis.set(lock_key, run_id, nx=True, ex=LOCK_TTL_SECONDS)
    if not got_lock:
        await bus.publish(key, "error", {"message": "该任务已有报告生成中, 请稍候"})
        await bus.publish(key, "done", {"status": "skipped"})
        return

    try:
        await _generate(task_id, run_id, key, bus, is_cancelled)
        await bus.publish(key, "done", {"status": "done"})
    except _Cancelled:
        await bus.publish(key, "done", {"status": "cancelled"})
    except Exception as e:
        logger.exception("LLM 报告生成失败 %s", task_id)
        await bus.publish(key, "error", {"message": str(e)[:2000]})
        await bus.publish(key, "done", {"status": "failed"})
    finally:
        await redis.delete(lock_key)


async def _generate(task_id: uuid.UUID, run_id: str, key: str,
                    bus: EventBus, is_cancelled) -> None:
    async with AsyncSessionLocal() as db:
        task = (await db.execute(select(Task).where(Task.id == task_id))).scalar_one_or_none()
        if task is None:
            raise RuntimeError("任务不存在")
        parser = ANALYZE_PARSERS.get(task.parser_type or "")
        parser_name = parser.def_.name if parser else (task.parser_type or "未知解析器")
        records = (await db.execute(
            select(ParsedEventRecord)
            .where(ParsedEventRecord.task_id == task_id)
            .order_by(ParsedEventRecord.ts.asc())
            .limit(MAX_EVENTS_FOR_LLM))).scalars().all()
        old_report = (await db.execute(
            select(Report).where(Report.task_id == task_id))).scalar_one_or_none()

    if not records:
        raise RuntimeError("任务无解析事件, 请先执行解析")
    if await is_cancelled():
        raise _Cancelled()

    events = [ParsedEvent(
        timestamp=r.ts, source_ip=r.source_ip, severity=r.severity,
        category=r.category, error_code=r.error_code, raw=r.raw, fields=r.fields or {},
    ) for r in records]

    parts: list[str] = []
    sections_out: list[dict] | None = None

    if llm.llm_enabled():
        # 真实 LLM: 逐 token 流式推送
        await bus.publish(key, "progress", {"percent": 10, "message": "LLM 分析中"})
        context = build_llm_context(events, parser_name)
        async for token in llm.stream_summary(context):
            if await is_cancelled():
                raise _Cancelled()
            parts.append(token)
            await bus.publish(key, "llm_token", {"text": token})
        summary = "".join(parts)
    else:
        # 规则引擎五段报告: 段边界 llm_section + 逐行 llm_token (打字机)
        sections_out = build_llm_report(events, parser_name)
        total_lines = sum(len(s["lines"]) for s in sections_out) or 1
        done_lines = 0
        for s in sections_out:
            await bus.publish(key, "llm_section", {"title": s["title"]})
            for line in s["lines"]:
                if await is_cancelled():
                    raise _Cancelled()
                await bus.publish(key, "llm_token", {"text": line + "\n", "line": True})
                parts.append(line)
                done_lines += 1
                await bus.publish(key, "progress", {
                    "percent": 10 + int(85 * done_lines / total_lines),
                    "message": s["title"]})
                await asyncio.sleep(TYPEWRITER_INTERVAL)
        summary = "\n\n".join(f"【{s['title']}】\n" + "\n".join(s["lines"]) for s in sections_out)

    # 覆盖 Report (保留原 health_score / findings, 只更新总结与内容)
    async with AsyncSessionLocal() as db:
        await db.execute(delete(Report).where(Report.task_id == task_id))
        db.add(Report(
            task_id=task_id,
            health_score=old_report.health_score if old_report else None,
            summary=summary,
            findings=(old_report.findings if old_report else []),
            content={"llm": True, "run_id": run_id, "parser_name": parser_name,
                     "event_count": len(events), "sections": sections_out},
        ))
        await db.commit()
