/* 审计日志 store: 记录由后端自动落库, 前端只做查询展示 */
import { defineStore } from 'pinia'
import { get } from '@/api/http'

export interface AuditRecord {
  id: number
  createdAt: string
  userName: string
  action: string
  teamId?: number | null
  teamName: string
  target: string
  success: boolean
}

export interface AuditQuery {
  teamId?: number | string
  action?: string
  kw?: string
  page?: number
  pageSize?: number
}

export const useAuditStore = defineStore('audit', {
  state: () => ({
    records: [] as AuditRecord[],
    total: 0,
    actions: [] as string[],   // 可选动作清单 (后端返回)
  }),
  actions: {
    async fetchRecords(q: AuditQuery = {}) {
      const data = await get<{ total: number; items: AuditRecord[]; actions: string[] }>('/audit', {
        team_id: q.teamId || undefined,
        action: q.action || undefined,
        kw: q.kw || undefined,
        page: q.page ?? 1,
        page_size: q.pageSize ?? 10,
      })
      this.records = data.items
      this.total = data.total
      this.actions = data.actions
    },
  },
})
