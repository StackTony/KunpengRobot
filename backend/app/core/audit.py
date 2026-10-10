"""审计日志写入辅助: 各 API 写操作调用, 统一记录操作人与团队."""
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog
from app.models.user import User


async def log_audit(
    db: AsyncSession,
    user: User | None,
    action: str,
    target: str,
    team_id: int | None = None,
    success: bool = True,
    detail: dict | None = None,
) -> None:
    """写一条审计记录 (随调用方事务提交).

    user 为 None 时 (如登录失败), user_id 为空、user_name 传外部提供的名字.
    """
    db.add(AuditLog(
        user_id=user.id if user else None,
        user_name=user.display_name or user.username if user else (detail or {}).get("user_name", ""),
        action=action,
        team_id=team_id,
        target=target[:255],
        success=success,
        detail=detail or {},
    ))
