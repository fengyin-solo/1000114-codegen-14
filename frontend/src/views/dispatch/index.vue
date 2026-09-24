<template>
  <section class="page" data-module="dispatch">
    <header class="page-head">
      <div>
        <h2>调度派单管理</h2>
        <p class="page-desc">
          维护调度单，围绕调度单号、关联订单、配送线路、指派车辆做登记、筛选与状态流转。
          当前岗位：{{ permissions?.role_label ?? '—' }}（{{ session.fleetLabel }}），越权行敏感字段已脱敏。
        </p>
      </div>
      <div class="page-actions">
        <button
          class="btn primary"
          type="button"
          :disabled="!creatableFleets.length"
          :title="creatableFleets.length ? '' : '当前岗位没有可下单的归属车队'"
          @click="openCreate"
        >
          登记调度单
        </button>
        <button class="btn" type="button" @click="exportRows">导出调度派单清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label v-for="field in filterFields" :key="field" class="filter-item">
        <span>{{ field }}</span>
        <input v-model="filters[field]" :placeholder="`按${field}检索`" />
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">{{ row[column] ?? '—' }}</td>
          <td class="row-actions">
            <template v-if="rowActions(row).length">
              <button
                v-for="action in rowActions(row)"
                :key="action"
                class="link"
                type="button"
                @click="runAction(action, row)"
              >
                {{ action }}
              </button>
            </template>
            <span v-else class="readonly-tag" title="非本车队的单子只读">只读</span>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无调度派单数据，可先登记调度单</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条调度派单记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
      <span v-else-if="noticeMessage" class="notice-text">{{ noticeMessage }}</span>
    </footer>

    <div v-if="createVisible" class="modal-mask" @click.self="closeCreate">
      <form class="modal-card" @submit.prevent="submitCreate">
        <h3>登记调度单</h3>
        <label v-for="field in createFields" :key="field" class="modal-item">
          <span>{{ field }}<em v-if="createRequired.includes(field)">*</em></span>
          <select v-if="field === '所属车队'" v-model="createForm[field]">
            <option value="" disabled>请选择归属车队</option>
            <option v-for="fleet in creatableFleets" :key="fleet" :value="fleet">{{ fleet }}</option>
          </select>
          <input v-else v-model="createForm[field]" :placeholder="`请输入${field}`" />
        </label>
        <p v-if="createError" class="error-text">{{ createError }}</p>
        <footer class="modal-actions">
          <button class="btn ghost" type="button" @click="closeCreate">取消</button>
          <button class="btn primary" type="submit">提交登记</button>
        </footer>
      </form>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'

import { request } from '@/api/client'
import { useSessionStore } from '@/stores/session'

type Row = Record<string, string | number | boolean | string[] | null>

interface PermissionDescriptor {
  role: string
  role_label: string
  fleets: string[]
  columns: string[]
  sensitive_fields: string[]
  masked_value: string
  creatable_fleets: string[]
  actions: string[]
}

const ENDPOINT = '/api/dispatch'
const session = useSessionStore()

const permissions = ref<PermissionDescriptor | null>(null)
const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const noticeMessage = ref('')
const filters = ref<Record<string, string>>({})
const stats = [{ label: '待派单', value: 0 }, { label: '今日发车', value: 0 }, { label: '撤销派单', value: 0 }]

// 列与动作入口完全由后端权限画像决定，岗位切换后随 permissions 一起刷新
const columns = computed(() => permissions.value?.columns ?? [])
const creatableFleets = computed(() => permissions.value?.creatable_fleets ?? [])
const filterFields = computed(() => columns.value.slice(0, 3))

const createVisible = ref(false)
const createForm = ref<Record<string, string>>({})
const createError = ref('')
const createRequired = ['调度单号', '关联订单', '配送线路', '所属车队']
const createFields = [...createRequired, '指派车辆', '指派司机', '计划发车时间']

function rowActions(row: Row): string[] {
  return Array.isArray(row.allowed_actions) ? (row.allowed_actions as string[]) : []
}

function resetFilters() {
  filters.value = {}
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  createForm.value = { 所属车队: creatableFleets.value[0] ?? '' }
  createError.value = ''
  createVisible.value = true
}

function closeCreate() {
  createVisible.value = false
}

async function submitCreate() {
  createError.value = ''
  try {
    const response = await request(ENDPOINT, {
      method: 'POST',
      body: JSON.stringify({ values: { ...createForm.value } }),
    })
    const payload = await response.json()
    if (!response.ok || !payload.ok) {
      createError.value = payload.message ?? '调度单登记被驳回'
      return
    }
    createVisible.value = false
    noticeMessage.value = payload.message ?? '调度单已登记'
    await reload()
  } catch (error) {
    createError.value = error instanceof Error ? error.message : '调度单登记失败'
  }
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  noticeMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action } }),
    })
    const payload = await response.json()
    if (!response.ok || !payload.ok) {
      // 越权或状态不允许时，把后端注明的驳回原因原样亮出来
      errorMessage.value = payload.message ?? '调度派单动作未生效'
      return
    }
    noticeMessage.value = payload.message ?? ''
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '调度派单操作失败'
  }
}

async function reloadPermissions() {
  const response = await request(`${ENDPOINT}/permissions`)
  if (!response.ok) {
    throw new Error('权限画像读取失败')
  }
  permissions.value = await response.json()
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams(filters.value as Record<string, string>).toString()
  try {
    const response = await request(`${ENDPOINT}?${query}`)
    if (!response.ok) {
      throw new Error('调度单列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '调度派单列表读取失败'
  }
}

async function reloadAll() {
  errorMessage.value = ''
  noticeMessage.value = ''
  try {
    await reloadPermissions()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '权限画像读取失败'
  }
  await reload()
}

onMounted(reloadAll)

// 岗位或归属车队变化时立即重拉权限画像与列表，可见/可改边界即时对齐
watch(
  () => [session.role, session.fleets.join(',')],
  () => {
    void reloadAll()
  },
)
</script>

<style scoped>
.readonly-tag {
  color: var(--muted);
  font-size: 12px;
}
.notice-text {
  color: #067647;
}
.modal-mask {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.4);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 20;
}
.modal-card {
  background: #fff;
  border-radius: 8px;
  padding: 16px 20px;
  width: 360px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.modal-card h3 {
  margin: 0;
}
.modal-item span {
  display: block;
  font-size: 12px;
  color: var(--muted);
}
.modal-item em {
  color: #b42318;
  font-style: normal;
}
.modal-item input,
.modal-item select {
  width: 100%;
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 6px 8px;
  font-size: 13px;
}
.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
</style>
