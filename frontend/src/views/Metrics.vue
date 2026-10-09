<template>
  <div class="kp-page">
    <el-card shadow="never">
      <template #header>
        <div class="toolbar">
          <span>性能趋势</span>
          <div class="toolbar-filters">
            <el-select v-model="host" placeholder="主机" style="width: 180px" clearable filterable @change="load">
              <el-option v-for="h in hosts" :key="h" :label="h" :value="h" />
            </el-select>
            <el-select v-model="metric" placeholder="指标" style="width: 200px" filterable @change="load">
              <el-option v-for="m in metricNames" :key="m" :label="m" :value="m" />
            </el-select>
            <el-date-picker v-model="range" type="datetimerange" range-separator="至"
                            start-placeholder="开始" end-placeholder="结束" @change="load" />
            <el-button size="small" @click="saveLayout">
              <el-icon style="margin-right: 4px"><Collection /></el-icon>保存布局
            </el-button>
          </div>
        </div>
      </template>

      <div v-if="!host" class="empty-chart">
        <el-empty description="暂无指标数据 — 上传日志包并完成分析后，性能指标将出现在此处" :image-size="88" />
      </div>
      <v-chart v-else :option="chartOption" style="height: 440px; width: 100%" autoresize />
    </el-card>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { LineChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent } from 'echarts/components'
import VChart from 'vue-echarts'
import http from '../api/http'

use([CanvasRenderer, LineChart, GridComponent, TooltipComponent, LegendComponent])

const hosts = ref([])
const metricNames = ref([])
const host = ref('')
const metric = ref('')
const range = ref([])
const points = ref([])

// 视图配置持久化: 从服务端恢复 (刷新/切页签/换设备不丢)
async function restoreLayout() {
  try {
    const { data } = await http.get('/preferences/dashboard.charts')
    if (data.pref_value?.host) host.value = data.pref_value.host
    if (data.pref_value?.metric) metric.value = data.pref_value.metric
  } catch { /* ignore */ }
}

async function saveLayout() {
  await http.put('/preferences/dashboard.charts', {
    pref_key: 'dashboard.charts',
    pref_value: { host: host.value, metric: metric.value },
  })
  ElMessage.success('图表布局已保存，刷新页面后将自动恢复')
}

async function load() {
  if (!host.value || !metric.value || range.value?.length !== 2) return
  const { data } = await http.post('/metrics/query', {
    host: host.value,
    metric_name: metric.value,
    start: range.value[0],
    end: range.value[1],
    interval_seconds: 60,
  })
  points.value = data.points
}

const chartOption = computed(() => ({
  tooltip: { trigger: 'axis' },
  grid: { left: 48, right: 24, top: 32, bottom: 36 },
  xAxis: { type: 'time', axisLine: { lineStyle: { color: '#dcdfe6' } } },
  yAxis: { type: 'value', splitLine: { lineStyle: { color: '#f0f2f6' } } },
  series: [{
    type: 'line', name: metric.value, showSymbol: false, smooth: true,
    lineStyle: { width: 2, color: '#2f5cac' },
    areaStyle: { color: 'rgba(47, 92, 172, 0.08)' },
    data: points.value,
  }],
}))

onMounted(async () => {
  const [{ data: h }, { data: n }] = await Promise.all([
    http.get('/metrics/hosts'),
    http.get('/metrics/names'),
  ])
  hosts.value = h.hosts
  metricNames.value = n.metric_names?.length ? n.metric_names : ['cpu.usage', 'mem.used_pct']
  if (hosts.value.length && !host.value) host.value = hosts.value[0]
  if (metricNames.value.length && !metric.value) metric.value = metricNames.value[0]
  const now = new Date()
  range.value = [new Date(now - 7 * 86400e3), now]
  await restoreLayout()
  await load()
})
</script>

<style scoped>
.toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.toolbar-filters {
  display: flex;
  align-items: center;
  gap: 10px;
  font-weight: 400;
}
.empty-chart { padding: 40px 0; }
</style>
