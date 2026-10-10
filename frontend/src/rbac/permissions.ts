/* 原子权限点定义 */

export interface PermDef {
  key: string
  group: string
  label: string
}

export const PERMISSIONS: PermDef[] = [
  { key: 'dashboard:view', group: '工作台', label: '查看工作台' },
  { key: 'team:view', group: '团队', label: '查看团队' },
  { key: 'team:create', group: '团队', label: '创建团队' },
  { key: 'team:invite', group: '团队', label: '邀请成员' },
  { key: 'team:remove', group: '团队', label: '移除成员' },
  { key: 'team:role', group: '团队', label: '调整成员角色' },
  { key: 'team:approve', group: '团队', label: '审批申请' },
  { key: 'asset:view', group: '资产库', label: '查看资产库' },
  { key: 'asset:create', group: '资产库', label: '创建资产库' },
  { key: 'asset:edit', group: '资产库', label: '编辑资产库' },
  { key: 'asset:delete', group: '资产库', label: '删除资产库' },
  { key: 'task:view', group: '解析任务', label: '查看解析任务' },
  { key: 'task:create', group: '解析任务', label: '创建解析任务' },
  { key: 'task:execute', group: '解析任务', label: '执行解析' },
  { key: 'task:delete', group: '解析任务', label: '删除任务' },
  { key: 'task:llm', group: '解析任务', label: '使用 LLM 分析' },
  { key: 'audit:view', group: '审计日志', label: '查看团队审计' },
]

export const PERM_GROUPS = ['工作台', '团队', '资产库', '解析任务', '审计日志']

/* ---------- 团队内固定三角色 ---------- */
export interface TeamRole {
  id: string
  name: string
  desc: string
  perms: string[] // '*' 表示全部
}

export const TEAM_ROLES: TeamRole[] = [
  {
    id: 'owner',
    name: '创建者',
    desc: '团队创建者，拥有团队内全部权限',
    perms: ['*'],
  },
  {
    id: 'team_admin',
    name: '管理员',
    desc: '管理成员与审批申请，任务与资产全权',
    perms: [
      'dashboard:view', 'team:view', 'team:create', 'team:invite', 'team:remove', 'team:role', 'team:approve',
      'asset:view', 'asset:create', 'asset:edit', 'asset:delete',
      'task:view', 'task:create', 'task:execute', 'task:delete', 'task:llm',
      'audit:view',
    ],
  },
  {
    id: 'member',
    name: '普通用户',
    desc: '查看团队资产与任务，可执行解析与 LLM 分析',
    perms: ['dashboard:view', 'team:view', 'asset:view', 'task:view', 'task:create', 'task:execute', 'task:llm'],
  },
]

export function teamRoleById(id: string): TeamRole | undefined {
  return TEAM_ROLES.find((r) => r.id === id)
}

export function teamRoleHasPerm(roleId: string, perm: string): boolean {
  const role = teamRoleById(roleId)
  if (!role) return false
  return role.perms.includes('*') || role.perms.includes(perm)
}
