"""解析结果聚合器: 时序分桶 / 类别占比 / 错误码频次 / IP 分组.

移植自 witty-log-analyzer/src/parser/aggregate.ts (MulanPSL-2.0),
语义 1:1 对齐 (分桶钳制、label 两种格式、topCode 平局取先遍历者).
"""
from datetime import datetime

from app.modules.analyze.parsers import ParsedEvent


def bucket_by_time(events: list[ParsedEvent], buckets: int = 24) -> list[dict]:
    """按时间均分桶, 每桶四级别计数 + 总数."""
    if not events:
        return []
    mn = events[0].timestamp
    mx = events[-1].timestamp
    span = max(mx - mn, 60_000)
    step = span / buckets

    def p2(n: int) -> str:
        return f"{n:02d}"

    out: list[dict] = []
    for i in range(buckets):
        t = int(mn + i * step)
        # 与前端同源: 本地时区显示 (bucket label 供 ECharts x 轴)
        lt = datetime.fromtimestamp(t / 1000)
        label = (f"{p2(lt.hour)}:{p2(lt.minute)}" if buckets <= 24
                 else f"{p2(lt.month)}-{p2(lt.day)} {p2(lt.hour)}时")
        out.append({"t": t, "label": label,
                    "critical": 0, "error": 0, "warning": 0, "info": 0, "total": 0})
    for e in events:
        idx = int((e.timestamp - mn) / step)
        idx = min(max(idx, 0), buckets - 1)  # 钳制
        out[idx][e.severity] += 1
        out[idx]["total"] += 1
    return out


def by_category(events: list[ParsedEvent]) -> list[dict]:
    """类别计数, 按值降序 (饼图 Top N 由调用方截取)."""
    m: dict[str, int] = {}
    for e in events:
        m[e.category] = m.get(e.category, 0) + 1
    return sorted(({"name": k, "value": v} for k, v in m.items()),
                  key=lambda x: -x["value"])


def by_error_code(events: list[ParsedEvent], top_n: int = 10) -> list[dict]:
    """错误码频次 Top N, 含级别/类别/样例 (前 160 字符)."""
    m: dict[str, dict] = {}
    for e in events:
        cur = m.get(e.error_code)
        if cur:
            cur["value"] += 1
        else:
            m[e.error_code] = {"name": e.error_code, "value": 1,
                               "severity": e.severity, "category": e.category,
                               "sample": e.raw[:160]}
    return sorted(m.values(), key=lambda x: -x["value"])[:top_n]


def by_ip(events: list[ParsedEvent]) -> list[dict]:
    """按源 IP 聚合: 四级别计数 + 高频错误码 (平局取先遍历者, 与 witty 一致)."""
    m: dict[str, dict] = {}
    for e in events:
        cur = m.get(e.source_ip)
        if cur is None:
            cur = {"ip": e.source_ip, "total": 0, "critical": 0, "error": 0,
                   "warning": 0, "info": 0, "_codes": {}}
            m[e.source_ip] = cur
        cur["total"] += 1
        cur[e.severity] += 1
        cur["_codes"][e.error_code] = cur["_codes"].get(e.error_code, 0) + 1
    out = []
    for v in m.values():
        top_code, cnt = "-", 0
        for c, n in v["_codes"].items():
            if n > cnt:  # 严格大于: 平局取先遍历者
                cnt, top_code = n, c
        out.append({"ip": v["ip"], "total": v["total"], "critical": v["critical"],
                    "error": v["error"], "warning": v["warning"], "info": v["info"],
                    "topCode": top_code, "topCodeCount": cnt})
    out.sort(key=lambda x: -x["total"])
    return out


def kpi_of(events: list[ParsedEvent]) -> dict:
    """结果页横幅 KPI: 总数/致命/错误/告警/源IP数(去重)/错误码数(去重)."""
    return {
        "total": len(events),
        "critical": sum(1 for e in events if e.severity == "critical"),
        "error": sum(1 for e in events if e.severity == "error"),
        "warning": sum(1 for e in events if e.severity == "warning"),
        "ips": len({e.source_ip for e in events}),
        "codes": len({e.error_code for e in events}),
    }
