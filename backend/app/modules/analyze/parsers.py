"""六种服务器日志解析器 + 注册表.

移植自 witty-log-analyzer/src/parser/parsers.ts (MulanPSL-2.0),
统一事件模型 ParsedEvent{timestamp(ms), source_ip, severity, category, error_code, raw, fields},
解析结果按 timestamp 升序排序 (与 witty 一致).
"""
import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime

# ---------------- 统一事件模型 ----------------

SEVERITIES = ("critical", "error", "warning", "info")


@dataclass
class ParsedEvent:
    timestamp: int                      # ms epoch
    source_ip: str = ""
    severity: str = "info"              # critical/error/warning/info
    category: str = ""                  # 中文类别 (风扇/温度/电源/磁盘/内存/处理器/电压/BMC/内核...)
    error_code: str = ""
    raw: str = ""
    fields: dict = field(default_factory=dict)


@dataclass
class ParserDef:
    type: str
    name: str
    desc: str
    file_hint: str


@dataclass
class AnalyzeParser:
    def_: ParserDef

    def parse(self, text: str) -> list[ParsedEvent]:
        raise NotImplementedError


def _ts(s: str) -> int:
    """时间字符串 -> ms epoch; 解析失败兜底 now-3600s (与 witty ts() 一致).

    naive 时间按本地时间解析 (与 JS Date.parse 行为一致).
    """
    try:
        t = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return int(t.timestamp() * 1000)
    except ValueError:
        return int(time.time() * 1000) - 3600_000


# ---------------- 1. SEL (ipmitool sel elist) ----------------

_SEL_RE = re.compile(
    r"^\s*(\d+)\s*\|\s*([^|]+?)\s*\|\s*([\d.]+)\s*\|\s*(\S+)\s*\|\s*(\S+)\s*\|\s*"
    r"([^|]+?)\s*\|\s*([A-Z]-0x[0-9A-Fa-f]+)\s*\|\s*(.+)$"
)


@dataclass
class SelParser(AnalyzeParser):
    def __init__(self):
        super().__init__(ParserDef(
            type="sel", name="BMC / SEL 日志",
            desc="ipmitool sel elist 导出的系统事件日志文本",
            file_hint="sel_elist_*.txt",
        ))

    def parse(self, text: str) -> list[ParsedEvent]:
        out: list[ParsedEvent] = []
        for line in text.split("\n"):
            m = _SEL_RE.match(line)
            if not m:
                continue
            rid, time_str, ip, _rec_type, evt_type, sensor, code, desc = m.groups()
            s = sensor.lower()
            if "fan" in s:
                cat = "风扇"
            elif "temp" in s:
                cat = "温度"
            elif "power" in s or "psu" in s:
                cat = "电源"
            elif "drive" in s:
                cat = "磁盘"
            elif "memory" in s:
                cat = "内存"
            elif "cpu" in s:
                cat = "处理器"
            elif "vrm" in s:
                cat = "电压"
            else:
                cat = "BMC"
            dl = desc.lower()
            if "critical" in evt_type.lower() or re.search(r"uncorrectable|ierr|failure", dl):
                sev = "critical"
            elif "error" in dl:
                sev = "error"
            elif re.search(r"warning|non-critical|predictive", dl):
                sev = "warning"
            else:
                sev = "info"
            # 时间格式 MM/DD/YYYY HH:MM:SS (witty 用 replace(-,/) 后 Date.parse)
            try:
                t = datetime.strptime(time_str.strip().replace("-", "/"), "%m/%d/%Y %H:%M:%S")
                ts_ms = int(t.timestamp() * 1000)
            except ValueError:
                ts_ms = _ts(time_str)
            out.append(ParsedEvent(
                timestamp=ts_ms, source_ip=ip, severity=sev, category=cat,
                error_code=code, raw=line,
                fields={"RecordId": rid, "Sensor": sensor.strip(),
                        "EventType": evt_type, "Description": desc.strip()},
            ))
        out.sort(key=lambda e: e.timestamp)
        return out


# ---------------- 2. Redfish JSON ----------------

_REDFISH_SEV = {"Critical": "critical", "Error": "error", "Warning": "warning", "OK": "info"}


@dataclass
class RedfishParser(AnalyzeParser):
    def __init__(self):
        super().__init__(ParserDef(
            type="redfish", name="Redfish JSON",
            desc="DMTF Redfish LogService 导出的结构化日志",
            file_hint="redfish_logservice_*.json",
        ))

    def parse(self, text: str) -> list[ParsedEvent]:
        try:
            doc = json.loads(text)
        except (json.JSONDecodeError, ValueError):
            return []
        members = doc if isinstance(doc, list) else (doc.get("Members") or [])
        out: list[ParsedEvent] = []
        for m in members:
            out.append(ParsedEvent(
                timestamp=_ts(m.get("Created") or ""),
                source_ip=m.get("OriginIp") or "0.0.0.0",
                severity=_REDFISH_SEV.get(m.get("Severity"), "info"),
                category=m.get("Category") or "System",
                error_code=m.get("OEMCode") or m.get("Id") or "RF-0",
                raw=m.get("Message") or "",
                fields={"Id": m.get("Id") or "", "Message": m.get("Message") or ""},
            ))
        out.sort(key=lambda e: e.timestamp)
        return out


# ---------------- 3. Syslog RFC3164 ----------------

_SYSLOG_RE = re.compile(
    r"^<(\d+)>(\w+\s+\d+\s[\d:]{8})\s+(\S+)\s+([\w./-]+)(?:\[\d+\])?:\s+(.*)$"
)
# PRI % 8 -> severity (与 witty SEV_NAMES 一致)
_SYSLOG_SEV = ("critical", "critical", "critical", "error", "warning", "info", "info", "info")
_CODE_RE = re.compile(r"\[([A-Z]+-\d+)\]")


@dataclass
class SyslogParser(AnalyzeParser):
    def __init__(self):
        super().__init__(ParserDef(
            type="syslog", name="Syslog (RFC3164)",
            desc="标准 syslog 转发/导出文本",
            file_hint="messages / syslog-*.log",
        ))

    def parse(self, text: str) -> list[ParsedEvent]:
        out: list[ParsedEvent] = []
        this_year = datetime.now().year
        for line in text.split("\n"):
            m = _SYSLOG_RE.match(line)
            if not m:
                continue
            pri, time_str, host, tag, msg = m.groups()
            sev = _SYSLOG_SEV[int(pri) % 8]
            cm = _CODE_RE.search(msg)
            try:
                # RFC3164 无年份, 补当前年 (与 witty 一致)
                t = datetime.strptime(f"{this_year} {time_str}", "%Y %b %d %H:%M:%S")
                ts_ms = int(t.timestamp() * 1000)
            except ValueError:
                ts_ms = _ts(f"{this_year} {time_str}")
            out.append(ParsedEvent(
                timestamp=ts_ms,
                source_ip=host if re.fullmatch(r"[\d.]+", host) else "0.0.0.0",
                severity=sev,
                category=tag.split("/")[0],
                error_code=cm.group(1) if cm else "SYS-0",
                raw=line,
                fields={"PRI": pri, "Host": host, "Tag": tag, "Message": msg},
            ))
        out.sort(key=lambda e: e.timestamp)
        return out


# ---------------- 4. dmesg ----------------

_DMESG_RE = re.compile(r"^\[([\d.]+)\]\s+\[([^\]]+)\]\s+\[([\d.]+)\]\s+(\w+)\s+:\s+(.+)$")


@dataclass
class DmesgParser(AnalyzeParser):
    def __init__(self):
        super().__init__(ParserDef(
            type="dmesg", name="内核日志 dmesg",
            desc="dmesg -T 输出，含主机 IP 标注",
            file_hint="dmesg_*.log",
        ))

    def parse(self, text: str) -> list[ParsedEvent]:
        out: list[ParsedEvent] = []
        for line in text.split("\n"):
            m = _DMESG_RE.match(line)
            if not m:
                continue
            mono, iso, ip, lvl, msg = m.groups()
            cm = _CODE_RE.search(msg)
            ml = msg.lower()
            if re.search(r"mce|machine check", ml):
                cat = "内存"
            elif re.search(r"nvme|sdb|sda|i/o", ml):
                cat = "磁盘"
            elif re.search(r"igc|eth|enp", ml):
                cat = "网络"
            elif "thermal" in ml:
                cat = "温度"
            else:
                cat = "内核"
            out.append(ParsedEvent(
                timestamp=_ts(iso), source_ip=ip,
                severity="error" if lvl == "err" else "info",
                category=cat,
                error_code=cm.group(1) if cm else "KRN-0",
                raw=line,
                fields={"Monotonic": mono, "Level": lvl, "Message": msg},
            ))
        out.sort(key=lambda e: e.timestamp)
        return out


# ---------------- 5. Windows 事件日志 (JSON lines) ----------------


@dataclass
class WindowsParser(AnalyzeParser):
    def __init__(self):
        super().__init__(ParserDef(
            type="windows", name="Windows 事件日志",
            desc="Get-WinEvent 导出的 JSON lines（EVTX 转 JSON）",
            file_hint="events_*.jsonl",
        ))

    def parse(self, text: str) -> list[ParsedEvent]:
        out: list[ParsedEvent] = []
        for line in text.split("\n"):
            t = line.strip()
            if not t:
                continue
            try:
                e = json.loads(t)
            except (json.JSONDecodeError, ValueError):
                continue
            level = e.get("Level")
            sev = {"Critical": "critical", "Error": "error",
                   "Warning": "warning"}.get(level, "info")
            out.append(ParsedEvent(
                timestamp=_ts(e.get("TimeCreated") or ""),
                source_ip=e.get("SourceIp") or "0.0.0.0",
                severity=sev,
                category=e.get("Category") or e.get("ProviderName") or "Windows",
                error_code=str(e.get("EventId") or "EVT-0"),
                raw=e.get("Message") or "",
                fields={"Provider": e.get("ProviderName") or "",
                        "EventId": str(e.get("EventId") or ""),
                        "Message": e.get("Message") or ""},
            ))
        out.sort(key=lambda e: e.timestamp)
        return out


# ---------------- 6. 通用正则（应用日志示例） ----------------

_APP_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2} [\d:]{8})\s+\[(ERROR|WARN|INFO|DEBUG)\]\s+\[(\S+)\]\s+"
    r"code=(\S+)\s+from=(\S+)\s+.*$"
)


@dataclass
class RegexParser(AnalyzeParser):
    def __init__(self):
        super().__init__(ParserDef(
            type="regex", name="通用正则解析",
            desc="自定义正则 + 字段映射（示例：应用日志）",
            file_hint="app_*.log",
        ))

    def parse(self, text: str) -> list[ParsedEvent]:
        out: list[ParsedEvent] = []
        for line in text.split("\n"):
            m = _APP_RE.match(line)
            if not m:
                continue
            time_str, level, svc, code, ip = m.groups()
            try:
                t = datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
                ts_ms = int(t.timestamp() * 1000)
            except ValueError:
                ts_ms = _ts(time_str.replace(" ", "T"))
            out.append(ParsedEvent(
                timestamp=ts_ms, source_ip=ip,
                severity={"ERROR": "error", "WARN": "warning"}.get(level, "info"),
                category=svc, error_code=code, raw=line,
                fields={"Service": svc, "Level": level},
            ))
        out.sort(key=lambda e: e.timestamp)
        return out


# ---------------- 注册表 ----------------

ANALYZE_PARSERS: dict[str, AnalyzeParser] = {
    p.def_.type: p for p in (
        SelParser(), RedfishParser(), SyslogParser(),
        DmesgParser(), WindowsParser(), RegexParser(),
    )
}


def parser_list() -> list[ParserDef]:
    """供前端解析类型卡片渲染."""
    return [p.def_ for p in ANALYZE_PARSERS.values()]
