/* 团队 store: 团队(三角色) → 资产库 → 任务 + 申请/邀请通知, 全量走后端 API */
import { defineStore } from 'pinia'
import { get, post, put, del } from '@/api/http'
import { teamRoleHasPerm } from '@/rbac/permissions'
import { useRbacStore } from '@/stores/rbac'

export interface TeamInfo {
  id: number
  name: string
  desc: string
  ownerUserId: number
  createdAt: string
  myRole?: string | null
  memberCount: number
  assetCount: number
  taskCount: number
}

export interface MemberInfo {
  userId: number
  name: string
  email: string
  title: string
  dept: string
  avatarHue: number
  role: string
}

export interface AssetInfo {
  id: number
  teamId: number
  name: string
  desc: string
  ipRange: string
  createdAt: string
  taskCount: number
}

export type NoticeType = 'invite' | 'apply'

export interface TeamNotice {
  id: number
  type: NoticeType
  teamId: number
  teamName: string
  fromUserId: number
  fromUserName: string
  toUserId: number
  toUserName: string
  role: string
  status: string
  createdAt: string
}

export interface TeamDetail extends TeamInfo {
  members: MemberInfo[]
  assets: AssetInfo[]
  pendingApplies: TeamNotice[]
}

export const useTeamsStore = defineStore('teams', {
  state: () => ({
    teams: [] as TeamInfo[],
    details: {} as Record<string, TeamDetail>,
    notices: [] as TeamNotice[],        // 我的待办: 发给我的邀请 + 我审批的申请
    appliedTeamIds: [] as number[],     // 本会话我已提交的入团申请 (前端防重复提示)
  }),
  getters: {
    teamById(state) {
      return (id: string | number) =>
        state.teams.find((t) => String(t.id) === String(id)) ?? state.details[String(id)]
    },
    /* 我在某团队的角色 (来自 /auth/me team_roles; 详情页补充 admin 的 owner 语义) */
    myRoleOf(state) {
      return (teamId: string | number) =>
        useRbacStore().myTeamRoles[String(teamId)] ?? state.details[String(teamId)]?.myRole ?? undefined
    },
    /* 我的通知 (后端 GET /notices 已按可见性过滤, 仅 pending) */
    myNotices(state): (userId: number | string) => TeamNotice[] {
      return () => state.notices
    },
    isApproverOf() {
      return (teamId: string | number) =>
        ['owner', 'team_admin'].includes(this.myRoleOf(teamId) ?? '')
    },
  },
  actions: {
    /* 团队内权限判定 (按团队成员角色; 平台管理员直通) */
    can(teamId: string | number, perm: string): boolean {
      const rbac = useRbacStore()
      if (rbac.isPlatformAdmin) return true
      const roleId = this.myRoleOf(teamId)
      if (!roleId) return false
      return teamRoleHasPerm(roleId, perm)
    },
    async fetchTeams() {
      this.teams = await get<TeamInfo[]>('/teams')
    },
    async fetchTeam(id: string | number) {
      const detail = await get<TeamDetail>(`/teams/${id}`)
      this.details[String(id)] = detail
      return detail
    },
    async fetchNotices() {
      this.notices = await get<TeamNotice[]>('/notices')
    },
    async createTeam(name: string, desc: string) {
      const team = await post<TeamInfo>('/teams', { name, desc })
      await this.fetchTeams()
      return team
    },
    async updateTeam(id: string | number, name: string, desc: string) {
      await put(`/teams/${id}`, { name, desc })
    },
    async invite(teamId: string | number, toUserId: number, roleId: string) {
      await post(`/teams/${teamId}/invite`, { user_id: toUserId, role: roleId })
    },
    async apply(teamId: string | number) {
      await post(`/teams/${teamId}/apply`)
      const tid = Number(teamId)
      if (!this.appliedTeamIds.includes(tid)) this.appliedTeamIds.push(tid)
    },
    async setMemberRole(teamId: string | number, userId: number, roleId: string) {
      await put(`/teams/${teamId}/members/${userId}`, { role: roleId })
    },
    async removeMember(teamId: string | number, userId: number) {
      await del(`/teams/${teamId}/members/${userId}`)
    },
    async resolveNotice(noticeId: number, accept: boolean) {
      await post(`/notices/${noticeId}/resolve`, { accept })
    },
  },
})
