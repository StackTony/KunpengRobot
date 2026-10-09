"""指标与用户偏好 API: 图表查询 (聚合/降采样) + 视图配置持久化."""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import MetricQuery, MetricSeries, PreferenceSave
from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.metric import MetricPoint, UserPreference
from app.models.user import User

router = APIRouter(tags=["metrics"])


@router.post("/metrics/query", response_model=MetricSeries)
async def query_metrics(
    body: MetricQuery,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
):
    """按主机/指标/时间范围查询; interval_seconds>0 时按时间桶降采样."""
    query = (
        select(MetricPoint.metric_time, MetricPoint.value)
        .where(
            MetricPoint.host == body.host,
            MetricPoint.metric_name == body.metric_name,
            MetricPoint.metric_time >= body.start,
            MetricPoint.metric_time <= body.end,
        )
        .order_by(MetricPoint.metric_time)
    )
    rows = (await db.execute(query)).all()
    points = [(r[0], r[1]) for r in rows]

    if body.interval_seconds > 0 and points:
        buckets: list[tuple[object, float]] = []
        current_bucket_start = None
        values: list[float] = []
        for ts, value in points:
            epoch = int(ts.timestamp())
            bucket = epoch - (epoch % body.interval_seconds)
            if bucket != current_bucket_start:
                if values:
                    buckets.append((current_bucket_start, sum(values) / len(values)))
                current_bucket_start, values = bucket, []
            values.append(value)
        if values:
            buckets.append((current_bucket_start, sum(values) / len(values)))
        points = buckets

    return MetricSeries(host=body.host, metric_name=body.metric_name, points=points)


@router.get("/metrics/hosts")
async def list_hosts(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
):
    rows = (await db.execute(select(MetricPoint.host).distinct())).scalars().all()
    return {"hosts": rows}


@router.get("/metrics/names")
async def list_metric_names(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
):
    """可用指标名列表 (供图表下拉动态选择, 不再前端硬编码)."""
    rows = (await db.execute(select(MetricPoint.metric_name).distinct())).scalars().all()
    return {"metric_names": sorted(rows)}


# ---------- 用户视图偏好 (图表配置持久化) ----------
@router.get("/preferences/{pref_key}")
async def get_preference(
    pref_key: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
):
    pref = (await db.execute(
        select(UserPreference).where(UserPreference.user_id == user.id, UserPreference.pref_key == pref_key)
    )).scalar_one_or_none()
    return {"pref_key": pref_key, "pref_value": pref.pref_value if pref else {}}


@router.put("/preferences/{pref_key}")
async def save_preference(
    pref_key: str,
    body: PreferenceSave,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
):
    pref = (await db.execute(
        select(UserPreference).where(UserPreference.user_id == user.id, UserPreference.pref_key == pref_key)
    )).scalar_one_or_none()
    if pref is None:
        pref = UserPreference(user_id=user.id, pref_key=pref_key, pref_value=body.pref_value)
        db.add(pref)
    else:
        pref.pref_value = body.pref_value
    await db.commit()
    return {"detail": "已保存"}
