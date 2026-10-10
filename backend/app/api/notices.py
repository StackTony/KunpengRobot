"""通知中心: 我的待办 (收到的邀请 ∪ 待我审批的申请) + 处理流转.

规则与 witty myNotices 一致:
- invite 且 status=pending: 仅 to_user (被邀请人) 可见/可处理
- apply  且 status=pending: 团队 owner/team_admin (审批人) 可见/可处理
- accept 时同事务 grantMember (成员不存在则加入, 角色取通知上的 role)
"""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import NoticeInfo, NoticeResolve
from app.api.teams import _notice_infos
from app.core.audit import log_audit
from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.team import Team, TeamMember, TeamNotice
from app.models.user import User

router = APIRouter(prefix="/notices", tags=["notices"])


async def _my_pending_applies(db: AsyncSession, user: User) -> list[int]:
    """我作为 owner/team_admin 的团队 → 其 pending apply 的 team_id 集合."""
    admin_teams = (await db.execute(
        select(TeamMember.team_id).where(
            TeamMember.user_id == user.id,
            TeamMember.role.in_(["owner", "team_admin"])))).scalars().all()
    if not admin_teams:
        return []
    return list((await db.execute(
        select(TeamNotice.team_id).where(
            TeamNotice.type == "apply", TeamNotice.status == "pending",
            TeamNotice.team_id.in_(admin_teams)))).scalars().all())


@router.get("", response_model=list[NoticeInfo])
async def my_notices(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
):
    """我的待办通知: 发给我的 pending 邀请 ∪ 我有权审批的 pending 申请."""
    invites = select(TeamNotice).where(
        TeamNotice.type == "invite", TeamNotice.status == "pending",
        TeamNotice.to_user_id == user.id)
    invite_infos = await _notice_infos(db, invites)
    apply_team_ids = await _my_pending_applies(db, user)
    apply_infos: list[NoticeInfo] = []
    if apply_team_ids:
        applies = select(TeamNotice).where(
            TeamNotice.type == "apply", TeamNotice.status == "pending",
            TeamNotice.team_id.in_(apply_team_ids))
        apply_infos = await _notice_infos(db, applies)
    # 邀请优先 (个人事务), 申请随后 (团队审批)
    return invite_infos + apply_infos


@router.post("/{notice_id}/resolve")
async def resolve_notice(
    notice_id: int,
    body: NoticeResolve,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
):
    """处理通知: invite 由被邀请人处理, apply 由团队审批角色处理; accept 同事务入团."""
    n = (await db.execute(select(TeamNotice).where(TeamNotice.id == notice_id))).scalar_one_or_none()
    if n is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "通知不存在")
    if n.status != "pending":
        raise HTTPException(status.HTTP_409_CONFLICT, f"通知已处理: {n.status}")

    team = (await db.execute(select(Team).where(Team.id == n.team_id))).scalar_one()

    if n.type == "invite":
        if n.to_user_id != user.id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "仅被邀请人本人可处理邀请")
        action, join_user_id = "处理团队邀请", n.to_user_id
    else:  # apply
        member = (await db.execute(select(TeamMember).where(
            TeamMember.team_id == n.team_id, TeamMember.user_id == user.id))).scalar_one_or_none()
        if member is None or member.role not in ("owner", "team_admin"):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "仅团队创建者/管理员可审批申请")
        action, join_user_id = "处理加入申请", n.from_user_id

    n.status = "accepted" if body.accept else "rejected"
    if body.accept:
        existing = (await db.execute(select(TeamMember).where(
            TeamMember.team_id == n.team_id, TeamMember.user_id == join_user_id))).scalar_one_or_none()
        if existing is None:
            db.add(TeamMember(team_id=n.team_id, user_id=join_user_id, role=n.role or "member"))
        else:
            existing.role = n.role or "member"

    join_target = (await db.execute(select(User).where(User.id == join_user_id))).scalar_one()
    log_audit(db, user, action,
              f"{team.name} / {join_target.display_name or join_target.username}"
              f" → {'同意' if body.accept else '拒绝'}",
              team_id=n.team_id)
    await db.commit()
    return {"detail": "已同意" if body.accept else "已拒绝"}
