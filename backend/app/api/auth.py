"""认证: 登录 / 刷新 / 登出 / 当前用户."""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import LoginRequest, RefreshRequest, TokenResponse, UserInfo
from app.core.audit import log_audit
from app.core.database import get_db
from app.core.deps import get_current_user, get_redis
from app.core.security import create_access_token, create_refresh_token, decode_token, verify_password
from app.models.team import Team, TeamMember
from app.models.user import User

router = APIRouter(prefix="/auth", tags=["auth"])
bearer = HTTPBearer(auto_error=False)


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, db: Annotated[AsyncSession, Depends(get_db)]):
    user = (await db.execute(select(User).where(User.username == body.username))).scalar_one_or_none()
    if user is None or not verify_password(body.password, user.hashed_password):
        log_audit(db, None, "登录平台", f"用户 {body.username}", success=False,
                  detail={"user_name": body.username})
        await db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "用户名或密码错误")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "用户已禁用")
    log_audit(db, user, "登录平台", "Web 控制台")
    await db.commit()
    return TokenResponse(
        access_token=create_access_token(str(user.id)),
        refresh_token=create_refresh_token(str(user.id)),
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(body: RefreshRequest, db: Annotated[AsyncSession, Depends(get_db)]):
    user_id = decode_token(body.refresh_token, "refresh")
    if user_id is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "刷新令牌无效或已过期")
    user = (await db.execute(select(User).where(User.id == int(user_id)))).scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "用户不存在或已禁用")
    return TokenResponse(
        access_token=create_access_token(str(user.id)),
        refresh_token=create_refresh_token(str(user.id)),
    )


@router.post("/logout")
async def logout(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    redis: Annotated[object, Depends(get_redis)],
):
    """将 access token 加入 Redis 黑名单, 直至其自然过期."""
    if credentials:
        ttl = 60 * 60  # 黑名单保留 1h (>= access token 生命周期即可)
        await redis.set(f"bl:{credentials.credentials}", "1", ex=ttl)
    return {"detail": "已注销"}


@router.get("/me", response_model=UserInfo)
async def me(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """当前用户: 平台角色/权限 + 展示字段 + 我在各团队的角色."""
    rows = (await db.execute(
        select(TeamMember, Team).join(Team, TeamMember.team_id == Team.id)
        .where(TeamMember.user_id == user.id))).all()
    team_roles = [{"team_id": t.id, "team_name": t.name, "role": m.role}
                  for m, t in rows]
    return UserInfo(
        id=user.id, username=user.username, email=user.email,
        display_name=user.display_name, is_active=user.is_active,
        roles=[r.name for r in user.roles],
        permissions=[p.code for r in user.roles for p in r.permissions],
        title=user.title, dept=user.dept, avatar_hue=user.avatar_hue,
        team_roles=team_roles,
    )
