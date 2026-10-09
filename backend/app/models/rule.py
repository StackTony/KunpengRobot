"""巡检/诊断规则模型 + 变更审计."""
import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class MatchType(str, enum.Enum):
    regex = "regex"          # 正则匹配日志行
    keyword = "keyword"      # 关键字包含
    threshold = "threshold"  # 指标阈值


class Severity(str, enum.Enum):
    info = "info"
    warn = "warn"
    error = "error"
    critical = "critical"


class Rule(Base):
    """规则为数据库实体, 版本化存储; Worker 按最大 version 感知变更并热加载."""
    __tablename__ = "rules"
    __table_args__ = (UniqueConstraint("name", "version", name="uq_rule_name_version"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128), index=True)
    description: Mapped[str] = mapped_column(String(512), default="")

    match_type: Mapped[MatchType] = mapped_column(Enum(MatchType))
    pattern: Mapped[str] = mapped_column(Text, default="")              # 正则表达式 / 关键字
    threshold: Mapped[dict] = mapped_column(JSONB, default=dict)        # 阈值规则: {metric, op, value}

    severity: Mapped[Severity] = mapped_column(Enum(Severity), default=Severity.warn)
    log_type: Mapped[str] = mapped_column(String(64), default="")       # 适用日志类型 (空=全部)
    server_type: Mapped[str] = mapped_column(String(64), default="")    # 适用服务器类型 (空=全部)

    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    priority: Mapped[int] = mapped_column(Integer, default=100)
    version: Mapped[int] = mapped_column(Integer, default=1, index=True)

    is_builtin: Mapped[bool] = mapped_column(Boolean, default=False)    # 预置规则
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class RuleAuditLog(Base):
    """规则变更审计: 记录操作人/动作/变更内容."""
    __tablename__ = "rule_audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    rule_id: Mapped[int] = mapped_column(ForeignKey("rules.id", ondelete="CASCADE"), index=True)
    rule_name: Mapped[str] = mapped_column(String(128))
    action: Mapped[str] = mapped_column(String(16))  # create / update / delete
    operator_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    detail: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
