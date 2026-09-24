import { defineStore } from 'pinia'

/** 岗位画像：切换岗位时归属车队随之调整，ops_admin 空数组表示不限车队 */
export const ROLE_PROFILES = {
  dispatcher: { label: '调度员', fleets: ['华东一队'] },
  fleet_admin: { label: '车队管理员', fleets: ['华东二队'] },
  ops_admin: { label: '运营管理员', fleets: [] as string[] },
} as const

export type RoleKey = keyof typeof ROLE_PROFILES

export const useSessionStore = defineStore('session', {
  state: () => ({
    operator: '值班管理员',
    shiftLabel: '白班 08:00-20:00',
    scope: '冷链物流温控运营平台',
    role: 'ops_admin' as RoleKey,
    fleets: [] as string[],
  }),
  getters: {
    canOperate: (state) => state.operator.length > 0,
    roleLabel: (state) => ROLE_PROFILES[state.role].label,
    fleetLabel: (state) => (state.role === 'ops_admin' ? '全部车队' : state.fleets.join('、') || '未分配车队'),
  },
  actions: {
    setShift(label: string) {
      this.shiftLabel = label
    },
    setRole(role: RoleKey) {
      this.role = role
      this.fleets = [...ROLE_PROFILES[role].fleets]
    },
  },
})
