"""API 服务入口: uvicorn app.main:app"""
import logging
from contextlib import asynccontextmanager
from datetime import datetime

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
from app.models.task import Task, Report, TaskStatus, TaskType  # noqa
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
        await seed_demo_tasks()


async def seed_demo_tasks() -> None:
    """演示解析任务 (幂等): 生成样例日志 → 解析 → 事件入库 → 五段报告.

    给工作台 KPI/团队任务列表/结果页演示提供真实数据 (不经过队列, 直接成品).
    """
    from datetime import timedelta

    from app.models.analyze import ParsedEventRecord
    from app.modules.analyze import ANALYZE_PARSERS
    from app.modules.analyze.demo_logs import DEMO_LOG_GENS
    from app.modules.analyze.report_builder import build_llm_report

    # (团队名, 任务名, parser, 创建用户, count, seed, ipPool)
    DEMO_TASKS = [
        ("北京A", "A 区例行 SEL 巡检", "sel", "guchuang", 360, 7,
         ["10.1.3.11", "10.1.3.12", "10.1.3.21", "10.1.3.22", "10.1.4.31", "10.1.4.32"]),
        ("北京A", "PSU2 故障专项分析", "redfish", "jiangguanli", 180, 21,
         ["10.1.3.11", "10.1.3.12", "10.1.3.21", "10.1.3.22", "10.1.4.31", "10.1.4.32"]),
        ("上海B", "B 区磁盘 IO 错误分析", "syslog", "jiangguanli", 280, 13,
         ["10.2.8.101", "10.2.8.102", "10.2.8.103", "10.2.9.10"]),
        ("上海B", "内核超时日志排查", "dmesg", "zhangshenpi", 240, 29,
         ["10.2.8.101", "10.2.8.102", "10.2.8.103", "10.2.9.10"]),
    ]

    async with AsyncSessionLocal() as db:
        for team_name, task_name, parser_type, username, count, seed, ips in DEMO_TASKS:
            if (await db.execute(select(Task).where(Task.name == task_name))).scalar_one_or_none():
                continue  # 幂等
            team = (await db.execute(select(Team).where(Team.name == team_name))).scalar_one_or_none()
            asset = (await db.execute(select(AssetLibrary).where(
                AssetLibrary.team_id == team.id))).scalars().first() if team else None
            creator = (await db.execute(select(User).where(User.username == username))).scalar_one_or_none()
            if asset is None or creator is None:
                continue

            text = DEMO_LOG_GENS[parser_type]({"count": count, "seed": seed, "ipPool": ips})
            parser = ANALYZE_PARSERS[parser_type]
            events = parser.parse(text)
            now_dt = datetime.now()

            task = Task(
                type=TaskType.analyze, status=TaskStatus.done,
                user_id=creator.id,
                filename=parser.def_.file_hint.replace("*", str(seed)),
                storage_path="", params={},
                name=task_name, parser_type=parser_type, asset_id=asset.id,
                log_size=len(text.encode("utf-8")), event_count=len(events),
                progress=100,
                created_at=now_dt - timedelta(hours=2 + seed % 40),
                finished_at=now_dt - timedelta(hours=1 + seed % 20),
            )
            db.add(task)
            await db.flush()
            db.add_all([ParsedEventRecord(
                task_id=task.id, ts=e.timestamp, source_ip=e.source_ip,
                severity=e.severity, category=e.category, error_code=e.error_code,
                raw=e.raw, fields=e.fields or {}) for e in events])
            sections = build_llm_report(events, parser.def_.name)
            db.add(Report(
                task_id=task.id,
                summary="\n\n".join(f"【{s['title']}】\n" + "\n".join(s["lines"]) for s in sections),
                content={"parser": parser_type, "parser_name": parser.def_.name,
                         "sections": sections, "event_count": len(events), "llm": False},
            ))
            db.add(AuditLog(
                user_id=creator.id,
                user_name=creator.display_name or creator.username,
                action="执行解析任务", team_id=team.id,
                target=f"{asset.name} / {task_name}（{len(events)} 条事件）",
            ))
        await db.commit()


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
