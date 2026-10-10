<script setup lang="ts">
/* 团队动态 / 审计面板（嵌入团队详情 Tab，服务端分页查询） */
import { computed, onMounted, ref, watch } from 'vue'
import { useAuditStore } from '@/stores/audit'
import { useRbacStore } from '@/stores/rbac'
import { apiError } from '@/api/http'
import { fmtTime } from '@/parser/types'

const props = defineProps<{ teamId: string }>()
const audit = useAuditStore()
const rbac = useRbacStore()

const onlyTeam = ref(true)
const actionFilter = ref('')
const kw = ref('')
const page = ref(1)
const PAGE_SIZE = 10
const loadErr = ref('')
const loading = ref(false)

async function load() {
  loading.value = true
  loadErr.value = ''
  try {
    await audit.fetchRecords({
      teamId: onlyTeam.value ? props.teamId : undefined,
      action: actionFilter.value || undefined,
      kw: kw.value.trim() || undefined,
      page: page.value,
      pageSize: PAGE_SIZE,
    })
  } catch (e) {
    loadErr.value = apiError(e)
  } finally {
    loading.value = false
  }
}
onMounted(load)
watch([onlyTeam, actionFilter, kw], () => {
  page.value = 1
  load()
})
watch(() => props.teamId, () => {
  page.value = 1
  load()
})

const totalPages = computed(() => Math.max(1, Math.ceil(audit.total / PAGE_SIZE)))
const isAdmin = computed(() => rbac.isPlatformAdmin)
</script>

<template>
  <div class="o-operate-bar">
    <div class="o-operate-left">
      <label v-if="isAdmin" class="only-toggle">
        <input type="checkbox" v-model="onlyTeam" />
        仅看本团队
      </label>
      <span v-else class="o-text-3" style="font-size: 13px">展示范围：与我相关的团队及个人操作</span>
    </div>
    <div class="o-operate-right">
      <select v-model="actionFilter" class="o-select">
        <option value="">全部动作</option>
        <option v-for="a in audit.actions" :key="a" :value="a">{{ a }}</option>
      </select>
      <input v-model="kw" class="o-input" placeholder="搜索操作人 / 对象" />
    </div>
  </div>

  <div v-if="loadErr" class="o-badge o-badge--danger" style="margin-bottom: 12px">{{ loadErr }}</div>
  <div v-if="loading" class="o-mono o-text-3" style="font-size: 12.5px; margin-bottom: 8px">加载中…</div>

  <div v-if="!audit.records.length && !loading" class="o-empty">
    <div class="icon">📭</div>
    <div>暂无匹配的团队动态</div>
  </div>

  <div v-else-if="audit.records.length" class="o-table-wrap">
    <table class="o-table">
      <thead><tr><th style="width: 180px">时间</th><th>操作人</th><th>动作</th><th>对象</th><th>团队</th><th>结果</th></tr></thead>
      <tbody>
        <tr v-for="r in audit.records" :key="r.id">
          <td class="o-mono o-text-3">{{ fmtTime(r.createdAt) }}</td>
          <td><b>{{ r.userName }}</b></td>
          <td><span class="o-badge o-badge--outline">{{ r.action }}</span></td>
          <td class="o-text-3">{{ r.target }}</td>
          <td class="o-text-3">{{ r.teamName || '—' }}</td>
          <td><span class="o-badge" :class="r.success ? 'o-badge--success' : 'o-badge--danger'">{{ r.success ? '成功' : '失败' }}</span></td>
        </tr>
      </tbody>
    </table>
  </div>

  <div class="o-pagination" v-if="totalPages > 1">
    <button :disabled="page <= 1" @click="page--; load()">‹</button>
    <button v-for="p in totalPages" :key="p" :class="{ active: page === p }" @click="page = p; load()">{{ p }}</button>
    <button :disabled="page >= totalPages" @click="page++; load()">›</button>
  </div>
</template>

<style scoped>
.only-toggle {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: var(--text-2);
  cursor: pointer;
}
</style>
