<template>
  <el-container style="height: 100vh">
    <!-- 深色侧边栏 -->
    <el-aside width="232px" class="kp-sidebar">
      <div class="brand">
        <div class="brand-mark">鲲</div>
        <div>
          <div class="brand-name">鲲鹏运维平台</div>
          <div class="brand-sub">KunpengRobot</div>
        </div>
      </div>
      <el-menu router :default-active="$route.path">
        <el-menu-item index="/dashboard">
          <el-icon><Odometer /></el-icon><span>总览</span>
        </el-menu-item>
        <el-menu-item index="/diagnosis">
          <el-icon><Search /></el-icon><span>故障诊断</span>
        </el-menu-item>
        <el-menu-item index="/inspection">
          <el-icon><Checked /></el-icon><span>智能巡检</span>
        </el-menu-item>
        <el-menu-item index="/metrics">
          <el-icon><TrendCharts /></el-icon><span>性能图表</span>
        </el-menu-item>
        <el-menu-item v-if="canManageRules" index="/rules">
          <el-icon><SetUp /></el-icon><span>规则管理</span>
        </el-menu-item>
      </el-menu>
    </el-aside>

    <el-container>
      <!-- 头部: 页面标题 + 用户 -->
      <el-header class="kp-header">
        <div class="page-title">{{ $route.meta.title || '' }}</div>
        <el-dropdown @command="onCommand">
          <span class="user-entry">
            <span class="avatar">{{ initial }}</span>
            <span class="username">{{ auth.user?.display_name || auth.user?.username }}</span>
            <el-icon><ArrowDown /></el-icon>
          </span>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item disabled>
                {{ (auth.user?.roles || []).join(' / ') || '普通用户' }}
              </el-dropdown-item>
              <el-dropdown-item divided command="logout">
                <el-icon><SwitchButton /></el-icon>退出登录
              </el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </el-header>

      <el-main class="kp-main">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup>
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const router = useRouter()

const canManageRules = computed(() =>
  auth.isAdmin || auth.permissions.includes('rule:manage'))
const initial = computed(() =>
  (auth.user?.display_name || auth.user?.username || '?').charAt(0).toUpperCase())

async function onCommand(cmd) {
  if (cmd === 'logout') {
    await auth.logout()
    router.push({ name: 'login' })
  }
}
</script>

<style scoped>
.kp-sidebar {
  background: var(--kp-bg-sidebar);
  display: flex;
  flex-direction: column;
}

.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 18px 20px 16px;
}

.brand-mark {
  width: 34px;
  height: 34px;
  border-radius: 8px;
  background: linear-gradient(135deg, #4a79c9, #2f5cac);
  color: #fff;
  font-weight: 700;
  font-size: 17px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.brand-name {
  color: #fff;
  font-size: 14px;
  font-weight: 600;
  line-height: 1.3;
}

.brand-sub {
  color: #6b7590;
  font-size: 10px;
  letter-spacing: 0.5px;
}

.kp-header {
  height: 56px;
  background: #fff;
  border-bottom: 1px solid var(--kp-border-card);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
}

.page-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--kp-text-primary);
}

.user-entry {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  color: var(--kp-text-primary);
  outline: none;
}

.avatar {
  width: 30px;
  height: 30px;
  border-radius: 50%;
  background: var(--el-color-primary-light-8);
  color: var(--el-color-primary);
  font-weight: 600;
  font-size: 13px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.username {
  font-size: 13px;
}

.kp-main {
  background: var(--kp-bg-canvas);
  padding: 20px 24px;
}
</style>
