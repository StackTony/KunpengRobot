"""LLM 诊断报告构建器: 五段式结构 (规则引擎生成, 供 LLM 未配置时降级与报告兜底).

移植自 witty-log-analyzer/src/parser/aggregate.ts 的 buildLlmReport (MulanPSL-2.0).
"""
from app.modules.analyze.aggregate import (by_error_code, by_ip, bucket_by_time, kpi_of)
from app.modules.analyze.parsers import ParsedEvent


def build_llm_report(events: list[ParsedEvent], parser_name: str) -> list[dict]:
    """基于聚合结果的五段诊断报告: [{title, lines: [...]}, ...]."""
    kpi = kpi_of(events)
    codes = by_error_code(events, 5)
    ips = by_ip(events)[:3]
    buckets = bucket_by_time(events, 12)
    peak = max(buckets, key=lambda b: b["total"], default={"label": "-", "total": 0})
    top = codes[0] if codes else None
    sev_label = {"critical": "致命", "error": "错误", "warning": "告警", "info": "信息"}

    health = ("较差" if kpi["critical"] + kpi["error"] > kpi["total"] * 0.3
              else "一般" if kpi["critical"] > 0 else "良好")
    ip_dist = ("高度不均，优先排查首台主机"
               if ips and (len(ips) < 2 or ips[0]["total"] > ips[1]["total"] * 2)
               else "相对均匀，倾向于共性原因（机房环境/供电/固件版本）")
    ip_summary = "、".join("{}({} 条)".format(i["ip"], i["total"]) for i in ips) or "无"

    return [
        {
            "title": "一、总体概况",
            "lines": [
                f"本次使用「{parser_name}」解析器共处理日志事件 {kpi['total']} 条，"
                f"涉及 {kpi['ips']} 个源 IP、{kpi['codes']} 种错误码。",
                f"其中致命 {kpi['critical']} 条、错误 {kpi['error']} 条、告警 {kpi['warning']} 条，"
                f"整体健康度为{health}。",
                f"事件时间分布存在明显峰值：{peak['label']} 前后（{peak['total']} 条），"
                f"提示该时段可能发生过一次集中故障或批量变更。",
            ],
        },
        {
            "title": "二、异常聚类",
            "lines": [
                f"{i + 1}. 错误码 {c['name']}（{c['category']} / {sev_label.get(c['severity'], c['severity'])}）"
                f"出现 {c['value']} 次，占比 {c['value'] / kpi['total'] * 100:.1f}%；"
                f"样例：{c['sample'][:100]}"
                for i, c in enumerate(codes)
            ] or ["未发现异常错误码。"],
        },
        {
            "title": "三、根因推断",
            "lines": [
                (f"高频错误码 {top['name']} 集中于「{top['category']}」类别，结合 BMC 场景经验，"
                 f"最可能的根因是{root_cause_hint(top['category'])}。"
                 if top else "未发现高频错误码，建议扩大采样时间范围。"),
                f"活跃源 IP {ip_summary}，事件在主机间分布{ip_dist}。",
            ],
        },
        {
            "title": "四、处置建议",
            "lines": [
                f"1. 优先处理错误码 {top['name'] if top else '-'}：{action_hint(top['category'] if top else '')}",
                "2. 对活跃 IP 主机执行带外硬件自检（ipmitool sdr / Redfish Diagnostics），"
                "核对固件与 BMC 时间同步。",
                "3. 将峰值时段与变更记录、动环告警（供电/温度）做时间线对齐，确认是否外部诱因。",
                "4. 建议把本次解析任务设为周期执行，持续观测错误码趋势变化。",
            ],
        },
        {
            "title": "五、置信度说明",
            "lines": [
                "本报告由规则引擎 + LLM 生成：统计置信度 92.0%，根因推断为经验规则匹配，"
                "建议结合现场信息复核。",
            ],
        },
    ]


def build_llm_context(events: list[ParsedEvent], parser_name: str) -> str:
    """拼装给真实 LLM 的上下文 (KPI + Top5 错误码 + Top3 IP + 峰值桶)."""
    kpi = kpi_of(events)
    codes = by_error_code(events, 5)
    ips = by_ip(events)[:3]
    buckets = bucket_by_time(events, 12)
    peak = max(buckets, key=lambda b: b["total"], default={"label": "-", "total": 0})
    lines = [
        f"解析器: {parser_name}",
        f"事件总数: {kpi['total']} (致命 {kpi['critical']} / 错误 {kpi['error']} / "
        f"告警 {kpi['warning']}), 源 IP {kpi['ips']} 个, 错误码 {kpi['codes']} 种",
        f"时间峰值: {peak['label']} 前后 {peak['total']} 条",
        "Top 错误码:",
        *[f"- {c['name']} ({c['category']}/{c['severity']}) x{c['value']}: {c['sample'][:120]}" for c in codes],
        "活跃 IP:",
        *[f"- {i['ip']}: {i['total']} 条, 高频码 {i['topCode']} x{i['topCodeCount']}" for i in ips],
    ]
    return "\n".join(lines)


def root_cause_hint(cat: str) -> str:
    """类别 -> 经验根因 (与 witty rootCauseHint 一致)."""
    m = {
        "风扇": "风扇转速异常或冗余失效（防尘网堵塞、风扇模块老化）",
        "温度": "散热风道异常或环境温度越限",
        "电源": "PSU 掉电或输入电压异常（供电模块/机柜 PDU）",
        "磁盘": "磁盘介质劣化（SMART 预警）或 RAID 降级",
        "内存": "ECC 可纠正错误累积，存在劣化风险",
        "处理器": "CPU IERR / MCE，多为硬件级故障",
        "电压": "VRM 供电越限",
        "存储": "存储控制器或介质错误",
        "网络": "链路抖动或网卡复位",
        "内核": "内核检测到的底层硬件错误",
    }
    return m.get(cat, "该类别硬件组件的异常行为，需结合传感器读数进一步定位")


def action_hint(cat: str) -> str:
    """类别 -> 处置建议 (与 witty actionHint 一致)."""
    m = {
        "风扇": "检查防尘网与风扇模块，必要时更换故障风扇并恢复冗余",
        "温度": "清理风道、核查机房环控，确认进风口温度",
        "电源": "检查 PSU 状态灯与 PDU 供电，更换故障电源模块",
        "磁盘": "查看 SMART 详情，预备更换磁盘并确认 RAID 重建策略",
        "内存": "运行内存诊断，规划停机更换可疑 DIMM",
        "处理器": "收集 MCE 记录并联系硬件厂商 RMA",
        "电压": "测量主板电压轨，核查 PSU 负载均衡",
    }
    return m.get(cat, "按厂商硬件诊断手册执行对应组件检查")
