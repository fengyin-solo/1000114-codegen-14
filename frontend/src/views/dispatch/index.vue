<template>
  <section class="page" data-module="dispatch">
    <header class="page-head">
      <div>
        <h2>调度派单管理</h2>
        <p class="page-desc">
          维护调度单，围绕调度单号、关联订单、配送线路、指派车辆做登记、筛选与状态流转。
          当前岗位：{{ session.role }}<template v-if="session.fleet"> · 归属{{ session.fleet }}</template>
          <span v-if="readonlyHint" class="role-hint">{{ readonlyHint }}</span>
        </p>
      </div>
      <div class="page-actions">
        <button v-if="scope?.can_create" class="btn primary" type="button" @click="openCreate">登记调度单</button>
        <p v-else class="role-hint">{{ session.role }}不可登记调度单</p>
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
          <td v-for="column in columns" :key="column">{{ formatCell(row, column) }}</td>
          <td class="row-actions">
            <template v-if="permittedActions(row).length || row.editable">
              <button
                v-for="action in permittedActions(row)"
                :key="action"
                class="link"
                type="button"
                @click="runAction(action, row)"
              >
                {{ action }}
              </button>
              <button
                v-if="row.editable"
                class="link"
                type="button"
                @click="openEdit(row)"
              >
                修改
              </button>
            </template>
            <span v-else class="readonly-tag">只读</span>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无调度派单数据，可先登记调度单</td>
        </tr>
      </tbody>
    </table>

    <!-- 登记调度单：调度员只能选择自己归属的车队，故直接锁定 -->
    <div v-if="createOpen" class="modal-mask" @click.self="closeCreate">
      <form class="modal-card" @submit.prevent="submitCreate">
        <h3>登记调度单</h3>
        <p class="role-hint">调度员仅能登记归属「{{ session.fleet }}」的调度单</p>
        <label v-for="field in createFormFields" :key="field" class="modal-field">
          <span>{{ field === '所属车队' ? `${field}（锁定为本车队）` : field }}</span>
          <input
            v-model="createForm[field]"
            :disabled="field === '所属车队'"
            :placeholder="`请输入${field}`"
          />
        </label>
        <footer class="modal-foot">
          <button class="btn" type="button" @click="closeCreate">取消</button>
          <button class="btn primary" type="submit">提交登记</button>
        </footer>
      </form>
    </div>

    <!-- 修改调度单：仅本车队管理员可见，字段白名单由后端 scope 下发 -->
    <div v-if="editOpen" class="modal-mask" @click.self="closeEdit">
      <form class="modal-card" @submit.prevent="submitEdit">
        <h3>修改调度单 {{ editId }}</h3>
        <p class="role-hint">
          车队管理员仅可改本车队单子的：{{ scope?.editable_fields.join('、') }}
        </p>
        <label v-for="field in scope?.editable_fields ?? []" :key="field" class="modal-field">
          <span>{{ field }}</span>
          <input v-model="editForm[field]" :placeholder="`请输入${field}`" />
        </label>
        <footer class="modal-foot">
          <button class="btn" type="button" @click="closeEdit">取消</button>
          <button class="btn primary" type="submit">保存修改</button>
        </footer>
      </form>
    </div>

    <footer class="page-foot">
      <span>共 {{ total }} 条调度派单记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'

import { request, withPrincipal } from '@/api/client'
import { useSessionStore } from '@/stores/session'

type Row = Record<string, string | number | boolean | string[] | null>

interface Scope {
  role: string
  principal: string
  principal_name: string
  fleet: string | null
  fleets: string[]
  columns: string[]
  actions: string[]
  can_create: boolean
  can_edit: boolean
  editable_fields: string[]
}

interface ActionResponse {
  ok: boolean
  message: string
  entry: Row | null
}

const ENDPOINT = '/api/dispatch'
const FLEET_FIELD = '所属车队'
const statuses = ["待派单", "已派单", "已发车", "已撤销"]
const stats = [{ label: "待派单", value: 0 }, { label: "今日发车", value: 0 }, { label: "撤销派单", value: 0 }]

const session = useSessionStore()

const scope = ref<Scope | null>(null)
const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const filters = ref<Record<string, string>>({})

// 列、动作、可建车队全部以后端 scope 为准；切换岗位后整体重取，杜绝残留旧权限。
const columns = computed(() => scope.value?.columns ?? [])
const filterFields = computed(() => (scope.value?.columns ?? []).slice(0, 3))

const createOpen = ref(false)
const createFormFields = ['调度单号', '关联订单', '配送线路', FLEET_FIELD]
const createForm = reactive<Record<string, string>>({})

const editOpen = ref(false)
const editId = ref<number | null>(null)
const editForm = reactive<Record<string, string>>({})

const readonlyHint = computed(() => {
  if (!scope.value || session.fleet === null) return ''
  return '（其他车队的调度单只读）'
})

function permittedActions(row: Row): string[] {
  return Array.isArray(row.permitted_actions) ? (row.permitted_actions as string[]) : []
}

function formatCell(row: Row, column: string): string {
  const value = row[column]
  return value === null || value === undefined || value === ''
    ? '—'
    : String(value)
}

function resetFilters() {
  filters.value = {}
  void reload()
}

function exportRows() {
  window.open(withPrincipal(`${ENDPOINT}/export`), '_blank')
}

function openCreate() {
  errorMessage.value = ''
  for (const field of createFormFields) createForm[field] = ''
  createForm[FLEET_FIELD] = session.fleet ?? ''
  createOpen.value = true
}

function closeCreate() {
  createOpen.value = false
}

function openEdit(row: Row) {
  errorMessage.value = ''
  editId.value = Number(row.id)
  for (const field of scope.value?.editable_fields ?? []) {
    editForm[field] = row[field] === null || row[field] === undefined ? '' : String(row[field])
  }
  editOpen.value = true
}

function closeEdit() {
  editOpen.value = false
  editId.value = null
}

async function loadScope() {
  const response = await request(`${ENDPOINT}/scope`)
  if (!response.ok) {
    throw new Error('岗位权限边界读取失败')
  }
  scope.value = (await response.json()) as Scope
}

async function submitCreate() {
  errorMessage.value = ''
  try {
    const response = await request(ENDPOINT, {
      method: 'POST',
      body: JSON.stringify({ values: { ...createForm } }),
    })
    const result = (await response.json()) as ActionResponse
    if (!result.ok) {
      errorMessage.value = result.message
      return
    }
    closeCreate()
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '调度单登记失败'
  }
}

async function submitEdit() {
  errorMessage.value = ''
  if (editId.value === null) return
  try {
    const response = await request(`${ENDPOINT}/${editId.value}`, {
      method: 'PUT',
      body: JSON.stringify({ values: { ...editForm } }),
    })
    const result = (await response.json()) as ActionResponse
    if (!result.ok) {
      errorMessage.value = result.message
      return
    }
    closeEdit()
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '调度单修改失败'
  }
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action } }),
    })
    const result = (await response.json()) as ActionResponse
    if (!result.ok) {
      // 越权提交：原样展示后端的驳回原因。
      errorMessage.value = result.message
      return
    }
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '调度派单操作失败'
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams(filters.value as Record<string, string>).toString()
  try {
    // 每次进入/刷新先重取岗位边界，再按新边界拉列表（字段投影在后端完成）。
    await loadScope()
    const response = await request(`${ENDPOINT}?${query}`)
    if (!response.ok) {
      throw new Error('调度单列表读取失败')
    }
    const payload = await response.json()
    rows.value = (payload.items ?? []) as Row[]
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '调度派单列表读取失败'
  }
}

// 顶栏切换岗位后，不必重进页面，可见与可改边界立即刷新。
watch(
  () => session.principalKey,
  () => {
    createOpen.value = false
    editOpen.value = false
    void reload()
  },
)

onMounted(reload)
</script>
