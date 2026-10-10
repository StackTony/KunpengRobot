"""团队模型: 多团队协作体系 (团队/成员/通知审批流).

移植自 witty-log-analyzer 前端 Demo 的团队概念, 落地为关系型模型.
"""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Team(Base):
    """团队: 资产库与任务的归属主体."""
    __tablename__ = "teams"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True)
    desc: Mapped[str] = mapped_column(String(255), default="")
    owner_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TeamMember(Base):
    """团队成员: 用户在团队内的角色 (owner / team_admin / member)."""
    __tablename__ = "team_members"
    __table_args__ = (
        UniqueConstraint("team_id", "user_id", name="uq_team_member"),
        {"comment": "团队内三角色, 权限映射见 app/core/team_rbac.py"},
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(16))  # owner / team_admin / member
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TeamNotice(Base):
    """团队通知: 邀请 (invite) 与加入申请 (apply) 的审批流转."""
    __tablename__ = "team_notices"
    __table_args__ = (
        {"comment": "pending -> accepted / rejected; invite 由被邀人处理, apply 由团队 owner/team_admin 审批"},
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    type: Mapped[str] = mapped_column(String(8))            # invite / apply
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), index=True)
    from_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))  # 发起人 (邀请者/申请者)
    to_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))    # 处理人 (被邀人/审批人)
    role: Mapped[str] = mapped_column(String(16), default="member")    # 邀请/申请的目标角色
    status: Mapped[str] = mapped_column(String(10), default="pending", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
