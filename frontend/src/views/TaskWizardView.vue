<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useTeamsStore } from '@/stores/teams'
import { useAssetsStore } from '@/stores/assets'
import { useRbacStore } from '@/stores/rbac'
import { PARSER_DEFS, parserList } from '@/parser/parsers'
import { genAppLog, genDmesg, genRedfish, genSel, genSyslog, genWindows } from '@/parser/mock-logs'
import http, { post, apiError } from '@/api/http'

const route = useRoute()
const rr = useRouter()
const teamsStore = useTeamsStore()
const assetsStore = useAssetsStore()
const rbac = useRbacStore()

const teamId = computed(() => route.params.id as string)
const team = computed(() => teamsStore.teamById(teamId.value))
const asset = computed(() => assetsStore.assetById(route.query.assetId as string))
const myRole = computed(() => teamsStore.myRoleOf(teamId.value))
const canView = computed(() => teamsStore.can(teamId.value, 'task:view'))
const canExecute = computed(() => teamsStore.can(teamId.value, 'task:execute'))

onMounted(() => {
  teamsStore.fetchTeam(teamId.value).then(() =>
    assetsStore.fetchTeamAssets(teamId.value)).catch(() => {})
})

const step = ref(1)
const taskName = ref('')
const parserType = ref('')
const running = ref(false)
const err = ref('')

const GEN: Record<string, (o: { count: number; seed?: number }) => string> = {
  sel: genSel, redfish: genRedfish, syslog: genSyslog, dmesg: genDmesg, windows: genWindows, regex: genAppLog,
}

/* ---------- 日志源：上传 / 粘贴 双模式 ---------- */
const sourceMode = ref<'upload' | 'paste'>('upload')
const fileInput = ref<HTMLInputElement>()
const file = ref<File | null>(null)
const fileName = ref('')
const logText = ref('')
const fileSize = ref(0)

async function pickFile() {
  if (!parserType.value) {
    err.value = '请先在下方选择解析类型，再上传文件'
    return
  }
  err.value = ''
  fileInput.value?.click()
}

async function onFileChosen(e: Event) {
  const f = (e.target as HTMLInputElement).files?.[0]
  if (!f) return
  file.value = f
  fileName.value = f.name
  fileSize.value = f.size
  logText.value = ''
  await runPrecheck(await f.slice(0, 512 * 1024).text())
}

function clearFile() {
  file.value = null
  fileName.value = ''
  fileSize.value = 0
  logText.value = ''
  preCount.value = 0
  preSample.value = []
  if (fileInput.value) fileInput.value.value = ''
}

function useSampleLog() {
  if (!parserType.value) {
    err.value = '请先选择解析类型'
    return
  }
  const gen = GEN[parserType.value]
  sourceMode.value = 'paste'
  logText.value = gen({ count: 320, seed: Math.floor(Math.random() * 900) })
  fileName.value = 'sample_' + parserType.value + '.log'
  fileSize.value = logText.value.length
  runPrecheck(logText.value.slice(0, 512 * 1024))
}

function onPasteInput() {
  if (logText.value && !fileName.value) fileName.value = 'pasted_input.log'
  fileSize.value = logText.value.length
}
watch([parserType, sourceMode], () => {
  preCount.value = 0
  preSample.value = []
})

const lineCount = computed(() => (logText.value ? logText.value.split('\n').filter((l) => l.trim()).length : 0))

/* ---------- 后端预检 (不落盘) ---------- */
const preChecking = ref(false)
const preCount = ref(0)
const preSample = ref<string[]>([])

async function runPrecheck(text: string) {
  if (!parserType.value || !text.trim()) {
    preCount.value = 0
    preSample.value = []
    return
  }
  preChecking.value = true
  try {
    const data = await post<{ count: number; sample: string[] }>('/tasks/precheck', {
      parser_type: parserType.value,
      text,
    })
    preCount.value = data.count
    preSample.value = data.sample ?? []
  } catch (e) {
    err.value = apiError(e)
    preCount.value = 0
  } finally {
    preChecking.value = false
  }
}

const hasContent = computed(() => !!file.value || !!logText.value.trim())
const contentSizeKb = computed(() => (fileSize.value / 1024).toFixed(1))

function toStep2() {
  if (!taskName.value.trim()) { err.value = '请填写任务名称'; return }
  if (!parserType.value) { err.value = '请选择解析类型'; return }
  if (!hasContent.value) { err.value = '请上传日志文件或粘贴日志内容'; return }
  if (!preCount.value) { err.value = '预检未通过：当前日志无法被所选解析器解析出事件，请检查类型是否匹配'; return }
  err.value = ''
  step.value = 2
}

async function execute() {
  if (!asset.value || running.value) return
  running.value = true
  err.value = ''
  try {
    let taskId: string
    if (sourceMode.value === 'upload' && file.value) {
      const form = new FormData()
      form.append('file', file.value)
      form.append('task_type', 'analyze')
      form.append('parser_type', parserType.value)
      form.append('task_name', taskName.value.trim())
      form.append('asset_id', String(asset.value.id))
      const res = await http.post('/api/tasks/upload', form)
      taskId = res.data.taskId
    } else {
      const data = await post<{ taskId: string }>('/tasks/upload-text', {
        name: taskName.value.trim(),
        parser_type: parserType.value,
        asset_id: asset.value.id,
        text: logText.value,
        filename: fileName.value || 'pasted_input.log',
      })
      taskId = data.taskId
    }
    rr.push(`/tasks/${taskId}`)
  } catch (e) {
    err.value = apiError(e)
    running.value = false
  }
}
</script>

<template>
  <div v-if="!myRole || !canView" class="o-empty o-card">
    <div class="icon">🔒</div>
    <div>无权创建解析任务</div>
    <div class="hint">你不属于该团队成员，或团队角色无「创建解析任务」权限（task:view / task:create）</div>
  </div>
  <template v-else-if="asset">
    <div class="o-page-head">
      <div>
        <h2>创建解析任务</h2>
        <div class="sub">
          <router-link :to="`/teams/${teamId}?tab=tasks`">{{ team?.name ?? '' }}</router-link>
          · {{ asset.name }} · <span class="o-mono o-text-3">{{ asset.ipRange || '—' }}</span>
        </div>
      </div>
      <span class="o-badge o-badge--outline">三步完成：准备日志 → 确认执行 → 查看结果</span>
    </div>

    <!-- 隐藏的真实文件选择器 -->
    <input ref="fileInput" type="file" style="display: none" @change="onFileChosen" />

    <!-- 步骤条 -->
    <div class="steps">
      <div class="step" :class="{ active: step >= 1, done: step > 1 }"><i>✓</i>准备日志</div>
      <div class="bar" :class="{ done: step > 1 }" />
      <div class="step" :class="{ active: step >= 2, done: step > 2 }"><i>2</i>确认执行</div>
      <div class="bar" />
      <div class="step" :class="{ active: step >= 3 }"><i>3</i>查看结果</div>
    </div>

    <!-- ====== Step 1 ====== -->
    <div v-if="step === 1" class="o-card">
      <div class="o-form-item">
        <label class="o-form-item__label required">任务名称</label>
        <input v-model="taskName" class="o-input" placeholder="如：A 区风扇故障专项分析" style="max-width: 420px" />
      </div>

      <div class="o-form-item">
        <label class="o-form-item__label required">解析类型</label>
        <div class="types">
          <button
            v-for="t in parserList()"
            :key="t.type"
            class="type"
            :class="{ selected: parserType === t.type }"
            @click="parserType = t.type"
          >
            <span class="check">✓</span>
            <b>{{ t.name }}</b>
            <span class="d">{{ t.desc }}</span>
            <span class="o-mono hint">{{ t.fileHint }}</span>
          </button>
        </div>
      </div>

      <div class="o-form-item">
        <label class="o-form-item__label required">日志内容</label>
        <div class="o-tabs" style="margin-bottom: 12px; width: fit-content">
          <button class="o-tabs__item" :class="{ 'is-active': sourceMode === 'upload' }" @click="sourceMode = 'upload'">上传文件</button>
          <button class="o-tabs__item" :class="{ 'is-active': sourceMode === 'paste' }" @click="sourceMode = 'paste'">粘贴文本</button>
        </div>

        <!-- 上传模式 -->
        <template v-if="sourceMode === 'upload'">
          <div class="o-upload" @click="pickFile">
            <div class="icon">📂</div>
            <div class="t">点击选择日志文件</div>
            <div class="s">支持 {{ parserType ? PARSER_DEFS[parserType].fileHint : 'sel_elist.txt / *.json / *.log 等导出文件' }} · 单文件 ≤ 200MB</div>
          </div>
          <div v-if="fileName" class="o-file-bar">
            <span style="font-size: 18px">📄</span>
            <div class="o-grow" style="min-width: 0">
              <div class="name" :title="fileName">{{ fileName }}</div>
              <div class="o-mono o-text-3">{{ contentSizeKb }} KB</div>
            </div>
            <button class="o-btn o-btn--sm" @click.stop="clearFile">移除</button>
          </div>
          <div class="o-row" style="margin-top: 10px">
            <button v-if="parserType" class="o-btn o-btn--sm" @click="useSampleLog">没有文件？填充示例日志</button>
          </div>
        </template>

        <!-- 粘贴模式 -->
        <template v-else>
          <textarea
            v-model="logText"
            class="o-textarea"
            style="min-height: 200px"
            placeholder="粘贴导出的日志内容（SEL elist 文本 / Redfish JSON / syslog / dmesg / Windows JSON lines / 应用日志）... ≤10MB"
            @input="onPasteInput"
          />
          <div class="o-row" style="margin-top: 8px">
            <button v-if="parserType" class="o-btn o-btn--sm" @click="useSampleLog">填充示例日志</button>
            <button v-if="logText" class="o-btn o-btn--sm o-btn--danger" @click="clearFile">清空</button>
            <span class="o-mono o-text-3">{{ contentSizeKb }} KB · {{ lineCount }} 行</span>
          </div>
        </template>

        <!-- 预检 -->
        <div v-if="preChecking" class="precheck">⏳ 解析器预检中…</div>
        <div v-else-if="hasContent && parserType" class="precheck" :class="preCount ? 'ok' : 'bad'">
          <template v-if="preCount">
            <b>✓ 解析器预检通过</b> — 可解析出 <b>{{ preCount }}</b> 条事件
            <template v-if="preSample.length">
              · 样例：<span class="o-mono sample">{{ preSample[0] }}</span>
            </template>
          </template>
          <template v-else>
            <b>✗ 预检失败</b> — 所选解析器无法从当前内容解析出事件，请检查类型是否匹配
          </template>
        </div>
      </div>

      <div v-if="err" class="err">⚠ {{ err }}</div>
      <div class="o-row" style="margin-top: 6px">
        <button class="o-btn" @click="rr.push(`/teams/${teamId}?tab=tasks`)">取消</button>
        <button class="o-btn o-btn--primary" @click="toStep2">下一步</button>
      </div>
    </div>

    <!-- ====== Step 2 ====== -->
    <div v-if="step === 2" class="o-card">
      <div class="confirm-grid">
        <div class="confirm-item">
          <span class="k">任务名称</span>
          <span class="v"><b>{{ taskName }}</b></span>
        </div>
        <div class="confirm-item">
          <span class="k">解析类型</span>
          <span class="v"><span class="o-badge o-badge--primary">{{ PARSER_DEFS[parserType].name }}</span></span>
        </div>
        <div class="confirm-item">
          <span class="k">日志文件</span>
          <span class="v o-mono">{{ fileName || 'pasted_input.log' }}</span>
        </div>
        <div class="confirm-item">
          <span class="k">所属资产库</span>
          <span class="v">{{ asset.name }}</span>
        </div>
        <div class="confirm-item">
          <span class="k">日志规模</span>
          <span class="v o-mono">{{ contentSizeKb }} KB{{ lineCount ? ' · ' + lineCount + ' 行' : '' }}</span>
        </div>
        <div class="confirm-item">
          <span class="k">预计解析</span>
          <span class="v o-mono"><b style="color: var(--primary)">{{ preCount }}</b> 条事件</span>
        </div>
        <div class="confirm-item">
          <span class="k">聚合维度</span>
          <span class="v">时间分布 · 事件类别 · 错误码 TopN · 源 IP 分组</span>
        </div>
      </div>
      <div v-if="err" class="err">⚠ {{ err }}</div>
      <div class="o-row" style="margin-top: 20px">
        <button class="o-btn" :disabled="running" @click="step = 1">上一步</button>
        <button v-if="canExecute" class="o-btn o-btn--primary" :disabled="running" @click="execute">
          <span v-if="!running">▶ 执行解析</span>
          <span v-else class="o-row" style="gap: 8px"><span class="spin" />解析中…</span>
        </button>
        <span v-else class="o-text-3" style="font-size: 13px">当前团队角色无「执行解析」权限（task:execute）</span>
      </div>
    </div>
  </template>
  <div v-else class="o-empty o-card">缺少资产库参数，请从团队任务页进入</div>
</template>

<style scoped>
.steps {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 20px;
  padding: 0 4px;
}
.step {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: var(--text-3);
  white-space: nowrap;
}
.step i {
  width: 22px;
  height: 22px;
  border-radius: 50%;
  border: 1px solid var(--border-strong);
  display: flex;
  align-items: center;
  justify-content: center;
  font: 600 11px/1 var(--mono);
  font-style: normal;
  background: var(--surface);
}
.step.active {
  color: var(--primary);
  font-weight: 600;
}
.step.active i {
  border-color: var(--primary);
  background: var(--primary);
  color: #fff;
}
.step.done i {
  background: var(--success-soft);
  border-color: var(--success);
  color: var(--success-deep);
}
.bar {
  flex: 1;
  min-width: 32px;
  height: 1px;
  background: var(--border-strong);
}
.bar.done {
  background: var(--success);
}
.types {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(230px, 1fr));
  gap: 10px;
}
.type {
  position: relative;
  text-align: left;
  padding: 14px 16px;
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  background: var(--surface);
  cursor: pointer;
  font: inherit;
  transition: all 0.15s;
}
.type:hover {
  border-color: var(--primary-hover);
  transform: translateY(-1px);
  box-shadow: var(--shadow-1);
}
.type.selected {
  border-color: var(--primary);
  background: var(--primary-soft);
}
.type .check {
  position: absolute;
  top: 10px;
  right: 10px;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: var(--primary);
  color: #fff;
  font-size: 11px;
  display: none;
  align-items: center;
  justify-content: center;
}
.type.selected .check {
  display: flex;
}
.type b {
  display: block;
  font-size: 14px;
}
.type .d {
  display: block;
  font-size: 12px;
  color: var(--text-2);
  margin-top: 4px;
  line-height: 1.6;
}
.type .hint {
  display: block;
  color: var(--text-4);
  margin-top: 4px;
}
.precheck {
  margin-top: 12px;
  padding: 10px 14px;
  border-radius: var(--radius);
  font-size: 13px;
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  background: var(--surface-3);
  color: var(--text-2);
}
.precheck.ok {
  background: var(--success-soft);
  color: var(--success-deep);
}
.precheck.bad {
  background: var(--danger-soft);
  color: var(--danger-deep);
}
.precheck .sample {
  max-width: 480px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  display: inline-block;
  vertical-align: bottom;
}
.err {
  color: var(--danger);
  font-size: 13px;
  margin-bottom: 12px;
}
.confirm-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 12px;
}
.confirm-item {
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 12px 16px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.confirm-item .k {
  font-size: 12px;
  color: var(--text-3);
}
.confirm-item .v {
  font-size: 13.5px;
}
.spin {
  width: 12px;
  height: 12px;
  border: 2px solid rgba(255, 255, 255, 0.4);
  border-top-color: #fff;
  border-radius: 50%;
  animation: rot 0.8s linear infinite;
  display: inline-block;
}
@keyframes rot {
  to { transform: rotate(360deg); }
}
</style>
