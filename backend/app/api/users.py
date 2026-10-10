"""用户列表: 邀请候选 (不含敏感字段)."""
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import UserBrief
from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=list[UserBrief])
async def list_users(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
):
    """全部在职用户 (登录即可见, 供团队邀请下拉)."""
    users = (await db.execute(
        select(User).where(User.is_active.is_(True)).order_by(User.id))).scalars().all()
    return [UserBrief(
        id=u.id, name=u.display_name or u.username, email=u.email,
        title=u.title, dept=u.dept, avatar_hue=u.avatar_hue) for u in users]
