import { createRouter, createWebHashHistory, type RouteRecordRaw } from 'vue-router'
import { useRbacStore } from '@/stores/rbac'

const routes: RouteRecordRaw[] = [
  { path: '/login', name: 'login', component: () => import('@/views/LoginView.vue'), meta: { public: true } },
  {
    path: '/',
    component: () => import('@/layouts/DefaultLayout.vue'),
    redirect: '/dashboard',
    children: [
      { path: 'dashboard', name: 'dashboard', component: () => import('@/views/DashboardView.vue'), meta: { title: '工作台', perm: 'dashboard:view', menu: true } },
      { path: 'teams', name: 'teams', component: () => import('@/views/TeamsView.vue'), meta: { title: '团队', perm: 'team:view', menu: true } },
      { path: 'teams/:id', name: 'team-detail', component: () => import('@/views/TeamDetailView.vue'), meta: { title: '团队详情', perm: 'team:view' } },
      { path: 'teams/:id/new-task', name: 'task-new', component: () => import('@/views/TaskWizardView.vue'), meta: { title: '创建解析任务', perm: 'task:create' } },
      { path: 'tasks/:taskId', name: 'task-result', component: () => import('@/views/TaskResultView.vue'), meta: { title: '解析结果', perm: 'task:view' } },
    ],
  },
  { path: '/:pathMatch(.*)*', redirect: '/dashboard' },
]

export const router = createRouter({
  history: createWebHashHistory(),
  routes,
})

router.beforeEach(async (to) => {
  const rbac = useRbacStore()
  if (to.meta.public) return true
  /* 无会话: 先尝试按本地 token 恢复 (页面刷新场景), 仍失败则回登录页 */
  if (!rbac.me) {
    if (!rbac.restored) await rbac.restore()
    if (!rbac.me) return { name: 'login' }
  }
  /* 平台级守卫只管菜单路由 (工作台/团队); 团队资源路由由页面内按团队角色 (can()) 控制 */
  const perm = to.meta.perm as string | undefined
  if (to.meta.menu && perm && !rbac.hasPerm(perm)) {
    return { name: 'dashboard', query: { denied: to.meta.title as string } }
  }
  return true
})
