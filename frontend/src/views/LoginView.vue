<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useRbacStore } from '@/stores/rbac'
import { apiError } from '@/api/http'

const rr = useRouter()
const rbac = useRbacStore()

/* 演示账号 (后端种子数据, 密码统一 demo123) */
const DEMO_ACCOUNTS = [
  { username: 'guchuang', name: '顾创建', desc: '团队创建者 · 运维主管', hue: 212 },
  { username: 'jiangguanli', name: '蒋管理', desc: '团队管理员 · 高级运维', hue: 268 },
  { username: 'sunputong', name: '孙普通', desc: '普通用户 · 运维工程师', hue: 20 },
  { username: 'zhangshenpi', name: '张审批', desc: '团队管理员 · 系统管理员', hue: 155 },
  { username: 'liyiban', name: '李一般', desc: '普通用户 · 运维工程师', hue: 330 },
]

const form = reactive({ username: '', password: '' })
const showPwd = ref(false)
const loading = ref(false)
const err = ref('')

async function login(username: string, password: string) {
  if (loading.value) return
  loading.value = true
  err.value = ''
  try {
    await rbac.login(username, password)
    rr.push('/dashboard')
  } catch (e) {
    err.value = apiError(e)
  } finally {
    loading.value = false
  }
}

function fillDemo(acc: { username: string }) {
  form.username = acc.username
  form.password = 'demo123'
  showPwd.value = true
  login(form.username, form.password)
}

function submit() {
  if (!form.username.trim() || !form.password) {
    err.value = '请输入用户名和密码'
    return
  }
  login(form.username.trim(), form.password)
}
</script>

<template>
  <div class="login">
    <div class="panel">
      <div class="brand">
        <span class="mark">鲲</span>
        <div>
          <h1>鲲鹏运维平台</h1>
          <p>服务器日志解析分析 · 团队协作 · 智能诊断</p>
        </div>
      </div>

      <form class="form" @submit.prevent="submit">
        <div class="o-form-item">
          <label class="o-form-item__label required">用户名</label>
          <input v-model="form.username" class="o-input" placeholder="用户名" autocomplete="username" />
        </div>
        <div class="o-form-item">
          <label class="o-form-item__label required">密码</label>
          <div class="pwd-row">
            <input
              v-model="form.password"
              class="o-input"
              :type="showPwd ? 'text' : 'password'"
              placeholder="密码"
              autocomplete="current-password"
            />
            <button type="button" class="o-btn o-btn--sm" @click="showPwd = !showPwd">
              {{ showPwd ? '隐藏' : '显示' }}
            </button>
          </div>
        </div>
        <div v-if="err" class="err">⚠ {{ err }}</div>
        <button class="o-btn o-btn--primary o-btn--lg" type="submit" :disabled="loading">
          <span v-if="!loading">登 录</span>
          <span v-else class="o-row" style="gap: 8px"><span class="spin" />登录中…</span>
        </button>
      </form>

      <div class="divider"><span>演示账号 · 密码统一 demo123</span></div>

      <div class="accounts">
        <button
          v-for="acc in DEMO_ACCOUNTS"
          :key="acc.username"
          class="account"
          type="button"
          :disabled="loading"
          @click="fillDemo(acc)"
        >
          <span class="avatar" :style="{ background: `hsl(${acc.hue}, 60%, 45%)` }">{{ acc.name.slice(0, 1) }}</span>
          <span class="info">
            <b>{{ acc.name }} <span class="o-mono o-text-3">{{ acc.username }}</span></b>
            <span class="o-text-3">{{ acc.desc }}</span>
          </span>
          <span class="go">进入 →</span>
        </button>
      </div>

      <div class="foot o-mono">
        团队三角色：创建者 / 管理员 / 普通用户 ｜ 申请与邀请在右上角 🔔 处理
      </div>
    </div>
  </div>
</template>

<style scoped>
.login {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background:
    radial-gradient(700px 360px at 12% 0%, rgba(30, 111, 255, 0.14), transparent 60%),
    radial-gradient(600px 300px at 90% 100%, rgba(77, 143, 255, 0.16), transparent 60%),
    var(--bg);
  padding: 24px;
}
.panel {
  width: 560px;
  max-width: 100%;
  max-height: calc(100vh - 48px);
  overflow: auto;
  background: var(--surface);
  border-radius: var(--radius-xl);
  box-shadow: var(--shadow-2);
  padding: 32px 36px;
}
.brand {
  display: flex;
  gap: 14px;
  align-items: center;
  margin-bottom: 22px;
}
.mark {
  width: 46px;
  height: 46px;
  border-radius: var(--radius);
  background: var(--primary);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
  font-weight: 700;
}
.brand h1 {
  font-size: 18px;
  font-weight: 700;
  color: var(--primary);
}
.brand p {
  font-size: 12.5px;
  color: var(--text-3);
  margin-top: 2px;
}
.form {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.pwd-row {
  display: flex;
  gap: 8px;
}
.pwd-row .o-input {
  flex: 1;
}
.err {
  color: var(--danger);
  font-size: 13px;
  margin-bottom: 10px;
}
.o-btn--lg {
  height: 42px;
  font-size: 15px;
  justify-content: center;
  margin-top: 6px;
}
.divider {
  display: flex;
  align-items: center;
  gap: 12px;
  margin: 22px 0 14px;
  color: var(--text-4);
  font-size: 12px;
}
.divider::before,
.divider::after {
  content: '';
  flex: 1;
  height: 1px;
  background: var(--border);
}
.accounts {
  display: grid;
  grid-template-columns: 1fr;
  gap: 8px;
}
.account {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 14px;
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  background: var(--surface);
  cursor: pointer;
  text-align: left;
  font: inherit;
  transition: all 0.2s;
}
.account:hover {
  border-color: var(--primary);
  background: var(--primary-soft);
  transform: translateY(-1px);
  box-shadow: var(--shadow-1);
}
.avatar {
  width: 34px;
  height: 34px;
  border-radius: 50%;
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  flex: none;
}
.info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
  font-size: 13px;
}
.info b {
  font-size: 13.5px;
}
.go {
  flex: none;
  font-size: 12px;
  color: var(--primary);
}
.foot {
  margin-top: 18px;
  color: var(--text-4);
  text-align: center;
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
