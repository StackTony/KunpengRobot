<template>
  <div class="kp-page">
    <el-card shadow="never">
      <template #header>巡检任务</template>
      <el-table :data="tasks" size="default" v-loading="loading">
        <el-table-column prop="id" label="任务 ID" min-width="260" show-overflow-tooltip>
          <template #default="{ row }">
            <span class="mono">{{ row.id }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="100">
          <template #default="{ row }">
            <el-tag size="small" :type="statusType(row.status)" effect="light">{{ statusText(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="进度" width="180">
          <template #default="{ row }">
            <el-progress :percentage="row.progress" :stroke-width="6" :show-text="false"
                         :color="progressColor(row.status)" />
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="创建时间" width="170">
          <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
        </el-table-column>
        <template #empty>
          <el-empty description="暂无巡检任务" :image-size="72" />
        </template>
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import http from '../api/http'

const tasks = ref([])
const loading = ref(false)

const STATUS = {
  pending: { text: '排队中', type: 'info' },
  running: { text: '巡检中', type: 'warning' },
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
    const { data } = await http.get('/tasks?limit=50')
    tasks.value = data.filter((t) => t.type === 'inspection')
  } catch { /* ignore */ } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.mono { font-family: Consolas, monospace; font-size: 12px; color: var(--kp-text-secondary); }
</style>
