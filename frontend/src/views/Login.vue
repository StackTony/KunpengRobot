<template>
  <div class="login-page">
    <el-card class="login-card" :body-style="{ padding: '36px 32px' }">
      <div class="login-brand">
        <div class="login-mark">鲲</div>
        <div class="login-title">鲲鹏运维平台</div>
        <div class="login-sub">故障诊断 · 智能巡检 · 性能分析</div>
      </div>
      <el-form :model="form" label-position="top" size="large" @submit.prevent="onLogin">
        <el-form-item label="用户名">
          <el-input v-model="form.username" placeholder="请输入用户名" :prefix-icon="User" />
        </el-form-item>
        <el-form-item label="密码">
          <el-input v-model="form.password" type="password" show-password
                    placeholder="请输入密码" :prefix-icon="Lock" @keyup.enter="onLogin" />
        </el-form-item>
        <el-button type="primary" size="large" style="width: 100%; margin-top: 4px"
                   :loading="loading" @click="onLogin">
          登 录
        </el-button>
      </el-form>
      <div class="login-footnote">KunpengRobot · 鲲鹏运维平台</div>
    </el-card>
  </div>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { User, Lock } from '@element-plus/icons-vue'
import { useAuthStore } from '../stores/auth'

const form = reactive({ username: '', password: '' })
const loading = ref(false)
const router = useRouter()
const auth = useAuthStore()

async function onLogin() {
  loading.value = true
  try {
    await auth.login(form.username, form.password)
    router.push({ name: 'dashboard' })
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '登录失败')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-page {
  display: flex;
  justify-content: center;
  align-items: center;
  height: 100vh;
  background:
    radial-gradient(ellipse at 20% 30%, rgba(90, 127, 189, 0.25), transparent 55%),
    radial-gradient(ellipse at 80% 75%, rgba(47, 92, 172, 0.2), transparent 50%),
    linear-gradient(160deg, #141a28 0%, #1d2433 100%);
}

.login-card {
  width: 400px;
}

.login-brand {
  text-align: center;
  margin-bottom: 28px;
}

.login-mark {
  width: 52px;
  height: 52px;
  margin: 0 auto 14px;
  border-radius: 12px;
  background: linear-gradient(135deg, #4a79c9, #2f5cac);
  color: #fff;
  font-weight: 700;
  font-size: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.login-title {
  font-size: 18px;
  font-weight: 600;
  color: var(--kp-text-primary);
}

.login-sub {
  margin-top: 6px;
  font-size: 12px;
  color: #909399;
  letter-spacing: 2px;
}

.login-footnote {
  margin-top: 20px;
  text-align: center;
  font-size: 11px;
  color: #c0c4cc;
}
</style>
