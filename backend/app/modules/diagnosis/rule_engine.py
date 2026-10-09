"""规则引擎: 从数据库加载启用的规则 (版本化热加载), 对解析结果匹配打分."""
import logging
import re
import time
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.rule import MatchType, Rule, Severity
from app.modules.diagnosis.parsers import LogEntry, ParseResult

logger = logging.getLogger(__name__)

SEVERITY_WEIGHT = {Severity.info: 1, Severity.warn: 3, Severity.error: 7, Severity.critical: 10}


@dataclass
class Finding:
    rule_id: int
    rule_name: str
    severity: str
    line_no: int
    raw: str
    matched_text: str = ""


class RuleEngine:
    """规则引擎: 每任务实例化一次; 规则集从 DB 加载最新启用版本.

    热加载: 规则表 version 全局递增, Worker 每任务加载时取最新, 无需重启.
    """

    def __init__(self, rules: list[Rule]):
        self._rules = rules
        self._compiled: list[tuple[Rule, re.Pattern | None]] = []
        for rule in rules:
            pattern = None
            if rule.match_type == MatchType.regex:
                pattern = re.compile(rule.pattern)  # 保存前已校验
            self._compiled.append((rule, pattern))

    @classmethod
    async def load(cls, db: AsyncSession) -> "RuleEngine":
        rules = (await db.execute(select(Rule).where(Rule.enabled.is_(True)))).scalars().all()
        return cls(list(rules))

    def match_entries(self, entries: list[LogEntry]) -> list[Finding]:
        """对日志条目跑正则/关键字规则, 返回命中明细."""
        findings: list[Finding] = []
        for line_no, entry in enumerate(entries, 1):
            for rule, pattern in self._compiled:
                if rule.match_type == MatchType.regex:
                    m = pattern.search(entry.raw) if pattern else None
                    if m:
                        findings.append(Finding(rule.id, rule.name, rule.severity.value,
                                                line_no, entry.raw[:500], m.group(0)[:200]))
                elif rule.match_type == MatchType.keyword:
                    if rule.pattern and rule.pattern in entry.raw:
                        findings.append(Finding(rule.id, rule.name, rule.severity.value,
                                                line_no, entry.raw[:500], rule.pattern))
        return findings

    def match_metrics(self, metrics: list[dict]) -> list[Finding]:
        """对指标点跑阈值规则."""
        findings: list[Finding] = []
        for rule, _ in self._compiled:
            if rule.match_type != MatchType.threshold:
                continue
            spec = rule.threshold or {}
            metric, op, value = spec.get("metric"), spec.get("op"), spec.get("value")
            if not metric or op not in (">", "<", ">=", "<=", "==") or value is None:
                continue
            for point in metrics:
                if point.get("metric_name") != metric:
                    continue
                if eval(f"{point['value']} {op} {value}"):  # noqa: 值来自受控配置, 保存时已校验
                    findings.append(Finding(
                        rule.id, rule.name, rule.severity.value, 0,
                        f"{point.get('host', '')} {metric}={point['value']} ({op} {value})"))
        return findings

    @staticmethod
    def health_score(findings: list[Finding]) -> int:
        """健康评分: 100 - 加权扣分, 下限 0."""
        penalty = sum(SEVERITY_WEIGHT[Severity(f.severity)] for f in findings)
        return max(0, 100 - min(100, penalty))
