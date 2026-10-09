"""诊断流水线: 解压校验 → 解析 → 规则引擎 → LLM 总结 → 报告, 全程事件流输出."""
import logging
import shutil
import tarfile
import zipfile
from pathlib import Path
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.events.event_bus import EventBus
from app.models.metric import MetricPoint
from app.models.rule import Rule
from app.models.task import Report, Task, TaskStatus
from app.modules.diagnosis import llm
from app.modules.diagnosis.parsers import identify_and_parse
from app.modules.diagnosis.rule_engine import Finding, RuleEngine

logger = logging.getLogger(__name__)

MAX_ENTRIES_FOR_CONTEXT = 200
EXTRACT_LIMIT_FILES = 5000
EXTRACT_LIMIT_BYTES = 2 * 1024 * 1024 * 1024  # 2GB 防 zip 炸弹


def safe_extract(archive_path: Path, dest: Path) -> list[Path]:
    """解压日志包 (zip/tar.gz), 防路径穿越与超大成员."""
    dest.mkdir(parents=True, exist_ok=True)
    extracted: list[Path] = []
    if zipfile.is_zipfile(archive_path):
        with zipfile.ZipFile(archive_path) as zf:
            total = 0
            for info in zf.infolist():
                if len(extracted) >= EXTRACT_LIMIT_FILES or total > EXTRACT_LIMIT_BYTES:
                    break
                target = (dest / info.filename).resolve()
                if not str(target).startswith(str(dest.resolve())):  # 路径穿越防护
                    continue
                total += info.file_size
                if not info.is_file():
                    continue
                zf.extract(info, dest)
                extracted.append(target)
    elif tarfile.is_tarfile(archive_path):
        with tarfile.open(archive_path) as tf:
            for member in tf.getmembers()[:EXTRACT_LIMIT_FILES]:
                if not member.isfile() or member.size > 256 * 1024 * 1024:
                    continue
                target = (dest / member.name).resolve()
                if not str(target).startswith(str(dest.resolve())):
                    continue
                tf.extract(member, dest)
                extracted.append(target)
    else:
        extracted.append(archive_path)  # 单文件直接分析
    return extracted


async def run_diagnosis(task_id: UUID, bus: EventBus, is_cancelled) -> None:
    """执行诊断任务全流程, 每步通过 bus.publish 实时输出."""
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
            logger.exception("诊断任务失败 %s", task_id)
            task.status = TaskStatus.failed
            task.error = str(e)[:2000]
            await bus.publish(str(task_id), "error", {"message": task.error})
        await db.commit()
        await bus.publish(str(task_id), "done", {"status": task.status})


def db_get(model, pk):
    from sqlalchemy import select
    return select(model).where(model.id == pk)


class _Cancelled(Exception):
    pass


async def _pipeline(db: AsyncSession, task: Task, bus: EventBus, is_cancelled) -> None:
    task_id = str(task.id)

    # 1. 解压
    await bus.publish(task_id, "progress", {"step": "extract", "percent": 5, "message": "解压与安全校验"})
    work_dir = Path(task.storage_path).parent / "extracted"
    files = safe_extract(Path(task.storage_path), work_dir)
    if not files:
        raise RuntimeError("日志包为空或格式不支持")
    if await is_cancelled():
        raise _Cancelled()

    # 2. 解析 (插件识别)
    all_findings: list[Finding] = []
    all_metrics: list[dict] = []
    file_stats: dict = {}
    for i, path in enumerate(files):
        if await is_cancelled():
            raise _Cancelled()
        await bus.publish(task_id, "progress", {
            "step": "parse", "percent": 10 + int(40 * (i + 1) / len(files)),
            "message": f"解析 {path.name} ({i + 1}/{len(files)})"})
        result = await identify_and_parse(path, task.params.get("server_type", ""))
        if result is None:
            continue
        file_stats[str(path.name)] = result.file_stats
        all_metrics.extend(result.metrics)
        # 3. 规则引擎 (按任务加载最新启用规则, 天然热加载)
        engine = await RuleEngine.load(db)
        findings = engine.match_entries(result.entries)
        all_findings.extend(findings)

    await bus.publish(task_id, "progress", {"step": "rules", "percent": 60,
                                            "message": f"规则匹配完成, 命中 {len(all_findings)} 条"})
    threshold_findings = RuleEngine([]).match_metrics(all_metrics)
    all_findings.extend(threshold_findings)

    for f in all_findings[:100]:
        await bus.publish(task_id, "finding", {
            "rule_name": f.rule_name, "severity": f.severity,
            "line_no": f.line_no, "text": f.raw[:300], "matched": f.matched_text})

    # 4. 指标入库
    if all_metrics:
        await bus.publish(task_id, "progress", {"step": "metrics", "percent": 70, "message": "性能指标入库"})
        db.add_all([MetricPoint(**m) for m in all_metrics[:100000]])

    # 5. LLM 总结 (流式 token 逐个推送)
    score = RuleEngine.health_score(all_findings)
    finding_dicts = [vars(f) for f in all_findings[:MAX_ENTRIES_FOR_CONTEXT]]
    await bus.publish(task_id, "progress", {"step": "llm", "percent": 80, "message": "智能总结生成中"})
    summary_parts: list[str] = []
    context = "规则命中结果:\n" + "\n".join(
        f"[{f['severity']}] {f['rule_name']}: {f.get('matched_text') or f.get('raw', '')[:150]}"
        for f in finding_dicts) if finding_dicts else "未命中任何规则"
    async for token in llm.stream_summary(context):
        if await is_cancelled():
            raise _Cancelled()
        summary_parts.append(token)
        await bus.publish(task_id, "llm_token", {"text": token})
    summary = "".join(summary_parts) if llm.llm_enabled() else llm.rule_only_summary(finding_dicts)

    # 6. 报告
    await bus.publish(task_id, "progress", {"step": "report", "percent": 95, "message": "生成报告"})
    report = Report(
        task_id=task.id, health_score=score, summary=summary,
        findings=finding_dicts,
        content={"file_stats": file_stats, "metric_count": len(all_metrics)},
    )
    db.add(report)
    task.progress = 95

    # 清理解压临时目录
    shutil.rmtree(work_dir, ignore_errors=True)
