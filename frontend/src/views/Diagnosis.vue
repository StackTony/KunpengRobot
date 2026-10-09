<template>
  <el-row :gutter="16">
    <!-- 上传与任务列表 -->
    <el-col :span="12">
      <el-card shadow="never">
        <template #header>日志包上传与诊断</template>
        <el-upload drag :auto-upload="true" :show-file-list="false" :http-request="doUpload"
                   accept=".zip,.tar,.gz,.tgz,.log,.txt">
          <div class="upload-area">
            <el-icon :size="30" color="#2f5cac"><UploadFilled /></el-icon>
            <div class="upload-title">拖拽日志包到此处，或点击选择文件</div>
            <div class="upload-hint">支持 zip / tar.gz / 单个日志文件，最大 2GB</div>
          </div>
        </el-upload>

        <el-table :data="tasks" style="margin-top: 16px" size="small">
          <el-table-column prop="filename" label="文件" min-width="140" show-overflow-tooltip />
          <el-table-column prop="status" label="状态" width="84">
            <template #default="{ row }">
              <el-tag :type="statusType(row.status)" size="small" effect="light">{{ statusText(row.status) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="progress" label="进度" width="110">
            <template #default="{ row }">
              <el-progress :percentage="row.progress" :stroke-width="6" :show-text="false"
                           :color="progressColor(row.status)" />
            </template>
          </el-table-column>
          <el-table-column label="操作" width="64">
            <template #default="{ row }">
              <el-button link type="primary" size="small" @click="watch(row.id)">查看</el-button>
            </template>
          </el-table-column>
          <template #empty>
            <el-empty description="暂无诊断任务" :image-size="56" />
          </template>
        </el-table>
      </el-card>
    </el-col>

    <!-- 实时分析输出 (SSE) -->
    <el-col :span="12">
      <el-card shadow="never">
        <template #header>
          <div class="output-header">
            <span>实时分析输出</span>
            <span class="output-actions">
              <el-tag v-if="currentTask" size="small" type="info" effect="plain" class="task-tag">
                {{ currentTask.slice(0, 8) }}
              </el-tag>
              <el-button v-if="output.length" link size="small" @click="output = []">清屏</el-button>
            </span>
          </div>
        </template>
        <div ref="outputRef" class="analysis-output">
          <div v-if="!output.length" class="output-placeholder">
            <el-icon :size="26" color="#4a5265"><Monitor /></el-icon>
            <p>上传日志包后，分析进度与结论将在此实时输出</p>
          </div>
          <div v-for="(line, i) in output" :key="i" :class="line.cls">{{ line.text }}</div>
        </div>
      </el-card>
    </el-col>
  </el-row>
</template>

<script setup>
import { nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import http from '../api/http'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const tasks = ref([])
const output = ref([])
const currentTask = ref('')
const outputRef = ref()
let es = null

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

async function loadTasks() {
  const { data } = await http.get('/tasks?limit=50')
  tasks.value = data.filter((t) => t.type === 'diagnosis')
}

async function doUpload({ file }) {
  const fd = new FormData()
  fd.append('file', file)
  const { data } = await http.post('/tasks/upload', fd, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  ElMessage.success('已入队，开始分析')
  await loadTasks()
  watch(data.task_id)
}

function watch(taskId) {
  currentTask.value = taskId
  output.value = []
  es?.close()
  // SSE: 历史补发 + 实时续流
  es = new EventSource(`/api/tasks/${taskId}/events?token=${auth.token}`)
  const push = (text, cls = '') => {
    output.value.push({ text, cls })
    nextTick(() => outputRef.value?.scrollTo({ top: 1e9 }))
  }
  es.addEventListener('progress', (e) => {
    const d = JSON.parse(e.data)
    push(`[${d.data.percent}%] ${d.data.message}`, 'step')
  })
  es.addEventListener('finding', (e) => {
    const d = JSON.parse(e.data).data
    push(`⚠ 命中: [${d.severity}] ${d.rule_name} ${d.text || ''}`, 'finding')
  })
  es.addEventListener('llm_token', (e) => {
    const d = JSON.parse(e.data)
    // 打字机效果: 追加到最后一段
    const last = output.value[output.value.length - 1]
    if (last && last.cls === 'llm') last.text += d.data.text
    else output.value.push({ text: d.data.text, cls: 'llm' })
    nextTick(() => outputRef.value?.scrollTo({ top: 1e9 }))
  })
  es.addEventListener('done', () => {
    push('—— 分析完成 ——', 'done')
    es?.close()
    loadTasks()
  })
  es.addEventListener('error', () => es?.close())
}

onMounted(loadTasks)
onBeforeUnmount(() => es?.close())
</script>

<style scoped>
.upload-area { padding: 22px 0; }
.upload-title { margin-top: 8px; font-size: 13px; color: var(--kp-text-primary); }
.upload-hint { margin-top: 4px; font-size: 12px; color: #a8abb2; }
.output-header { display: flex; align-items: center; justify-content: space-between; }
.output-actions { display: flex; align-items: center; gap: 8px; }
.task-tag { font-family: Consolas, monospace; }

.analysis-output {
  height: 480px;
  overflow-y: auto;
  background: #1b2030;
  color: #d4d7e0;
  font-family: Consolas, 'Cascadia Mono', monospace;
  font-size: 12px;
  line-height: 1.7;
  padding: 14px 16px;
  border-radius: 6px;
}

.output-placeholder {
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  color: #4a5265;
  font-size: 12px;
}

.step { color: #7ba3e0; }
.finding { color: #e0a878; }
.llm { color: #6fcbb4; white-space: pre-wrap; }
.done { color: #7fc98a; font-weight: bold; margin-top: 6px; }
</style>
