<script setup lang="ts">
/* 规则管理: 巡检/诊断规则 CRUD, 版本化热加载, 平台级 rule:manage 权限控制 */
import { computed, onMounted, reactive, ref } from 'vue'
import { get, post, put, del, apiError } from '@/api/http'
import { fmtTime } from '@/parser/types'
import { useRbacStore } from '@/stores/rbac'

const rbac = useRbacStore()
const canManage = computed(() => rbac.hasPerm('rule:manage'))

interface RuleRow {
  id: number
  name: string
  description: string
  matchType: 'keyword' | 'regex' | 'threshold'
  pattern: string
  threshold: Record<string, any>
  severity: 'info' | 'warn' | 'error' | 'critical'
  logType: string
  serverType: string
  enabled: boolean
  priority: number
  version: number
  isBuiltin: boolean
  createdAt: string
}

const MATCH_LABEL: Record<RuleRow['matchType'], string> = { keyword: '关键字', regex: '正则', threshold: '阈值' }
const MATCH_BADGE: Record<RuleRow['matchType'], string> = {
  keyword: 'o-badge--outline', regex: 'o-badge--primary', threshold: 'o-badge--warning',
}
const SEV_LABEL: Record<RuleRow['severity'], string> = { info: '提示', warn: '警告', error: '错误', critical: '严重' }
const SEV_BADGE: Record<RuleRow['severity'], string> = {
  info: 'o-badge--grey', warn: 'o-badge--warning', error: 'o-badge--danger', critical: 'o-badge--danger',
}
const OPS = ['>', '>=', '<', '<=', '==', '!=']

const rules = ref<RuleRow[]>([])
const loading = ref(false)
const loadErr = ref('')

async function load() {
  loading.value = true
  loadErr.value = ''
  try {
    rules.value = await get<RuleRow[]>('/rules')
  } catch (e) {
    loadErr.value = apiError(e)
  } finally {
    loading.value = false
  }
}
onMounted(load)

/* ---------- 编辑弹窗 ---------- */
const showEdit = ref(false)
const editingId = ref<number | null>(null)
const saveErr = ref('')
const saving = ref(false)

const emptyForm = () => ({
  name: '',
  description: '',
  match_type: 'keyword' as RuleRow['matchType'],
  pattern: '',
  threshold: { metric: '', op: '>', value: 0 },
  severity: 'warn' as RuleRow['severity'],
  log_type: '',
  server_type: '',
  enabled: true,
  priority: 100,
})
const form = reactive(emptyForm())

function openEdit(row?: RuleRow) {
  saveErr.value = ''
  editingId.value = row?.id ?? null
  Object.assign(form, emptyForm(), row ? {
    name: row.name, description: row.description, match_type: row.matchType,
    pattern: row.pattern, threshold: { ...row.threshold }, severity: row.severity,
    log_type: row.logType, server_type: row.serverType, enabled: row.enabled,
    priority: row.priority,
  } : {})
  showEdit.value = true
}

function pickMatch(t: RuleRow['matchType']) {
  form.match_type = t
}

async function save() {
  if (!form.name.trim()) {
    saveErr.value = '请填写规则名称'
    return
  }
  saveErr.value = ''
  saving.value = true
  try {
    const body: Record<string, any> = {
      name: form.name.trim(), description: form.description, match_type: form.match_type,
      severity: form.severity, log_type: form.log_type, server_type: form.server_type,
      enabled: form.enabled, priority: Number(form.priority) || 1,
    }
    if (form.match_type === 'threshold') {
      body.pattern = ''
      body.threshold = { metric: form.threshold.metric, op: form.threshold.op, value: Number(form.threshold.value) }
    } else {
      body.pattern = form.pattern
      body.threshold = {}
    }
    if (editingId.value) await put(`/rules/${editingId.value}`, body)
    else await post('/rules', body)
    showEdit.value = false
    await load()
  } catch (e) {
    saveErr.value = apiError(e)
  } finally {
    saving.value = false
  }
}

async function remove(row: RuleRow) {
  if (!window.confirm(`确认删除规则「${row.name}」？`)) return
  loadErr.value = ''
  try {
    await del(`/rules/${row.id}`)
    await load()
  } catch (e) {
    loadErr.value = apiError(e)
  }
}
</script>

<template>
  <div class="o-operate-bar">
    <div class="o-operate-left">
      <h2>巡检 / 诊断规则</h2>
      <span class="o-mono o-text-3">规则版本化存储，Worker 感知版本变化后热加载，无需重启</span>
    </div>
    <div class="o-operate-right">
      <button v-permission="'rule:manage'" class="o-btn o-btn--primary" @click="openEdit()">＋ 新增规则</button>
    </div>
  </div>

  <div v-if="loadErr" class="o-mono" style="color: var(--danger); margin-bottom: 12px">⚠ {{ loadErr }}</div>

  <div class="o-card">
    <div class="o-table-wrap">
      <table class="o-table">
        <thead>
          <tr>
            <th>名称</th><th>匹配类型</th><th>匹配内容</th><th>级别</th>
            <th>优先级</th><th>版本</th><th>状态</th><th>更新时间</th><th></th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="!rules.length && !loading">
            <td colspan="9"><div class="o-empty" style="padding: 48px 0">📭 暂无规则</div></td>
          </tr>
          <tr v-for="r in rules" :key="r.id">
            <td>
              <b>{{ r.name }}</b>
              <span v-if="r.isBuiltin" class="o-badge o-badge--brand" style="margin-left: 6px">内置</span>
              <div v-if="r.description" class="o-text-3 desc">{{ r.description }}</div>
            </td>
            <td><span class="o-badge" :class="MATCH_BADGE[r.matchType]">{{ MATCH_LABEL[r.matchType] }}</span></td>
            <td>
              <span v-if="r.matchType !== 'threshold'" class="o-mono pattern">{{ r.pattern || '—' }}</span>
              <span v-else class="o-mono pattern">
                {{ r.threshold?.metric }} {{ r.threshold?.op }} {{ r.threshold?.value }}
              </span>
            </td>
            <td><span class="o-badge" :class="SEV_BADGE[r.severity]">{{ SEV_LABEL[r.severity] }}</span></td>
            <td class="o-mono">{{ r.priority }}</td>
            <td class="o-mono">v{{ r.version }}</td>
            <td>
              <span class="o-badge" :class="r.enabled ? 'o-badge--success' : 'o-badge--grey'">
                {{ r.enabled ? '启用' : '停用' }}
              </span>
            </td>
            <td class="o-mono o-text-3">{{ fmtTime(r.createdAt) }}</td>
            <td class="actions">
              <template v-if="canManage">
                <button class="o-btn o-btn--text o-btn--sm" @click="openEdit(r)">编辑</button>
                <button class="o-btn o-btn--text o-btn--sm danger" :disabled="r.isBuiltin" @click="remove(r)">删除</button>
              </template>
              <span v-else class="o-text-3">—</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>

  <!-- 新增/编辑弹窗 -->
  <div v-if="showEdit" class="o-modal-mask" @click.self="showEdit = false">
    <div class="o-modal">
      <div class="o-modal__title">{{ editingId ? '编辑规则' : '新增规则' }}</div>
      <div class="o-form-item">
        <label class="o-form-item__label required">名称</label>
        <input v-model="form.name" class="o-input" placeholder="规则名称，如：OOM 错误检测" />
      </div>
      <div class="o-form-item">
        <label class="o-form-item__label">描述</label>
        <textarea v-model="form.description" class="o-textarea" rows="2" placeholder="规则用途说明（可选）"></textarea>
      </div>
      <div class="o-form-item">
        <label class="o-form-item__label required">匹配类型</label>
        <div class="match-chips">
          <button
            v-for="(label, key) in MATCH_LABEL"
            :key="key"
            class="match-chip"
            :class="{ active: form.match_type === key }"
            @click="pickMatch(key)"
          >{{ label }}</button>
        </div>
      </div>
      <div v-if="form.match_type !== 'threshold'" class="o-form-item">
        <label class="o-form-item__label required">匹配内容</label>
        <input
          v-model="form.pattern" class="o-input mono-input"
          :placeholder="form.match_type === 'regex' ? '正则表达式，如 ERROR|PANIC' : '关键字，如 Out of memory'"
        />
      </div>
      <template v-else>
        <div class="o-form-item">
          <label class="o-form-item__label required">指标名</label>
          <input v-model="form.threshold.metric" class="o-input mono-input" placeholder="如 cpu.usage" />
        </div>
        <div class="o-form-item">
          <label class="o-form-item__label required">比较符</label>
          <select v-model="form.threshold.op" class="o-select" style="width: 120px">
            <option v-for="op in OPS" :key="op" :value="op">{{ op }}</option>
          </select>
        </div>
        <div class="o-form-item">
          <label class="o-form-item__label required">阈值</label>
          <input v-model.number="form.threshold.value" type="number" class="o-input" style="width: 160px" />
        </div>
      </template>
      <div class="o-form-item">
        <label class="o-form-item__label">级别</label>
        <select v-model="form.severity" class="o-select" style="width: 140px">
          <option v-for="(label, key) in SEV_LABEL" :key="key" :value="key">{{ label }}</option>
        </select>
      </div>
      <div class="o-form-item">
        <label class="o-form-item__label">优先级</label>
        <input v-model.number="form.priority" type="number" min="1" max="999" class="o-input" style="width: 120px" />
        <span class="o-mono o-text-3" style="align-self: center; margin-left: 8px">数值越小越先匹配</span>
      </div>
      <div class="o-form-item">
        <label class="o-form-item__label">启用</label>
        <label class="switch">
          <input v-model="form.enabled" type="checkbox" />
          <span>{{ form.enabled ? '启用中' : '已停用' }}</span>
        </label>
      </div>
      <div v-if="saveErr" class="o-mono" style="color: var(--danger); font-size: 12.5px">⚠ {{ saveErr }}</div>
      <div class="o-modal__foot">
        <button class="o-btn" @click="showEdit = false">取消</button>
        <button class="o-btn o-btn--primary" :disabled="saving" @click="save">{{ saving ? '保存中…' : '保存' }}</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.desc {
  font-size: 12px;
  max-width: 260px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.pattern {
  display: inline-block;
  max-width: 280px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  vertical-align: bottom;
  font-size: 12px;
}
.actions {
  white-space: nowrap;
  text-align: right;
}
.actions .danger {
  color: var(--danger);
}
.mono-input {
  font-family: var(--mono);
}
.match-chips {
  display: flex;
  gap: 8px;
}
.match-chip {
  border: 1px solid var(--border);
  background: var(--surface);
  border-radius: var(--radius);
  padding: 7px 18px;
  font: inherit;
  font-size: 13.5px;
  cursor: pointer;
  color: var(--text-2);
}
.match-chip:hover {
  border-color: var(--primary);
  color: var(--primary);
}
.match-chip.active {
  border-color: var(--primary);
  background: var(--primary-soft);
  color: var(--primary);
  font-weight: 600;
}
.switch {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-size: 13.5px;
  color: var(--text-2);
  cursor: pointer;
}
</style>
