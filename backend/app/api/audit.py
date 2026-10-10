"""审计日志 API: 团队级过滤 + 关键字/动作筛选 + 分页.

- 指定 team_id: 需要该团队 audit:view 权限
- 未指定: 只看「我的团队 ∪ 我自己」的记录 (非管理员无法全库检索)
"""
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import AuditPage, AuditRecordOut
from app.core.database import get_db
from app.core.deps import ensure_team_perm, get_current_user, is_platform_admin
from app.core.team_rbac import AUDIT_ACTIONS
from app.models.audit import AuditLog
from app.models.team import Team, TeamMember
from app.models.user import User

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("", response_model=AuditPage)
async def query_audit(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    team_id: int | None = None,
    action: str | None = None,
    kw: str | None = None,
    page: int = 1,
    page_size: int = Query(default=20, le=100),
):
    if team_id is not None:
        await ensure_team_perm(db, user, team_id, "audit:view")
        scope = AuditLog.team_id == team_id
    elif is_platform_admin(user):
        scope = None  # 平台管理员全库
    else:
        my_teams = (await db.execute(
            select(TeamMember.team_id).where(TeamMember.user_id == user.id))).scalars().all()
        conds = [AuditLog.user_id == user.id]
        if my_teams:
            conds.append(AuditLog.team_id.in_(my_teams))
        scope = or_(*conds)

    query = select(AuditLog)
    count_query = select(func.count()).select_from(AuditLog)
    if scope is not None:
        query = query.where(scope)
        count_query = count_query.where(scope)
    if action:
        query = query.where(AuditLog.action == action)
        count_query = count_query.where(AuditLog.action == action)
    if kw:
        like = f"%{kw}%"
        query = query.where(or_(AuditLog.target.ilike(like), AuditLog.user_name.ilike(like)))
        count_query = count_query.where(or_(AuditLog.target.ilike(like), AuditLog.user_name.ilike(like)))

    total = (await db.execute(count_query)).scalar_one()
    rows = (await db.execute(query.order_by(AuditLog.created_at.desc())
                             .offset((page - 1) * page_size).limit(page_size))).scalars().all()

    team_names = dict((await db.execute(
        select(Team.id, Team.name).where(Team.id.in_(
            [r.team_id for r in rows if r.team_id] or [0])))).all())
    items = [AuditRecordOut(
        id=r.id, created_at=r.created_at, user_name=r.user_name, action=r.action,
        team_id=r.team_id, team_name=team_names.get(r.team_id, "") if r.team_id else "",
        target=r.target, success=r.success) for r in rows]
    return AuditPage(total=total, items=items, actions=list(AUDIT_ACTIONS))
