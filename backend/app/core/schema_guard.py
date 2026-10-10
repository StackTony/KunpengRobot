"""Schema 守卫: 幂等补充 create_all 无法处理的存量表变更.

create_all 只建新表, 不给已有表加列/不改枚举类型.
此处在 create_all 之前执行幂等原生 SQL (可重复运行):
- ALTER TYPE ... ADD VALUE IF NOT EXISTS (PG >= 12)
- ALTER TABLE ... ADD COLUMN IF NOT EXISTS

注意: ALTER TYPE 新增值与"使用该值"必须分属不同事务,
守卫单独提交, 种子数据在后续事务使用, 安全.

这是开发模式的过渡补丁, 生产环境请使用 Alembic 迁移 (见 docs/功能点清单.md).
"""
import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

logger = logging.getLogger(__name__)

# (SQL, 说明)
_GUARDS: list[tuple[str, str]] = [
    # tasks 表: analyze 任务扩展列 (witty 解析任务)
    ("ALTER TYPE tasktype ADD VALUE IF NOT EXISTS 'analyze'", "tasktype 枚举加 analyze"),
    ("ALTER TABLE tasks ADD COLUMN IF NOT EXISTS name VARCHAR(128) DEFAULT ''", "tasks.name"),
    ("ALTER TABLE tasks ADD COLUMN IF NOT EXISTS parser_type VARCHAR(32) DEFAULT ''", "tasks.parser_type"),
    ("ALTER TABLE tasks ADD COLUMN IF NOT EXISTS asset_id INTEGER REFERENCES asset_libraries(id)", "tasks.asset_id"),
    ("ALTER TABLE tasks ADD COLUMN IF NOT EXISTS log_size BIGINT DEFAULT 0", "tasks.log_size"),
    ("ALTER TABLE tasks ADD COLUMN IF NOT EXISTS event_count INTEGER DEFAULT 0", "tasks.event_count"),
    # users 表: 前端展示字段 (witty User 模型)
    ("ALTER TABLE users ADD COLUMN IF NOT EXISTS title VARCHAR(64) DEFAULT ''", "users.title"),
    ("ALTER TABLE users ADD COLUMN IF NOT EXISTS dept VARCHAR(64) DEFAULT ''", "users.dept"),
    ("ALTER TABLE users ADD COLUMN IF NOT EXISTS avatar_hue INTEGER DEFAULT 212", "users.avatar_hue"),
]


async def run_schema_guard(engine: AsyncEngine) -> None:
    """幂等执行存量表结构补丁, 单独事务提交."""
    applied = 0
    for sql, desc in _GUARDS:
        try:
            async with engine.begin() as conn:
                await conn.execute(text(sql))
            applied += 1
        except Exception as e:  # noqa: BLE001
            # 新库首次启动时 tasktype 枚举可能尚不存在 (由 create_all 创建), 跳过即可
            logger.debug("schema 守卫跳过 %s: %s", desc, e)
    if applied:
        logger.info("schema 守卫: 已检查 %d 项", len(_GUARDS))
