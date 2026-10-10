/* 平台用户 store: 真实登录 (JWT) + 我的团队角色缓存 + 邀请候选用户 */
import { defineStore } from 'pinia'
import { get, post, TOKEN_KEY, REFRESH_KEY } from '@/api/http'

export interface UserBrief {
  id: number
  name: string
  email: string
  title: string
  dept: string
  avatarHue: number
}

export interface CurrentUser extends UserBrief {
  username: string
  roles: string[]
  permissions: string[]
}

/* 平台级基础权限: 所有登录用户可进入工作台、查看团队、创建团队; 资源级权限看团队角色 */
export const USER_PLATFORM_PERMS = ['dashboard:view', 'team:view', 'team:create']

export const useRbacStore = defineStore('rbac', {
  state: () => ({
    users: [] as UserBrief[],          // 邀请候选 (惰性加载 GET /users)
    me: null as CurrentUser | null,
    currentUserId: 0 as number,
    myTeamRoles: {} as Record<string, string>, // teamId -> role
    restored: false,                   // 页面刷新后是否已尝试恢复会话
  }),
  getters: {
    currentUser(state): CurrentUser | null {
      return state.me
    },
    isPlatformAdmin(state): boolean {
      return !!state.me && (state.me.roles.includes('admin') || state.me.permissions.includes('*'))
    },
  },
  actions: {
    async login(username: string, password: string) {
      const data = await post<{ accessToken: string; refreshToken: string }>('/auth/login', {
        username, password,
      })
      localStorage.setItem(TOKEN_KEY, data.accessToken)
      localStorage.setItem(REFRESH_KEY, data.refreshToken)
      await this.fetchMe()
    },
    async fetchMe() {
      const data = await get<any>('/auth/me')
      this.me = {
        id: data.id,
        username: data.username,
        name: data.displayName || data.username,
        email: data.email,
        title: data.title ?? '',
        dept: data.dept ?? '',
        avatarHue: data.avatarHue ?? 212,
        roles: data.roles ?? [],
        permissions: data.permissions ?? [],
      }
      this.currentUserId = data.id
      const roles: Record<string, string> = {}
      for (const tr of data.teamRoles ?? []) roles[String(tr.teamId)] = tr.role
      this.myTeamRoles = roles
    },
    /** 页面刷新后按本地 token 恢复会话; 失败返回 false */
    async restore(): Promise<boolean> {
      if (!localStorage.getItem(TOKEN_KEY)) {
        this.restored = true
        return false
      }
      try {
        await this.fetchMe()
        return true
      } catch {
        localStorage.removeItem(TOKEN_KEY)
        localStorage.removeItem(REFRESH_KEY)
        return false
      } finally {
        this.restored = true
      }
    },
    async logout() {
      try {
        await post('/auth/logout')
      } catch {
        /* 黑名单失败不阻断登出 */
      }
      localStorage.removeItem(TOKEN_KEY)
      localStorage.removeItem(REFRESH_KEY)
      this.me = null
      this.currentUserId = 0
      this.myTeamRoles = {}
    },
    async ensureUsers() {
      if (this.users.length) return
      this.users = await get<UserBrief[]>('/users')
    },
    userById(id: number | string): UserBrief | undefined {
      return this.users.find((u) => String(u.id) === String(id))
    },
    /** 平台级权限 (菜单守卫用); 团队资源权限请用 teamsStore.can() */
    hasPerm(perm: string): boolean {
      if (!this.me) return false
      if (this.isPlatformAdmin) return true
      return USER_PLATFORM_PERMS.includes(perm) || this.me.permissions.includes(perm)
    },
  },
})
