"""任务: 日志上传(入队即返回) / 文本直传 / 预检 / 任务列表 / 详情 / 取消 / 删除.

上传类型: diagnosis (通用诊断) / analyze (witty 解析任务, 指定解析器+资产库) /
inspection (智能巡检); analyze 走团队级 RBAC (task:create).
"""
import os
import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile, status
from sqlalchemy import delete as sa_delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.analysis import _ensure_task_perm, _load_visible_task, _team_id_of_task
from app.api.schemas import (PrecheckRequest, PrecheckResponse, TaskInfo, TextUploadRequest,
                             UploadResponse)
from app.core.audit import log_audit
from app.core.config import get_settings
from app.core.database import get_db
from app.core.deps import get_current_user, get_redis
from app.models.asset import AssetLibrary
from app.models.task import Task, TaskStatus, TaskType
from app.models.user import User
from app.modules.analyze import ANALYZE_PARSERS
from app.queue.task_queue import TaskQueue

router = APIRouter(prefix="/tasks", tags=["tasks"])
settings = get_settings()

ALLOWED_SUFFIXES = {".zip", ".tar", ".gz", ".tgz", ".log", ".txt",
                    ".json", ".jsonl"}  # witty: redfish/windows 为 JSON 导出


async def _save_upload(file: UploadFile, task_id: uuid.UUID, limit: int) -> tuple[Path, int]:
    """流式落盘 (防超大), 返回 (storage_path, size); 超限自动清理."""
    upload_dir = Path(settings.DATA_DIR) / "uploads" / str(task_id)
    upload_dir.mkdir(parents=True, exist_ok=True)
    storage_path = upload_dir / (file.filename or "upload.bin")
    size = 0
    with open(storage_path, "wb") as f:
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > limit:
                f.close()
                storage_path.unlink(missing_ok=True)
                raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "文件超出大小限制")
            f.write(chunk)
    return storage_path, size


async def _check_analyze_target(db: AsyncSession, user: User, parser_type: str, asset_id: int):
    """analyze 任务入参校验: 解析器存在 + 资产库存在; 返回 (parser, asset)."""
    from app.core.deps import ensure_team_perm

    parser = ANALYZE_PARSERS.get(parser_type or "")
    if parser is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"未知解析器类型: {parser_type}")
    asset = (await db.execute(select(AssetLibrary)
                              .where(AssetLibrary.id == asset_id))).scalar_one_or_none()
    if asset is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "资产库不存在")
    await ensure_team_perm(db, user, asset.team_id, "task:create")
    return parser, asset


@router.post("/precheck", response_model=PrecheckResponse)
async def precheck(
    body: PrecheckRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
):
    """解析预检: 前端只传日志前 512KB 切片, 返回可解析条数与样例 (不落盘不入队)."""
    parser = ANALYZE_PARSERS.get(body.parser_type or "")
    if parser is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"未知解析器类型: {body.parser_type}")
    events = parser.parse(body.text)
    return PrecheckResponse(count=len(events),
                            sample=[e.raw[:200] for e in events[:3]])


@router.post("/upload-text", response_model=UploadResponse)
async def upload_text(
    body: TextUploadRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    redis: Annotated[object, Depends(get_redis)],
):
    """向导粘贴文本直传 (≤10MB): 落临时文件 → analyze 任务 → 入队."""
    parser, asset = await _check_analyze_target(db, user, body.parser_type, body.asset_id)

    task_id = uuid.uuid4()
    upload_dir = Path(settings.DATA_DIR) / "uploads" / str(task_id)
    upload_dir.mkdir(parents=True, exist_ok=True)
    storage_path = upload_dir / (body.filename or "pasted.log")
    storage_path.write_text(body.text, encoding="utf-8")

    task = Task(
        id=task_id, type=TaskType.analyze, status=TaskStatus.pending,
        user_id=user.id, filename=body.filename or "pasted.log",
        storage_path=str(storage_path), params={},
        name=body.name, parser_type=body.parser_type, asset_id=asset.id,
        log_size=len(body.text.encode("utf-8")),
    )
    db.add(task)
    log_audit(db, user, "创建解析任务", f"{asset.name} / {body.name}",
              team_id=asset.team_id)
    await db.commit()

    queue = TaskQueue(redis)
    await queue.enqueue(str(task_id), "analyze", {"storage_path": str(storage_path)})
    return UploadResponse(task_id=task_id, status=task.status)


@router.post("/upload", response_model=UploadResponse)
async def upload(
    file: UploadFile,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    redis: Annotated[object, Depends(get_redis)],
    server_type: Annotated[str, Form()] = "",
    task_type: Annotated[str, Form()] = "diagnosis",   # diagnosis / analyze / inspection
    parser_type: Annotated[str, Form()] = "",
    task_name: Annotated[str, Form()] = "",
    asset_id: Annotated[int | None, Form()] = None,
):
    """上传日志包: 保存文件 → 创建任务 → 入队 → 立即返回 task_id (分析异步进行)."""
    if task_type not in ("diagnosis", "analyze", "inspection"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"不支持的任务类型: {task_type}")

    # 按用户限流
    rate_key = f"rate:upload:{user.id}"
    count = await redis.incr(rate_key)
    if count == 1:
        await redis.expire(rate_key, 60)
    if count > settings.UPLOAD_RATE_LIMIT_PER_MIN:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "上传过于频繁, 请稍后再试")

    suffix = Path(file.filename or "").suffix.lower()
    if suffix and suffix not in ALLOWED_SUFFIXES and not (file.filename or "").endswith(".tar.gz"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"不支持的文件类型: {suffix}")

    asset = None
    if task_type == "analyze":
        if asset_id is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "解析任务必须指定资产库")
        _, asset = await _check_analyze_target(db, user, parser_type, asset_id)

    task_id = uuid.uuid4()
    storage_path, size = await _save_upload(file, task_id, settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024)

    task = Task(
        id=task_id, type=TaskType(task_type), status=TaskStatus.pending,
        user_id=user.id, filename=file.filename or "upload.bin",
        storage_path=str(storage_path), params={"server_type": server_type},
        name=task_name, parser_type=parser_type,
        asset_id=(asset.id if asset else None), log_size=size,
    )
    db.add(task)
    if asset is not None:
        log_audit(db, user, "创建解析任务",
                  f"{asset.name} / {task_name or file.filename}", team_id=asset.team_id)
    await db.commit()

    queue = TaskQueue(redis)
    await queue.enqueue(str(task_id), task_type,
                        {"storage_path": str(storage_path), "server_type": server_type})
    return UploadResponse(task_id=task_id, status=task.status)


@router.get("", response_model=list[TaskInfo])
async def list_tasks(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    type: TaskType | None = None,
    limit: int = 50,
):
    """普通用户看自己的任务; 管理员看全部; 可按任务类型过滤 (巡检页用)."""
    query = select(Task).order_by(Task.created_at.desc()).limit(min(limit, 200))
    if type is not None:
        query = query.where(Task.type == type)
    if not {"admin"}.intersection(r.name for r in user.roles):
        query = query.where(Task.user_id == user.id)
    tasks = (await db.execute(query)).scalars().all()
    if not tasks:
        return []
    creators = {u.id: (u.display_name or u.username) for u in
                (await db.execute(select(User).where(
                    User.id.in_({t.user_id for t in tasks})))).scalars()}
    assets = {a.id: a.name for a in
              (await db.execute(select(AssetLibrary).where(
                  AssetLibrary.id.in_({t.asset_id for t in tasks if t.asset_id} or [0])))).scalars()}
    return [TaskInfo(
        id=t.id, type=t.type, status=t.status, filename=t.filename,
        progress=t.progress, error=t.error, created_at=t.created_at,
        finished_at=t.finished_at, name=t.name, parser_type=t.parser_type,
        asset_id=t.asset_id, log_size=t.log_size, event_count=t.event_count,
        creator_name=creators.get(t.user_id, ""),
        asset_name=assets.get(t.asset_id, "") if t.asset_id else "") for t in tasks]


@router.get("/{task_id}", response_model=TaskInfo)
async def get_task(
    task_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
):
    task = await _load_visible_task(db, user, task_id)
    creator = (await db.execute(select(User).where(User.id == task.user_id))).first()
    asset_name = ""
    if task.asset_id:
        asset_name = (await db.execute(select(AssetLibrary.name)
                                       .where(AssetLibrary.id == task.asset_id))).scalar_one_or_none() or ""
    return TaskInfo(
        id=task.id, type=task.type, status=task.status, filename=task.filename,
        progress=task.progress, error=task.error, created_at=task.created_at,
        finished_at=task.finished_at, name=task.name, parser_type=task.parser_type,
        asset_id=task.asset_id, log_size=task.log_size, event_count=task.event_count,
        creator_name=creator[0].display_name if creator else "",
        asset_name=asset_name)


@router.delete("/{task_id}")
async def delete_task(
    task_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
):
    """删除任务 (task:delete; 事件随任务 CASCADE, 上传文件一并清理)."""
    task = (await db.execute(select(Task).where(Task.id == task_id))).scalar_one_or_none()
    if task is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "任务不存在")
    await _ensure_task_perm(db, user, task, "task:delete")
    team_id = await _team_id_of_task(db, task)
    log_audit(db, user, "删除解析任务", task.name or task.filename, team_id=team_id)
    # 先删关联数据 (Report/ParsedEventRecord, ORM 层未配置级联)
    from app.models.analyze import ParsedEventRecord
    from app.models.task import Report
    await db.execute(sa_delete(Report).where(Report.task_id == task_id))
    await db.execute(sa_delete(ParsedEventRecord).where(ParsedEventRecord.task_id == task_id))
    await db.delete(task)
    await db.commit()
    if task.storage_path:
        Path(task.storage_path).unlink(missing_ok=True)
        try:
            Path(task.storage_path).parent.rmdir()  # 空目录才移除
        except OSError:
            pass
    return {"detail": "任务已删除"}


@router.post("/{task_id}/cancel")
async def cancel_task(
    task_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    redis: Annotated[object, Depends(get_redis)],
):
    """取消: pending 直接置 cancelled; running 由 Worker 监听取消标记后停止."""
    task = (await db.execute(select(Task).where(Task.id == task_id))).scalar_one_or_none()
    if task is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "任务不存在")
    await _ensure_task_perm(db, user, task, "task:execute")
    if task.status in (TaskStatus.done, TaskStatus.failed, TaskStatus.cancelled):
        raise HTTPException(status.HTTP_409_CONFLICT, f"任务已结束: {task.status}")
    if task.status == TaskStatus.pending:
        task.status = TaskStatus.cancelled
        await db.commit()
    else:
        await redis.set(f"cancel:{task_id}", "1", ex=3600)  # Worker 轮询此标记
    return {"detail": "已请求取消"}
