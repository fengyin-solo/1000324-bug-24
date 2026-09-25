<template>
  <section class="page" data-module="alarm">
    <header class="page-head">
      <div>
        <h2>告警中心管理</h2>
        <p class="page-desc">维护告警事件，围绕告警编号、告警类型、告警等级、触发设备做登记、筛选与状态流转。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记告警事件</button>
        <button class="btn" type="button" @click="exportRows">导出告警中心清单</button>
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
            <template v-for="action in actions" :key="action">
              <button
                class="link"
                type="button"
                :disabled="!canRun(action, row) || pendingKey === actionKey(action, row)"
                @click="runAction(action, row)"
              >
                {{ action }}
              </button>
            </template>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无告警中心数据，可先登记告警事件</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条告警中心记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>

const ENDPOINT = '/api/alarm'
const columns = ["告警编号", "告警类型", "告警等级", "触发设备", "触发时间", "确认人员", "处置说明", "告警状态"]
const actions = ["确认告警", "处置告警", "忽略告警"]
const terminalStatuses = ["已处置", "已忽略"]
const stats = ref([
  { label: "今日告警", value: 0 },
  { label: "待确认告警", value: 0 },
  { label: "高等级告警", value: 0 },
])

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const filters = ref<Record<string, string>>({})
const filterFields = columns.slice(0, 3)
// 记录正在提交的动作，连点两次时第二次直接忽略，保证同一动作只提交一次。
const pendingKey = ref('')

function actionKey(action: string, row: Row) {
  return `${row.id}:${action}`
}

function statusOf(row: Row): string {
  return String(row['告警状态'] ?? row.status ?? '待确认')
}

function canRun(action: string, row: Row): boolean {
  const status = statusOf(row)
  // 终态告警不再允许流转，忽略掉的告警不会回到待确认。
  if (terminalStatuses.includes(status)) {
    return false
  }
  return status !== '已确认' || action !== '确认告警'
}

function resetFilters() {
  filters.value = {}
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  errorMessage.value = '告警事件登记入口尚未接入审批流'
}

async function runAction(action: string, row: Row) {
  if (!canRun(action, row) || pendingKey.value) {
    return
  }
  const key = actionKey(action, row)
  pendingKey.value = key
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ action }),
    })
    if (!response.ok) {
      throw new Error('告警中心动作未生效，请稍后重试')
    }
    const payload = (await response.json()) as { ok: boolean; message?: string }
    if (!payload.ok) {
      throw new Error(payload.message || '告警中心动作未生效，请稍后重试')
    }
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '告警中心操作失败'
  } finally {
    pendingKey.value = ''
  }
}

async function reloadStats() {
  const query = new URLSearchParams(filters.value as Record<string, string>).toString()
  try {
    const response = await request(`${ENDPOINT}/stats?${query}`)
    if (!response.ok) {
      return
    }
    const payload = (await response.json()) as { total: number; pending: number; high_level: number }
    stats.value = [
      { label: "今日告警", value: payload.total },
      { label: "待确认告警", value: payload.pending },
      { label: "高等级告警", value: payload.high_level },
    ]
  } catch {
    // 统计读不出来时保留上次的值，不影响列表操作。
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams(filters.value as Record<string, string>).toString()
  try {
    const response = await request(`${ENDPOINT}?${query}`)
    if (!response.ok) {
      throw new Error('告警事件列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
    await reloadStats()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '告警中心列表读取失败'
  }
}

onMounted(reload)
</script>
