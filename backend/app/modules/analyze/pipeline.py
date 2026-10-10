"""解析任务流水线: 读日志文本 → 指定解析器解析 → 事件分批入库 → 规则匹配 → 五段报告兜底.

与 diagnosis/pipeline.py 同构的状态机 (running→done/cancelled/failed),
区别在于: 不做格式探测与解压, 由用户显式指定 parser_type; 解析结果为
统一事件模型 ParsedEvent, 入库供结果页聚合可视化; LLM 报告按需触发
(见 llm_report.py), 本流水线先写入规则引擎版五段报告兜底.
"""
import logging
from pathlib import Path
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.events.event_bus import EventBus
from app.models.analyze import ParsedEventRecord
from app.models.task import Report, Task, TaskStatus
from app.modules.analyze import ANALYZE_PARSERS
from app.modules.analyze.report_builder import build_llm_report
from app.modules.diagnosis.parsers import LogEntry
from app.modules.diagnosis.rule_engine import RuleEngine

logger = logging.getLogger(__name__)

BATCH_SIZE = 500          # 事件入库批量
RULE_CHUNK = 5000         # 规则匹配分块 (避免海量事件一次性构造 LogEntry 列表)
MAX_FINDINGS_EMIT = 100   # finding 事件最多向前端推送条数 (全量仍在报告中)


class _Cancelled(Exception):
    pass


def db_get(model, pk):
    return select(model).where(model.id == pk)


async def run_analyze(task_id: UUID, bus: EventBus, is_cancelled) -> None:
    """执行解析任务全流程, 事件流输出到 {task_id} 通道."""
    async with AsyncSessionLocal() as db:
        task = (await db.execute(db_get(Task, task_id))).scalar_one_or_none()
        if task is None:
            return
        task.status = TaskStatus.running
        await db.commit()

        try:
            await _pipeline(db, task, bus, is_cancelled)
            task.status = TaskStatus.done
            task.progress = 100
        except _Cancelled:
            task.status = TaskStatus.cancelled
        except Exception as e:
            logger.exception("解析任务失败 %s", task_id)
            task.status = TaskStatus.failed
            task.error = str(e)[:2000]
            await bus.publish(str(task_id), "error", {"message": task.error})
        await db.commit()
        await bus.publish(str(task_id), "done", {"status": task.status})


async def _pipeline(db: AsyncSession, task: Task, bus: EventBus, is_cancelled) -> None:
    task_id = str(task.id)
    parser = ANALYZE_PARSERS.get(task.parser_type or "")
    if parser is None:
        raise RuntimeError(f"未知解析器类型: {task.parser_type}")

    # 1. 读取日志文本
    await bus.publish(task_id, "progress", {"step": "read", "percent": 5, "message": "读取日志文件"})
    path = Path(task.storage_path)
    if not path.is_file():
        raise RuntimeError(f"日志文件不存在: {task.filename or task.storage_path}")
    text = path.read_text(encoding="utf-8", errors="replace")
    task.log_size = path.stat().st_size
    if await is_cancelled():
        raise _Cancelled()

    # 2. 解析为统一事件模型
    await bus.publish(task_id, "progress", {
        "step": "parse", "percent": 20, "message": f"「{parser.def_.name}」解析中"})
    events = parser.parse(text)
    if not events:
        raise RuntimeError("未解析到任何日志事件, 请确认日志格式与所选解析器匹配")
    if await is_cancelled():
        raise _Cancelled()

    # 3. 分批入库 (重跑时先清旧事件)
    await bus.publish(task_id, "progress", {
        "step": "store", "percent": 40, "message": f"事件入库 (共 {len(events)} 条)"})
    await db.execute(delete(ParsedEventRecord).where(ParsedEventRecord.task_id == task.id))
    for start in range(0, len(events), BATCH_SIZE):
        if await is_cancelled():
            raise _Cancelled()
        batch = events[start:start + BATCH_SIZE]
        db.add_all([ParsedEventRecord(
            task_id=task.id, ts=e.timestamp, source_ip=e.source_ip,
            severity=e.severity, category=e.category, error_code=e.error_code,
            raw=e.raw, fields=e.fields or {},
        ) for e in batch])
        await db.flush()
        done = min(start + BATCH_SIZE, len(events))
        await bus.publish(task_id, "progress", {
            "step": "store", "percent": 40 + int(30 * done / len(events)),
            "message": f"事件入库 {done}/{len(events)}"})
    task.event_count = len(events)

    # 4. 规则引擎匹配 (复用全局规则集, LogEntry 适配; 分块控内存)
    await bus.publish(task_id, "progress", {"step": "rules", "percent": 75, "message": "规则匹配中"})
    engine = await RuleEngine.load(db)
    findings = []
    for start in range(0, len(events), RULE_CHUNK):
        if await is_cancelled():
            raise _Cancelled()
        chunk = events[start:start + RULE_CHUNK]
        findings.extend(engine.match_entries([LogEntry(raw=e.raw) for e in chunk]))
    await bus.publish(task_id, "progress", {
        "step": "rules", "percent": 85, "message": f"规则匹配完成, 命中 {len(findings)} 条"})
    for f in findings[:MAX_FINDINGS_EMIT]:
        await bus.publish(task_id, "finding", {
            "rule_name": f.rule_name, "severity": f.severity,
            "line_no": f.line_no, "text": (f.raw or "")[:300], "matched": f.matched_text})

    # 5. 五段式报告兜底 (LLM 按需生成时会覆盖此报告)
    await bus.publish(task_id, "progress", {"step": "report", "percent": 95, "message": "生成分析报告"})
    sections = build_llm_report(events, parser.def_.name)
    summary = "\n\n".join(f"【{s['title']}】\n" + "\n".join(s["lines"]) for s in sections)
    await db.execute(delete(Report).where(Report.task_id == task.id))
    db.add(Report(
        task_id=task.id, health_score=RuleEngine.health_score(findings),
        summary=summary, findings=[vars(f) for f in findings[:200]],
        content={"parser": parser.def_.type, "parser_name": parser.def_.name,
                 "sections": sections, "event_count": len(events), "llm": False},
    ))
    task.progress = 95
