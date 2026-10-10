<script setup lang="ts">
/* 团队三角色：卡片可点击切换，权限对照表联动高亮选中角色列 */
import { computed, ref } from 'vue'
import { PERMISSIONS, PERM_GROUPS, TEAM_ROLES, teamRoleHasPerm } from '@/rbac/permissions'

const selectedId = ref('owner')
const selected = computed(() => TEAM_ROLES.find((r) => r.id === selectedId.value) ?? TEAM_ROLES[0])

const ROLE_BADGE: Record<string, string> = {
  owner: 'o-badge--primary',
  team_admin: 'o-badge--brand',
  member: 'o-badge--outline',
}

type Row = { key: string; type: 'group'; label: string } | { key: string; type: 'perm'; label: string; permKey: string }
const rows = computed<Row[]>(() => {
  const list: Row[] = []
  for (const g of PERM_GROUPS) {
    list.push({ key: 'g-' + g, type: 'group', label: g })
    for (const p of PERMISSIONS.filter((x) => x.group === g)) {
      list.push({ key: 'p-' + p.key, type: 'perm', label: p.label, permKey: p.key })
    }
  }
  return list
})

function select(id: string) {
  selectedId.value = id
}
function permCountOf(r: { perms: string[] }): number {
  return r.perms.includes('*')
    ? PERMISSIONS.length
    : r.perms.filter((p) => PERMISSIONS.some((d) => d.key === p)).length
}
</script>

<template>
  <div class="o-card" style="margin-bottom: 16px">
    <div class="o-card__title">
      团队内固定角色
      <span class="hint">点击卡片或表头切换，查看该角色的权限范围</span>
    </div>
    <div class="role-cards">
      <button
        v-for="r in TEAM_ROLES"
        :key="r.id"
        class="role-card"
        :class="{ selected: selectedId === r.id, ['role-' + r.id]: true }"
        @click="select(r.id)"
      >
        <span class="check">✓</span>
        <div class="role-name">
          <span class="o-badge" :class="ROLE_BADGE[r.id]">{{ r.name }}</span>
        </div>
        <p>{{ r.desc }}</p>
        <div class="o-mono role-count">
          {{ selectedId === r.id ? '当前查看 · ' : '' }}{{ r.perms.includes('*') ? '全部权限' : permCountOf(r) + ' 项权限' }}
        </div>
      </button>
    </div>
  </div>

  <div class="o-card">
    <div class="o-card__title">
      权限对照表
      <span class="hint">高亮列为「{{ selected.name }}」· ✓ 拥有 · — 无</span>
    </div>
    <div class="o-table-wrap">
      <table class="o-table role-table">
        <thead>
          <tr>
            <th>权限点</th>
            <th
              v-for="r in TEAM_ROLES"
              :key="r.id"
              class="col-role"
              :class="{ 'col-active': selectedId === r.id }"
              @click="select(r.id)"
            >
              {{ r.name }}
              <span class="col-arrow">{{ selectedId === r.id ? '▾' : '' }}</span>
            </th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in rows" :key="row.key" :class="{ 'group-row': row.type === 'group' }">
            <td v-if="row.type === 'group'" colspan="99">{{ row.label }}</td>
            <template v-else>
              <td>
                {{ row.label }}
                <span class="o-mono o-text-3 perm-key">{{ row.permKey }}</span>
              </td>
              <td
                v-for="r in TEAM_ROLES"
                :key="r.id"
                class="check-cell"
                :class="{ 'col-active': selectedId === r.id }"
              >
                <span v-if="teamRoleHasPerm(r.id, row.permKey)" class="yes">✓</span>
                <span v-else class="no">—</span>
              </td>
            </template>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<style scoped>
.role-cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 12px;
}
.role-card {
  position: relative;
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: 16px 18px;
  background: var(--surface);
  cursor: pointer;
  font: inherit;
  text-align: left;
  transition: all 0.15s;
}
.role-card:hover {
  border-color: var(--primary-hover);
  transform: translateY(-1px);
  box-shadow: var(--shadow-1);
}
.role-card.selected {
  border-color: var(--primary);
  background: var(--primary-soft);
}
.role-card .check {
  position: absolute;
  top: 12px;
  right: 12px;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: var(--primary);
  color: #fff;
  font-size: 11px;
  display: none;
  align-items: center;
  justify-content: center;
}
.role-card.selected .check {
  display: flex;
}
.role-card p {
  font-size: 12.5px;
  color: var(--text-2);
  line-height: 1.7;
  margin-top: 10px;
}
.role-card .role-count {
  margin-top: 10px;
  color: var(--text-3);
  font-size: 11px;
  min-height: 16px;
}
.role-card.selected .role-count {
  color: var(--primary);
  font-weight: 600;
}
.role-table th.col-role {
  text-align: center;
  min-width: 96px;
  cursor: pointer;
  user-select: none;
  transition: background 0.15s;
}
.role-table th.col-role:hover {
  color: var(--primary);
}
.role-table th.col-role.col-active {
  color: var(--primary);
  background: var(--primary-soft);
  border-bottom-color: var(--primary);
}
.col-arrow {
  font-size: 11px;
}
.role-table .check-cell {
  text-align: center;
  transition: all 0.15s;
}
.role-table .check-cell:not(.col-active) {
  opacity: 0.4;
}
.role-table .check-cell.col-active {
  background: var(--primary-soft);
}
.yes {
  color: var(--success);
  font-weight: 700;
}
.no {
  color: var(--text-4);
}
.perm-key {
  font-size: 11px;
  margin-left: 6px;
}
.group-row td {
  background: var(--surface-3);
  font-weight: 600;
  font-size: 12.5px;
  color: var(--text-2);
  padding: 6px 16px;
}
</style>
