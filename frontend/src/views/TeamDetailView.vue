<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useTeamsStore, type TeamDetail } from '@/stores/teams'
import { useAssetsStore, type AnalyzeTask } from '@/stores/assets'
import { useRbacStore } from '@/stores/rbac'
import { PARSER_DEFS, parserList } from '@/parser/parsers'
import { get } from '@/api/http'
import type { CodeStat } from '@/parser/aggregate'
import { fmtTime, sevBadgeClass, sevLabel, type Severity } from '@/parser/types'
import { TEAM_ROLES, teamRoleById } from '@/rbac/permissions'
import { apiError } from '@/api/http'
import type { EChartsOption } from 'echarts'
import ChartBase from '@/components/ChartBase.vue'
import TeamRolesPanel from '@/components/TeamRolesPanel.vue'
import TeamAuditPanel from '@/components/TeamAuditPanel.vue'

const route = useRoute()
const rr = useRouter()
const teamsStore = useTeamsStore()
const assetsStore = useAssetsStore()
const rbac = useRbacStore()

const teamId = computed(() => route.params.id as string)
const team = computed<TeamDetail | undefined>(() => teamsStore.details[teamId.value])
const loadErr = ref('')

async function loadTeam() {
  loadErr.value = ''
  try {
    await teamsStore.fetchTeam(teamId.value)
  } catch (e) {
    loadErr.value = apiError(e)
  }
}
onMounted(loadTeam)
watch(teamId, loadTeam)

/* 团队内权限（按团队成员角色） */
function can(perm: string): boolean {
  return team.value ? teamsStore.can(team.value.id, perm) : false
}
const myRole = computed(() => (team.value ? teamsStore.myRoleOf(team.value.id) : undefined))
const isApprover = computed(() => !!team.value && teamsStore.isApproverOf(team.value.id))

function parserName(type: string) {
  return PARSER_DEFS[type]?.name ?? type
}

const TAB_KEYS = ['tasks', 'members', 'roles', 'audit'] as const
type TabKey = (typeof TAB_KEYS)[number]
const tab = ref<TabKey>((TAB_KEYS as readonly string[]).includes(route.query.tab as string) ? (route.query.tab as TabKey) : 'tasks')

/* ---------- 任务 Tab：资产库选择 + 服务端分页 ---------- */
const assetId = ref<number | ''>('')
watch(
  () => team.value?.assets,
  (list) => {
    if (list?.length && !list.some((a) => a.id === assetId.value)) assetId.value = list[0].id
  },
  { immediate: true },
)
const asset = computed(() => team.value?.assets.find((a) => a.id === assetId.value))

const typeFilter = ref('')
const statusFilter = ref('')
const taskSearch = ref('')
const page = ref(1)
const PAGE_SIZE = 5
const tasksErr = ref('')
const tasksLoading = ref(false)

async function loadTasks() {
  if (!asset.value) return
  tasksLoading.value = true
  tasksErr.value = ''
  try {
    await assetsStore.fetchAssetTasks(asset.value.id, {
      statusFilter: statusFilter.value || undefined,
      parserType: typeFilter.value || undefined,
      kw: taskSearch.value.trim() || undefined,
      page: page.value,
      pageSize: PAGE_SIZE,
    })
  } catch (e) {
    tasksErr.value = apiError(e)
  } finally {
    tasksLoading.value = false
  }
}
watch([typeFilter, statusFilter, taskSearch, assetId], () => {
  page.value = 1
  loadTasks()
})
watch(tab, (t) => {
  if (t === 'tasks') loadTasks()
})
onMounted(() => {
  if (tab.value === 'tasks') loadTasks()
})

const taskTotal = computed(() => assetsStore.lastPage?.total ?? 0)
const pagedTasks = computed<AnalyzeTask[]>(() => assetsStore.lastPage?.items ?? [])
const totalPages = computed(() => Math.max(1, Math.ceil(taskTotal.value / PAGE_SIZE)))

function sparkOf(taskId: string): Record<string, any>[] {
  return assetsStore.lastPage?.sparks?.[taskId] ?? []
}
function criticalOf(t: AnalyzeTask): number {
  return sparkOf(t.id).reduce((s, b) => s + (b.critical ?? 0), 0)
}
function errorOf(t: AnalyzeTask): number {
  return sparkOf(t.id).reduce((s, b) => s + (b.error ?? 0), 0)
}

/* 任务状态徽章 (后端 6 态) */
const STATUS_BADGE: Record<string, { label: string; cls: string }> = {
  pending: { label: '排队中', cls: 'o-badge--outline' },
  running: { label: '解析中', cls: 'o-badge--brand' },
  done: { label: '已完成', cls: 'o-badge--success' },
  failed: { label: '失败', cls: 'o-badge--danger' },
  cancelled: { label: '已取消', cls: 'o-badge--grey' },
  interrupted: { label: '已中断', cls: 'o-badge--grey' },
}
function statusBadge(s: string) {
  return STATUS_BADGE[s] ?? { label: s, cls: 'o-badge--outline' }
}

/* ---------- 展开行：spark 图 + Top 错误码 (懒加载 stats) ---------- */
const expanded = ref<string[]>([])
const topCodeCache = ref<Record<string, CodeStat[]>>({})
const statsLoading = ref<Record<string, boolean>>({})

async function toggleExpand(id: string) {
  if (expanded.value.includes(id)) {
    expanded.value = expanded.value.filter((x) => x !== id)
    return
  }
  expanded.value = [...expanded.value, id]
  if (!topCodeCache.value[id]) {
    statsLoading.value[id] = true
    try {
      const stats = await get<{ codes: CodeStat[] }>(`/tasks/${id}/stats`)
      topCodeCache.value[id] = stats.codes.slice(0, 3)
    } catch {
      topCodeCache.value[id] = []
    } finally {
      statsLoading.value[id] = false
    }
  }
}

const SEV_COLORS: Record<Severity, string> = {
  critical: '#ef4444', error: '#f59e0b', warning: '#fbbf24', info: '#1e6fff',
}
function sparkOption(taskId: string): EChartsOption {
  const buckets = sparkOf(taskId)
  const seriesKeys = (['critical', 'error', 'warning'] as const).filter((k) => buckets.some((b) => b[k] > 0))
  return {
    grid: { left: 34, right: 8, top: 8, bottom: 20 },
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'category', data: buckets.map((b) => b.label), axisLabel: { fontSize: 10 } },
    yAxis: { type: 'value', axisLabel: { fontSize: 10 } },
    series: seriesKeys.map((s) => ({
      name: sevLabel(s),
      type: 'bar',
      stack: 't',
      barMaxWidth: 10,
      itemStyle: { color: SEV_COLORS[s] },
      data: buckets.map((b) => b[s] ?? 0),
    })),
  }
}

const taskErr = ref('')
async function removeTask(taskId: string, taskName: string) {
  if (!window.confirm(`确认删除任务「${taskName}」？删除后不可恢复`)) return
  taskErr.value = ''
  try {
    await assetsStore.removeTask(taskId)
    await loadTasks()
  } catch (e) {
    taskErr.value = apiError(e)
  }
}

/* ---------- 团队设置 ---------- */
const showEdit = ref(false)
const editForm = ref({ name: '', desc: '' })
const saveErr = ref('')
function openEdit() {
  if (!team.value) return
  editForm.value = { name: team.value.name, desc: team.value.desc }
  saveErr.value = ''
  showEdit.value = true
}
async function saveTeam() {
  if (!team.value || !editForm.value.name) return
  saveErr.value = ''
  try {
    await teamsStore.updateTeam(team.value.id, editForm.value.name, editForm.value.desc)
    await loadTeam()
    showEdit.value = false
  } catch (e) {
    saveErr.value = apiError(e)
  }
}

/* ---------- 成员与审批 ---------- */
const memberErr = ref('')
const pendingApplies = computed(() => team.value?.pendingApplies ?? [])
async function resolveApply(id: number, accept: boolean) {
  memberErr.value = ''
  try {
    await teamsStore.resolveNotice(id, accept)
    await Promise.all([loadTeam(), teamsStore.fetchNotices()])
  } catch (e) {
    memberErr.value = apiError(e)
  }
}

const showInvite = ref(false)
const inviteForm = ref({ userId: '' as number | '', roleId: 'member' })
const inviteErr = ref('')
const inviteCandidates = computed(() =>
  rbac.users.filter((m) => !team.value?.members.some((x) => x.userId === m.id)),
)
watch(showInvite, (v) => {
  if (v) {
    inviteErr.value = ''
    rbac.ensureUsers().catch(() => {})
  }
})
async function invite() {
  if (!inviteForm.value.userId || !team.value) return
  inviteErr.value = ''
  try {
    await teamsStore.invite(team.value.id, inviteForm.value.userId, inviteForm.value.roleId)
    inviteForm.value = { userId: '', roleId: 'member' }
    showInvite.value = false
  } catch (e) {
    inviteErr.value = apiError(e)
  }
}
async function changeRole(userId: number, roleId: string) {
  if (!team.value) return
  memberErr.value = ''
  try {
    await teamsStore.setMemberRole(team.value.id, userId, roleId)
    await loadTeam()
  } catch (e) {
    memberErr.value = apiError(e)
  }
}
async function revoke(userId: number, name: string) {
  if (!team.value) return
  if (!window.confirm(`确认将 ${name} 移出团队？`)) return
  memberErr.value = ''
  try {
    await teamsStore.removeMember(team.value.id, userId)
    await loadTeam()
  } catch (e) {
    memberErr.value = apiError(e)
  }
}
</script>

<template>
  <div v-if="loadErr" class="o-empty o-card">
    <div class="icon">⚠️</div>
    <div>{{ loadErr }}</div>
  </div>
  <template v-else-if="team">
    <div class="team-head-bar">
      <div class="info">
        <h2>
          {{ team.name }}
          <span v-if="myRole" class="o-badge o-badge--brand">我 · {{ teamRoleById(myRole)?.name }}</span>
          <span class="o-badge o-badge--outline">{{ team.memberCount }} 成员</span>
          <span class="o-badge o-badge--outline">{{ team.assets.length }} 资产库</span>
        </h2>
        <div class="sub">{{ team.desc }} · 建于 {{ (team.createdAt || '').slice(0, 10) }}</div>
      </div>
      <button v-if="can('team:role')" class="o-btn" @click="openEdit">团队设置</button>
    </div>

    <nav class="o-page-nav">
      <button class="o-page-nav__item" :class="{ active: tab === 'tasks' }" @click="tab = 'tasks'">
        任务 <span class="count">{{ team.taskCount }}</span>
      </button>
      <button class="o-page-nav__item" :class="{ active: tab === 'members' }" @click="tab = 'members'">
        团队 <span class="count">{{ team.memberCount }}</span>
      </button>
      <button class="o-page-nav__item" :class="{ active: tab === 'roles' }" @click="tab = 'roles'">
        角色 <span class="count">{{ TEAM_ROLES.length }}</span>
      </button>
      <button v-if="can('audit:view')" class="o-page-nav__item" :class="{ active: tab === 'audit' }" @click="tab = 'audit'">
        审计
      </button>
    </nav>

    <!-- ====== 任务 Tab ====== -->
    <section v-if="tab === 'tasks'">
      <div class="asset-bar o-card">
        <div class="asset-bar-left">
          <span class="lbl">资产库</span>
          <select v-if="team.assets.length > 1" v-model="assetId" class="o-select" style="width: 220px">
            <option v-for="a in team.assets" :key="a.id" :value="a.id">{{ a.name }}</option>
          </select>
          <template v-else-if="asset">
            <b>{{ asset.name }}</b>
            <span class="o-mono o-text-3">{{ asset.ipRange || '—' }}</span>
          </template>
          <span v-if="!team.assets.length" class="o-text-3">团队暂无资产库</span>
        </div>
        <div class="o-row">
          <button v-if="asset && can('task:create')" class="o-btn o-btn--primary" @click="rr.push(`/teams/${team.id}/new-task?assetId=${asset.id}`)">
            + 创建解析任务
          </button>
        </div>
      </div>

      <div v-if="taskErr || memberErr" class="o-badge o-badge--danger" style="margin-bottom: 12px">{{ taskErr || memberErr }}</div>

      <div v-if="!team.assets.length" class="o-empty">
        <div class="icon">📭</div>
        <div>该团队还没有资产库</div>
        <div class="hint">创建团队时会自动生成同名默认资产库</div>
      </div>

      <template v-else-if="asset">
        <div class="o-operate-bar">
          <div class="o-operate-left">
            <span v-if="tasksLoading" class="o-mono o-text-3" style="font-size: 12.5px">加载中…</span>
            <span v-else class="o-mono o-text-3" style="font-size: 12.5px">共 {{ taskTotal }} 个任务</span>
          </div>
          <div class="o-operate-right">
            <select v-model="typeFilter" class="o-select">
              <option value="">全部类型</option>
              <option v-for="p in parserList()" :key="p.type" :value="p.type">{{ p.name }}</option>
            </select>
            <select v-model="statusFilter" class="o-select">
              <option value="">全部状态</option>
              <option value="done">已完成</option>
              <option value="running">解析中</option>
              <option value="pending">排队中</option>
              <option value="failed">失败</option>
              <option value="cancelled">已取消</option>
            </select>
            <input v-model="taskSearch" class="o-input" placeholder="搜索任务名称 / 文件" />
          </div>
        </div>

        <div v-if="!pagedTasks.length && !tasksLoading" class="o-empty">
          <div class="icon">📭</div>
          <div>暂无任务</div>
          <div class="hint">点击右上角按钮创建第一个解析任务</div>
        </div>

        <div v-else class="o-table-wrap">
          <table class="o-table o-table--sticky-action">
            <thead>
              <tr>
                <th style="width: 30px"></th>
                <th>名称 / 文件</th><th>类型</th><th>事件数</th><th>致命 / 错误</th><th>创建人</th><th>创建时间</th><th>状态</th><th>操作</th>
              </tr>
            </thead>
            <tbody>
              <template v-for="t in pagedTasks" :key="t.id">
                <tr>
                  <td>
                    <button class="o-expand-btn" :title="expanded.includes(t.id) ? '收起明细' : '展开明细'" @click="toggleExpand(t.id)">
                      {{ expanded.includes(t.id) ? '▾' : '▸' }}
                    </button>
                  </td>
                  <td>
                    <div class="task-name" :title="t.name || t.filename">{{ t.name || t.filename }}</div>
                    <div class="task-path o-mono" :title="t.filename">{{ t.filename }}</div>
                  </td>
                  <td><span class="o-badge o-badge--outline">{{ parserName(t.parserType) }}</span></td>
                  <td class="o-mono num">{{ t.eventCount }}</td>
                  <td class="o-mono num">
                    <span style="color: var(--danger)">{{ criticalOf(t) }}</span>
                    /
                    <span style="color: var(--warning)">{{ errorOf(t) }}</span>
                  </td>
                  <td>{{ t.creatorName || '—' }}</td>
                  <td class="o-mono o-text-3">{{ fmtTime(t.createdAt) }}</td>
                  <td>
                    <span class="o-badge" :class="statusBadge(t.status).cls">
                      {{ t.status === 'running' ? `解析中 ${t.progress}%` : statusBadge(t.status).label }}
                    </span>
                  </td>
                  <td>
                    <div class="o-row" style="gap: 2px">
                      <router-link class="o-btn o-btn--sm o-btn--text" :to="`/tasks/${t.id}`">查看结果</router-link>
                      <button v-if="can('task:delete')" class="o-btn o-btn--sm o-btn--text o-btn--danger" @click="removeTask(t.id, t.name || t.filename)">删除</button>
                    </div>
                  </td>
                </tr>
                <tr v-if="expanded.includes(t.id)" class="o-expand-tr">
                  <td></td>
                  <td colspan="8">
                    <div class="expand-body">
                      <div class="expand-chart">
                        <div class="expand-title">事件时序（按级别堆叠）</div>
                        <ChartBase :option="sparkOption(t.id)" height="150px" />
                      </div>
                      <div class="expand-side">
                        <div class="expand-title">Top 错误码</div>
                        <div v-if="statsLoading[t.id]" class="o-mono o-text-3">统计加载中…</div>
                        <template v-else-if="(topCodeCache[t.id] ?? []).length">
                          <div v-for="c in topCodeCache[t.id]" :key="c.name" class="code-chip">
                            <span class="o-badge" :class="sevBadgeClass(c.severity as Severity)">{{ c.name }}</span>
                            <span class="o-mono o-text-3">{{ c.category }} · {{ c.value }} 次</span>
                          </div>
                        </template>
                        <div v-else class="o-mono o-text-3">暂无错误码统计</div>
                        <router-link class="o-btn o-btn--sm" :to="`/tasks/${t.id}`" style="margin-top: 10px; width: fit-content">
                          查看完整分析 →
                        </router-link>
                      </div>
                    </div>
                  </td>
                </tr>
              </template>
            </tbody>
          </table>
        </div>

        <div class="o-pagination" v-if="totalPages > 1">
          <button :disabled="page <= 1" @click="page--; loadTasks()">‹</button>
          <button v-for="p in totalPages" :key="p" :class="{ active: page === p }" @click="page = p; loadTasks()">{{ p }}</button>
          <button :disabled="page >= totalPages" @click="page++; loadTasks()">›</button>
        </div>
      </template>
    </section>

    <!-- ====== 团队 Tab ====== -->
    <section v-else-if="tab === 'members'">
      <!-- 待审批申请 -->
      <div v-if="pendingApplies.length && isApprover" class="o-card apply-card">
        <div class="o-card__title">
          待审批申请
          <span class="hint">{{ pendingApplies.length }} 条 · 也可在右上角 🔔 通知中心处理</span>
        </div>
        <div v-if="memberErr" class="o-badge o-badge--danger" style="margin-bottom: 8px">{{ memberErr }}</div>
        <div v-for="n in pendingApplies" :key="n.id" class="apply-row">
          <div class="apply-info">
            <b>{{ n.fromUserName }}</b>
            <span class="o-mono o-text-3">{{ n.role === 'team_admin' ? '申请为管理员' : '申请加入' }} · {{ fmtTime(n.createdAt) }}</span>
          </div>
          <div class="o-row" style="gap: 8px">
            <button class="o-btn o-btn--sm o-btn--primary" @click="resolveApply(n.id, true)">同意</button>
            <button class="o-btn o-btn--sm" @click="resolveApply(n.id, false)">拒绝</button>
          </div>
        </div>
      </div>

      <div class="o-operate-bar">
        <div class="o-operate-left">
          <span class="o-text-3" style="font-size: 13px">团队内固定三角色：创建者 / 管理员 / 普通用户，详见「角色」页签</span>
        </div>
        <div class="o-operate-right">
          <button v-if="can('team:invite')" class="o-btn o-btn--primary" @click="showInvite = true">+ 邀请成员</button>
        </div>
      </div>

      <div class="o-table-wrap">
        <table class="o-table o-table--sticky-action">
          <thead>
            <tr><th>成员</th><th>部门</th><th>邮箱</th><th>团队角色</th><th>操作</th></tr>
          </thead>
          <tbody>
            <tr v-if="!team.members.length">
              <td colspan="5"><div class="o-empty">📭 团队暂无成员</div></td>
            </tr>
            <tr v-for="m in team.members" :key="m.userId">
              <td>
                <div class="o-row" style="gap: 8px">
                  <span class="avatar" :style="{ background: `hsl(${m.avatarHue ?? 210}, 60%, 48%)` }">
                    {{ m.name.slice(0, 1) }}
                  </span>
                  <b>{{ m.name }}</b>
                </div>
              </td>
              <td class="o-text-3">{{ m.dept || '—' }}</td>
              <td class="o-mono o-text-3">{{ m.email || '—' }}</td>
              <td>
                <select
                  v-if="can('team:role') && m.role !== 'owner'"
                  class="o-select role-select"
                  :value="m.role"
                  @change="changeRole(m.userId, ($event.target as HTMLSelectElement).value)"
                >
                  <option v-for="r in TEAM_ROLES.filter(x => x.id !== 'owner')" :key="r.id" :value="r.id">{{ r.name }}</option>
                </select>
                <span v-else class="o-badge" :class="m.role === 'owner' ? 'o-badge--primary' : 'o-badge--outline'">
                  {{ teamRoleById(m.role)?.name ?? m.role }}
                </span>
              </td>
              <td>
                <button
                  v-if="can('team:remove') && m.role !== 'owner'"
                  class="o-btn o-btn--sm o-btn--text o-btn--danger"
                  @click="revoke(m.userId, m.name)"
                >
                  移出团队
                </button>
                <span v-else class="o-mono o-text-3">—</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <!-- ====== 角色 Tab ====== -->
    <section v-else-if="tab === 'roles'">
      <TeamRolesPanel />
    </section>

    <!-- ====== 审计 Tab ====== -->
    <section v-else-if="tab === 'audit'">
      <TeamAuditPanel :team-id="String(team.id)" />
    </section>

    <!-- 团队设置弹窗 -->
    <div v-if="showEdit" class="o-modal-mask" @click.self="showEdit = false">
      <div class="o-modal">
        <div class="o-modal__title">团队设置 — {{ team.name }}</div>
        <div class="o-form-item">
          <label class="o-form-item__label required">团队名称</label>
          <input v-model="editForm.name" class="o-input" />
        </div>
        <div class="o-form-item">
          <label class="o-form-item__label">描述</label>
          <input v-model="editForm.desc" class="o-input" />
        </div>
        <div v-if="saveErr" class="o-badge o-badge--danger">{{ saveErr }}</div>
        <div class="o-modal__foot">
          <button class="o-btn" @click="showEdit = false">取消</button>
          <button class="o-btn o-btn--primary" @click="saveTeam">保存</button>
        </div>
      </div>
    </div>

    <!-- 邀请成员弹窗（发出邀请通知，对方在右上角确认） -->
    <div v-if="showInvite" class="o-modal-mask" @click.self="showInvite = false">
      <div class="o-modal">
        <div class="o-modal__title">邀请成员加入 {{ team.name }}</div>
        <div class="o-form-item">
          <label class="o-form-item__label required">选择用户</label>
          <select v-model="inviteForm.userId" class="o-select">
            <option :value="''" disabled>请选择</option>
            <option v-for="m in inviteCandidates" :key="m.id" :value="m.id">{{ m.name }}（{{ m.dept }} · {{ m.email }}）</option>
          </select>
        </div>
        <div class="o-form-item">
          <label class="o-form-item__label required">团队角色</label>
          <select v-model="inviteForm.roleId" class="o-select">
            <option v-for="r in TEAM_ROLES.filter(x => x.id !== 'owner')" :key="r.id" :value="r.id">{{ r.name }} — {{ r.desc }}</option>
          </select>
        </div>
        <div v-if="inviteErr" class="o-badge o-badge--danger">{{ inviteErr }}</div>
        <div class="o-mono o-text-3" style="font-size: 12px">对方将在右上角 🔔 通知中心收到邀请，确认后加入</div>
        <div class="o-modal__foot">
          <button class="o-btn" @click="showInvite = false">取消</button>
          <button class="o-btn o-btn--primary" @click="invite">发送邀请</button>
        </div>
      </div>
    </div>
  </template>
  <div v-else class="o-empty o-card">团队加载中…</div>
</template>

<style scoped>
.team-head-bar {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 20px;
  flex-wrap: wrap;
}
.team-head-bar h2 {
  font-size: 20px;
  font-weight: 700;
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.team-head-bar .sub {
  font-size: 13px;
  color: var(--text-2);
  margin-top: 4px;
}
.asset-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 16px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}
.asset-bar-left {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.asset-bar .lbl {
  font-size: 13px;
  color: var(--text-2);
}
.task-name {
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.task-path {
  color: var(--text-3);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 280px;
}
.expand-body {
  display: grid;
  grid-template-columns: 3fr 2fr;
  gap: 20px;
}
@media (max-width: 900px) {
  .expand-body { grid-template-columns: 1fr; }
}
.expand-title {
  font-size: 12.5px;
  font-weight: 600;
  color: var(--text-2);
  margin-bottom: 8px;
}
.code-chip {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 8px;
}
.apply-card {
  margin-bottom: 16px;
  border-left: 3px solid var(--warning);
}
.apply-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 0;
  border-bottom: 1px solid var(--border);
}
.apply-row:last-child {
  border-bottom: 0;
}
.apply-info {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 13px;
  flex-wrap: wrap;
}
.avatar {
  width: 26px;
  height: 26px;
  border-radius: 50%;
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  flex: none;
}
.role-select {
  width: 130px;
  height: 30px;
  font-size: 13px;
}
</style>
