<template>
  <div class="kp-page">
    <!-- 统计卡片 -->
    <el-row :gutter="16">
      <el-col :span="6" v-for="stat in stats" :key="stat.label">
        <el-card shadow="never">
          <div class="kp-stat">
            <div class="kp-stat-icon" :style="{ background: stat.bg, color: stat.color }">
              <el-icon><component :is="stat.icon" /></el-icon>
            </div>
            <div>
              <div class="kp-stat-value">{{ stat.value }}</div>
              <div class="kp-stat-label">{{ stat.label }}</div>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 最近任务 -->
    <el-card shadow="never">
      <template #header>最近任务</template>
      <el-table :data="tasks" size="default" v-loading="loading">
        <el-table-column prop="filename" label="文件" min-width="220" show-overflow-tooltip>
          <template #default="{ row }">
            <el-icon style="vertical-align: -2px; margin-right: 6px; color: #909399"><Document /></el-icon>
            {{ row.filename || row.id }}
          </template>
        </el-table-column>
        <el-table-column prop="type" label="类型" width="90">
          <template #default="{ row }">
            <el-tag size="small" effect="plain" :type="row.type === 'diagnosis' ? 'primary' : 'success'">
              {{ row.type === 'diagnosis' ? '诊断' : '巡检' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="100">
          <template #default="{ row }">
            <el-tag size="small" :type="statusType(row.status)" effect="light">{{ statusText(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="进度" width="160">
          <template #default="{ row }">
            <el-progress :percentage="row.progress" :stroke-width="6"
                         :show-text="false" :color="progressColor(row.status)" />
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="创建时间" width="170">
          <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="80">
          <template #default="{ row }">
            <el-button link type="primary" size="small"
                       @click="$router.push(row.type === 'diagnosis' ? '/diagnosis' : '/inspection')">
              查看
            </el-button>
          </template>
        </el-table-column>
        <template #empty>
          <el-empty description="暂无任务，前往故障诊断上传日志包" :image-size="72" />
        </template>
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import http from '../api/http'

const tasks = ref([])
const loading = ref(false)

const stats = computed(() => [
  { label: '任务总数', value: tasks.value.length, icon: 'Files', bg: '#e6edf7', color: '#2f5cac' },
  { label: '进行中', value: running.value, icon: 'Loading', bg: '#fdf3e4', color: '#b88230' },
  { label: '已完成', value: done.value, icon: 'CircleCheck', bg: '#e9f5ec', color: '#4b9e65' },
  { label: '异常', value: failed.value, icon: 'WarningFilled', bg: '#fdf0ef', color: '#c3272b' },
])

const running = computed(() => tasks.value.filter((t) => ['running', 'pending'].includes(t.status)).length)
const done = computed(() => tasks.value.filter((t) => t.status === 'done').length)
const failed = computed(() => tasks.value.filter((t) => ['failed', 'interrupted'].includes(t.status)).length)

const STATUS = {
  pending: { text: '排队中', type: 'info' },
  running: { text: '分析中', type: 'warning' },
  done: { text: '已完成', type: 'success' },
  failed: { text: '失败', type: 'danger' },
  cancelled: { text: '已取消', type: 'info' },
  interrupted: { text: '已中断', type: 'danger' },
}
const statusText = (s) => STATUS[s]?.text || s
const statusType = (s) => STATUS[s]?.type || 'info'
const progressColor = (s) => ({ done: '#4b9e65', failed: '#c3272b', interrupted: '#c3272b' }[s] || '#2f5cac')

function formatTime(t) {
  if (!t) return ''
  return new Date(t).toLocaleString('zh-CN', { hour12: false })
}

onMounted(async () => {
  loading.value = true
  try {
    const { data } = await http.get('/tasks?limit=100')
    tasks.value = data
  } catch { /* ignore */ } finally {
    loading.value = false
  }
})
</script>
