"""FastAPI 依赖注入: 当前用户 / RBAC 权限校验 / Redis 客户端."""
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import decode_token
from app.models.user import User

bearer_scheme = HTTPBearer(auto_error=False)
settings = get_settings()

_redis: Redis | None = None


def init_redis(redis: Redis) -> None:
    global _redis
    _redis = redis


def get_redis() -> Redis:
    assert _redis is not None, "Redis 未初始化"
    return _redis


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "未认证")
    user_id = decode_token(credentials.credentials, "access")
    if user_id is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "令牌无效或已过期")
    # 登出黑名单 (Redis): jti 直接以 token 值哈希存储, 此处简单校验 token 是否被拉黑
    redis = get_redis()
    if await redis.get(f"bl:{credentials.credentials}"):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "令牌已注销")
    user = (await db.execute(select(User).where(User.id == int(user_id), User.is_active.is_(True)))).scalar_one_or_none()
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "用户不存在或已禁用")
    return user


def require_permission(*permission_codes: str):
    """要求当前用户拥有任一给定权限码 (通过其角色)."""

    async def checker(user: Annotated[User, Depends(get_current_user)]) -> User:
        user_perms = {p.code for role in user.roles for p in role.permissions}
        if not user_perms.intersection(permission_codes):
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"需要权限: {permission_codes}")
        return user

    return checker


# 常用权限依赖
RequireAdmin = Depends(require_permission("admin"))
RequireRuleManage = Depends(require_permission("admin", "rule:manage"))
