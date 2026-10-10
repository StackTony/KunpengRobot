<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { get } from '@/api/http'
import { useRbacStore } from '@/stores/rbac'
import { PARSER_DEFS } from '@/parser/parsers'
import { fmtTime } from '@/parser/types'
import type { AnalyzeTask } from '@/stores/assets'
import type { EChartsOption } from 'echarts'
import ChartBase from '@/components/ChartBase.vue'

const route = useRoute()
const rbac = useRbacStore()

const denied = computed(() => (route.query.denied as string) || '')

interface DashboardData {
  teams: number
  assets: number
  tasks: number
  kpi: { total: number; critical: number; error: number; warning: number }
  recentTasks: AnalyzeTask[]
  topCodes: { name: string; value: number }[]
}

const data = ref<DashboardData | null>(null)
const loadErr = ref('')
const loading = ref(false)

async function load() {
  loading.value = true
  loadErr.value = ''
  try {
    data.value = await get<DashboardData>('/dashboard')
  } catch (e: any) {
    loadErr.value = e?.response?.data?.detail || '加载工作台数据失败'
  } finally {
    loading.value = false
  }
}
onMounted(load)

const codeChart = computed<EChartsOption>(() => {
  const top = data.value?.topCodes ?? []
  return {
    grid: { left: 70, right: 30, top: 16, bottom: 28 },
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'value' },
    yAxis: { type: 'category', data: top.map((t) => t.name).reverse(), axisLabel: { fontFamily: 'Menlo, Consolas, monospace' } },
    series: [
      {
        type: 'bar',
        data: top.map((t) => t.value).reverse(),
        itemStyle: { color: '#1e6fff' },
        barMaxWidth: 18,
        label: { show: true, position: 'right' },
      },
    ],
  }
})

function parserName(type: string) {
  return PARSER_DEFS[type]?.name ?? type
}
</script>

<template>
  <div class="o-badge o-badge--danger" v-if="denied" style="margin-bottom: 16px">
    无权访问「{{ denied }}」—— 当前角色未授予该菜单权限
  </div>

  <div class="o-page-head">
    <div>
      <h2>工作台</h2>
      <div class="sub">欢迎，{{ rbac.currentUser?.name }} —— 以下是我的团队范围内解析任务的汇总视图</div>
    </div>
    <button class="o-btn o-btn--sm" :disabled="loading" @click="load">{{ loading ? '刷新中…' : '↻ 刷新' }}</button>
  </div>

  <div v-if="loadErr" class="o-empty o-card">
    <div class="icon">⚠️</div>
    <div>{{ loadErr }}</div>
  </div>

  <template v-else-if="data">
    <div class="o-kpis" style="margin-bottom: 20px">
      <div class="o-kpi"><b>{{ data.teams }}</b><span>团队</span></div>
      <div class="o-kpi"><b>{{ data.assets }}</b><span>资产库</span></div>
      <div class="o-kpi"><b>{{ data.tasks }}</b><span>解析任务</span></div>
      <div class="o-kpi"><b>{{ data.kpi.total }}</b><span>日志事件总量</span></div>
      <div class="o-kpi"><b style="color: var(--danger)">{{ data.kpi.critical }}</b><span>致命事件</span></div>
      <div class="o-kpi"><b style="color: var(--warning)">{{ data.kpi.error }}</b><span>错误事件</span></div>
    </div>

    <div class="grid">
      <div class="o-card">
        <div class="o-card__title">全局错误码 Top 8<span class="o-mono o-text-3">我的团队合并</span></div>
        <ChartBase v-if="data.topCodes.length" :option="codeChart" height="320px" />
        <div v-else class="o-empty" style="padding: 60px 0">
          <div class="icon">📭</div>
          <div>暂无事件数据，请先执行解析任务</div>
        </div>
      </div>

      <div class="o-card">
        <div class="o-card__title">近期解析任务</div>
        <table class="o-table">
          <thead>
            <tr><th>任务</th><th>类型</th><th>事件数</th><th>时间</th><th></th></tr>
          </thead>
          <tbody>
            <tr v-if="!data.recentTasks.length">
              <td colspan="5"><div class="o-empty" style="padding: 36px 0">📭 暂无解析任务</div></td>
            </tr>
            <tr v-for="t in data.recentTasks" :key="t.id">
              <td>
                <router-link :to="`/tasks/${t.id}`">{{ t.name || t.filename }}</router-link>
                <div class="o-mono o-text-3">{{ t.assetName || '—' }} · {{ t.creatorName }}</div>
              </td>
              <td><span class="o-badge o-badge--outline">{{ parserName(t.parserType) }}</span></td>
              <td class="o-mono">{{ t.eventCount }}</td>
              <td class="o-mono o-text-3">{{ fmtTime(t.createdAt) }}</td>
              <td><router-link class="o-btn o-btn--text" :to="`/tasks/${t.id}`">查看结果</router-link></td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </template>
</template>

<style scoped>
.grid {
  display: grid;
  grid-template-columns: 5fr 7fr;
  gap: 16px;
}
@media (max-width: 1080px) {
  .grid { grid-template-columns: 1fr; }
}
</style>
