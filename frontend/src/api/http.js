import axios from 'axios'
import { useAuthStore } from '../stores/auth'
import router from '../router'

const http = axios.create({ baseURL: '/api', timeout: 60000 })

http.interceptors.request.use((config) => {
  const auth = useAuthStore()
  if (auth.token) config.headers.Authorization = `Bearer ${auth.token}`
  return config
})

http.interceptors.response.use(
  (res) => res,
  async (err) => {
    if (err.response?.status === 401) {
      const auth = useAuthStore()
      const refreshed = await auth.tryRefresh()
      if (refreshed) return http(err.config) // 重放原请求
      auth.logout()
      router.push({ name: 'login' })
    }
    return Promise.reject(err)
  }
)

export default http
