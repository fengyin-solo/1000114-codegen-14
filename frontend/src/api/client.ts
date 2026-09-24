/** 统一请求封装：拼后端地址、带上当前岗位身份、抛网络错误、给页脚留一句可读的说明。 */
const API_BASE = import.meta.env.VITE_API_BASE ?? ''

/** 读取当前岗位身份键：请求头 X-Principal 是后端分权判定的依据。 */
export function currentPrincipalKey(): string {
  return localStorage.getItem('dispatch.principal') ?? 'dispatcher_a'
}

export function withPrincipal(path: string): string {
  // 导出等走 window.open 的场景无法带请求头，用 query 参数兜底。
  const separator = path.includes('?') ? '&' : '?'
  return `${path}${separator}principal=${encodeURIComponent(currentPrincipalKey())}`
}

export function request(path: string, init?: RequestInit): Promise<Response> {
  const url = path.startsWith('http') ? path : `${API_BASE}${path}`
  const headers = new Headers(init?.headers ?? { 'Content-Type': 'application/json' })
  if (!headers.has('X-Principal')) {
    headers.set('X-Principal', currentPrincipalKey())
  }
  return fetch(url, { ...init, headers }).catch((error: unknown) => {
    const detail = error instanceof Error ? error.message : '请求未送达'
    throw new Error(`接口请求失败：${detail}`)
  })
}

export async function fetchJson<T>(path: string): Promise<T> {
  const response = await request(path)
  if (!response.ok) {
    throw new Error(`接口返回 ${response.status}，数据未更新`)
  }
  return (await response.json()) as T
}
