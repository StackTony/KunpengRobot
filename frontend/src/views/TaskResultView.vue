<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useAssetsStore, type AnalyzeTask } from '@/stores/assets'
import { useTeamsStore } from '@/stores/teams'
import { PARSER_DEFS } from '@/parser/parsers'
import type { TaskStats } from '@/parser/aggregate'
import { fmtTime, sevBadgeClass, sevLabel, type Severity } from '@/parser/types'
import { get, post, apiError, TOKEN_KEY } from '@/api/http'
import type { EChartsOption } from 'echarts'
import ChartBase from '@/components/ChartBase.vue'

const route = useRoute()
const assetsStore = useAssetsStore()
const teamsStore = useTeamsStore()

const taskId = computed(() => route.params.taskId as string)

const task = ref<AnalyzeTask | null>(null)
const noAccess = ref(false)
const notFound = ref(false)
const loadErr = ref('')
let pollTimer: number | undefined

async function loadTask() {
  loadErr.value = ''
  try {
    task.value = await assetsStore.fetchTask(taskId.value)
    noAccess.value = false
    notFound.value = false
    /* 关联资产 → 团队 (面包屑/权限用) */
    if (task.value.assetId) assetsStore.fetchAsset(task.value.assetId).catch(() => {})
  } catch (e: any) {
    if (e?.response?.status === 403) noAccess.value = true
    else if (e?.response?.status === 404) notFound.value = true
    else loadErr.value = apiError(e)
  }
}

/* ---------- 聚合统计 (done 后加载; running 轮询任务状态) ---------- */
const stats = ref<TaskStats | null>(null)

async function loadStats() {
  try {
    stats.value = await get<TaskStats>(`/tasks/${taskId.value}/stats`)
  } catch {
    stats.value = null
  }
}

function schedulePoll() {
  if (pollTimer) window.clearInterval(pollTimer)
  pollTimer = window.setInterval(async () => {
    await loadTask()
    const s = task.value?.status
    if (s && !['pending', 'running'].includes(s)) {
      window.clearInterval(pollTimer)
      pollTimer = undefined
      if (s === 'done') await loadStats()
    }
  }, 2000)
}

onMounted(async () => {
  await loadTask()
  if (task.value) {
    if (['pending', 'running'].includes(task.value.status)) schedulePoll()
    else if (task.value.status === 'done') await loadStats()
  }
})
onBeforeUnmount(() => {
  if (pollTimer) window.clearInterval(pollTimer)
  closeLlm()
})

/* ---------- 权限 ---------- */
const teamOfTask = computed(() => {
  const assetId = task.value?.assetId
  if (!assetId) return undefined
  const asset = assetsStore.assetById(assetId)
  return asset ? teamsStore.teamById(asset.teamId) : undefined
})
const teamId = computed(() => teamOfTask.value?.id ? String(teamOfTask.value.id) : '')
const canLlm = computed(() => !!teamId.value && teamsStore.can(teamId.value, 'task:llm'))
const parserName = computed(() => task.value ? (PARSER_DEFS[task.value.parserType]?.name ?? task.value.parserType) : '')

const kpi = computed(() => stats.value?.kpi ?? { total: 0, critical: 0, error: 0, warning: 0, ips: 0, codes: 0 })
const running = computed(() => !!task.value && ['pending', 'running'].includes(task.value.status))

const tab = ref<'overview' | 'codes' | 'ips' | 'raw' | 'llm'>('overview')

/* ---------- 图表 (数据来自 /stats) ---------- */
const SEV_COLORS: Record<Severity, string> = {
  critical: '#ef4444', error: '#f59e0b', warning: '#fbbf24', info: '#1e6fff',
}
const timeChart = computed<EChartsOption>(() => {
  const buckets = stats.value?.timeBuckets ?? []
  return {
    grid: { left: 48, right: 20, top: 30, bottom: 56 },
    tooltip: { trigger: 'axis' },
    legend: { top: 0, data: ['致命', '错误', '告警', '信息'] },
    dataZoom: [
      { type: 'inside' },
      { type: 'slider', height: 18, bottom: 8 },
    ],
    xAxis: { type: 'category', data: buckets.map((b) => b.label), boundaryGap: false },
    yAxis: { type: 'value' },
    series: (['critical', 'error', 'warning', 'info'] as Severity[]).map((s) => ({
      name: sevLabel(s),
      type: 'line',
      stack: 'total',
      areaStyle: { opacity: 0.15 },
      emphasis: { focus: 'series' },
      itemStyle: { color: SEV_COLORS[s] },
      data: buckets.map((b) => b[s]),
    })),
  }
})
const pieChart = computed<EChartsOption>(() => {
  const cats = (stats.value?.categories ?? []).slice(0, 8)
  return {
    tooltip: { trigger: 'item', formatter: '{b}: {c}（{d}%）' },
    legend: { orient: 'vertical', right: 4, top: 'middle', itemWidth: 10, itemHeight: 10 },
    series: [
      {
        type: 'pie',
        radius: ['42%', '68%'],
        center: ['38%', '50%'],
        label: { show: false },
        data: cats.map((c) => ({ name: c.name, value: c.value })),
        color: ['#1e6fff', '#4d8fff', '#85b8ff', '#b3d1ff', '#00b365', '#f59e0b', '#ef4444', '#98a3b3'],
      },
    ],
  }
})
const codeChart = computed<EChartsOption>(() => {
  const codes = (stats.value?.codes ?? []).slice(0, 10)
  return {
    grid: { left: 80, right: 30, top: 16, bottom: 28 },
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'value' },
    yAxis: { type: 'category', data: codes.map((c) => c.name).reverse(), axisLabel: { fontFamily: 'Menlo, Consolas, monospace' } },
    series: [{
      type: 'bar',
      data: codes.map((c) => c.value).reverse(),
      itemStyle: { color: '#1e6fff' },
      barMaxWidth: 16,
      label: { show: true, position: 'right' },
    }],
  }
})
const ipChart = computed<EChartsOption>(() => {
  const ips = (stats.value?.ips ?? []).slice(0, 10)
  return {
    grid: { left: 110, right: 30, top: 30, bottom: 28 },
    tooltip: { trigger: 'axis' },
    legend: { top: 0, data: ['致命', '错误', '告警', '信息'] },
    xAxis: { type: 'value' },
    yAxis: { type: 'category', data: ips.map((i) => i.ip).reverse(), axisLabel: { fontFamily: 'Menlo, Consolas, monospace' } },
    series: [
      { name: '致命', type: 'bar', stack: 't', data: ips.map((i) => i.critical).reverse(), itemStyle: { color: '#ef4444' }, barMaxWidth: 16 },
      { name: '错误', type: 'bar', stack: 't', data: ips.map((i) => i.error).reverse(), itemStyle: { color: '#f59e0b' } },
      { name: '告警', type: 'bar', stack: 't', data: ips.map((i) => i.warning).reverse(), itemStyle: { color: '#fbbf24' } },
      { name: '信息', type: 'bar', stack: 't', data: ips.map((i) => i.info).reverse(), itemStyle: { color: '#1e6fff' } },
    ],
  }
})
const ipStats = computed(() => stats.value?.ips ?? [])
const codeStats = computed(() => (stats.value?.codes ?? []).slice(0, 15))

/* ---------- 原始日志：服务端筛选 + 分页 ---------- */
interface EventRow {
  id: number
  ts: number
  sourceIp: string
  severity: Severity
  category: string
  errorCode: string
  raw: string
  fields: Record<string, string>
}

const ipFilter = ref('')
const sevFilter = ref<'' | Severity>('')
const catFilter = ref('')
const codeFilter = ref('')
const kwFilter = ref('')
const pageSize = ref(20)
const page = ref(1)
const logs = ref<EventRow[]>([])
const logsTotal = ref(0)
const logsLoading = ref(false)
let logsSeq = 0

const sevChips = computed(() => ([
  { key: '', label: '全部', count: kpi.value.total },
  { key: 'critical', label: '致命', count: kpi.value.critical },
  { key: 'error', label: '错误', count: kpi.value.error },
  { key: 'warning', label: '告警', count: kpi.value.warning },
  { key: 'info', label: '信息', count: kpi.value.total - kpi.value.critical - kpi.value.error - kpi.value.warning },
]))

async function loadLogs() {
  if (running.value) return
  const seq = ++logsSeq
  logsLoading.value = true
  try {
    const data = await get<{ total: number; items: EventRow[] }>(`/tasks/${taskId.value}/logs`, {
      severity: sevFilter.value || undefined,
      category: catFilter.value || undefined,
      error_code: codeFilter.value || undefined,
      source_ip: ipFilter.value || undefined,
      kw: kwFilter.value.trim() || undefined,
      page: page.value,
      page_size: pageSize.value,
    })
    if (seq !== logsSeq) return   // 丢弃过期响应
    logs.value = data.items
    logsTotal.value = data.total
  } finally {
    if (seq === logsSeq) logsLoading.value = false
  }
}

const totalPages = computed(() => Math.max(1, Math.ceil(logsTotal.value / pageSize.value)))
const hasAnyFilter = computed(() => !!(ipFilter.value || sevFilter.value || catFilter.value || codeFilter.value || kwFilter.value))
function clearAll() {
  ipFilter.value = ''
  sevFilter.value = ''
  catFilter.value = ''
  codeFilter.value = ''
  kwFilter.value = ''
}
watch([ipFilter, sevFilter, catFilter, codeFilter, kwFilter, pageSize], () => {
  page.value = 1
  loadLogs()
})
watch(page, loadLogs)
watch(tab, (t) => {
  if (t === 'raw' && !logs.value.length) loadLogs()
})

/* 图表点击联动 */
function onPieClick(p: any) {
  catFilter.value = p.name
  tab.value = 'raw'
}
function onCodeClick(p: any) {
  codeFilter.value = p.name
  tab.value = 'raw'
}
function onIpClick(p: any) {
  ipFilter.value = p.name
  tab.value = 'raw'
}
function fieldsSummary(e: EventRow) {
  return Object.entries(e.fields)
    .slice(0, 4)
    .map(([k, v]) => `${k}=${v}`)
    .join(' · ')
}

/* ---------- LLM (按需触发 + SSE 流式) ---------- */
const llmStarted = ref(false)
const llmLines = ref<{ kind: 'title' | 'line'; text: string }[]>([])
const llmProgress = ref(0)
const llmErr = ref('')
const llmStreaming = ref(false)
const llmBody = ref<HTMLElement>()
let es: EventSource | null = null

function closeLlm() {
  es?.close()
  es = null
  llmStreaming.value = false
}

function scrollLlm() {
  requestAnimationFrame(() => {
    if (llmBody.value) llmBody.value.scrollTop = llmBody.value.scrollHeight
  })
}

async function startLlm() {
  llmErr.value = ''
  llmLines.value = []
  llmProgress.value = 0
  try {
    const { runId } = await post<{ runId: string }>(`/tasks/${taskId.value}/llm`)
    llmStarted.value = true
    llmStreaming.value = true
    const token = localStorage.getItem(TOKEN_KEY) ?? ''
    es = new EventSource(`/api/tasks/${taskId.value}/llm/events?run_id=${encodeURIComponent(runId)}&token=${encodeURIComponent(token)}`)
    es.addEventListener('llm_section', (ev) => {
      const d = JSON.parse((ev as MessageEvent).data)
      llmLines.value.push({ kind: 'title', text: d.title ?? '' })
      scrollLlm()
    })
    es.addEventListener('llm_token', (ev) => {
      const d = JSON.parse((ev as MessageEvent).data)
      if (d.line) {
        llmLines.value.push({ kind: 'line', text: d.text ?? '' })
      } else {
        /* 流式 token: 追加到最后一条正文行 */
        const last = llmLines.value[llmLines.value.length - 1]
        if (last && last.kind === 'line') last.text += d.text ?? ''
        else llmLines.value.push({ kind: 'line', text: d.text ?? '' })
      }
      scrollLlm()
    })
    es.addEventListener('progress', (ev) => {
      const d = JSON.parse((ev as MessageEvent).data)
      llmProgress.value = d.progress ?? 0
    })
    es.addEventListener('done', () => {
      closeLlm()
      llmProgress.value = 100
    })
    es.addEventListener('error', (ev) => {
      const me = ev as MessageEvent
      if (me.data) {
        try {
          const d = JSON.parse(me.data)
          llmErr.value = d.error || '报告生成失败'
        } catch {
          llmErr.value = '报告生成失败'
        }
      }
      closeLlm()
    })
    es.onerror = () => {
      /* done/error 事件正常到达后连接关闭; 避免误报 */
      if (llmStreaming.value && !llmLines.value.length && !llmErr.value) {
        llmErr.value = 'SSE 连接中断，请重试'
        closeLlm()
      }
    }
  } catch (e) {
    llmErr.value = apiError(e)
  }
}
</script>

<template>
  <div v-if="noAccess" class="o-empty o-card">
    <div class="icon">🔒</div>
    <div>无权查看该任务</div>
    <div class="hint">你不属于该任务所属团队的成员，或团队角色无「查看解析任务」权限</div>
  </div>
  <div v-else-if="notFound" class="o-empty o-card">
    <div class="icon">📭</div>
    <div>任务不存在或已被删除</div>
  </div>
  <div v-else-if="loadErr" class="o-empty o-card">
    <div class="icon">⚠️</div>
    <div>{{ loadErr }}</div>
  </div>
  <template v-else-if="task">
    <!-- 信息横幅 + 统计 -->
    <div class="o-banner">
      <div class="banner-left">
        <router-link v-if="teamId" :to="`/teams/${teamId}?tab=tasks`" class="back-btn">
          ← 返回{{ task.assetName || '团队' }}
        </router-link>
        <h2>
          {{ task.name || task.filename }}
          <span class="o-badge o-badge--outline">{{ parserName }}</span>
        </h2>
        <div class="meta">
          <router-link v-if="teamId" :to="`/teams/${teamId}?tab=tasks`">{{ task.assetName || '—' }}</router-link>
          <span class="o-mono o-text-3">{{ task.filename }}（{{ (task.logSize / 1024).toFixed(1) }} KB）</span>
          <span class="o-text-3">{{ task.creatorName }} · {{ fmtTime(task.createdAt) }}</span>
        </div>
      </div>
      <div class="o-banner-stats">
        <div class="o-banner-stat"><b>{{ kpi.total }}</b><span>事件总数</span></div>
        <div class="o-banner-stat"><b style="color: var(--danger)">{{ kpi.critical }}</b><span>致命</span></div>
        <div class="o-banner-stat"><b style="color: var(--warning)">{{ kpi.error }}</b><span>错误</span></div>
        <div class="o-banner-stat"><b>{{ kpi.warning }}</b><span>告警</span></div>
        <div class="o-banner-stat"><b>{{ kpi.ips }}</b><span>源 IP</span></div>
        <div class="o-banner-stat"><b>{{ kpi.codes }}</b><span>错误码</span></div>
      </div>
      <button v-if="canLlm && !running" class="o-btn o-btn--primary" @click="tab = 'llm'">✦ AI 分析</button>
    </div>

    <!-- 解析中提示 -->
    <div v-if="running" class="o-card" style="margin-bottom: 16px">
      <div class="o-row" style="gap: 10px">
        <span class="spin" style="border-color: var(--primary-tint); border-top-color: var(--primary)" />
        <b>任务{{ task.status === 'pending' ? '排队中' : '解析中' }}… {{ task.progress }}%</b>
        <span class="o-text-3" style="font-size: 13px">解析完成后本页将自动刷新展示聚合结果</span>
      </div>
    </div>
    <div v-else-if="task.status === 'failed'" class="o-badge o-badge--danger" style="margin-bottom: 16px">
      解析失败：{{ task.error || '未知错误' }}
    </div>

    <div class="o-tabs">
      <button class="o-tabs__item" :class="{ 'is-active': tab === 'overview' }" @click="tab = 'overview'">总览</button>
      <button class="o-tabs__item" :class="{ 'is-active': tab === 'codes' }" @click="tab = 'codes'">错误码分析</button>
      <button class="o-tabs__item" :class="{ 'is-active': tab === 'ips' }" @click="tab = 'ips'">IP 聚合</button>
      <button class="o-tabs__item" :class="{ 'is-active': tab === 'raw' }" @click="tab = 'raw'">原始日志 <span class="o-badge o-badge--outline">{{ kpi.total }}</span></button>
      <button v-if="canLlm" class="o-tabs__item" :class="{ 'is-active': tab === 'llm' }" @click="tab = 'llm'">✦ LLM 分析</button>
    </div>

    <!-- 总览 -->
    <div v-if="tab === 'overview'" class="grid-2">
      <div class="o-card">
        <div class="o-card__title">事件时序分布<span class="hint">滚轮 / 滑块缩放时间窗</span></div>
        <ChartBase v-if="stats?.timeBuckets?.length" :option="timeChart" height="340px" />
        <div v-else class="o-empty" style="padding: 80px 0"><div class="icon">📊</div><div>暂无统计数据</div></div>
      </div>
      <div class="o-card">
        <div class="o-card__title">事件类别占比<span class="hint">点击扇区筛选日志</span></div>
        <ChartBase v-if="stats?.categories?.length" :option="pieChart" height="340px" @chart-click="onPieClick" />
        <div v-else class="o-empty" style="padding: 80px 0"><div class="icon">📊</div><div>暂无统计数据</div></div>
      </div>
    </div>

    <!-- 错误码 -->
    <div v-if="tab === 'codes'" class="grid-2">
      <div class="o-card">
        <div class="o-card__title">错误码 Top 10<span class="hint">点击柱条筛选日志</span></div>
        <ChartBase v-if="codeStats.length" :option="codeChart" height="340px" @chart-click="onCodeClick" />
        <div v-else class="o-empty" style="padding: 80px 0"><div class="icon">📊</div><div>暂无统计数据</div></div>
      </div>
      <div class="o-table-wrap has-vscroll">
        <table class="o-table">
          <thead><tr><th>错误码</th><th>类别</th><th>级别</th><th>次数</th><th>占比</th></tr></thead>
          <tbody>
            <tr v-for="c in codeStats" :key="c.name" style="cursor: pointer" @click="codeFilter = c.name; tab = 'raw'">
              <td class="o-mono"><b>{{ c.name }}</b></td>
              <td>{{ c.category }}</td>
              <td><span class="o-badge" :class="sevBadgeClass(c.severity as Severity)">{{ sevLabel(c.severity as Severity) }}</span></td>
              <td class="o-mono num">{{ c.value }}</td>
              <td class="o-mono num">{{ kpi.total ? ((c.value / kpi.total) * 100).toFixed(1) : '0' }}%</td>
            </tr>
            <tr v-if="!codeStats.length"><td colspan="5"><div class="o-empty" style="padding: 36px 0">📭 暂无错误码数据</div></td></tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- IP 聚合 -->
    <div v-if="tab === 'ips'">
      <div class="o-card" style="margin-bottom: 16px">
        <div class="o-card__title">源 IP 事件量 Top 10<span class="hint">点击柱条或表格行筛选日志</span></div>
        <ChartBase v-if="ipStats.length" :option="ipChart" height="320px" @chart-click="onIpClick" />
        <div v-else class="o-empty" style="padding: 60px 0"><div class="icon">📊</div><div>暂无统计数据</div></div>
      </div>
      <div class="o-table-wrap has-vscroll">
        <table class="o-table">
          <thead><tr><th>源 IP</th><th>事件总量</th><th>致命</th><th>错误</th><th>告警</th><th>信息</th><th>高频错误码</th><th></th></tr></thead>
          <tbody>
            <tr v-for="s in ipStats" :key="s.ip" style="cursor: pointer" @click="ipFilter = s.ip; tab = 'raw'">
              <td class="o-mono"><b>{{ s.ip }}</b></td>
              <td class="o-mono num">{{ s.total }}</td>
              <td class="o-mono num" style="color: var(--danger)">{{ s.critical }}</td>
              <td class="o-mono num" style="color: var(--warning)">{{ s.error }}</td>
              <td class="o-mono num">{{ s.warning }}</td>
              <td class="o-mono num o-text-3">{{ s.info }}</td>
              <td class="o-mono">{{ s.topCode }} × {{ s.topCodeCount }}</td>
              <td><span class="o-btn o-btn--sm">筛选日志</span></td>
            </tr>
            <tr v-if="!ipStats.length"><td colspan="8"><div class="o-empty" style="padding: 36px 0">📭 暂无 IP 数据</div></td></tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- 原始日志 -->
    <div v-if="tab === 'raw'">
      <!-- 筛选条 -->
      <div class="raw-toolbar o-card">
        <div class="row-1">
          <div class="o-chips">
            <button
              v-for="c in sevChips"
              :key="c.key"
              class="o-chips__item"
              :class="{ 'is-active': sevFilter === c.key }"
              @click="sevFilter = c.key as any"
            >
              {{ c.label }} <span class="cnt">{{ c.count }}</span>
            </button>
          </div>
          <div class="o-grow" />
          <select v-model="ipFilter" class="o-select" style="width: 160px">
            <option value="">全部 IP</option>
            <option v-for="s in ipStats" :key="s.ip" :value="s.ip">{{ s.ip }}（{{ s.total }}）</option>
          </select>
          <select v-model="codeFilter" class="o-select" style="width: 150px">
            <option value="">全部错误码</option>
            <option v-for="c in codeStats" :key="c.name" :value="c.name">{{ c.name }}（{{ c.value }}）</option>
          </select>
          <select v-model="catFilter" class="o-select" style="width: 130px">
            <option value="">全部类别</option>
            <option v-for="c in stats?.categories ?? []" :key="c.name" :value="c.name">{{ c.name }}（{{ c.value }}）</option>
          </select>
        </div>
        <div class="row-2">
          <input v-model="kwFilter" class="o-input" style="width: 320px" placeholder="🔍 搜索原始日志 / 解析字段..." />
          <span v-if="hasAnyFilter" class="o-btn o-btn--sm o-btn--text" style="color: var(--danger)" @click="clearAll">清空全部筛选</span>
          <div class="o-grow" />
          <span class="o-mono o-text-3">
            {{ logsLoading ? '加载中…' : `${logsTotal} 条 · 第 ${page}/${totalPages} 页` }}
          </span>
          <select v-model.number="pageSize" class="o-select" style="width: 90px">
            <option :value="20">20 条/页</option>
            <option :value="50">50 条/页</option>
            <option :value="100">100 条/页</option>
          </select>
        </div>
      </div>

      <!-- 表格（竖向滚动 + sticky 表头） -->
      <div class="o-table-wrap has-vscroll">
        <table class="o-table">
          <thead><tr><th style="width: 165px">时间</th><th>源 IP</th><th>级别</th><th>类别</th><th>错误码</th><th>解析字段</th></tr></thead>
          <tbody>
            <tr v-if="!logs.length && !logsLoading">
              <td colspan="6"><div class="o-empty" style="padding: 36px 0">📭 当前筛选条件下无匹配日志</div></td>
            </tr>
            <tr v-for="e in logs" :key="e.id">
              <td class="o-mono o-text-3">{{ fmtTime(e.ts) }}</td>
              <td class="o-mono">{{ e.sourceIp }}</td>
              <td><span class="o-badge" :class="sevBadgeClass(e.severity)">{{ sevLabel(e.severity) }}</span></td>
              <td>{{ e.category }}</td>
              <td class="o-mono">{{ e.errorCode }}</td>
              <td class="o-mono o-text-3 fields" :title="e.raw">{{ fieldsSummary(e) || e.raw.slice(0, 80) }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="o-pagination" v-if="totalPages > 1">
        <button :disabled="page <= 1" @click="page--">‹</button>
        <button
          v-for="p in (totalPages <= 7 ? totalPages : (page <= 4 ? [1,2,3,4,5,-1,totalPages] : page >= totalPages - 3 ? [1,-1,totalPages-4,totalPages-3,totalPages-2,totalPages-1,totalPages] : [1,-1,page-1,page,page+1,-1,totalPages]))"
          :key="p + '-' + Math.random()"
          :class="{ active: page === p, ellipsis: p === -1 }"
          :disabled="p === -1"
          @click="p !== -1 && (page = p)"
        >
          {{ p === -1 ? '…' : p }}
        </button>
        <button :disabled="page >= totalPages" @click="page++">›</button>
      </div>
    </div>

    <!-- LLM 分析 -->
    <div v-if="tab === 'llm'">
      <div v-if="!canLlm" class="o-empty o-card">当前团队角色无「使用 LLM 分析」权限（task:llm）</div>
      <div v-else-if="running" class="o-empty o-card">任务解析完成后才能生成 AI 分析报告</div>
      <div v-else class="o-card llm">
        <div class="llm-head">
          <span class="o-badge o-badge--primary">✦ LLM 智能诊断</span>
          <span class="o-mono o-text-3">基于 {{ kpi.total }} 条事件聚合特征 · 后端规则报告 + LLM 增强</span>
          <div class="o-grow" />
          <button v-if="!llmStarted" class="o-btn o-btn--primary" @click="startLlm">▶ 开始分析</button>
          <button v-else class="o-btn" :disabled="llmStreaming" @click="startLlm">{{ llmStreaming ? `生成中 ${llmProgress}%` : '↻ 重新分析' }}</button>
        </div>
        <div v-if="llmErr" class="o-badge o-badge--danger" style="margin-bottom: 12px">⚠ {{ llmErr }}</div>
        <div v-if="!llmStarted" class="o-empty">
          <div class="icon">🤖</div>
          <div>点击「开始分析」，AI 将输出诊断报告</div>
          <div class="hint">总体概况 → 异常聚类 → 根因推断 → 处置建议 → 置信度（未配置 LLM 时输出规则引擎报告）</div>
        </div>
        <div v-else ref="llmBody" class="llm-body scrollbar">
          <div v-for="(l, i) in llmLines" :key="i" :class="l.kind">
            {{ l.text }}<span v-if="i === llmLines.length - 1 && llmStreaming" class="cursor" />
          </div>
          <div v-if="llmStreaming && !llmLines.length" class="o-mono o-text-3">报告生成中… {{ llmProgress }}%</div>
        </div>
      </div>
    </div>
  </template>
  <div v-else class="o-empty o-card">任务加载中…</div>
</template>

<style scoped>
.grid-2 {
  display: grid;
  grid-template-columns: 3fr 2fr;
  gap: 16px;
}
@media (max-width: 1080px) {
  .grid-2 { grid-template-columns: 1fr; }
}
.banner-left .back-btn {
  display: inline-block;
  font-size: 13px;
  color: var(--primary);
  background: var(--primary-soft);
  border-radius: var(--radius);
  padding: 2px 10px;
  margin-bottom: 8px;
}
.banner-left .back-btn:hover {
  background: var(--primary-tint);
}
.banner-left h2 {
  font-size: 19px;
  font-weight: 700;
  display: flex;
  align-items: center;
  gap: 10px;
}
.banner-left .meta {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 6px;
  font-size: 12.5px;
  flex-wrap: wrap;
}
.raw-toolbar {
  padding: 14px 16px;
  margin-bottom: 12px;
}
.raw-toolbar .row-1,
.raw-toolbar .row-2 {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.raw-toolbar .row-2 {
  margin-top: 10px;
}
.fields {
  max-width: 420px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.llm-head {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}
.llm-body {
  font-size: 13.5px;
  line-height: 1.9;
  max-height: 520px;
  overflow: auto;
  background: #fbfcfe;
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: 20px 24px;
}
.llm-body .title {
  font-weight: 600;
  color: var(--primary);
  margin-top: 16px;
  font-size: 14px;
}
.llm-body .title:first-child {
  margin-top: 0;
}
.llm-body .line {
  color: var(--text-2);
  padding-left: 12px;
  border-left: 2px solid var(--primary-tint);
  margin-top: 4px;
}
.cursor {
  display: inline-block;
  width: 7px;
  height: 15px;
  background: var(--primary);
  margin-left: 3px;
  vertical-align: -2px;
  animation: blink 0.9s step-end infinite;
}
@keyframes blink {
  50% { opacity: 0; }
}
.o-pagination button.ellipsis {
  border: none;
  background: transparent;
  cursor: default;
}
.spin {
  width: 14px;
  height: 14px;
  border: 2px solid rgba(30, 111, 255, 0.2);
  border-top-color: #1e6fff;
  border-radius: 50%;
  animation: rot 0.8s linear infinite;
  display: inline-block;
  flex: none;
}
@keyframes rot {
  to { transform: rotate(360deg); }
}
</style>
