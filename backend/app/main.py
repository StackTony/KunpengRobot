"""API 服务入口: uvicorn app.main:app"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from redis.asyncio import Redis
from sqlalchemy import select

from app.api import api_router
from app.core.config import get_settings
from app.core.database import AsyncSessionLocal, Base, engine
from app.core.deps import init_redis
from app.core.security import hash_password
from app.models import Permission, Role, User  # noqa: 确保建表
from app.models.rule import Rule  # noqa
from app.models.task import Task, Report  # noqa
from app.models.metric import MetricPoint, UserPreference  # noqa

logging.basicConfig(level=logging.DEBUG if get_settings().DEBUG else logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")

settings = get_settings()


async def seed_initial_data() -> None:
    """初始化: 内置角色/权限 + 默认管理员 admin/admin123 (首次启动)."""
    async with AsyncSessionLocal() as db:
        perms = {
            "admin": "管理员", "task:upload": "上传日志", "task:view": "查看任务",
            "rule:manage": "规则管理", "report:view": "查看报告",
        }
        perm_objs = {}
        for code, desc in perms.items():
            obj = (await db.execute(select(Permission).where(Permission.code == code))).scalar_one_or_none()
            if obj is None:
                obj = Permission(code=code, description=desc)
                db.add(obj)
            perm_objs[code] = obj

        admin_role = (await db.execute(select(Role).where(Role.name == "admin"))).scalar_one_or_none()
        if admin_role is None:
            admin_role = Role(name="admin", description="管理员")
            db.add(admin_role)
        admin_role.permissions = list(perm_objs.values())

        user_role = (await db.execute(select(Role).where(Role.name == "user"))).scalar_one_or_none()
        if user_role is None:
            user_role = Role(name="user", description="普通用户")
            db.add(user_role)
        user_role.permissions = [perm_objs[k] for k in ("task:upload", "task:view", "report:view")]

        admin = (await db.execute(select(User).where(User.username == "admin"))).scalar_one_or_none()
        if admin is None:
            admin = User(username="admin", email="admin@kunpeng.local",
                         hashed_password=hash_password("admin123"),
                         display_name="管理员", roles=[admin_role])
            db.add(admin)
        await db.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Redis
    redis = Redis.from_url(settings.REDIS_URL, decode_responses=True)
    init_redis(redis)
    # 建表 (开发模式; 生产用 alembic 迁移)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await seed_initial_data()
    yield
    await redis.aclose()


app = FastAPI(title=settings.APP_NAME, version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境收紧为前端域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.API_PREFIX)


@app.get("/health")
async def health():
    return {"status": "ok", "app": settings.APP_NAME}
