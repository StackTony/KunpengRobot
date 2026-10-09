"""巡检检查项插件体系: 每个检查项一个 Checker, 注册制接入."""
import re
from dataclasses import dataclass, field
from typing import Awaitable, Callable

from app.modules.diagnosis.parsers import LogEntry

CHECKERS: dict[str, "Checker"] = []


@dataclass
class CheckResult:
    name: str
    passed: bool
    severity: str = "warn"           # 未通过时的级别
    message: str = ""
    metrics: list[dict] = field(default_factory=list)  # 采集到的性能指标点


@dataclass
class InspectionContext:
    """巡检输入: 上传的巡检数据包解析结果 + 服务器信息."""
    server_type: str = ""
    entries: list[LogEntry] = field(default_factory=list)
    metrics: list[dict] = field(default_factory=list)


class Checker:
    """检查项基类: 子类实现 check()."""
    name: str = "base"
    description: str = ""

    async def check(self, ctx: InspectionContext) -> CheckResult:
        raise NotImplementedError


def register(checker_cls: type[Checker]) -> type[Checker]:
    CHECKERS.append(checker_cls())
    return checker_cls


@register
class ErrorLogChecker(Checker):
    """示例检查项: 错误日志条目检查."""
    name = "error_log"
    description = "检查日志中的 ERROR/CRITICAL 条目"

    async def check(self, ctx: InspectionContext) -> CheckResult:
        errors = [e for e in ctx.entries if e.level in ("error", "critical")]
        metrics = [{"metric_name": "log.error_count", "host": "unknown",
                    "value": len(errors)}]
        if len(errors) >= 10:
            return CheckResult(self.name, False, "error",
                               f"发现 {len(errors)} 条错误级日志", metrics)
        if errors:
            return CheckResult(self.name, False, "warn",
                               f"发现 {len(errors)} 条错误级日志", metrics)
        return CheckResult(self.name, True, "info", "无错误日志", metrics)


@register
class WarnLogChecker(Checker):
    """示例检查项: 告警日志条目检查."""
    name = "warn_log"
    description = "检查日志中的 WARN 条目"

    async def check(self, ctx: InspectionContext) -> CheckResult:
        warns = [e for e in ctx.entries if e.level == "warn"]
        metrics = [{"metric_name": "log.warn_count", "host": "unknown",
                    "value": len(warns)}]
        if len(warns) >= 50:
            return CheckResult(self.name, False, "warn",
                               f"告警日志 {len(warns)} 条, 建议关注", metrics)
        return CheckResult(self.name, True, "info", f"告警日志 {len(warns)} 条", metrics)
