"""性能指标时序数据 + 用户视图偏好.

metric_points 采用 PostgreSQL 时间分区表 (按月), 分区 DDL 由 alembic 迁移
或 metrics/partitions.py 中的管理函数创建, 查询侧完全透明.
"""
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, DOUBLE_PRECISION, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class MetricPoint(Base):
    """一条指标数据点: (时间, 主机, 指标名) -> 值.

    分区键为 metric_time (按月 RANGE 分区), 应用侧正常写入即可路由.
    """
    __tablename__ = "metric_points"
    __table_args__ = (
        Index("ix_metric_points_lookup", "host", "metric_name", "metric_time"),
        {"postgresql_partition_by": "RANGE (metric_time)"},
    )

    metric_time: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), primary_key=True)
    host: Mapped[str] = mapped_column(String(128), primary_key=True)
    metric_name: Mapped[str] = mapped_column(String(64), primary_key=True)  # e.g. cpu.usage / mem.used_pct
    value: Mapped[float] = mapped_column(DOUBLE_PRECISION)
    tags: Mapped[dict] = mapped_column(JSONB, default=dict)                 # 额外标签 (磁盘名/网卡名等)
    task_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)  # 来源任务


class UserPreference(Base):
    """用户视图偏好 (图表布局/所选指标/时间范围等), 落库保证刷新/换设备不丢."""
    __tablename__ = "user_preferences"
    __table_args__ = (UniqueConstraint("user_id", "pref_key", name="uq_user_pref"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    pref_key: Mapped[str] = mapped_column(String(64))   # e.g. dashboard.charts
    pref_value: Mapped[dict] = mapped_column(JSONB, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
