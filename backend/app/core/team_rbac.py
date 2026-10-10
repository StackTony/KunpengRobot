"""团队级 RBAC 常量: 17 原子权限点 + 团队内三角色权限映射.

与前端 src/rbac/permissions.ts 保持镜像 (witty-log-analyzer),
修改任一侧必须同步另一侧.
"""

# 17 个原子权限点 (key, 分组, 中文标签)
PERMISSIONS_17: list[tuple[str, str, str]] = [
    ("dashboard:view", "工作台", "查看工作台"),
    ("team:view", "团队", "查看团队"),
    ("team:create", "团队", "创建团队"),
    ("team:invite", "团队", "邀请成员"),
    ("team:remove", "团队", "移除成员"),
    ("team:role", "团队", "调整成员角色"),
    ("team:approve", "团队", "审批申请"),
    ("asset:view", "资产库", "查看资产库"),
    ("asset:create", "资产库", "创建资产库"),
    ("asset:edit", "资产库", "编辑资产库"),
    ("asset:delete", "资产库", "删除资产库"),
    ("task:view", "解析任务", "查看解析任务"),
    ("task:create", "解析任务", "创建解析任务"),
    ("task:execute", "解析任务", "执行解析"),
    ("task:delete", "解析任务", "删除任务"),
    ("task:llm", "解析任务", "使用 LLM 分析"),
    ("audit:view", "审计日志", "查看团队审计"),
]

PERM_GROUPS = ["工作台", "团队", "资产库", "解析任务", "审计日志"]

# 团队内三角色 -> 权限映射 ('*' 表示全部)
TEAM_ROLE_PERMS: dict[str, list[str]] = {
    "owner": ["*"],
    "team_admin": [p[0] for p in PERMISSIONS_17],
    "member": ["dashboard:view", "team:view", "asset:view",
               "task:view", "task:create", "task:execute", "task:llm"],
}


def team_role_has_perm(role: str, perm: str) -> bool:
    """判断团队角色是否具备某权限."""
    perms = TEAM_ROLE_PERMS.get(role, [])
    return "*" in perms or perm in perms


# 审计动作中文标签 (与前端 TeamAuditPanel 的 ACTIONS 下拉对齐)
AUDIT_ACTIONS = [
    "登录平台", "创建团队", "编辑团队", "申请加入团队", "邀请加入团队",
    "处理团队邀请", "处理加入申请", "调整成员角色", "移除团队成员",
    "创建解析任务", "执行解析任务", "删除解析任务", "使用 LLM 分析",
]
