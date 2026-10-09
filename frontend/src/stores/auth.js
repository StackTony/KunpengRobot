import { defineStore } from 'pinia'
import http from '../api/http'

export const useAuthStore = defineStore('auth', {
  state: () => ({
    token: localStorage.getItem('kp_token') || '',
    refreshToken: localStorage.getItem('kp_refresh') || '',
    user: JSON.parse(localStorage.getItem('kp_user') || 'null'),
  }),
  getters: {
    permissions: (s) => s.user?.permissions || [],
    isAdmin: (s) => (s.user?.roles || []).includes('admin'),
  },
  actions: {
    async login(username, password) {
      const { data } = await http.post('/auth/login', { username, password })
      this.token = data.access_token
      this.refreshToken = data.refresh_token
      localStorage.setItem('kp_token', this.token)
      localStorage.setItem('kp_refresh', this.refreshToken)
      await this.fetchMe()
    },
    async fetchMe() {
      const { data } = await http.get('/auth/me')
      this.user = data
      localStorage.setItem('kp_user', JSON.stringify(data))
    },
    async tryRefresh() {
      if (!this.refreshToken) return false
      try {
        const { data } = await http.post('/auth/refresh', { refresh_token: this.refreshToken })
        this.token = data.access_token
        this.refreshToken = data.refresh_token
        localStorage.setItem('kp_token', this.token)
        localStorage.setItem('kp_refresh', this.refreshToken)
        return true
      } catch {
        return false
      }
    },
    async logout() {
      try { await http.post('/auth/logout') } catch { /* ignore */ }
      this.doClear()
    },
    doClear() {
      this.token = ''
      this.refreshToken = ''
      this.user = null
      localStorage.removeItem('kp_token')
      localStorage.removeItem('kp_refresh')
      localStorage.removeItem('kp_user')
    },
  },
})
