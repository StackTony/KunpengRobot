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
from app.core.schema_guard import run_schema_guard
from app.core.security import hash_password
from app.core.team_rbac import PERMISSIONS_17
from app.models import Permission, Role, User  # noqa: 确保建表
from app.models.asset import AssetLibrary  # noqa
from app.models.audit import AuditLog  # noqa
from app.models.rule import Rule  # noqa
from app.models.task import Task, Report  # noqa
from app.models.team import Team, TeamMember, TeamNotice  # noqa
from app.models.metric import MetricPoint, UserPreference  # noqa
from app.models.analyze import ParsedEventRecord  # noqa

logging.basicConfig(level=logging.DEBUG if get_settings().DEBUG else logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")

settings = get_settings()

# 演示账号 (密码统一 demo123, 仅演示用; 生产环境 SEED_DEMO_DATA=False 关闭)
DEMO_USERS = [
    # (username, display_name, email, title, dept, avatar_hue)
    ("guchuang", "顾创建", "guchuang@kunpeng.local", "运维主管", "基础设施部", 212),
    ("jiangguanli", "蒋管理", "jiangguanli@kunpeng.local", "高级运维", "基础设施部", 268),
    ("sunputong", "孙普通", "sunputong@kunpeng.local", "运维工程师", "监控组", 20),
    ("zhangshenpi", "张审批", "zhangshenpi@kunpeng.local", "系统管理员", "系统部", 155),
    ("liyiban", "李一般", "liyiban@kunpeng.local", "运维工程师", "系统部", 330),
]


async def seed_initial_data() -> None:
    """初始化 (幂等): 权限/角色 + 默认管理员 admin/admin123 + 演示数据."""
    async with AsyncSessionLocal() as db:
        # ---- 权限: 旧 5 个 + 新 17 个原子权限点 ----
        perms = {
            "admin": "管理员", "task:upload": "上传日志", "task:view": "查看任务",
            "rule:manage": "规则管理", "report:view": "查看报告",
        }
        for code, group, label in PERMISSIONS_17:
            perms.setdefault(code, label)
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
        user_role.permissions = [perm_objs[k] for k in
                                 ("task:upload", "task:view", "report:view",
                                  "dashboard:view", "team:view", "team:create")]

        admin = (await db.execute(select(User).where(User.username == "admin"))).scalar_one_or_none()
        if admin is None:
            admin = User(username="admin", email="admin@kunpeng.local",
                         hashed_password=hash_password("admin123"),
                         display_name="管理员", roles=[admin_role])
            db.add(admin)
        await db.commit()

    if settings.SEED_DEMO_DATA:
        await seed_teams()
        # 演示解析任务在 seed_demo_tasks() 中创建 (依赖解析器模块, 见 app/modules/analyze)


async def seed_teams() -> None:
    """演示团队/资产库/成员/通知 (幂等)."""
    async with AsyncSessionLocal() as db:
        admin_role = (await db.execute(select(Role).where(Role.name == "admin"))).scalar_one()

        # ---- 演示用户 ----
        demo_user_objs = {}
        for username, name, email, title, dept, hue in DEMO_USERS:
            u = (await db.execute(select(User).where(User.username == username))).scalar_one_or_none()
            if u is None:
                u = User(username=username, email=email,
                         hashed_password=hash_password("demo123"),
                         display_name=name, title=title, dept=dept,
                         avatar_hue=hue, roles=[admin_role] if username == "guchuang" else [])
                db.add(u)
            demo_user_objs[username] = u
        await db.flush()

        # ---- 团队: 北京A (顾创建 owner + 蒋管理 team_admin + 孙普通 member) ----
        if (await db.execute(select(Team).where(Team.name == "北京A"))).scalar_one_or_none() is None:
            team = Team(name="北京A", desc="北京机房 A 区服务器运维团队",
                        owner_user_id=demo_user_objs["guchuang"].id)
            db.add(team)
            await db.flush()
            db.add_all([
                TeamMember(team_id=team.id, user_id=demo_user_objs["guchuang"].id, role="owner"),
                TeamMember(team_id=team.id, user_id=demo_user_objs["jiangguanli"].id, role="team_admin"),
                TeamMember(team_id=team.id, user_id=demo_user_objs["sunputong"].id, role="member"),
            ])
            db.add(AssetLibrary(team_id=team.id, name="北京A",
                                desc="北京机房 A 区通用服务器资产", ip_range="10.1.3.0/24"))
            # 待处理邀请: 蒋管理邀请孙普通 (孙普通登录后通知中心可见)
            db.add(TeamNotice(type="invite", team_id=team.id,
                              from_user_id=demo_user_objs["jiangguanli"].id,
                              to_user_id=demo_user_objs["sunputong"].id, role="member"))

        # ---- 团队: 上海B (蒋管理 owner + 张审批 team_admin) ----
        if (await db.execute(select(Team).where(Team.name == "上海B"))).scalar_one_or_none() is None:
            team = Team(name="上海B", desc="上海机房 B 区服务器运维团队",
                        owner_user_id=demo_user_objs["jiangguanli"].id)
            db.add(team)
            await db.flush()
            db.add_all([
                TeamMember(team_id=team.id, user_id=demo_user_objs["jiangguanli"].id, role="owner"),
                TeamMember(team_id=team.id, user_id=demo_user_objs["zhangshenpi"].id, role="team_admin"),
            ])
            db.add(AssetLibrary(team_id=team.id, name="上海B",
                                desc="上海机房 B 区通用服务器资产", ip_range="10.2.8.0/24"))
            # 待审批申请: 李一般申请加入 (张审批登录后通知中心可见)
            db.add(TeamNotice(type="apply", team_id=team.id,
                              from_user_id=demo_user_objs["liyiban"].id,
                              to_user_id=demo_user_objs["zhangshenpi"].id, role="member"))

        await db.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Redis
    redis = Redis.from_url(settings.REDIS_URL, decode_responses=True)
    init_redis(redis)
    # 存量表结构守卫 (幂等, 先于 create_all; 单独事务提交)
    await run_schema_guard(engine)
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
