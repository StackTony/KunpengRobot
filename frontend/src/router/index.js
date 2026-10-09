import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const routes = [
  { path: '/login', name: 'login', component: () => import('../views/Login.vue') },
  {
    path: '/',
    component: () => import('../views/Layout.vue'),
    children: [
      { path: '', redirect: '/dashboard' },
      { path: 'dashboard', name: 'dashboard', component: () => import('../views/Dashboard.vue'), meta: { title: '总览' } },
      { path: 'diagnosis', name: 'diagnosis', component: () => import('../views/Diagnosis.vue'), meta: { title: '故障诊断' } },
      { path: 'inspection', name: 'inspection', component: () => import('../views/Inspection.vue'), meta: { title: '智能巡检' } },
      { path: 'metrics', name: 'metrics', component: () => import('../views/Metrics.vue'), meta: { title: '性能图表' } },
      { path: 'rules', name: 'rules', component: () => import('../views/Rules.vue'), meta: { title: '规则管理', perm: 'rule:manage' } },
    ],
  },
]

const router = createRouter({ history: createWebHistory(), routes })

router.beforeEach((to) => {
  const auth = useAuthStore()
  if (to.name !== 'login' && !auth.token) return { name: 'login' }
  if (to.meta.perm && !auth.permissions.includes(to.meta.perm) && !auth.permissions.includes('admin')) {
    return { name: 'dashboard' }
  }
})

export default router
