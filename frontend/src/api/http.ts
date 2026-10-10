/* Axios 实例: Bearer 注入 + 响应驼峰化 + 401 刷新重放 */
import axios from 'axios'

export const TOKEN_KEY = 'kp_token'
export const REFRESH_KEY = 'kp_refresh'

const http = axios.create({ baseURL: '/api', timeout: 60000 })

http.interceptors.request.use((config) => {
  const token = localStorage.getItem(TOKEN_KEY)
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

let refreshing: Promise<boolean> | null = null

async function tryRefresh(): Promise<boolean> {
  const refresh = localStorage.getItem(REFRESH_KEY)
  if (!refresh) return false
  try {
    const { data } = await axios.post('/api/auth/refresh', { refresh_token: refresh })
    localStorage.setItem(TOKEN_KEY, data.access_token)
    localStorage.setItem(REFRESH_KEY, data.refresh_token)
    return true
  } catch {
    return false
  }
}

http.interceptors.response.use(
  (res) => res,
  async (err) => {
    const original = err.config
    if (err.response?.status === 401 && !original._retried) {
      original._retried = true
      refreshing = refreshing ?? tryRefresh().finally(() => { refreshing = null })
      if (await refreshing) return http(original) // 重放原请求
      localStorage.removeItem(TOKEN_KEY)
      localStorage.removeItem(REFRESH_KEY)
      if (location.hash !== '#/login') location.hash = '#/login'
    }
    return Promise.reject(err)
  },
)

/* ---------- 后端 snake_case → 前端 camelCase 深度转换 ---------- */
/* fields/sparks/threshold 等键为运行时数据字典, 其键不做转换 */
const SKIP_KEYS = new Set(['fields', 'sparks', 'threshold', 'pref_value', 'prefValue'])

function camelize(value: unknown, parentKey = ''): unknown {
  if (Array.isArray(value)) return value.map((v) => camelize(v))
  if (value && typeof value === 'object') {
    if (SKIP_KEYS.has(parentKey)) return value
    const out: Record<string, unknown> = {}
    for (const [k, v] of Object.entries(value as Record<string, unknown>)) {
      const ck = SKIP_KEYS.has(k) ? k : k.replace(/_([a-z0-9])/g, (_, c: string) => c.toUpperCase())
      out[ck] = camelize(v, k)
    }
    return out
  }
  return value
}

/** 抛出后端 detail 错误信息 (统一给视图层 catch) */
export function apiError(e: unknown): string {
  if (axios.isAxiosError(e)) {
    const d = e.response?.data as { detail?: string } | undefined
    if (typeof d?.detail === 'string') return d.detail
  }
  return (e as Error)?.message || '请求失败'
}

/** 发起 GET 请求并自动驼峰化响应体 */
export async function get<T = any>(url: string, params?: Record<string, unknown>): Promise<T> {
  const res = await http.get(url, { params })
  return camelize(res.data) as T
}

/** 发起 POST 请求并自动驼峰化响应体 */
export async function post<T = any>(url: string, body?: unknown): Promise<T> {
  const res = await http.post(url, body)
  return camelize(res.data) as T
}

/** 发起 PUT 请求并自动驼峰化响应体 */
export async function put<T = any>(url: string, body?: unknown): Promise<T> {
  const res = await http.put(url, body)
  return camelize(res.data) as T
}

/** 发起 DELETE 请求并自动驼峰化响应体 */
export async function del<T = any>(url: string): Promise<T> {
  const res = await http.delete(url)
  return camelize(res.data) as T
}

export default http
