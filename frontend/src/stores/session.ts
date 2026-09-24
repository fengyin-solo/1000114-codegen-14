import { defineStore } from 'pinia'

/** 岗位身份键，需要与后端 app/auth.py 的 PRINCIPALS 保持一致。 */
export type PrincipalKey = 'dispatcher_a' | 'manager_a' | 'dispatcher_b' | 'ops_admin'

export interface PrincipalOption {
  key: PrincipalKey
  name: string
  role: string
  fleet: string | null
}

/** 岗位目录：切换岗位即以此重算调度派单页的可见/可改边界。 */
export const PRINCIPAL_OPTIONS: PrincipalOption[] = [
  { key: 'dispatcher_a', name: '张调度', role: '调度员', fleet: '一车队' },
  { key: 'manager_a', name: '李队长', role: '车队管理员', fleet: '一车队' },
  { key: 'dispatcher_b', name: '王调度', role: '调度员', fleet: '二车队' },
  { key: 'ops_admin', name: '周运营', role: '运营管理员', fleet: null },
]

const STORAGE_KEY = 'dispatch.principal'

export function getStoredPrincipalKey(): PrincipalKey {
  const raw = localStorage.getItem(STORAGE_KEY)
  return PRINCIPAL_OPTIONS.some((item) => item.key === raw)
    ? (raw as PrincipalKey)
    : 'dispatcher_a'
}

export const useSessionStore = defineStore('session', {
  state: () => {
    const principalKey = getStoredPrincipalKey()
    const principal = PRINCIPAL_OPTIONS.find((item) => item.key === principalKey)!
    return {
      principalKey,
      principalName: principal.name,
      role: principal.role,
      fleet: principal.fleet,
      shiftLabel: '白班 08:00-20:00',
      scope: '冷链物流温控运营平台',
    }
  },
  getters: {
    canOperate: (state) => state.principalKey.length > 0,
    /** 顶栏展示：姓名 · 岗位（归属车队）。 */
    operator(state): string {
      return state.fleet
        ? `${state.principalName}（${state.role}·${state.fleet}）`
        : `${state.principalName}（${state.role}）`
    },
  },
  actions: {
    setPrincipal(key: PrincipalKey) {
      const principal = PRINCIPAL_OPTIONS.find((item) => item.key === key)
      if (!principal || principal.key === this.principalKey) return
      this.principalKey = principal.key
      this.principalName = principal.name
      this.role = principal.role
      this.fleet = principal.fleet
      localStorage.setItem(STORAGE_KEY, principal.key)
    },
    setShift(label: string) {
      this.shiftLabel = label
    },
  },
})
