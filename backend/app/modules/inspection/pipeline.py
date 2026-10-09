"""巡检流水线: 解析输入 → 遍历检查项插件 → 规则引擎 → LLM 总结 → 报告."""
import logging
from pathlib import Path
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.events.event_bus import EventBus
from app.models.metric import MetricPoint
from app.models.task import Report, Task, TaskStatus
from app.modules.diagnosis import llm
from app.modules.diagnosis.pipeline import safe_extract
from app.modules.diagnosis.parsers import identify_and_parse
from app.modules.diagnosis.rule_engine import RuleEngine
from app.modules.inspection.checkers import CHECKERS, InspectionContext

logger = logging.getLogger(__name__)


async def run_inspection(task_id: UUID, bus: EventBus, is_cancelled) -> None:
    async with AsyncSessionLocal() as db:
        task = (await db.execute(_get(Task, task_id))).scalar_one_or_none()
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
            logger.exception("巡检任务失败 %s", task_id)
            task.status = TaskStatus.failed
            task.error = str(e)[:2000]
            await bus.publish(str(task_id), "error", {"message": task.error})
        await db.commit()
        await bus.publish(str(task_id), "done", {"status": task.status})


def _get(model, pk):
    from sqlalchemy import select
    return select(model).where(model.id == pk)


class _Cancelled(Exception):
    pass


async def _pipeline(db: AsyncSession, task: Task, bus: EventBus, is_cancelled) -> None:
    task_id = str(task.id)

    # 1. 解压与解析
    await bus.publish(task_id, "progress", {"step": "extract", "percent": 5, "message": "解压巡检数据包"})
    work_dir = Path(task.storage_path).parent / "extracted"
    files = safe_extract(Path(task.storage_path), work_dir)
    if not files:
        raise RuntimeError("巡检数据包为空")

    ctx = InspectionContext(server_type=task.params.get("server_type", ""))
    for i, path in enumerate(files):
        if await is_cancelled():
            raise _Cancelled()
        await bus.publish(task_id, "progress", {
            "step": "parse", "percent": 10 + int(20 * (i + 1) / len(files)),
            "message": f"解析 {path.name}"})
        result = await identify_and_parse(path, ctx.server_type)
        if result:
            ctx.entries.extend(result.entries)
            ctx.metrics.extend(result.metrics)

    # 2. 逐检查项执行 (插件)
    results = []
    for i, checker in enumerate(CHECKERS):
        if await is_cancelled():
            raise _Cancelled()
        await bus.publish(task_id, "progress", {
            "step": "check", "percent": 30 + int(40 * (i + 1) / len(CHECKERS)),
            "message": f"检查项: {checker.name}"})
        try:
            r = await checker.check(ctx)
        except Exception:
            logger.exception("检查项 %s 执行失败", checker.name)
            continue
        results.append(r)
        await bus.publish(task_id, "finding", {
            "checker": r.name, "passed": r.passed, "severity": r.severity, "message": r.message})

    # 3. 规则引擎 (复用诊断规则: 对解析条目做正则/关键字匹配)
    engine = await RuleEngine.load(db)
    findings = engine.match_entries(ctx.entries[:100000])
    for f in findings[:100]:
        await bus.publish(task_id, "finding", {
            "rule_name": f.rule_name, "severity": f.severity, "text": f.raw[:300]})

    # 4. 指标入库
    all_metrics = ctx.metrics + [m for r in results for m in r.metrics]
    if all_metrics:
        db.add_all([MetricPoint(**m) for m in all_metrics[:100000]])

    # 5. 健康评分与 LLM 总结
    from app.modules.diagnosis.rule_engine import SEVERITY_WEIGHT
    from app.models.rule import Severity
    failed = [r for r in results if not r.passed]
    penalty = sum(SEVERITY_WEIGHT.get(Severity(r.severity), 3) for r in failed) + len(findings) * 2
    score = max(0, 100 - min(100, penalty))

    await bus.publish(task_id, "progress", {"step": "llm", "percent": 80, "message": "智能总结生成中"})
    context = "巡检结果:\n" + "\n".join(
        f"[{'未通过' if not r.passed else '通过'}] {r.name}: {r.message}" for r in results)
    if findings:
        context += "\n规则命中:\n" + "\n".join(f"[{f.severity}] {f.rule_name}" for f in findings[:50])

    summary_parts = []
    if llm.llm_enabled():
        async for token in llm.stream_summary(context):
            if await is_cancelled():
                raise _Cancelled()
            summary_parts.append(token)
            await bus.publish(task_id, "llm_token", {"text": token})
        summary = "".join(summary_parts)
    else:
        summary = llm.rule_only_summary(
            [{"severity": f.severity, "rule_name": f.rule_name, "matched_text": f.matched_text} for f in findings]
        )

    # 6. 报告
    db.add(Report(
        task_id=task.id, health_score=score, summary=summary,
        findings=[{"checker": r.name, "passed": r.passed, "severity": r.severity, "message": r.message}
                  for r in results],
        content={"rule_hits": len(findings), "metric_count": len(all_metrics)},
    ))
    task.progress = 95
