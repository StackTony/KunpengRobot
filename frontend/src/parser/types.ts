/* 统一事件模型与解析器接口 */

export type Severity = 'critical' | 'error' | 'warning' | 'info'

export interface ParsedEvent {
  timestamp: number // ms epoch
  sourceIp: string
  severity: Severity
  category: string
  errorCode: string
  raw: string
  fields: Record<string, string>
}

export interface ParserDef {
  type: string
  name: string
  desc: string
  fileHint: string
}

export const SEVERITY_ORDER: Record<Severity, number> = {
  critical: 0, error: 1, warning: 2, info: 3,
}

export function sevBadgeClass(s: Severity): string {
  return { critical: 'o-badge--danger', error: 'o-badge--danger', warning: 'o-badge--warning', info: 'o-badge--success' }[s]
}

export function sevLabel(s: Severity): string {
  return { critical: '致命', error: '错误', warning: '告警', info: '信息' }[s]
}

export function fmtTime(ms: number | string | Date): string {
  const d = new Date(ms)
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`
}
