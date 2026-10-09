"""任务: 日志包上传(入队即返回) / 任务列表 / 任务详情 / 取消."""
import os
import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import TaskInfo, UploadResponse
from app.core.config import get_settings
from app.core.database import get_db
from app.core.deps import get_current_user, get_redis
from app.models.task import Task, TaskStatus, TaskType
from app.models.user import User
from app.queue.task_queue import TaskQueue

router = APIRouter(prefix="/tasks", tags=["tasks"])
settings = get_settings()

ALLOWED_SUFFIXES = {".zip", ".tar", ".gz", ".tgz", ".tar.gz", ".log", ".txt"}


@router.post("/upload", response_model=UploadResponse)
async def upload(
    file: UploadFile,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    redis: Annotated[object, Depends(get_redis)],
    server_type: str = "",
):
    """上传日志包: 保存文件 → 创建任务 → 入队 → 立即返回 task_id (分析异步进行)."""
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

    task_id = uuid.uuid4()
    upload_dir = Path(settings.DATA_DIR) / "uploads" / str(task_id)
    upload_dir.mkdir(parents=True, exist_ok=True)
    storage_path = upload_dir / (file.filename or "upload.bin")

    size = 0
    limit = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    with open(storage_path, "wb") as f:
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > limit:
                f.close()
                storage_path.unlink(missing_ok=True)
                raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "文件超出大小限制")
            f.write(chunk)

    task = Task(
        id=task_id, type=TaskType.diagnosis, status=TaskStatus.pending,
        user_id=user.id, filename=file.filename or "upload.bin",
        storage_path=str(storage_path),
        params={"server_type": server_type},
    )
    db.add(task)
    await db.commit()

    queue = TaskQueue(redis)
    await queue.enqueue(str(task_id), "diagnosis", {"storage_path": str(storage_path), "server_type": server_type})
    return UploadResponse(task_id=task_id, status=task.status)


@router.get("", response_model=list[TaskInfo])
async def list_tasks(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    limit: int = 50,
):
    """普通用户看自己的任务; 管理员看全部."""
    query = select(Task).order_by(Task.created_at.desc()).limit(min(limit, 200))
    if not {"admin"}.intersection(r.name for r in user.roles):
        query = query.where(Task.user_id == user.id)
    return (await db.execute(query)).scalars().all()


@router.get("/{task_id}", response_model=TaskInfo)
async def get_task(
    task_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
):
    task = (await db.execute(select(Task).where(Task.id == task_id))).scalar_one_or_none()
    if task is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "任务不存在")
    if task.user_id != user.id and "admin" not in {r.name for r in user.roles}:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "无权访问该任务")
    return task


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
    if task.user_id != user.id and "admin" not in {r.name for r in user.roles}:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "无权操作该任务")
    if task.status in (TaskStatus.done, TaskStatus.failed, TaskStatus.cancelled):
        raise HTTPException(status.HTTP_409_CONFLICT, f"任务已结束: {task.status}")
    if task.status == TaskStatus.pending:
        task.status = TaskStatus.cancelled
        await db.commit()
    else:
        await redis.set(f"cancel:{task_id}", "1", ex=3600)  # Worker 轮询此标记
    return {"detail": "已请求取消"}
