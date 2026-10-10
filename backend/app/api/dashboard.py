"""工作台: 一次返回我的团队范围内的计数 / KPI / 最近任务 / 高频错误码."""
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import DashboardResponse, TaskInfo
from app.core.database import get_db
from app.core.deps import get_current_user, is_platform_admin
from app.models.asset import AssetLibrary
from app.models.task import Task
from app.models.team import Team, TeamMember
from app.models.user import User

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("", response_model=DashboardResponse)
async def dashboard(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
):
    """我的团队范围聚合 (平台管理员为全量范围)."""
    if is_platform_admin(user):
        team_ids = list((await db.execute(select(Team.id))).scalars().all())
    else:
        team_ids = list((await db.execute(
            select(TeamMember.team_id).where(TeamMember.user_id == user.id))).scalars().all())

    asset_ids = list((await db.execute(
        select(AssetLibrary.id).where(AssetLibrary.team_id.in_(team_ids or [0])))).scalars().all())
    task_query = select(Task).where(Task.asset_id.in_(asset_ids or [0]))
    tasks = (await db.execute(task_query.order_by(Task.created_at.desc())
                              .limit(500))).scalars().all()

    # KPI 与 Top 错误码: 直接在事件表按范围聚合 (SQL, 免加载)
    from app.models.analyze import ParsedEventRecord
    task_ids = [t.id for t in tasks]
    kpi = {"total": 0, "critical": 0, "error": 0, "warning": 0}
    top_codes: list[dict] = []
    if task_ids:
        rows = (await db.execute(
            select(ParsedEventRecord.severity, func.count())
            .where(ParsedEventRecord.task_id.in_(task_ids))
            .group_by(ParsedEventRecord.severity))).all()
        for sev, cnt in rows:
            kpi["total"] += cnt
            if sev in kpi:
                kpi[sev] = cnt
        code_rows = (await db.execute(
            select(ParsedEventRecord.error_code, func.count())
            .where(ParsedEventRecord.task_id.in_(task_ids), ParsedEventRecord.error_code != "")
            .group_by(ParsedEventRecord.error_code)
            .order_by(func.count().desc()).limit(8))).all()
        top_codes = [{"name": c, "value": n} for c, n in code_rows]

    recent: list[TaskInfo] = []
    asset_names = dict((await db.execute(
        select(AssetLibrary.id, AssetLibrary.name)
        .where(AssetLibrary.id.in_([t.asset_id for t in tasks[:10]] or [0])))).all())
    for t in tasks[:10]:
        creator = (await db.execute(select(User.display_name, User.username)
                                    .where(User.id == t.user_id))).first()
        recent.append(TaskInfo(
            id=t.id, type=t.type, status=t.status, filename=t.filename,
            progress=t.progress, error=t.error, created_at=t.created_at,
            finished_at=t.finished_at, name=t.name, parser_type=t.parser_type,
            asset_id=t.asset_id, log_size=t.log_size, event_count=t.event_count,
            creator_name=(creator[0] or creator[1]) if creator else "",
            asset_name=asset_names.get(t.asset_id, "") if t.asset_id else ""))

    return DashboardResponse(
        teams=len(team_ids), assets=len(asset_ids), tasks=len(tasks),
        kpi=kpi, recent_tasks=recent, top_codes=top_codes)
