/* 确定性伪随机 mock 样例日志生成器（demo 数据源） */

function mulberry32(seed: number) {
  let a = seed
  return function () {
    a |= 0; a = (a + 0x6d2b79f5) | 0
    let t = Math.imul(a ^ (a >>> 15), 1 | a)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

export interface GenOptions {
  count: number
  hours?: number // 覆盖最近 N 小时
  ipPool?: string[]
  seed?: number
}

const DEFAULT_IPS = [
  '10.1.3.11', '10.1.3.12', '10.1.3.21', '10.1.3.22', '10.1.3.23',
  '10.1.4.31', '10.1.4.32', '10.2.8.101', '10.2.8.102', '192.168.30.5',
]

/* ---------------- SEL (ipmitool sel elist 格式) ---------------- */
const SEL_EVENTS = [
  { sensor: 'Fan #0x45', code: 'F-0x45', cat: '风扇', sev: 'critical', desc: 'Fan redundancy lost' },
  { sensor: 'Fan #0x46', code: 'F-0x46', cat: '风扇', sev: 'warning', desc: 'Fan predictive failure' },
  { sensor: 'Temp #0x01', code: 'T-0x01', cat: '温度', sev: 'critical', desc: 'Upper Critical going high' },
  { sensor: 'Temp #0x02', code: 'T-0x02', cat: '温度', sev: 'warning', desc: 'Upper Non-critical going high' },
  { sensor: 'Power Unit #0x0A', code: 'P-0x0A', cat: '电源', sev: 'critical', desc: 'Power unit failure' },
  { sensor: 'PSU2 Status', code: 'P-0x1B', cat: '电源', sev: 'error', desc: 'Predictive failure asserted' },
  { sensor: 'Drive Slot #0x66', code: 'D-0x66', cat: '磁盘', sev: 'error', desc: 'Drive fault detected' },
  { sensor: 'Drive Slot #0x67', code: 'D-0x67', cat: '磁盘', sev: 'warning', desc: 'Drive predictive failure' },
  { sensor: 'Memory #0x30', code: 'M-0x30', cat: '内存', sev: 'error', desc: 'Correctable ECC error' },
  { sensor: 'Memory #0x31', code: 'M-0x31', cat: '内存', sev: 'critical', desc: 'Uncorrectable ECC error' },
  { sensor: 'CPU #0x01', code: 'C-0x01', cat: '处理器', sev: 'critical', desc: 'IERR asserted' },
  { sensor: 'VRM #0x50', code: 'V-0x50', cat: '电压', sev: 'warning', desc: 'Voltage out of range' },
  { sensor: 'SEL', code: 'S-0x00', cat: 'BMC', sev: 'info', desc: 'Event log disabled' },
]

export function genSel(opts: GenOptions): string {
  const rand = mulberry32(opts.seed ?? 42)
  const ips = opts.ipPool ?? DEFAULT_IPS
  const hours = opts.hours ?? 24
  const now = Date.now()
  const lines: string[] = [
    'SEL Record ID          | Timestamp             | Record Type | Info | Event Details',
    '---------------------------------------------------------------------------',
  ]
  for (let i = opts.count; i > 0; i--) {
    // 权重：让个别传感器高频出现，方便演示聚合效果
    const idx = rand() < 0.28 ? 0 : Math.floor(rand() * SEL_EVENTS.length)
    const e = SEL_EVENTS[idx]
    const ts = new Date(now - rand() * hours * 3600 * 1000)
    const p = (n: number) => String(n).padStart(2, '0')
    const stamp = `${p(ts.getMonth() + 1)}/${p(ts.getDate())}/${ts.getFullYear()} ${p(ts.getHours())}:${p(ts.getMinutes())}:${p(ts.getSeconds())}`
    const ip = ips[Math.floor(rand() * ips.length)]
    const recId = String(opts.count - i + 1).padStart(4, ' ')
    lines.push(
      `  ${recId} | ${stamp} | ${ip} | 0x${(2).toString()} | ${e.sev === 'info' ? 'Event' : 'Threshold'} | ${e.sensor} | ${e.code} | ${e.desc}`,
    )
  }
  return lines.join('\n')
}

/* ---------------- Redfish LogService JSON ---------------- */
export function genRedfish(opts: GenOptions): string {
  const rand = mulberry32(opts.seed ?? 7)
  const ips = opts.ipPool ?? DEFAULT_IPS
  const hours = opts.hours ?? 24
  const now = Date.now()
  const catalog = [
    { msg: 'The fan redundancy is lost.', code: 'F-0x45', cat: 'Cooling', sev: 'Critical' },
    { msg: 'Drive 34 predictive failure asserted.', code: 'D-0x66', cat: 'Storage', sev: 'Warning' },
    { msg: 'PSU2 input lost or out-of-range.', code: 'P-0x1B', cat: 'Power', sev: 'Critical' },
    { msg: 'Correctable memory error logged.', code: 'M-0x30', cat: 'Memory', sev: 'Warning' },
    { msg: 'System board VRM voltage out of range.', code: 'V-0x50', cat: 'Voltage', sev: 'Warning' },
    { msg: 'CPU machine check error.', code: 'C-0x01', cat: 'Processor', sev: 'Critical' },
    { msg: 'Host power on.', code: 'S-0x00', cat: 'System', sev: 'OK' },
  ]
  const members = []
  for (let i = 0; i < opts.count; i++) {
    const idx = rand() < 0.3 ? 0 : Math.floor(rand() * catalog.length)
    const e = catalog[idx]
    const ts = new Date(now - rand() * hours * 3600 * 1000)
    members.push({
      Id: String(i + 1),
      Created: ts.toISOString(),
      Severity: e.sev,
      Message: e.msg,
      OEMCode: e.code,
      Category: e.cat,
      OriginIp: ips[Math.floor(rand() * ips.length)],
    })
  }
  return JSON.stringify({ '@odata.type': '#LogServiceCollection.LogServiceCollection', Members: members }, null, 2)
}

/* ---------------- Syslog RFC3164 ---------------- */
export function genSyslog(opts: GenOptions): string {
  const rand = mulberry32(opts.seed ?? 11)
  const ips = opts.ipPool ?? DEFAULT_IPS
  const hours = opts.hours ?? 24
  const now = Date.now()
  const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
  const catalog = [
    { tag: 'sshd', sev: 'error', code: 'NET-443', msg: 'Failed password for root from 10.2.8.101 port 51234 ssh2' },
    { tag: 'kernel', sev: 'critical', code: 'KRN-001', msg: 'I/O error, dev sdb, sector 1051200' },
    { tag: 'systemd', sev: 'warning', code: 'SVC-501', msg: 'nginx.service: Failed with result exit-code' },
    { tag: 'smartd', sev: 'error', code: 'DSK-051', msg: 'Device: /dev/sda, 1 Currently unreadable pending sectors' },
    { tag: 'ntpd', sev: 'info', code: 'NTP-000', msg: 'clock synchronized to 10.1.4.31' },
    { tag: 'dhclient', sev: 'warning', code: 'NET-662', msg: 'lease of 10.1.3.22 obtained, renewal in 3600 seconds' },
  ]
  const lines = []
  for (let i = 0; i < opts.count; i++) {
    const idx = rand() < 0.25 ? 1 : Math.floor(rand() * catalog.length)
    const e = catalog[idx]
    const ts = new Date(now - rand() * hours * 3600 * 1000)
    const p = (n: number) => String(n).padStart(2, ' ')
    const stamp = `${MONTHS[ts.getMonth()]} ${p(ts.getDate())} ${String(ts.getHours()).padStart(2, '0')}:${String(ts.getMinutes()).padStart(2, '0')}:${String(ts.getSeconds()).padStart(2, '0')}`
    const host = ips[Math.floor(rand() * ips.length)]
    const facility = 3 // system daemons
    const sevNum = { critical: 2, error: 3, warning: 4, info: 6 }[e.sev as 'critical'] ?? 6
    lines.push(`<${facility * 8 + sevNum}>${stamp} ${host} ${e.tag}[${1000 + Math.floor(rand() * 8000)}]: [${e.code}] ${e.msg}`)
  }
  return lines.join('\n')
}

/* ---------------- dmesg ---------------- */
export function genDmesg(opts: GenOptions): string {
  const rand = mulberry32(opts.seed ?? 23)
  const ips = opts.ipPool ?? DEFAULT_IPS
  const hours = opts.hours ?? 24
  const now = Date.now()
  const catalog = [
    { sev: 'critical', code: 'MEM-277', msg: 'mce: [Hardware Error]: Machine check events logged' },
    { sev: 'error', code: 'DSK-051', msg: 'blk_update_request: I/O error, dev sdb, sector 1051200' },
    { sev: 'error', code: 'NET-921', msg: 'igc 0000:01:00.0 enp1s0: Reset adapter' },
    { sev: 'warning', code: 'THERM-01', msg: 'thermal thermal_zone6: critical temperature reached (105 C), shutting down' },
    { sev: 'warning', code: 'NVME-14', msg: 'nvme nvme0: I/O 448 QID 3 timeout, aborting' },
    { sev: 'info', code: 'PCI-000', msg: 'pci 0000:00:1f.2: waking up' },
  ]
  const lines: string[] = []
  let lastSec = 100 + rand() * 1000
  for (let i = 0; i < opts.count; i++) {
    lastSec += rand() * 140
    const idx = rand() < 0.3 ? 2 : Math.floor(rand() * catalog.length)
    const e = catalog[idx]
    const ts = new Date(now - rand() * hours * 3600 * 1000)
    const ip = ips[Math.floor(rand() * ips.length)]
    lines.push(`[${lastSec.toFixed(6)}] [${ts.toISOString()}] [${ip}] ${e.sev === 'info' ? 'info' : 'err'} : ${e.msg} [${e.code}]`)
  }
  return lines.join('\n')
}

/* ---------------- Windows 事件日志 (JSON lines) ---------------- */
export function genWindows(opts: GenOptions): string {
  const rand = mulberry32(opts.seed ?? 31)
  const ips = opts.ipPool ?? DEFAULT_IPS
  const hours = opts.hours ?? 24
  const now = Date.now()
  const catalog = [
    { provider: 'disk', level: 'Error', code: 'EVT-153', cat: '存储', msg: 'The driver detected a controller error on \\Device\\HarddiskDrive2.' },
    { provider: 'Microsoft-Windows-Kernel-Power', level: 'Critical', code: 'EVT-41', cat: '电源', msg: 'The system has rebooted without cleanly shutting down first.' },
    { provider: 'Service Control Manager', level: 'Error', code: 'EVT-7034', cat: '服务', msg: 'Service W32Time terminated unexpectedly.' },
    { provider: 'Microsoft-Windows-WHEA-Logger', level: 'Error', code: 'EVT-18', cat: '硬件', msg: 'A corrected hardware error has occurred.' },
    { provider: 'Dnscache', level: 'Information', code: 'EVT-1104', cat: '网络', msg: 'The DNS proxy service was unable to read the local hosts file.' },
  ]
  const lines = []
  for (let i = 0; i < opts.count; i++) {
    const idx = rand() < 0.3 ? 0 : Math.floor(rand() * catalog.length)
    const e = catalog[idx]
    const ts = new Date(now - rand() * hours * 3600 * 1000)
    lines.push(JSON.stringify({
      TimeCreated: ts.toISOString(),
      ProviderName: e.provider,
      Level: e.level,
      EventId: e.code,
      Category: e.cat,
      SourceIp: ips[Math.floor(rand() * ips.length)],
      Message: e.msg,
    }))
  }
  return lines.join('\n')
}

/* ---------------- 通用应用日志（自定义正则示例） ---------------- */
export function genAppLog(opts: GenOptions): string {
  const rand = mulberry32(opts.seed ?? 55)
  const ips = opts.ipPool ?? DEFAULT_IPS
  const hours = opts.hours ?? 24
  const now = Date.now()
  const catalog = [
    { sev: 'ERROR', code: 'E5003', msg: 'upstream timeout calling inventory-service' },
    { sev: 'ERROR', code: 'E5010', msg: 'connection refused to redis master' },
    { sev: 'WARN', code: 'W2001', msg: 'slow query 2.4s: SELECT * FROM orders' },
    { sev: 'WARN', code: 'W2011', msg: 'circuit breaker half-open' },
    { sev: 'INFO', code: 'I0000', msg: 'request completed 200' },
  ]
  const lines = []
  for (let i = 0; i < opts.count; i++) {
    const idx = rand() < 0.35 ? 0 : Math.floor(rand() * catalog.length)
    const e = catalog[idx]
    const ts = new Date(now - rand() * hours * 3600 * 1000)
    const p = (n: number) => String(n).padStart(2, '0')
    const stamp = `${ts.getFullYear()}-${p(ts.getMonth() + 1)}-${p(ts.getDate())} ${p(ts.getHours())}:${p(ts.getMinutes())}:${p(ts.getSeconds())}`
    const ip = ips[Math.floor(rand() * ips.length)]
    lines.push(`${stamp} [${e.sev}] [order-svc] code=${e.code} from=${ip} trace=tr-${Math.floor(rand() * 90000)} msg=${e.msg}`)
  }
  return lines.join('\n')
}
