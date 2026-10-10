<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useTeamsStore } from '@/stores/teams'
import { useRbacStore } from '@/stores/rbac'
import { teamRoleById } from '@/rbac/permissions'
import { apiError } from '@/api/http'

const rr = useRouter()
const teamsStore = useTeamsStore()
const rbac = useRbacStore()

const kw = ref('')
const page = ref(1)
const PAGE_SIZE = 6
const actionErr = ref('')
const creating = ref(false)

onMounted(() => {
  teamsStore.fetchTeams().catch(() => {})
  teamsStore.fetchNotices().catch(() => {})
})

const filtered = computed(() => {
  const k = kw.value.trim()
  return k ? teamsStore.teams.filter((t) => t.name.includes(k) || t.desc.includes(k)) : teamsStore.teams
})
const totalPages = computed(() => Math.max(1, Math.ceil(filtered.value.length / PAGE_SIZE)))
const paged = computed(() => filtered.value.slice((page.value - 1) * PAGE_SIZE, page.value * PAGE_SIZE))
watch(kw, () => (page.value = 1))

const myRole = (t: { id: number }) => teamsStore.myRoleOf(t.id)
const hasPendingApply = (t: { id: number }) => teamsStore.appliedTeamIds.includes(t.id)

async function applyJoin(t: { id: number; name: string }) {
  actionErr.value = ''
  try {
    await teamsStore.apply(t.id)
  } catch (e) {
    actionErr.value = apiError(e)
  }
}

const showModal = ref(false)
const form = ref({ name: '', desc: '' })
async function create() {
  if (!form.value.name.trim() || creating.value) return
  creating.value = true
  actionErr.value = ''
  try {
    /* 后端同事务创建团队 + owner 成员 + 同名默认资产库 */
    const team = await teamsStore.createTeam(form.value.name.trim(), form.value.desc.trim())
    showModal.value = false
    form.value = { name: '', desc: '' }
    rr.push(`/teams/${team.id}`)
  } catch (e) {
    actionErr.value = apiError(e)
  } finally {
    creating.value = false
  }
}
</script>

<template>
  <div class="o-operate-bar">
    <div class="o-operate-left">
      <h2 style="font-size: 20px; font-weight: 700">团队</h2>
    </div>
    <div class="o-operate-right">
      <input v-model="kw" class="o-input" placeholder="搜索团队..." />
      <button v-permission="'team:create'" class="o-btn o-btn--primary" @click="showModal = true">+ 创建团队</button>
    </div>
  </div>

  <div v-if="actionErr" class="o-badge o-badge--danger" style="margin-bottom: 12px">{{ actionErr }}</div>

  <div v-if="!filtered.length" class="o-empty">
    <div class="icon">👥</div>
    <div>暂无团队</div>
  </div>

  <div v-else class="card-grid">
    <div v-for="t in paged" :key="t.id" class="o-card o-card--float team-card">
      <div class="team-head">
        <div class="team-name" :title="t.name">{{ t.name }}</div>
        <span v-if="myRole(t)" class="o-badge o-badge--brand">我 · {{ teamRoleById(myRole(t)!)?.name }}</span>
      </div>
      <div class="team-desc" :title="t.desc">{{ t.desc || '—' }}</div>
      <div class="team-stats">
        <span><b>{{ t.memberCount }}</b> 成员</span>
        <span><b>{{ t.assetCount }}</b> 资产库</span>
        <span><b>{{ t.taskCount }}</b> 任务</span>
      </div>
      <div class="team-foot">
        <span class="o-mono o-text-3">建于 {{ (t.createdAt || '').slice(0, 10) }}</span>
        <div class="o-row" style="gap: 8px">
          <button v-if="!myRole(t)" class="o-btn o-btn--sm" :disabled="hasPendingApply(t)" @click="applyJoin(t)">
            {{ hasPendingApply(t) ? '申请中...' : '+ 申请加入' }}
          </button>
          <button class="o-btn o-btn--sm o-btn--primary enter-btn" @click="rr.push(`/teams/${t.id}`)">进入团队 →</button>
        </div>
      </div>
    </div>
  </div>

  <div class="o-pagination" v-if="totalPages > 1">
    <button :disabled="page <= 1" @click="page--">‹</button>
    <button v-for="p in totalPages" :key="p" :class="{ active: page === p }" @click="page = p">{{ p }}</button>
    <button :disabled="page >= totalPages" @click="page++">›</button>
  </div>

  <div v-if="showModal" class="o-modal-mask" @click.self="showModal = false">
    <div class="o-modal">
      <div class="o-modal__title">创建团队</div>
      <div class="o-form-item">
        <label class="o-form-item__label required">团队名称</label>
        <input v-model="form.name" class="o-input" placeholder="如：广州机房 C 区运维组" />
      </div>
      <div class="o-form-item">
        <label class="o-form-item__label">描述</label>
        <input v-model="form.desc" class="o-input" placeholder="职责、负责范围" />
      </div>
      <div class="o-mono o-text-3" style="font-size: 12px">创建后你将成为团队「创建者」，系统自动建立同名默认资产库，可邀请管理员与普通用户</div>
      <div class="o-modal__foot">
        <button class="o-btn" @click="showModal = false">取消</button>
        <button class="o-btn o-btn--primary" :disabled="creating" @click="create">{{ creating ? '创建中…' : '创建' }}</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.card-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(min(320px, 100%), 1fr));
  gap: 16px;
}
.team-card {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 20px;
}
.team-head {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  flex-wrap: wrap;
}
.team-name {
  min-width: 0;
  font-size: 16px;
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.team-desc {
  font-size: 13px;
  color: var(--text-2);
  line-height: 1.6;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  min-height: 42px;
}
.team-stats {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 14px;
  font-size: 12px;
  color: var(--text-2);
}
.team-stats b {
  color: var(--text-1);
  font-weight: 600;
}
.team-foot {
  margin-top: auto;
  padding-top: 12px;
  border-top: 1px solid var(--border);
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.enter-btn {
  min-width: 104px;
  justify-content: center;
}
</style>
