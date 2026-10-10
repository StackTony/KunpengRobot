"""确定性伪随机演示日志生成器 (demo 数据源, 供种子演示任务).

移植自 witty-log-analyzer/src/parser/mock-logs.ts (MulanPSL-2.0).
前端"填充示例日志"按钮仍用 TS 版生成器, 两侧格式一致但独立实现.
"""
import json
from datetime import datetime, timedelta

DEFAULT_IPS = [
    "10.1.3.11", "10.1.3.12", "10.1.3.21", "10.1.3.22", "10.1.3.23",
    "10.1.4.31", "10.1.4.32", "10.2.8.101", "10.2.8.102", "192.168.30.5",
]

_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
           "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _mulberry32(seed: int):
    """与 witty mulberry32 一致的确定性伪随机 [0, 1)."""
    a = seed & 0xFFFFFFFF

    def rand() -> float:
        nonlocal a
        a = (a + 0x6D2B79F5) & 0xFFFFFFFF
        t = a
        t = (t ^ (t >> 15)) * (t | 1) & 0xFFFFFFFF
        t = (t ^ (t + ((t ^ (t >> 7)) * (t | 61) & 0xFFFFFFFF))) & 0xFFFFFFFF
        return ((t ^ (t >> 14)) & 0xFFFFFFFF) / 4294967296

    return rand


def _opt(opts: dict, key: str, default):
    return opts.get(key, default)


# ---------------- SEL (ipmitool sel elist 格式) ----------------

_SEL_EVENTS = [
    {"sensor": "Fan #0x45", "code": "F-0x45", "sev": "critical", "desc": "Fan redundancy lost"},
    {"sensor": "Fan #0x46", "code": "F-0x46", "sev": "warning", "desc": "Fan predictive failure"},
    {"sensor": "Temp #0x01", "code": "T-0x01", "sev": "critical", "desc": "Upper Critical going high"},
    {"sensor": "Temp #0x02", "code": "T-0x02", "sev": "warning", "desc": "Upper Non-critical going high"},
    {"sensor": "Power Unit #0x0A", "code": "P-0x0A", "sev": "critical", "desc": "Power unit failure"},
    {"sensor": "PSU2 Status", "code": "P-0x1B", "sev": "error", "desc": "Predictive failure asserted"},
    {"sensor": "Drive Slot #0x66", "code": "D-0x66", "sev": "error", "desc": "Drive fault detected"},
    {"sensor": "Drive Slot #0x67", "code": "D-0x67", "sev": "warning", "desc": "Drive predictive failure"},
    {"sensor": "Memory #0x30", "code": "M-0x30", "sev": "error", "desc": "Correctable ECC error"},
    {"sensor": "Memory #0x31", "code": "M-0x31", "sev": "critical", "desc": "Uncorrectable ECC error"},
    {"sensor": "CPU #0x01", "code": "C-0x01", "sev": "critical", "desc": "IERR asserted"},
    {"sensor": "VRM #0x50", "code": "V-0x50", "sev": "warning", "desc": "Voltage out of range"},
    {"sensor": "SEL", "code": "S-0x00", "sev": "info", "desc": "Event log disabled"},
]


def gen_sel(opts: dict) -> str:
    rand = _mulberry32(_opt(opts, "seed", 42))
    ips = _opt(opts, "ipPool", DEFAULT_IPS)
    hours = _opt(opts, "hours", 24)
    count = _opt(opts, "count", 100)
    now = datetime.now()
    lines = [
        "SEL Record ID          | Timestamp             | Record Type | Info | Event Details",
        "---------------------------------------------------------------------------",
    ]
    for i in range(count, 0, -1):
        idx = 0 if rand() < 0.28 else int(rand() * len(_SEL_EVENTS))
        e = _SEL_EVENTS[idx]
        ts = now - timedelta(milliseconds=rand() * hours * 3600 * 1000)
        stamp = ts.strftime("%m/%d/%Y %H:%M:%S")
        ip = ips[int(rand() * len(ips))]
        rec_id = str(count - i + 1).rjust(4)
        lines.append(
            f"  {rec_id} | {stamp} | {ip} | 0x2 | "
            f"{'Event' if e['sev'] == 'info' else 'Threshold'} | {e['sensor']} | {e['code']} | {e['desc']}"
        )
    return "\n".join(lines)


# ---------------- Redfish LogService JSON ----------------

_REDFISH_CATALOG = [
    {"msg": "The fan redundancy is lost.", "code": "F-0x45", "cat": "Cooling", "sev": "Critical"},
    {"msg": "Drive 34 predictive failure asserted.", "code": "D-0x66", "cat": "Storage", "sev": "Warning"},
    {"msg": "PSU2 input lost or out-of-range.", "code": "P-0x1B", "cat": "Power", "sev": "Critical"},
    {"msg": "Correctable memory error logged.", "code": "M-0x30", "cat": "Memory", "sev": "Warning"},
    {"msg": "System board VRM voltage out of range.", "code": "V-0x50", "cat": "Voltage", "sev": "Warning"},
    {"msg": "CPU machine check error.", "code": "C-0x01", "cat": "Processor", "sev": "Critical"},
    {"msg": "Host power on.", "code": "S-0x00", "cat": "System", "sev": "OK"},
]


def gen_redfish(opts: dict) -> str:
    rand = _mulberry32(_opt(opts, "seed", 7))
    ips = _opt(opts, "ipPool", DEFAULT_IPS)
    hours = _opt(opts, "hours", 24)
    count = _opt(opts, "count", 100)
    now = datetime.now()
    members = []
    for i in range(count):
        idx = 0 if rand() < 0.3 else int(rand() * len(_REDFISH_CATALOG))
        e = _REDFISH_CATALOG[idx]
        ts = now - timedelta(milliseconds=rand() * hours * 3600 * 1000)
        members.append({
            "Id": str(i + 1),
            "Created": ts.isoformat() + "Z",
            "Severity": e["sev"],
            "Message": e["msg"],
            "OEMCode": e["code"],
            "Category": e["cat"],
            "OriginIp": ips[int(rand() * len(ips))],
        })
    return json.dumps({"@odata.type": "#LogServiceCollection.LogServiceCollection",
                       "Members": members}, indent=2, ensure_ascii=False)


# ---------------- Syslog RFC3164 ----------------

_SYSLOG_CATALOG = [
    {"tag": "sshd", "sev": "error", "code": "NET-443", "msg": "Failed password for root from 10.2.8.101 port 51234 ssh2"},
    {"tag": "kernel", "sev": "critical", "code": "KRN-001", "msg": "I/O error, dev sdb, sector 1051200"},
    {"tag": "systemd", "sev": "warning", "code": "SVC-501", "msg": "nginx.service: Failed with result exit-code"},
    {"tag": "smartd", "sev": "error", "code": "DSK-051", "msg": "Device: /dev/sda, 1 Currently unreadable pending sectors"},
    {"tag": "ntpd", "sev": "info", "code": "NTP-000", "msg": "clock synchronized to 10.1.4.31"},
    {"tag": "dhclient", "sev": "warning", "code": "NET-662", "msg": "lease of 10.1.3.22 obtained, renewal in 3600 seconds"},
]


def gen_syslog(opts: dict) -> str:
    rand = _mulberry32(_opt(opts, "seed", 11))
    ips = _opt(opts, "ipPool", DEFAULT_IPS)
    hours = _opt(opts, "hours", 24)
    count = _opt(opts, "count", 100)
    now = datetime.now()
    sev_num = {"critical": 2, "error": 3, "warning": 4, "info": 6}
    lines = []
    for _ in range(count):
        idx = 1 if rand() < 0.25 else int(rand() * len(_SYSLOG_CATALOG))
        e = _SYSLOG_CATALOG[idx]
        ts = now - timedelta(milliseconds=rand() * hours * 3600 * 1000)
        stamp = f"{_MONTHS[ts.month - 1]} {str(ts.day).rjust(2)} {ts.strftime('%H:%M:%S')}"
        host = ips[int(rand() * len(ips))]
        pri = 3 * 8 + sev_num.get(e["sev"], 6)
        lines.append(f"<{pri}>{stamp} {host} {e['tag']}[{1000 + int(rand() * 8000)}]: [{e['code']}] {e['msg']}")
    return "\n".join(lines)


# ---------------- dmesg ----------------

_DMESG_CATALOG = [
    {"sev": "critical", "code": "MEM-277", "msg": "mce: [Hardware Error]: Machine check events logged"},
    {"sev": "error", "code": "DSK-051", "msg": "blk_update_request: I/O error, dev sdb, sector 1051200"},
    {"sev": "error", "code": "NET-921", "msg": "igc 0000:01:00.0 enp1s0: Reset adapter"},
    {"sev": "warning", "code": "THERM-01", "msg": "thermal thermal_zone6: critical temperature reached (105 C), shutting down"},
    {"sev": "warning", "code": "NVME-14", "msg": "nvme nvme0: I/O 448 QID 3 timeout, aborting"},
    {"sev": "info", "code": "PCI-000", "msg": "pci 0000:00:1f.2: waking up"},
]


def gen_dmesg(opts: dict) -> str:
    rand = _mulberry32(_opt(opts, "seed", 23))
    ips = _opt(opts, "ipPool", DEFAULT_IPS)
    hours = _opt(opts, "hours", 24)
    count = _opt(opts, "count", 100)
    now = datetime.now()
    lines = []
    last_sec = 100 + rand() * 1000
    for _ in range(count):
        last_sec += rand() * 140
        idx = 2 if rand() < 0.3 else int(rand() * len(_DMESG_CATALOG))
        e = _DMESG_CATALOG[idx]
        ts = now - timedelta(milliseconds=rand() * hours * 3600 * 1000)
        ip = ips[int(rand() * len(ips))]
        lines.append(f"[{last_sec:.6f}] [{ts.isoformat() + 'Z'}] [{ip}] "
                     f"{'info' if e['sev'] == 'info' else 'err'} : {e['msg']} [{e['code']}]")
    return "\n".join(lines)


# ---------------- Windows 事件日志 (JSON lines) ----------------

_WINDOWS_CATALOG = [
    {"provider": "disk", "level": "Error", "code": "EVT-153", "cat": "存储",
     "msg": "The driver detected a controller error on \\Device\\HarddiskDrive2."},
    {"provider": "Microsoft-Windows-Kernel-Power", "level": "Critical", "code": "EVT-41", "cat": "电源",
     "msg": "The system has rebooted without cleanly shutting down first."},
    {"provider": "Service Control Manager", "level": "Error", "code": "EVT-7034", "cat": "服务",
     "msg": "Service W32Time terminated unexpectedly."},
    {"provider": "Microsoft-Windows-WHEA-Logger", "level": "Error", "code": "EVT-18", "cat": "硬件",
     "msg": "A corrected hardware error has occurred."},
    {"provider": "Dnscache", "level": "Information", "code": "EVT-1104", "cat": "网络",
     "msg": "The DNS proxy service was unable to read the local hosts file."},
]


def gen_windows(opts: dict) -> str:
    rand = _mulberry32(_opt(opts, "seed", 31))
    ips = _opt(opts, "ipPool", DEFAULT_IPS)
    hours = _opt(opts, "hours", 24)
    count = _opt(opts, "count", 100)
    now = datetime.now()
    lines = []
    for _ in range(count):
        idx = 0 if rand() < 0.3 else int(rand() * len(_WINDOWS_CATALOG))
        e = _WINDOWS_CATALOG[idx]
        ts = now - timedelta(milliseconds=rand() * hours * 3600 * 1000)
        lines.append(json.dumps({
            "TimeCreated": ts.isoformat() + "Z",
            "ProviderName": e["provider"],
            "Level": e["level"],
            "EventId": e["code"],
            "Category": e["cat"],
            "SourceIp": ips[int(rand() * len(ips))],
            "Message": e["msg"],
        }, ensure_ascii=False))
    return "\n".join(lines)


# ---------------- 通用应用日志 ----------------

_APP_CATALOG = [
    {"sev": "ERROR", "code": "E5003", "msg": "upstream timeout calling inventory-service"},
    {"sev": "ERROR", "code": "E5010", "msg": "connection refused to redis master"},
    {"sev": "WARN", "code": "W2001", "msg": "slow query 2.4s: SELECT * FROM orders"},
    {"sev": "WARN", "code": "W2011", "msg": "circuit breaker half-open"},
    {"sev": "INFO", "code": "I0000", "msg": "request completed 200"},
]


def gen_app_log(opts: dict) -> str:
    rand = _mulberry32(_opt(opts, "seed", 55))
    ips = _opt(opts, "ipPool", DEFAULT_IPS)
    hours = _opt(opts, "hours", 24)
    count = _opt(opts, "count", 100)
    now = datetime.now()
    lines = []
    for _ in range(count):
        idx = 0 if rand() < 0.35 else int(rand() * len(_APP_CATALOG))
        e = _APP_CATALOG[idx]
        ts = now - timedelta(milliseconds=rand() * hours * 3600 * 1000)
        ip = ips[int(rand() * len(ips))]
        lines.append(f"{ts.strftime('%Y-%m-%d %H:%M:%S')} [{e['sev']}] [order-svc] "
                     f"code={e['code']} from={ip} trace=tr-{int(rand() * 90000)} msg={e['msg']}")
    return "\n".join(lines)


# parser_type -> 生成器
DEMO_LOG_GENS = {
    "sel": gen_sel, "redfish": gen_redfish, "syslog": gen_syslog,
    "dmesg": gen_dmesg, "windows": gen_windows, "regex": gen_app_log,
}
