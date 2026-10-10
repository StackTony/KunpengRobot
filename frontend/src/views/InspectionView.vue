<script setup lang="ts">
/* 智能巡检: 上传日志包发起巡检 (规则引擎优先 + LLM 总结) + 任务列表实时进度 */
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { get, post, apiError } from '@/api/http'
import { fmtTime } from '@/parser/types'

interface InspectionTask {
  id: string
  status: 'pending' | 'running' | 'done' | 'failed' | 'cancelled' | 'interrupted'
  filename: string
  name?: string
  progress: number
  error?: string
  createdAt: string
  finishedAt?: string
  logSize: number
  eventCount: number
  creatorName: string
}

const STATUS_BADGE: Record<InspectionTask['status'], { label: string; cls: string }> = {
  pending: { label: '排队中', cls: 'o-badge--grey' },
  running: { label: '巡检中', cls: 'o-badge--warning' },
  done: { label: '已完成', cls: 'o-badge--success' },
  failed: { label: '失败', cls: 'o-badge--danger' },
  cancelled: { label: '已取消', cls: 'o-badge--grey' },
  interrupted: { label: '已中断', cls: 'o-badge--danger' },
}

const tasks = ref<InspectionTask[]>([])
const loading = ref(false)
const loadErr = ref('')
const uploadTip = ref('')
const uploading = ref(false)
const fileInput = ref<HTMLInputElement>()
let pollTimer: number | undefined

const hasActive = computed(() =>
  tasks.value.some((t) => t.status === 'pending' || t.status === 'running'),
)

async function load(silent = false) {
  if (!silent) loading.value = true
  try {
    const data = await get<InspectionTask[]>('/tasks', { type: 'inspection', limit: 50 })
    tasks.value = data
    loadErr.value = ''
  } catch (e) {
    loadErr.value = apiError(e)
  } finally {
    loading.value = false
  }
  schedulePoll()
}

/* 有排队/运行中任务时每 2s 轮询刷新进度 */
function schedulePoll() {
  if (pollTimer) {
    clearTimeout(pollTimer)
    pollTimer = undefined
  }
  if (hasActive.value) {
    pollTimer = setTimeout(() => load(true), 2000)
  }
}

function pickFile() {
  fileInput.value?.click()
}

async function onFileChosen(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  uploading.value = true
  uploadTip.value = ''
  try {
    const fd = new FormData()
    fd.append('file', file)
    fd.append('task_type', 'inspection')
    fd.append('task_name', file.name.replace(/\.[^.]+$/, ''))
    const data = await post<{ taskId: string; status: string }>('/tasks/upload', fd)
    uploadTip.value = `巡检任务已创建（${data.taskId.slice(0, 8)}…），正在排队执行`
    await load(true)
  } catch (e) {
    uploadTip.value = ''
    loadErr.value = apiError(e)
  } finally {
    uploading.value = false
  }
}

onMounted(() => load())
onBeforeUnmount(() => {
  if (pollTimer) clearTimeout(pollTimer)
})
</script>

<template>
  <div class="o-operate-bar">
    <div class="o-operate-left">
      <h2>智能巡检</h2>
      <span class="o-mono o-text-3">规则引擎优先匹配，LLM 智能化总结（未配置时降级纯规则）</span>
    </div>
    <div class="o-operate-right">
      <input ref="fileInput" type="file" accept=".zip,.tar,.gz,.tgz,.log,.txt,.json,.jsonl" hidden @change="onFileChosen" />
      <button class="o-btn o-btn--primary" :disabled="uploading" @click="pickFile">
        {{ uploading ? '上传中…' : '上传日志包发起巡检' }}
      </button>
    </div>
  </div>

  <div v-if="uploadTip" class="o-mono" style="color: var(--primary); margin-bottom: 12px">✓ {{ uploadTip }}</div>
  <div v-if="loadErr" class="o-mono" style="color: var(--danger); margin-bottom: 12px">⚠ {{ loadErr }}</div>

  <div class="o-card">
    <div class="o-card__title">
      巡检任务
      <span class="o-mono o-text-3">{{ tasks.length }} 条 · 仅显示自己发起的巡检（管理员可见全部）</span>
    </div>
    <div class="o-table-wrap">
      <table class="o-table">
        <thead>
          <tr>
            <th>任务</th><th>状态</th><th style="width: 200px">进度</th><th>日志大小</th><th>事件数</th><th>创建时间</th><th>完成时间</th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="!tasks.length && !loading">
            <td colspan="7">
              <div class="o-empty" style="padding: 48px 0">
                <div class="icon">🔍</div>
                <div>暂无巡检任务 — 上传日志包发起第一次巡检</div>
              </div>
            </td>
          </tr>
          <tr v-for="t in tasks" :key="t.id">
            <td>
              <b>{{ t.name || t.filename }}</b>
              <div class="o-mono o-text-3">{{ t.id }}</div>
            </td>
            <td>
              <span class="o-badge" :class="STATUS_BADGE[t.status].cls">{{ STATUS_BADGE[t.status].label }}</span>
              <div v-if="t.error" class="o-mono err">{{ t.error }}</div>
            </td>
            <td>
              <div class="progress">
                <div
                  class="progress-bar"
                  :class="{ bad: t.status === 'failed' || t.status === 'interrupted' }"
                  :style="{ width: (t.status === 'done' ? 100 : t.progress) + '%' }"
                ></div>
              </div>
              <span class="o-mono o-text-3">{{ t.status === 'done' ? 100 : t.progress }}%</span>
            </td>
            <td class="o-mono">{{ t.logSize ? (t.logSize / 1024).toFixed(1) + ' KB' : '—' }}</td>
            <td class="o-mono">{{ t.eventCount || '—' }}</td>
            <td class="o-mono o-text-3">{{ fmtTime(t.createdAt) }}</td>
            <td class="o-mono o-text-3">{{ t.finishedAt ? fmtTime(t.finishedAt) : '—' }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<style scoped>
.err {
  color: var(--danger);
  font-size: 11.5px;
  max-width: 160px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.progress {
  display: inline-block;
  width: 120px;
  height: 6px;
  border-radius: 3px;
  background: var(--border);
  overflow: hidden;
  vertical-align: middle;
  margin-right: 8px;
}
.progress-bar {
  height: 100%;
  border-radius: 3px;
  background: var(--primary);
  transition: width 0.4s ease;
}
.progress-bar.bad {
  background: var(--danger);
}
</style>
