"""资产库模型: 按 IP 段组织设备资产, 解析任务归属资产库."""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AssetLibrary(Base):
    """资产库: 归属唯一团队 (关系型用资产侧 FK 表达, 替代前端 Demo 的 team.assetIds 数组)."""
    __tablename__ = "asset_libraries"

    id: Mapped[int] = mapped_column(primary_key=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(64))
    desc: Mapped[str] = mapped_column(String(255), default="")
    ip_range: Mapped[str] = mapped_column(String(128), default="")  # e.g. 10.1.3.0/24
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
