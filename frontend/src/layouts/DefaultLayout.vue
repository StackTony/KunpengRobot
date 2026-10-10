<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { router } from '@/router'
import { useRbacStore } from '@/stores/rbac'
import { useTeamsStore } from '@/stores/teams'
import { useAssetsStore } from '@/stores/assets'
import { teamRoleById } from '@/rbac/permissions'
import { fmtTime } from '@/parser/types'
import { apiError } from '@/api/http'

const route = useRoute()
const rr = useRouter()
const rbac = useRbacStore()
const teamsStore = useTeamsStore()
const assetsStore = useAssetsStore()

/* 动态面包屑：首页 / 团队 / 团队名 / 当前页，中间层级可点击返回 */
interface Crumb {
  label: string
  to?: string
}
const cachedTask = computed(() => assetsStore.taskCached(route.params.taskId as string))
const cachedAsset = computed(() =>
  cachedTask.value?.assetId ? assetsStore.assetById(cachedTask.value.assetId) : undefined,
)
const cachedTeam = computed(() =>
  cachedAsset.value ? teamsStore.teamById(cachedAsset.value.teamId) : undefined,
)

const crumbs = computed<Crumb[]>(() => {
  const items: Crumb[] = []
  if (route.name !== 'dashboard') items.push({ label: '首页', to: '/dashboard' })
  if (route.name === 'team-detail' || route.name === 'task-new') {
    items.push({ label: '团队', to: '/teams' })
    const t = teamsStore.teamById(route.params.id as string)
    if (route.name === 'task-new') {
      items.push({ label: t?.name ?? '团队', to: `/teams/${route.params.id}?tab=tasks` })
    } else {
      items.push({ label: t?.name ?? '团队' })
    }
  }
  if (route.name === 'task-result') {
    items.push({ label: '团队', to: '/teams' })
    items.push({
      label: cachedTeam.value?.name ?? cachedTask.value?.assetName ?? '团队',
      to: cachedTeam.value ? `/teams/${cachedTeam.value.id}?tab=tasks` : '/teams',
    })
  }
  /* 末级标题：仅当最后一级还是可点击链接（或无层级）时追加，避免「团队 / 团队」重复 */
  const last = items[items.length - 1]
  if (!last || last.to) {
    items.push({ label: (route.meta.title as string) ?? '' })
  }
  return items
})

const menus = computed(() =>
  router
    .getRoutes()
    .filter((r) => r.meta?.menu && r.meta?.perm && rbac.hasPerm(r.meta.perm as string))
    .map((r) => ({ path: r.path, title: r.meta.title as string })),
)

const user = computed(() => rbac.currentUser)
const myTeamRole = computed(() => {
  for (const [tid, rid] of Object.entries(rbac.myTeamRoles)) {
    if (rid === 'owner' && teamsStore.teamById(tid)) return '创建者'
  }
  return ''
})

/* ---------- 头像下拉 + 通知中心 ---------- */
const menuOpen = ref(false)
const noticeOpen = ref(false)

const myNotices = computed(() => teamsStore.notices)
const noticeCount = computed(() => myNotices.value.length)
const resolveErr = ref('')

onMounted(() => {
  teamsStore.fetchNotices().catch(() => {})
})

async function resolve(n: { id: number; type: string; fromUserName: string }, accept: boolean) {
  resolveErr.value = ''
  try {
    await teamsStore.resolveNotice(n.id, accept)
    await teamsStore.fetchNotices()
  } catch (e) {
    resolveErr.value = apiError(e)
  }
}

async function logout() {
  menuOpen.value = false
  noticeOpen.value = false
  await rbac.logout()
  rr.push('/login')
}
</script>

<template>
  <div class="shell" @click="menuOpen = false; noticeOpen = false">
    <header class="topbar" @click.stop>
      <div class="left">
        <span class="logo" @click="rr.push('/dashboard')">鲲鹏运维平台</span>
        <nav class="nav">
          <router-link
            v-for="m in menus"
            :key="m.path"
            :to="m.path"
            class="nav-item"
            active-class="is-active"
          >
            {{ m.title }}
          </router-link>
        </nav>
      </div>
      <div class="right" @click.stop>
        <!-- 通知 -->
        <div class="bell-wrap">
          <button class="bell" :class="{ 'has': noticeCount }" @click="noticeOpen = !noticeOpen; menuOpen = false">
            🔔
            <span v-if="noticeCount" class="dot">{{ noticeCount }}</span>
          </button>
          <div v-if="noticeOpen" class="notice-panel">
            <div class="notice-head">
              <b>申请与邀请</b>
              <span class="o-mono o-text-3">{{ noticeCount }} 条待处理</span>
            </div>
            <div v-if="resolveErr" class="notice-err">⚠ {{ resolveErr }}</div>
            <div v-if="!myNotices.length" class="o-empty" style="padding: 28px 0">📭 暂无待处理的申请或邀请</div>
            <div v-for="n in myNotices" :key="n.id" class="notice-item">
              <div class="notice-body">
                <template v-if="n.type === 'invite'">
                  <b>{{ n.fromUserName }}</b> 邀请你加入
                  <b>{{ n.teamName }}</b>
                  <span class="o-badge o-badge--brand">{{ teamRoleById(n.role)?.name }}</span>
                </template>
                <template v-else>
                  <b>{{ n.fromUserName }}</b> 申请加入
                  <b>{{ n.teamName }}</b>
                </template>
                <div class="o-mono o-text-3">{{ fmtTime(n.createdAt) }}</div>
              </div>
              <div class="notice-actions">
                <button class="o-btn o-btn--sm o-btn--primary" @click="resolve(n, true)">同意</button>
                <button class="o-btn o-btn--sm" @click="resolve(n, false)">拒绝</button>
              </div>
            </div>
          </div>
        </div>

        <!-- 头像菜单 -->
        <div class="user-wrap">
          <button class="user-btn" @click="menuOpen = !menuOpen; noticeOpen = false">
            <span class="avatar" :style="{ background: `hsl(${user?.avatarHue ?? 210}, 65%, 50%)` }">{{
              user?.name.slice(0, 1)
            }}</span>
            <span class="name">{{ user?.name }}</span>
            <span v-if="myTeamRole" class="o-badge o-badge--brand">{{ myTeamRole }}</span>
            <span v-else-if="user?.dept" class="o-badge o-badge--outline">{{ user?.dept }}</span>
          </button>
          <div v-if="menuOpen" class="user-menu">
            <div class="user-info">
              <b>{{ user?.name }}</b>
              <span class="o-mono o-text-3">{{ user?.email }}</span>
              <span class="o-mono o-text-3">{{ user?.dept }}{{ user?.title ? ' · ' + user.title : '' }}</span>
            </div>
            <button class="menu-row" @click="noticeOpen = true; menuOpen = false">
              申请与邀请 <span v-if="noticeCount" class="o-badge o-badge--danger">{{ noticeCount }}</span>
            </button>
            <button class="menu-row danger" @click="logout">退出登录</button>
          </div>
        </div>
      </div>
    </header>

    <main class="main" @click="noticeOpen = false; menuOpen = false">
      <div class="crumb">
        <template v-for="(c, i) in crumbs" :key="i">
          <router-link v-if="c.to" :to="c.to">{{ c.label }}</router-link>
          <span v-else-if="i < crumbs.length - 1" class="mid">{{ c.label }}</span>
          <span v-else class="current">{{ c.label }}</span>
          <span v-if="i < crumbs.length - 1" class="sep">/</span>
        </template>
      </div>
      <router-view />
    </main>
  </div>
</template>

<style scoped>
.shell {
  min-height: 100vh;
}
.topbar {
  height: var(--topbar-h);
  background: var(--surface);
  border-bottom: 1px solid var(--border);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  z-index: 100;
}
.left {
  display: flex;
  align-items: center;
  gap: 28px;
  min-width: 0;
}
.logo {
  font-size: 18px;
  font-weight: 700;
  color: var(--primary);
  white-space: nowrap;
  cursor: pointer;
}
.nav {
  display: flex;
  align-items: center;
  gap: 4px;
  overflow-x: auto;
}
.nav-item {
  padding: 6px 14px;
  border-radius: var(--radius);
  color: var(--text-2);
  font-size: 14px;
  white-space: nowrap;
}
.nav-item:hover {
  color: var(--primary);
  background: var(--primary-soft);
}
.nav-item.is-active {
  color: var(--primary);
  background: var(--primary-soft);
  font-weight: 600;
}
.right {
  display: flex;
  align-items: center;
  gap: 14px;
}
.bell-wrap, .user-wrap {
  position: relative;
}
.bell {
  border: none;
  background: transparent;
  font-size: 17px;
  cursor: pointer;
  position: relative;
  padding: 4px 6px;
  border-radius: var(--radius);
}
.bell:hover {
  background: var(--primary-soft);
}
.bell .dot {
  position: absolute;
  top: -2px;
  right: -4px;
  min-width: 16px;
  height: 16px;
  padding: 0 4px;
  border-radius: 8px;
  background: var(--danger);
  color: #fff;
  font: 600 10px/16px var(--mono);
}
.notice-panel {
  position: absolute;
  right: 0;
  top: calc(100% + 10px);
  width: 400px;
  max-width: calc(100vw - 32px);
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-2);
  z-index: 200;
  max-height: 460px;
  overflow: auto;
}
.notice-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 14px 18px;
  border-bottom: 1px solid var(--border);
  font-size: 14px;
}
.notice-err {
  padding: 10px 18px;
  font-size: 12.5px;
  color: var(--danger);
  border-bottom: 1px solid var(--border);
}
.notice-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 18px;
  border-bottom: 1px solid var(--border);
}
.notice-item:last-child {
  border-bottom: 0;
}
.notice-body {
  font-size: 13px;
  line-height: 1.7;
}
.notice-actions {
  display: flex;
  gap: 8px;
  flex: none;
}
.user-btn {
  display: flex;
  align-items: center;
  gap: 10px;
  border: none;
  background: transparent;
  cursor: pointer;
  padding: 4px 8px;
  border-radius: var(--radius);
  font: inherit;
}
.user-btn:hover {
  background: var(--primary-soft);
}
.avatar {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
}
.name {
  font-size: 13px;
  font-weight: 600;
}
.user-menu {
  position: absolute;
  right: 0;
  top: calc(100% + 10px);
  width: 240px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-2);
  z-index: 200;
  overflow: hidden;
}
.user-info {
  display: flex;
  flex-direction: column;
  gap: 3px;
  padding: 14px 18px;
  border-bottom: 1px solid var(--border);
  font-size: 13px;
}
.menu-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  border: none;
  background: transparent;
  padding: 12px 18px;
  font: inherit;
  font-size: 13.5px;
  cursor: pointer;
  text-align: left;
}
.menu-row:hover {
  background: var(--primary-soft);
  color: var(--primary);
}
.menu-row.danger:hover {
  color: var(--danger);
  background: var(--danger-soft);
}
.main {
  max-width: 1400px;
  margin: 0 auto;
  padding: 80px 24px 24px;
  min-height: calc(100vh - var(--topbar-h));
}
.crumb {
  font-size: 14px;
  color: var(--text-2);
  margin-bottom: 16px;
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.crumb .mid {
  color: var(--text-2);
}
.crumb .current {
  color: var(--primary);
  font-weight: 600;
}
.crumb .sep {
  color: var(--text-4);
}
</style>
