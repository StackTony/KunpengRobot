"""资产库 API: 团队内资产 CRUD + 资产下任务分页列表 (含时序 spark 概览)."""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import AssetCreate, AssetInfo, AssetUpdate, TaskInfo, TaskListPage
from app.core.database import get_db
from app.core.deps import ensure_team_perm, get_current_user, require_team_perm
from app.models.asset import AssetLibrary
from app.models.task import Task
from app.models.user import User

router = APIRouter(tags=["assets"])

SPARK_BUCKETS = 16


async def _load_asset(db: AsyncSession, asset_id: int) -> AssetLibrary:
    asset = (await db.execute(select(AssetLibrary).where(AssetLibrary.id == asset_id))).scalar_one_or_none()
    if asset is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "资产库不存在")
    return asset


def _asset_info(a: AssetLibrary, task_count: int = 0) -> AssetInfo:
    return AssetInfo(id=a.id, team_id=a.team_id, name=a.name, desc=a.desc,
                     ip_range=a.ip_range, created_at=a.created_at, task_count=task_count)


@router.get("/teams/{team_id}/assets", response_model=list[AssetInfo])
async def list_assets(
    team_id: int,
    trio: Annotated[tuple, Depends(require_team_perm("asset:view"))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """团队资产库列表 (含每库任务数)."""
    _, team, _ = trio
    assets = (await db.execute(select(AssetLibrary).where(AssetLibrary.team_id == team_id)
                               .order_by(AssetLibrary.created_at))).scalars().all()
    counts = dict((await db.execute(
        select(Task.asset_id, func.count())
        .where(Task.asset_id.in_([a.id for a in assets] or [0]))
        .group_by(Task.asset_id))).all())
    return [_asset_info(a, counts.get(a.id, 0)) for a in assets]


@router.post("/teams/{team_id}/assets", response_model=AssetInfo, status_code=status.HTTP_201_CREATED)
async def create_asset(
    team_id: int,
    body: AssetCreate,
    trio: Annotated[tuple, Depends(require_team_perm("asset:create"))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    _, team, _ = trio
    asset = AssetLibrary(team_id=team_id, name=body.name, desc=body.desc, ip_range=body.ip_range)
    db.add(asset)
    await db.commit()
    return _asset_info(asset)


@router.get("/assets/{asset_id}", response_model=AssetInfo)
async def get_asset(
    asset_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
):
    asset = await _load_asset(db, asset_id)
    await ensure_team_perm(db, user, asset.team_id, "asset:view")
    count = (await db.execute(select(func.count()).select_from(Task)
                              .where(Task.asset_id == asset_id))).scalar_one()
    return _asset_info(asset, count)


@router.put("/assets/{asset_id}", response_model=AssetInfo)
async def update_asset(
    asset_id: int,
    body: AssetUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
):
    asset = await _load_asset(db, asset_id)
    await ensure_team_perm(db, user, asset.team_id, "asset:edit")
    asset.name, asset.desc, asset.ip_range = body.name, body.desc, body.ip_range
    await db.commit()
    return _asset_info(asset)


@router.delete("/assets/{asset_id}")
async def delete_asset(
    asset_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
):
    """删除资产库: 级联删除库下解析任务 (事件随任务 CASCADE)."""
    asset = await _load_asset(db, asset_id)
    await ensure_team_perm(db, user, asset.team_id, "asset:delete")
    tasks = (await db.execute(select(Task).where(Task.asset_id == asset_id))).scalars().all()
    for t in tasks:
        await db.delete(t)
    await db.delete(asset)
    await db.commit()
    return {"detail": "资产库及库下任务已删除"}


async def _spark_of(db: AsyncSession, task_id) -> list[dict]:
    """单任务 16 桶时序概览 (SQL width_bucket, 免全量加载)."""
    rows = (await db.execute(text("""
        WITH t AS (SELECT min(ts) mn, max(ts) mx FROM parsed_events WHERE task_id = :tid)
        SELECT width_bucket(pe.ts, t.mn, t.mx + 1, :n) AS b,
               count(*) AS total,
               count(*) FILTER (WHERE pe.severity = 'critical') AS critical,
               count(*) FILTER (WHERE pe.severity = 'error') AS error
        FROM parsed_events pe, t
        WHERE pe.task_id = :tid
        GROUP BY 1 ORDER BY 1
    """), {"tid": str(task_id), "n": SPARK_BUCKETS})).all()
    if not rows:
        return []
    bounds = (await db.execute(text(
        "SELECT min(ts) mn, max(ts) mx FROM parsed_events WHERE task_id = :tid"),
        {"tid": str(task_id)})).one()
    mn, mx = int(bounds.mn), int(bounds.mx)
    step = max(mx - mn, 60_000) / SPARK_BUCKETS
    by_idx = {int(r[0]): (int(r[1]), int(r[2]), int(r[3])) for r in rows}
    from datetime import datetime
    out = []
    for i in range(SPARK_BUCKETS):
        t = int(mn + i * step)
        lt = datetime.fromtimestamp(t / 1000)
        total, crit, err = by_idx.get(i + 1, (0, 0, 0))  # width_bucket 从 1 起
        out.append({"t": t,
                    "label": f"{lt.hour:02d}:{lt.minute:02d}",
                    "total": total, "critical": crit, "error": err})
    return out


@router.get("/assets/{asset_id}/tasks", response_model=TaskListPage)
async def list_asset_tasks(
    asset_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    status_filter: str | None = None,
    parser_type: str | None = None,
    kw: str | None = None,
    page: int = 1,
    page_size: int = 10,
):
    """资产库下任务 (服务端分页/筛选 + 每任务 spark)."""
    asset = await _load_asset(db, asset_id)
    await ensure_team_perm(db, user, asset.team_id, "task:view")

    query = select(Task).where(Task.asset_id == asset_id)
    if status_filter:
        query = query.where(Task.status == status_filter)
    if parser_type:
        query = query.where(Task.parser_type == parser_type)
    if kw:
        query = query.where(Task.name.ilike(f"%{kw}%"))
    total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar_one()
    tasks = (await db.execute(query.order_by(Task.created_at.desc())
                              .offset((page - 1) * page_size).limit(page_size))).scalars().all()

    items, sparks = [], {}
    for t in tasks:
        creator = (await db.execute(select(User.display_name, User.username)
                                    .where(User.id == t.user_id))).first()
        items.append(TaskInfo(
            id=t.id, type=t.type, status=t.status, filename=t.filename,
            progress=t.progress, error=t.error, created_at=t.created_at,
            finished_at=t.finished_at, name=t.name, parser_type=t.parser_type,
            asset_id=t.asset_id, log_size=t.log_size, event_count=t.event_count,
            creator_name=(creator[0] or creator[1]) if creator else "",
            asset_name=asset.name))
        sparks[str(t.id)] = await _spark_of(db, t.id)
    return TaskListPage(total=total, items=items, sparks=sparks)
