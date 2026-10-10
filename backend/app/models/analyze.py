"""解析事件存储: analyze 任务解析出的结构化日志事件.

统一事件模型与 witty-log-analyzer 的 ParsedEvent 对齐:
{timestamp(ms), sourceIp, severity, category, errorCode, raw, fields}
供结果页时序/饼图/错误码/IP 聚合与原始日志多维筛选.
"""
import uuid

from sqlalchemy import BigInteger, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ParsedEventRecord(Base):
    __tablename__ = "parsed_events"
    __table_args__ = (
        # 任务内查询都以 task_id 打头: 分页/时序/错误码三个场景
        Index("ix_pe_task_ts", "task_id", "ts"),
        Index("ix_pe_task_code", "task_id", "error_code"),
        {"comment": "随任务级联删除; 单任务万级行不做分区, 数据量增长后再考虑"},
    )

    id: Mapped[int] = mapped_column(BigInteger, autoincrement=True, primary_key=True)
    task_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tasks.id", ondelete="CASCADE"))
    ts: Mapped[int] = mapped_column(BigInteger)                 # ms epoch, 与前端 fmtTime(ms) 一致
    source_ip: Mapped[str] = mapped_column(String(64), default="")
    severity: Mapped[str] = mapped_column(String(16), default="info")  # critical/error/warning/info
    category: Mapped[str] = mapped_column(String(64), default="")
    error_code: Mapped[str] = mapped_column(String(64), default="")
    raw: Mapped[str] = mapped_column(Text, default="")
    fields: Mapped[dict] = mapped_column(JSONB, default=dict)
