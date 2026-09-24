/** 统一请求封装：拼后端地址、附带操作人身份、抛网络错误、给页脚留一句可读的说明。 */
import { useSessionStore } from '@/stores/session'

const API_BASE = import.meta.env.VITE_API_BASE ?? ''

/** 把当前岗位与归属车队写进请求头，后端据此做越权判定；pinia 未就绪时静默降级。
 *  车队名含中文，按 percent-encode 编码，避免 HTTP 头 latin-1 解码后变乱码。 */
function identityHeaders(): Record<string, string> {
  try {
    const session = useSessionStore()
    return {
      'X-Operator-Role': session.role,
      'X-Operator-Fleets': session.fleets.map(encodeURIComponent).join(','),
    }
  } catch {
    return {}
  }
}

export function request(path: string, init?: RequestInit): Promise<Response> {
  const url = path.startsWith('http') ? path : `${API_BASE}${path}`
  return fetch(url, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...identityHeaders(),
      ...((init?.headers as Record<string, string>) ?? {}),
    },
  }).catch((error: unknown) => {
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
