/* 聚合结果类型 (聚合计算在后端完成, 前端只消费 /tasks/{id}/stats 响应) */

export interface TimeBucket {
  t: number
  label: string
  critical: number
  error: number
  warning: number
  info: number
  total: number
}

export interface NameValue {
  name: string
  value: number
}

export interface CodeStat extends NameValue {
  severity: string
  category: string
  sample: string
}

export interface IpStat {
  ip: string
  total: number
  critical: number
  error: number
  warning: number
  info: number
  topCode: string
  topCodeCount: number
}

export interface TaskKpi {
  total: number
  critical: number
  error: number
  warning: number
  ips: number
  codes: number
}

export interface TaskStats {
  kpi: TaskKpi
  timeBuckets: TimeBucket[]
  categories: NameValue[]
  codes: CodeStat[]
  ips: IpStat[]
}
