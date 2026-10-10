"""团队 API: 列表/创建/详情/编辑 + 邀请/申请 + 成员角色管理 (团队级 RBAC).

对齐 witty-log-analyzer 团队体系: 三角色 (owner/team_admin/member)、
邀请与申请审批流、创建团队自动建同名资产库.
"""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import (InviteRequest, MemberInfo, MemberRoleUpdate, NoticeInfo,
                             TeamCreate, TeamDetail, TeamInfo, TeamUpdate)
from app.core.audit import log_audit
from app.core.database import get_db
from app.core.deps import get_current_user, load_team_role, require_team_perm
from app.models.asset import AssetLibrary
from app.models.task import Task
from app.models.team import Team, TeamMember, TeamNotice
from app.models.user import User

router = APIRouter(prefix="/teams", tags=["teams"])

VALID_ROLES = {"member", "team_admin"}  # owner 仅经创建/转让产生, 不走邀请与角色调整


async def _team_aggregates(db: AsyncSession, team_ids: list[int]) -> dict[int, dict]:
    """每团队聚合: 成员数/资产数/任务数."""
    out = {tid: {"members": 0, "assets": 0, "tasks": 0} for tid in team_ids}
    if not team_ids:
        return out
    for row in (await db.execute(
        select(TeamMember.team_id, func.count())
        .where(TeamMember.team_id.in_(team_ids)).group_by(TeamMember.team_id))).all():
        out[row[0]]["members"] = row[1]
    for row in (await db.execute(
        select(AssetLibrary.team_id, func.count())
        .where(AssetLibrary.team_id.in_(team_ids)).group_by(AssetLibrary.team_id))).all():
        out[row[0]]["assets"] = row[1]
    for row in (await db.execute(
        select(Task.asset_id, func.count()).join(AssetLibrary, Task.asset_id == AssetLibrary.id)
        .where(AssetLibrary.team_id.in_(team_ids)).group_by(Task.asset_id))).all():
        # 任务数挂在资产维度, 汇总回团队
        asset = (await db.execute(select(AssetLibrary.team_id)
                                  .where(AssetLibrary.id == row[0]))).scalar_one_or_none()
        if asset is not None:
            out[asset]["tasks"] += row[1]
    return out


def _team_info(team: Team, agg: dict, my_role: str | None) -> TeamInfo:
    return TeamInfo(
        id=team.id, name=team.name, desc=team.desc,
        owner_user_id=team.owner_user_id, created_at=team.created_at,
        my_role=my_role, member_count=agg["members"],
        asset_count=agg["assets"], task_count=agg["tasks"])


@router.get("", response_model=list[TeamInfo])
async def list_teams(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
):
    """全部团队概览 (非成员也可看, 供「申请加入」); my_role 标识我的角色."""
    teams = (await db.execute(select(Team).order_by(Team.created_at.desc()))).scalars().all()
    my_roles = {m.team_id: m.role for m in (await db.execute(
        select(TeamMember).where(TeamMember.user_id == user.id))).scalars()}
    aggs = await _team_aggregates(db, [t.id for t in teams])
    return [_team_info(t, aggs.get(t.id, {"members": 0, "assets": 0, "tasks": 0}),
                       my_roles.get(t.id)) for t in teams]


@router.post("", response_model=TeamInfo, status_code=status.HTTP_201_CREATED)
async def create_team(
    body: TeamCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
):
    """创建团队: 同事务建 Team + owner 成员 + 同名资产库 (对齐 witty 联动)."""
    if (await db.execute(select(Team).where(Team.name == body.name))).scalar_one_or_none():
        raise HTTPException(status.HTTP_409_CONFLICT, "团队名已存在")
    team = Team(name=body.name, desc=body.desc, owner_user_id=user.id)
    db.add(team)
    await db.flush()
    db.add(TeamMember(team_id=team.id, user_id=user.id, role="owner"))
    db.add(AssetLibrary(team_id=team.id, name=body.name,
                        desc=f"{body.name} 默认资产库", ip_range=""))
    log_audit(db, user, "创建团队", f"{body.name}（你自动成为创建者）", team_id=team.id)
    await db.commit()
    return TeamInfo(id=team.id, name=team.name, desc=team.desc,
                    owner_user_id=team.owner_user_id, created_at=team.created_at,
                    my_role="owner", member_count=1, asset_count=1, task_count=0)


@router.get("/{team_id}", response_model=TeamDetail)
async def team_detail(
    team_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
):
    """团队详情: 成员/资产库/待审批申请 (申请仅 owner/team_admin 可见)."""
    team = (await db.execute(select(Team).where(Team.id == team_id))).scalar_one_or_none()
    if team is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "团队不存在")
    _, my_role = await load_team_role(db, user, team_id)

    members = [MemberInfo(
        user_id=u.id, name=u.display_name or u.username, email=u.email,
        title=u.title, dept=u.dept, avatar_hue=u.avatar_hue, role=m.role)
        for m, u in (await db.execute(
            select(TeamMember, User).join(User, TeamMember.user_id == User.id)
            .where(TeamMember.team_id == team_id)
            .order_by(TeamMember.created_at))).all()]

    assets = (await db.execute(
        select(AssetLibrary).where(AssetLibrary.team_id == team_id)
        .order_by(AssetLibrary.created_at))).scalars().all()
    asset_task_counts = dict((await db.execute(
        select(Task.asset_id, func.count()).where(Task.asset_id.in_([a.id for a in assets] or [0]))
        .group_by(Task.asset_id))).all())
    from app.api.schemas import AssetInfo
    asset_infos = [AssetInfo(id=a.id, team_id=a.team_id, name=a.name, desc=a.desc,
                             ip_range=a.ip_range, created_at=a.created_at,
                             task_count=asset_task_counts.get(a.id, 0)) for a in assets]

    pending_applies: list[NoticeInfo] = []
    if my_role in ("owner", "team_admin"):
        pending_applies = await _notice_infos(db, select(TeamNotice).where(
            TeamNotice.team_id == team_id, TeamNotice.type == "apply",
            TeamNotice.status == "pending"))

    agg = (await _team_aggregates(db, [team_id])).get(team_id,
                                                      {"members": 0, "assets": 0, "tasks": 0})
    return TeamDetail(
        id=team.id, name=team.name, desc=team.desc, owner_user_id=team.owner_user_id,
        created_at=team.created_at, my_role=my_role,
        member_count=agg["members"], asset_count=agg["assets"], task_count=agg["tasks"],
        members=members, assets=asset_infos, pending_applies=pending_applies)


@router.put("/{team_id}", response_model=TeamInfo)
async def update_team(
    team_id: int,
    body: TeamUpdate,
    trio: Annotated[tuple, Depends(require_team_perm("team:role"))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """编辑团队信息 (owner / team_admin)."""
    user, team, _ = trio
    if body.name != team.name:
        if (await db.execute(select(Team).where(Team.name == body.name))).scalar_one_or_none():
            raise HTTPException(status.HTTP_409_CONFLICT, "团队名已存在")
    team.name, team.desc = body.name, body.desc
    log_audit(db, user, "编辑团队", body.name, team_id=team_id)
    await db.commit()
    agg = (await _team_aggregates(db, [team_id])).get(team_id,
                                                      {"members": 0, "assets": 0, "tasks": 0})
    _, my_role = await load_team_role(db, user, team_id)
    return _team_info(team, agg, my_role)


async def _notice_infos(db: AsyncSession, query) -> list[NoticeInfo]:
    """TeamNotice 行 → NoticeInfo (join 团队名/发起人/处理人)."""
    rows = (await db.execute(
        query)).scalars().all()
    out: list[NoticeInfo] = []
    for n in rows:
        team_name = (await db.execute(select(Team.name).where(Team.id == n.team_id))).scalar_one_or_none() or ""
        from_name = (await db.execute(select(User.display_name, User.username)
                                      .where(User.id == n.from_user_id))).first()
        to_name = (await db.execute(select(User.display_name, User.username)
                                    .where(User.id == n.to_user_id))).first()
        out.append(NoticeInfo(
            id=n.id, type=n.type, team_id=n.team_id, team_name=team_name,
            from_user_id=n.from_user_id,
            from_user_name=(from_name[0] or from_name[1]) if from_name else "",
            to_user_id=n.to_user_id,
            to_user_name=(to_name[0] or to_name[1]) if to_name else "",
            role=n.role, status=n.status, created_at=n.created_at))
    return out


@router.post("/{team_id}/invite", status_code=status.HTTP_201_CREATED)
async def invite_member(
    team_id: int,
    body: InviteRequest,
    trio: Annotated[tuple, Depends(require_team_perm("team:invite"))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """邀请成员 (owner/team_admin): 生成 pending 邀请, 待对方在通知中心确认."""
    user, team, _ = trio
    if body.role not in VALID_ROLES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"角色必须是: {sorted(VALID_ROLES)}")
    target = (await db.execute(select(User).where(User.id == body.user_id))).scalar_one_or_none()
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "用户不存在")
    if (await db.execute(select(TeamMember).where(
            TeamMember.team_id == team_id, TeamMember.user_id == body.user_id))).scalar_one_or_none():
        raise HTTPException(status.HTTP_409_CONFLICT, "该用户已是团队成员")
    dup = (await db.execute(select(TeamNotice).where(
        TeamNotice.type == "invite", TeamNotice.team_id == team_id,
        TeamNotice.to_user_id == body.user_id, TeamNotice.status == "pending"))).scalar_one_or_none()
    if dup is None:  # 重复 pending 邀请幂等跳过
        db.add(TeamNotice(type="invite", team_id=team_id, from_user_id=user.id,
                          to_user_id=body.user_id, role=body.role))
    log_audit(db, user, "邀请加入团队",
              f"{team.name} / {target.display_name or target.username}（对方右上角确认）",
              team_id=team_id)
    await db.commit()
    return {"detail": "邀请已发送"}


@router.post("/{team_id}/apply", status_code=status.HTTP_201_CREATED)
async def apply_join(
    team_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
):
    """申请加入团队 (任意登录用户): 生成 pending 申请, 待 owner/team_admin 审批."""
    team = (await db.execute(select(Team).where(Team.id == team_id))).scalar_one_or_none()
    if team is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "团队不存在")
    if (await db.execute(select(TeamMember).where(
            TeamMember.team_id == team_id, TeamMember.user_id == user.id))).scalar_one_or_none():
        raise HTTPException(status.HTTP_409_CONFLICT, "你已是团队成员")
    dup = (await db.execute(select(TeamNotice).where(
        TeamNotice.type == "apply", TeamNotice.team_id == team_id,
        TeamNotice.from_user_id == user.id, TeamNotice.status == "pending"))).scalar_one_or_none()
    if dup is None:
        # 默认审批人: 团队 owner (与 witty apply 行为一致)
        db.add(TeamNotice(type="apply", team_id=team_id, from_user_id=user.id,
                          to_user_id=team.owner_user_id, role="member"))
    log_audit(db, user, "申请加入团队", team.name, team_id=team_id)
    await db.commit()
    return {"detail": "申请已提交"}


@router.put("/{team_id}/members/{member_user_id}")
async def update_member_role(
    team_id: int,
    member_user_id: int,
    body: MemberRoleUpdate,
    trio: Annotated[tuple, Depends(require_team_perm("team:role"))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """调整成员角色 (owner/team_admin); owner 角色受保护不可调整."""
    user, team, _ = trio
    if body.role not in VALID_ROLES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"角色必须是: {sorted(VALID_ROLES)}")
    member = (await db.execute(select(TeamMember).where(
        TeamMember.team_id == team_id, TeamMember.user_id == member_user_id))).scalar_one_or_none()
    if member is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "成员不存在")
    if member.role == "owner":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "创建者角色不可调整")
    member.role = body.role
    target = (await db.execute(select(User).where(User.id == member_user_id))).scalar_one()
    log_audit(db, user, "调整成员角色",
              f"{team.name} / {target.display_name or target.username} → {body.role}",
              team_id=team_id)
    await db.commit()
    return {"detail": "角色已更新"}


@router.delete("/{team_id}/members/{member_user_id}")
async def remove_member(
    team_id: int,
    member_user_id: int,
    trio: Annotated[tuple, Depends(require_team_perm("team:remove"))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """移除团队成员 (owner/team_admin); owner 不可被移除, 也不可移除自己."""
    user, team, _ = trio
    member = (await db.execute(select(TeamMember).where(
        TeamMember.team_id == team_id, TeamMember.user_id == member_user_id))).scalar_one_or_none()
    if member is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "成员不存在")
    if member.role == "owner":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "创建者不可被移除")
    if member_user_id == user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "不可移除自己")
    await db.delete(member)
    target = (await db.execute(select(User).where(User.id == member_user_id))).scalar_one()
    log_audit(db, user, "移除团队成员",
              f"{team.name} / {target.display_name or target.username}", team_id=team_id)
    await db.commit()
    return {"detail": "成员已移除"}
