import axios, { AxiosError } from 'axios'

export const TOKEN_KEY = 'sentinel.token'

export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api/v1'

export const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 120_000,
  headers: { 'Content-Type': 'application/json' },
})

api.interceptors.request.use((config) => {
  const token = localStorage.getItem(TOKEN_KEY)
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

api.interceptors.response.use(
  (response) => response,
  (error: AxiosError) => {
    if (error.response?.status === 401 && !window.location.pathname.startsWith('/login')) {
      localStorage.removeItem(TOKEN_KEY)
      window.location.assign('/login')
    }
    return Promise.reject(error)
  },
)

export function errorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const detail = (error.response?.data as { detail?: unknown } | undefined)?.detail
    if (typeof detail === 'string') return detail
    if (Array.isArray(detail)) {
      return detail
        .map((item) => {
          if (item && typeof item === 'object' && 'msg' in item && 'loc' in item) {
            const loc = (item as { loc: (string | number)[] }).loc
            return `${loc.slice(1).join('.')}: ${(item as { msg: string }).msg}`
          }
          return JSON.stringify(item)
        })
        .join('; ')
    }
    if (error.code === 'ECONNABORTED') return 'Request timed out. The server may still be processing it.'
    if (!error.response) return 'Cannot reach the API. Confirm the backend is running.'
    return `${error.response.status} ${error.response.statusText}`
  }
  if (error instanceof Error) return error.message
  return 'Unexpected error'
}
