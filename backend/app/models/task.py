"""分析任务模型 (诊断/巡检/解析任务统一)."""
import enum
import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class TaskType(str, enum.Enum):
    diagnosis = "diagnosis"      # 故障诊断日志分析
    inspection = "inspection"    # 智能巡检
    analyze = "analyze"          # 解析任务 (witty: 指定解析器的事件化分析)


class TaskStatus(str, enum.Enum):
    pending = "pending"
    running = "running"
    done = "done"
    failed = "failed"
    cancelled = "cancelled"
    interrupted = "interrupted"  # 进程重启遗留, 可重新下发


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    type: Mapped[TaskType] = mapped_column(Enum(TaskType))
    status: Mapped[TaskStatus] = mapped_column(Enum(TaskStatus), default=TaskStatus.pending, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)

    # 上传/输入
    filename: Mapped[str] = mapped_column(String(255), default="")
    storage_path: Mapped[str] = mapped_column(String(512), default="")  # 日志包存储位置
    params: Mapped[dict] = mapped_column(JSONB, default=dict)           # 附加参数 (服务器类型/巡检模板等)

    # 解析任务扩展 (witty 接入; 诊断/巡检任务这些列为空)
    name: Mapped[str] = mapped_column(String(128), default="")          # 任务名称
    parser_type: Mapped[str] = mapped_column(String(32), default="")    # sel/redfish/syslog/dmesg/windows/regex
    asset_id: Mapped[int | None] = mapped_column(ForeignKey("asset_libraries.id"), index=True, nullable=True)
    log_size: Mapped[int] = mapped_column(BigInteger, default=0)        # 上传日志字节数
    event_count: Mapped[int] = mapped_column(Integer, default=0)        # 解析事件数 (冗余计数, 避免 COUNT)

    # 执行
    progress: Mapped[int] = mapped_column(Integer, default=0)           # 0-100
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    report: Mapped["Report | None"] = relationship(back_populates="task", uselist=False, lazy="selectin")


class Report(Base):
    """分析报告: 规则命中明细 + LLM 总结."""
    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), unique=True)
    health_score: Mapped[int | None] = mapped_column(Integer)           # 巡检健康评分 0-100
    summary: Mapped[str] = mapped_column(Text, default="")              # LLM/规则总结
    findings: Mapped[list] = mapped_column(JSONB, default=list)         # 规则命中条目
    content: Mapped[dict] = mapped_column(JSONB, default=dict)          # 完整报告结构
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    task: Mapped[Task] = relationship(back_populates="report")
