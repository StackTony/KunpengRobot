"""规则管理: 管理员增删改查 + 正则安全校验 + 变更审计 + 版本热加载."""
import re
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import RuleCreate, RuleInfo, RuleUpdate
from app.core.database import get_db
from app.core.deps import get_current_user, get_redis
from app.models.rule import MatchType, Rule, RuleAuditLog
from app.models.user import User

router = APIRouter(prefix="/rules", tags=["rules"])

# 防灾难性回溯: 禁止嵌套量子等危险模式 (保守黑名单 + 编译超时不可用时的兜底)
DANGEROUS_REGEX = re.compile(r"(\((?:[^()]*\+|\+[^()]*)\))|(\{.*,\s*,.*\})|(?:\(\?.*\))")


def validate_rule(body: RuleCreate) -> None:
    if body.match_type == MatchType.regex:
        if not body.pattern:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "正则规则必须有 pattern")
        if DANGEROUS_REGEX.search(body.pattern):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "正则存在灾难性回溯风险, 请改写")
        try:
            re.compile(body.pattern)
        except re.error as e:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"正则语法错误: {e}")
    elif body.match_type == MatchType.keyword and not body.pattern:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "关键字规则必须有 pattern")
    elif body.match_type == MatchType.threshold:
        if not {"metric", "op", "value"} <= set(body.threshold.keys()):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "阈值规则需包含 metric/op/value")


@router.get("", response_model=list[RuleInfo])
async def list_rules(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    enabled_only: bool = False,
):
    query = select(Rule).order_by(Rule.priority, Rule.id)
    if enabled_only:
        query = query.where(Rule.enabled.is_(True))
    return (await db.execute(query)).scalars().all()


@router.post("", response_model=RuleInfo, status_code=201)
async def create_rule(
    body: RuleCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
):
    if "rule:manage" not in {p.code for r in user.roles for p in r.permissions}:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "需要规则管理权限")
    validate_rule(body)
    max_version = (await db.execute(select(func.max(Rule.version)))).scalar() or 0
    rule = Rule(**body.model_dump(), version=max_version + 1, created_by=user.id)
    db.add(rule)
    db.add(RuleAuditLog(rule_id=rule.id, rule_name=rule.name, action="create",
                        operator_id=user.id, detail=body.model_dump()))
    await db.commit()
    await db.refresh(rule)
    return rule


@router.put("/{rule_id}", response_model=RuleInfo)
async def update_rule(
    rule_id: int,
    body: RuleUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
):
    if "rule:manage" not in {p.code for r in user.roles for p in r.permissions}:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "需要规则管理权限")
    validate_rule(body)
    rule = (await db.execute(select(Rule).where(Rule.id == rule_id))).scalar_one_or_none()
    if rule is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "规则不存在")
    # 版本化: 更新即产生新版本号, Worker 感知到版本变化后热加载
    max_version = (await db.execute(select(func.max(Rule.version)))).scalar() or 0
    old = {c.name: getattr(rule, c.name) for c in rule.__table__.columns}
    for key, value in body.model_dump().items():
        setattr(rule, key, value)
    rule.version = max_version + 1
    db.add(RuleAuditLog(rule_id=rule.id, rule_name=rule.name, action="update",
                        operator_id=user.id, detail={"old": old, "new": body.model_dump()}))
    await db.commit()
    await db.refresh(rule)
    return rule


@router.delete("/{rule_id}")
async def delete_rule(
    rule_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
):
    if "rule:manage" not in {p.code for r in user.roles for p in r.permissions}:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "需要规则管理权限")
    rule = (await db.execute(select(Rule).where(Rule.id == rule_id))).scalar_one_or_none()
    if rule is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "规则不存在")
    if rule.is_builtin:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "内置规则不可删除, 可停用")
    db.add(RuleAuditLog(rule_id=rule.id, rule_name=rule.name, action="delete",
                        operator_id=user.id, detail={}))
    await db.delete(rule)
    await db.commit()
    return {"detail": "已删除"}
