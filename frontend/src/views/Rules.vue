<template>
  <div class="kp-page">
    <el-card shadow="never">
      <template #header>
        <div class="rules-toolbar">
          <span>巡检 / 诊断规则</span>
          <el-button type="primary" size="small" :icon="Plus" @click="openEdit()">新增规则</el-button>
        </div>
      </template>

      <el-table :data="rules" size="default" v-loading="loading">
        <el-table-column prop="name" label="名称" width="180" show-overflow-tooltip />
        <el-table-column prop="match_type" label="匹配类型" width="96">
          <template #default="{ row }">
            <el-tag size="small" effect="plain" :type="matchTagType(row.match_type)">
              {{ MATCH_LABEL[row.match_type] || row.match_type }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="pattern" label="匹配内容" min-width="200" show-overflow-tooltip>
          <template #default="{ row }">
            <span class="mono">{{ row.pattern || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="severity" label="级别" width="90">
          <template #default="{ row }">
            <span class="severity-dot" :style="{ background: severityColor(row.severity) }" />
            {{ SEVERITY_LABEL[row.severity] || row.severity }}
          </template>
        </el-table-column>
        <el-table-column prop="version" label="版本" width="72" />
        <el-table-column prop="enabled" label="状态" width="76">
          <template #default="{ row }">
            <el-tag size="small" :type="row.enabled ? 'success' : 'info'" effect="light">
              {{ row.enabled ? '启用' : '停用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="128">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="openEdit(row)">编辑</el-button>
            <el-button link type="danger" size="small" :disabled="row.is_builtin" @click="remove(row)">
              删除
            </el-button>
          </template>
        </el-table-column>
        <template #empty>
          <el-empty description="暂无规则" :image-size="72" />
        </template>
      </el-table>
    </el-card>

    <el-dialog v-model="dialog" :title="editing ? '编辑规则' : '新增规则'" width="560px"
               destroy-on-close>
      <el-form :model="form" label-width="90px">
        <el-form-item label="名称" required>
          <el-input v-model="form.name" placeholder="规则名称，如：OOM 错误检测" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="form.description" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="匹配类型">
          <el-radio-group v-model="form.match_type">
            <el-radio value="keyword">关键字</el-radio>
            <el-radio value="regex">正则</el-radio>
            <el-radio value="threshold">阈值</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item v-if="form.match_type !== 'threshold'" label="匹配内容">
          <el-input v-model="form.pattern" :placeholder="form.match_type === 'regex' ? '正则表达式' : '关键字'"
                    class="mono-input" />
        </el-form-item>
        <el-form-item label="级别">
          <el-select v-model="form.severity">
            <el-option v-for="(label, key) in SEVERITY_LABEL" :key="key" :label="label" :value="key" />
          </el-select>
        </el-form-item>
        <el-form-item label="优先级">
          <el-input-number v-model="form.priority" :min="1" :max="999" />
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="form.enabled" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialog = false">取消</el-button>
        <el-button type="primary" @click="save">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import http from '../api/http'

const rules = ref([])
const loading = ref(false)
const dialog = ref(false)
const editing = ref(null)

const MATCH_LABEL = { keyword: '关键字', regex: '正则', threshold: '阈值' }
const SEVERITY_LABEL = { info: '提示', warn: '警告', error: '错误', critical: '严重' }
const SEVERITY_COLOR = { info: '#909399', warn: '#b88230', error: '#d95050', critical: '#c3272b' }
const matchTagType = (t) => ({ keyword: 'info', regex: 'primary', threshold: 'warning' }[t] || 'info')
const severityColor = (s) => SEVERITY_COLOR[s] || '#909399'

const empty = {
  name: '', description: '', match_type: 'keyword', pattern: '',
  severity: 'warn', priority: 100, enabled: true,
}
const form = reactive({ ...empty })

async function load() {
  loading.value = true
  try {
    const { data } = await http.get('/rules')
    rules.value = data
  } finally {
    loading.value = false
  }
}

function openEdit(row) {
  editing.value = row || null
  Object.assign(form, row || empty)
  dialog.value = true
}

async function save() {
  if (!form.name.trim()) {
    ElMessage.warning('请填写规则名称')
    return
  }
  try {
    if (editing.value) await http.put(`/rules/${editing.value.id}`, form)
    else await http.post('/rules', form)
    ElMessage.success('已保存，Worker 将热加载新版本规则')
    dialog.value = false
    load()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '保存失败')
  }
}

async function remove(row) {
  await ElMessageBox.confirm(`确认删除规则「${row.name}」？`, '删除确认', { type: 'warning' })
  try {
    await http.delete(`/rules/${row.id}`)
    load()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '删除失败')
  }
}

onMounted(load)
</script>

<style scoped>
.rules-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.mono { font-family: Consolas, monospace; font-size: 12px; color: var(--kp-text-secondary); }
.mono-input :deep(input) { font-family: Consolas, monospace; }
.severity-dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  margin-right: 6px;
  vertical-align: 1px;
}
</style>
