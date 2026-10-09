"""指标存储: 时间分区管理 / 写入 / 聚合查询 / 过期清理.

分区策略: 按月 RANGE 分区 (metric_time). 分区表父表由 Base.metadata 建表,
子分区由 ensure_partitions() 动态创建 (近月 + 预创建下一月).
"""
import logging
from datetime import datetime, timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

_PARTITION_SQL = """
CREATE TABLE IF NOT EXISTS metric_points_{partition} PARTITION OF metric_points
FOR VALUES FROM ('{start}') TO ('{end}')
"""


def _partition_name(month_start: datetime) -> str:
    return month_start.strftime("%Y%m")


async def ensure_partitions(db: AsyncSession, months_ahead: int = 1) -> None:
    """确保当月与未来 N 个月的分区存在; 由 Worker 的 APScheduler 每日调用."""
    now = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    for offset in range(0, months_ahead + 2):
        start = now + timedelta(days=31 * offset)
        start = start.replace(day=1)
        end = (start + timedelta(days=32)).replace(day=1)
        partition = _partition_name(start)
        await db.execute(text(_PARTITION_SQL.format(partition=partition, start=start, end=end)))
    await db.commit()


async def drop_expired_partitions(db: AsyncSession, retention_days: int) -> int:
    """删除超过保留期的历史分区, 返回删除数."""
    cutoff = (datetime.utcnow() - timedelta(days=retention_days)).replace(
        day=1, hour=0, minute=0, second=0, microsecond=0)
    result = await db.execute(text(
        "SELECT inhrelid::regclass FROM pg_inherits "
        "WHERE inhparent = 'metric_points'::regclass"
    ))
    dropped = 0
    for (rel,) in result:
        name = str(rel)
        try:
            part_month = datetime.strptime(name.split("_")[-1], "%Y%m")
        except ValueError:
            continue
        if part_month < cutoff:
            await db.execute(text(f"DROP TABLE IF EXISTS {name}"))
            dropped += 1
            logger.info("删除过期指标分区: %s", name)
    if dropped:
        await db.commit()
    return dropped
