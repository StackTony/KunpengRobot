/* 资产库 + 解析任务 store: 任务不再内嵌全量事件, 分页/聚合走后端 */
import { defineStore } from 'pinia'
import { get, post, put, del } from '@/api/http'
import type { AssetInfo } from '@/stores/teams'

export interface AnalyzeTask {
  id: string
  type: string
  status: string              // pending / running / done / failed / cancelled / interrupted
  filename: string
  progress: number
  error: string
  createdAt: string
  finishedAt?: string | null
  name: string
  parserType: string
  assetId?: number | null
  logSize: number
  eventCount: number
  creatorName: string
  assetName: string
}

export interface TaskListPage {
  total: number
  items: AnalyzeTask[]
  sparks: Record<string, Record<string, any>[]>   // taskId -> 16 桶 [{t,label,total,critical,error,...}]
}

export interface AssetTasksQuery {
  statusFilter?: string
  parserType?: string
  kw?: string
  page?: number
  pageSize?: number
}

export const useAssetsStore = defineStore('assets', {
  state: () => ({
    assets: [] as AssetInfo[],                          // 已加载过的资产库 (带 teamId)
    tasks: {} as Record<string, AnalyzeTask>,           // 任务缓存 (详情页轮询/面包屑用)
    lastPage: null as TaskListPage | null,              // 最近一次资产任务分页结果
    loading: false,
  }),
  getters: {
    assetById(state) {
      return (id: string | number) => state.assets.find((a) => String(a.id) === String(id))
    },
    taskCached(state) {
      return (taskId: string | number) => state.tasks[String(taskId)]
    },
  },
  actions: {
    _mergeAssets(list: AssetInfo[]) {
      for (const a of list) {
        const i = this.assets.findIndex((x) => x.id === a.id)
        if (i >= 0) this.assets[i] = a
        else this.assets.push(a)
      }
    },
    /* 拉取某团队的资产库列表 (团队详情/向导入口用) */
    async fetchTeamAssets(teamId: string | number) {
      const list = await get<AssetInfo[]>(`/teams/${teamId}/assets`)
      this._mergeAssets(list)
      return list
    },
    async fetchAsset(assetId: string | number) {
      const a = await get<AssetInfo>(`/assets/${assetId}`)
      this._mergeAssets([a])
      return a
    },
    async createAsset(teamId: string | number, body: { name: string; desc?: string; ipRange?: string }) {
      const a = await post<AssetInfo>(`/teams/${teamId}/assets`, {
        name: body.name, desc: body.desc ?? '', ip_range: body.ipRange ?? '',
      })
      this._mergeAssets([a])
      return a
    },
    async updateAsset(id: string | number, body: { name: string; desc?: string; ipRange?: string }) {
      const a = await put<AssetInfo>(`/assets/${id}`, {
        name: body.name, desc: body.desc ?? '', ip_range: body.ipRange ?? '',
      })
      this._mergeAssets([a])
      return a
    },
    async removeAsset(id: string | number) {
      await del(`/assets/${id}`)
      this.assets = this.assets.filter((a) => String(a.id) !== String(id))
    },
    /* 资产库任务分页 (服务端筛选 + spark 聚合) */
    async fetchAssetTasks(assetId: string | number, q: AssetTasksQuery = {}) {
      this.loading = true
      try {
        const page = await get<TaskListPage>(`/assets/${assetId}/tasks`, {
          status_filter: q.statusFilter || undefined,
          parser_type: q.parserType || undefined,
          kw: q.kw || undefined,
          page: q.page ?? 1,
          page_size: q.pageSize ?? 10,
        })
        this.lastPage = page
        for (const t of page.items) this.tasks[t.id] = t
        return page
      } finally {
        this.loading = false
      }
    },
    /* 任务详情 (含可见性校验, 403 时抛错) */
    async fetchTask(taskId: string) {
      const t = await get<AnalyzeTask>(`/tasks/${taskId}`)
      this.tasks[taskId] = t
      return t
    },
    async removeTask(taskId: string) {
      await del(`/tasks/${taskId}`)
      delete this.tasks[taskId]
    },
  },
})
