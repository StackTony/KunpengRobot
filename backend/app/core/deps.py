"""FastAPI 依赖注入: 当前用户 / RBAC 权限校验 / Redis 客户端."""
from typing import Annotated

from fastapi import Depends, HTTPException, Query, status
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


async def _authenticate(token_value: str, db: AsyncSession) -> User:
    """token 值 → 用户 (含有效期 / 登出黑名单 / 存活校验)."""
    user_id = decode_token(token_value, "access")
    if user_id is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "令牌无效或已过期")
    # 登出黑名单 (Redis): jti 直接以 token 值哈希存储, 此处简单校验 token 是否被拉黑
    redis = get_redis()
    if await redis.get(f"bl:{token_value}"):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "令牌已注销")
    user = (await db.execute(select(User).where(User.id == int(user_id), User.is_active.is_(True)))).scalar_one_or_none()
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "用户不存在或已禁用")
    return user


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "未认证")
    return await _authenticate(credentials.credentials, db)


async def get_current_user_or_query(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
    token: Annotated[str | None, Query(description="查询参数认证: 浏览器 EventSource 无法携带 Header")] = None,
) -> User:
    """Header 优先, 缺失时回退 ?token= 查询参数 (SSE EventSource 场景)."""
    if credentials is not None:
        return await _authenticate(credentials.credentials, db)
    if token:
        return await _authenticate(token, db)
    raise HTTPException(status.HTTP_401_UNAUTHORIZED, "未认证")


def require_permission(*permission_codes: str):
    """要求当前用户拥有任一给定权限码 (通过其角色)."""

    async def checker(user: Annotated[User, Depends(get_current_user)]) -> User:
        user_perms = {p.code for role in user.roles for p in role.permissions}
        if not user_perms.intersection(permission_codes):
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"需要权限: {permission_codes}")
        return user

    return checker


def is_platform_admin(user: User) -> bool:
    return "admin" in {r.name for r in user.roles}


async def load_team_role(db: AsyncSession, user: User, team_id: int):
    """返回 (team, my_role); 平台管理员对任意团队返回 role='owner' 语义的 admin."""
    from app.models.team import Team, TeamMember

    team = (await db.execute(select(Team).where(Team.id == team_id))).scalar_one_or_none()
    if team is None:
        return None, None
    if is_platform_admin(user):
        return team, "owner"
    member = (await db.execute(
        select(TeamMember).where(TeamMember.team_id == team_id, TeamMember.user_id == user.id)
    )).scalar_one_or_none()
    return team, (member.role if member else None)


async def ensure_team_perm(db: AsyncSession, user: User, team_id: int, perm: str):
    """校验用户在团队内角色具备 perm; 返回 (team, role), 不满足抛 403/404."""
    from app.core.team_rbac import team_role_has_perm

    team, role = await load_team_role(db, user, team_id)
    if team is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "团队不存在")
    if role is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "非团队成员, 无权操作")
    if not team_role_has_perm(role, perm):
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"需要团队权限: {perm}")
    return team, role


def require_team_perm(perm: str):
    """工厂依赖: 路由路径含 {team_id} 时使用, 返回 (user, team, role).

    用法: trio: Annotated[tuple[User, Team, str], Depends(require_team_perm("asset:create"))]
    非路径场景 (如经 asset_id 反查团队) 请改用 ensure_team_perm().
    """

    async def checker(
        team_id: int,
        user: Annotated[User, Depends(get_current_user)],
        db: Annotated[AsyncSession, Depends(get_db)],
    ):
        return await ensure_team_perm(db, user, team_id, perm)

    return checker


# 常用权限依赖
RequireAdmin = Depends(require_permission("admin"))
RequireRuleManage = Depends(require_permission("admin", "rule:manage"))
