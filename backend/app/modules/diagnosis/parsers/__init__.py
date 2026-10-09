"""日志解析器插件体系: 每种日志格式一个 Parser, 注册制接入.

新增日志格式 = 新增模块内 parser 文件并调用 register(), 不动核心代码.
"""
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Awaitable

PARSERS: dict[str, "LogParser"] = {}


@dataclass
class LogEntry:
    """结构化日志行."""
    raw: str
    timestamp: datetime | None = None
    level: str = ""          # INFO/WARN/ERROR/CRITICAL...
    component: str = ""      # 来源组件/服务
    fields: dict = field(default_factory=dict)


@dataclass
class ParseResult:
    entries: list[LogEntry] = field(default_factory=list)
    metrics: list[dict] = field(default_factory=list)  # 提取的性能指标点 [{time, host, metric_name, value, tags}]
    file_stats: dict = field(default_factory=dict)     # 文件级统计 {lines, errors, warns}


class LogParser:
    """解析器基类: 子类实现 detect() 与 parse_file()."""
    name: str = "base"

    def detect(self, path: Path, sample: list[str]) -> bool:
        """根据文件名/内容样本判断能否解析该文件."""
        return False

    async def parse_file(self, path: Path, server_type: str = "") -> ParseResult:
        raise NotImplementedError


def register(parser_cls: type[LogParser]) -> type[LogParser]:
    instance = parser_cls()
    PARSERS[instance.name] = instance
    return parser_cls


async def identify_and_parse(path: Path, server_type: str = "") -> ParseResult | None:
    """格式识别: 按注册顺序尝试 detect, 命中即解析."""
    sample: list[str] = []
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            for _ in range(50):
                line = f.readline()
                if not line:
                    break
                sample.append(line)
    except OSError:
        return None
    for parser in PARSERS.values():
        if parser.detect(path, sample):
            return await parser.parse_file(path, server_type)
    return None


@register
class GenericTextParser(LogParser):
    """兜底通用文本解析器: 提取常见时间戳/级别行."""
    name = "generic_text"
    LEVEL_MAP = {"info": "info", "warn": "warn", "warning": "warn", "error": "error",
                 "err": "error", "fatal": "critical", "critical": "critical", "debug": "debug"}
    TS_PATTERN = re.compile(
        r"(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?)|"
        r"(\w{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2})"
    )

    def detect(self, path: Path, sample: list[str]) -> bool:
        return path.suffix.lower() in (".log", ".txt", ".out", "") or bool(sample)

    async def parse_file(self, path: Path, server_type: str = "") -> ParseResult:
        result = ParseResult()
        result.file_stats = {"lines": 0, "errors": 0, "warns": 0}
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.rstrip("\n")
                result.file_stats["lines"] += 1
                lower = line.lower()
                level = ""
                for key, value in self.LEVEL_MAP.items():
                    if key in lower:
                        level = value
                        break
                if level == "error" or level == "critical":
                    result.file_stats["errors"] += 1
                elif level == "warn":
                    result.file_stats["warns"] += 1
                ts_match = self.TS_PATTERN.search(line)
                result.entries.append(LogEntry(raw=line, level=level))
                if len(result.entries) > 500000:  # 防内存失控, 超大文件截断
                    break
        return result
