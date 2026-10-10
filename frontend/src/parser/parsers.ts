/* 六种日志解析器定义 (解析由后端完成, 前端只保留元数据用于展示与预检) */
import type { ParserDef } from './types'

export const PARSER_DEFS: Record<string, ParserDef> = {
  sel: {
    type: 'sel',
    name: 'BMC / SEL 日志',
    desc: 'ipmitool sel elist 导出的系统事件日志文本',
    fileHint: 'sel_elist_*.txt',
  },
  redfish: {
    type: 'redfish',
    name: 'Redfish JSON',
    desc: 'DMTF Redfish LogService 导出的结构化日志',
    fileHint: 'redfish_logservice_*.json',
  },
  syslog: {
    type: 'syslog',
    name: 'Syslog (RFC3164)',
    desc: '标准 syslog 转发/导出文本',
    fileHint: 'messages / syslog-*.log',
  },
  dmesg: {
    type: 'dmesg',
    name: '内核日志 dmesg',
    desc: 'dmesg -T 输出，含主机 IP 标注',
    fileHint: 'dmesg_*.log',
  },
  windows: {
    type: 'windows',
    name: 'Windows 事件日志',
    desc: 'Get-WinEvent 导出的 JSON lines（EVTX 转 JSON）',
    fileHint: 'events_*.jsonl',
  },
  regex: {
    type: 'regex',
    name: '通用正则解析',
    desc: '自定义正则 + 字段映射（示例：应用日志）',
    fileHint: 'app_*.log',
  },
}

export function parserList(): ParserDef[] {
  return Object.values(PARSER_DEFS)
}
