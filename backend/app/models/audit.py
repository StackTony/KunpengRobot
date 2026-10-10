"""通用操作审计日志 (团队级).

与 RuleAuditLog 分工: 规则 CRUD 继续走 RuleAuditLog, 本表记录平台/团队操作
(登录/创建团队/邀请/审批/任务/LLM 分析等), action 存中文标签与前端筛选下拉对齐.
"""
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        {"comment": "team_id 结构化过滤, 替代前端 Demo 的 target 字符串 includes 匹配"},
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    user_name: Mapped[str] = mapped_column(String(64), default="")     # 冗余快照, 防用户改名
    action: Mapped[str] = mapped_column(String(32))                    # 中文标签, e.g. 创建团队
    team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id"), index=True)
    target: Mapped[str] = mapped_column(String(255), default="")       # 操作对象描述
    success: Mapped[bool] = mapped_column(Boolean, default=True)
    detail: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
