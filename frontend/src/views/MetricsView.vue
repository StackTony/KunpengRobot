<script setup lang="ts">
/* 性能趋势图表: 主机/指标/时间范围查询 + 降采样 + 视图配置服务端持久化 (刷新/切页不丢) */
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { get, post, put, apiError } from '@/api/http'
import type { EChartsOption } from 'echarts'
import ChartBase from '@/components/ChartBase.vue'

const PREF_KEY = 'dashboard.charts'
const RANGES = [
  { key: '1h', label: '近 1 小时', ms: 3600e3 },
  { key: '6h', label: '近 6 小时', ms: 6 * 3600e3 },
  { key: '24h', label: '近 24 小时', ms: 24 * 3600e3 },
  { key: '7d', label: '近 7 天', ms: 7 * 86400e3 },
]

const hosts = ref<string[]>([])
const metricNames = ref<string[]>([])
const host = ref('')
const metric = ref('')
const rangeKey = ref('24h')
const points = ref<[string, number][]>([])
const loading = ref(false)
const loadErr = ref('')
const savedTip = ref('')
let savedTimer: number | undefined

const range = computed(() => RANGES.find((r) => r.key === rangeKey.value) ?? RANGES[2])

async function loadLists() {
  try {
    const [h, n] = await Promise.all([
      get<{ hosts: string[] }>('/metrics/hosts'),
      get<{ metricNames: string[] }>('/metrics/names'),
    ])
    hosts.value = h.hosts ?? []
    metricNames.value = n.metricNames?.length ? n.metricNames : ['cpu.usage', 'mem.used_pct']
  } catch (e) {
    loadErr.value = apiError(e)
  }
}

async function load() {
  if (!host.value || !metric.value) return
  loadErr.value = ''
  loading.value = true
  try {
    const end = new Date()
    const start = new Date(end.getTime() - range.value.ms)
    const data = await post<{ host: string; metricName: string; points: [string, number][] }>('/metrics/query', {
      host: host.value,
      metric_name: metric.value,
      start: start.toISOString(),
      end: end.toISOString(),
      /* 降采样窗口: 时间跨度越大窗口越大, 保证点数可控 */
      interval_seconds: range.value.ms >= 7 * 86400e3 ? 3600 : range.value.ms >= 6 * 3600e3 ? 300 : 60,
    })
    points.value = data.points ?? []
  } catch (e) {
    loadErr.value = apiError(e)
  } finally {
    loading.value = false
  }
}

/* ---------- 视图配置持久化 ---------- */
async function restoreLayout() {
  try {
    const data = await get<{ prefValue: Record<string, any> }>(`/preferences/${PREF_KEY}`)
    const pref = data.prefValue ?? {}
    if (pref.host && hosts.value.includes(pref.host)) host.value = pref.host
    if (pref.metric && metricNames.value.includes(pref.metric)) metric.value = pref.metric
    if (pref.rangeKey && RANGES.some((r) => r.key === pref.rangeKey)) rangeKey.value = pref.rangeKey
  } catch { /* 忽略恢复失败 */ }
}

async function saveLayout() {
  savedTip.value = ''
  try {
    await put(`/preferences/${PREF_KEY}`, {
      pref_key: PREF_KEY,
      pref_value: { host: host.value, metric: metric.value, rangeKey: rangeKey.value },
    })
    savedTip.value = '已保存，刷新或换设备后自动恢复'
    if (savedTimer) clearTimeout(savedTimer)
    savedTimer = setTimeout(() => (savedTip.value = ''), 3000)
  } catch (e) {
    loadErr.value = apiError(e)
  }
}

const chartOption = computed<EChartsOption>(() => ({
  tooltip: { trigger: 'axis' },
  grid: { left: 56, right: 24, top: 32, bottom: 40 },
  xAxis: { type: 'time' },
  yAxis: { type: 'value' },
  dataZoom: [{ type: 'inside' }],
  series: [{
    type: 'line',
    name: metric.value,
    showSymbol: false,
    smooth: true,
    lineStyle: { width: 2, color: '#1e6fff' },
    areaStyle: { opacity: 0.1 },
    data: points.value,
  }],
}))

const pointCount = computed(() => points.value.length)

onMounted(async () => {
  await loadLists()
  if (hosts.value.length && !host.value) host.value = hosts.value[0]
  if (metricNames.value.length && !metric.value) metric.value = metricNames.value[0]
  await restoreLayout()
  await load()
})
onBeforeUnmount(() => {
  if (savedTimer) clearTimeout(savedTimer)
})
</script>

<template>
  <div class="o-operate-bar">
    <div class="o-operate-left">
      <h2>性能趋势</h2>
      <span class="o-mono o-text-3">数据来自解析任务提取的指标点，服务端持久保存</span>
    </div>
    <div class="o-operate-right">
      <select v-model="host" class="o-select" @change="load">
        <option value="" disabled>选择主机</option>
        <option v-for="h in hosts" :key="h" :value="h">{{ h }}</option>
      </select>
      <select v-model="metric" class="o-select" @change="load">
        <option value="" disabled>选择指标</option>
        <option v-for="m in metricNames" :key="m" :value="m">{{ m }}</option>
      </select>
      <select v-model="rangeKey" class="o-select" @change="load">
        <option v-for="r in RANGES" :key="r.key" :value="r.key">{{ r.label }}</option>
      </select>
      <button class="o-btn" @click="saveLayout">保存布局</button>
    </div>
  </div>

  <div v-if="savedTip" class="o-mono" style="color: var(--success, #00b365); margin-bottom: 12px">✓ {{ savedTip }}</div>
  <div v-if="loadErr" class="o-mono" style="color: var(--danger); margin-bottom: 12px">⚠ {{ loadErr }}</div>

  <div class="o-card">
    <div class="o-card__title">
      {{ host || '性能趋势' }} · {{ metric || '—' }}
      <span class="o-mono o-text-3">{{ range.label }} · {{ pointCount }} 个数据点{{ loading ? ' · 加载中…' : '' }}</span>
    </div>
    <ChartBase v-if="host && pointCount" :option="chartOption" height="440px" />
    <div v-else class="o-empty" style="padding: 120px 0">
      <div class="icon">📉</div>
      <div>暂无指标数据 — 上传日志包并完成分析后，性能指标将出现在此处</div>
    </div>
  </div>
</template>

<style scoped>
</style>
