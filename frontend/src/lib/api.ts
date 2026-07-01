// 统一 fetch 封装；dev 走 vite proxy，prod 同源
const BASE = ''
const getLang = () => {
  try {
    return localStorage.getItem('sparkling-lang') === 'en' ? 'en' : 'zh'
  } catch {
    return 'zh'
  }
}

interface ApiErrorBody {
  message?: string
  detail?: string
}

export class ApiError extends Error {
  status?: number

  constructor(message: string, status?: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

const parseErrorMessage = async (res: Response): Promise<string> => {
  const text = await res.text()
  if (!text) return `${res.status} ${res.statusText}`
  try {
    const body = JSON.parse(text) as ApiErrorBody
    return body.message || body.detail || text
  } catch {
    return text
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response
  try {
    res = await fetch(BASE + path, {
      ...init,
      headers: { 'Content-Type': 'application/json', ...(init?.headers || {}) },
    })
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error)
    throw new ApiError(getLang() === 'en' ? `Cannot connect to backend service: ${message}` : `无法连接后端服务：${message}`)
  }
  if (!res.ok) throw new ApiError(await parseErrorMessage(res), res.status)
  return res.status === 204 ? (undefined as T) : ((await res.json()) as T)
}

export const api = {
  get: <T,>(p: string) => request<T>(p),
  post: <T,>(p: string, body?: unknown) =>
    request<T>(p, { method: 'POST', body: body ? JSON.stringify(body) : undefined }),
  put: <T,>(p: string, body?: unknown) =>
    request<T>(p, { method: 'PUT', body: body ? JSON.stringify(body) : undefined }),
  patch: <T,>(p: string, body?: unknown) =>
    request<T>(p, { method: 'PATCH', body: body ? JSON.stringify(body) : undefined }),
  del: <T,>(p: string) => request<T>(p, { method: 'DELETE' }),
}
