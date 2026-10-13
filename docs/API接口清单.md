# 后端对外接口清单

项目后端为 FastAPI 应用，所有路由挂载在 `/api` 前缀下（`backend/app/main.py`），共 12 个路由模块、40 个对外接口。

## 1. 认证 — backend/app/api/auth.py

| 函数 | 接口 | 作用 |
|---|---|---|
| `login` | POST `/api/auth/login` | 用户名密码登录，校验密码与账号状态，返回 access/refresh 双令牌 |
| `refresh` | POST `/api/auth/refresh` | 用 refresh token 换发新令牌 |
| `logout` | POST `/api/auth/logout` | 登出，将 access token 写入 Redis 黑名单直至自然过期 |
| `me` | GET `/api/auth/me` | 当前用户信息：平台角色/权限、展示字段、在各团队的角色 |

## 2. 用户 — backend/app/api/users.py

| 函数 | 接口 | 作用 |
|---|---|---|
| `list_users` | GET `/api/users` | 全部在职用户列表（不含敏感字段，供团队邀请下拉） |

## 3. 工作台 — backend/app/api/dashboard.py

| 函数 | 接口 | 作用 |
|---|---|---|
| `dashboard` | GET `/api/dashboard` | 我的团队范围聚合：团队/资产/任务计数、KPI、最近任务、Top 错误码（管理员为全量） |

## 4. 团队 — backend/app/api/teams.py

| 函数 | 接口 | 作用 |
|---|---|---|
| `list_teams` | GET `/api/teams` | 全部团队概览（非成员也可看，供申请加入），带 my_role |
| `create_team` | POST `/api/teams` | 创建团队，同事务建 owner 成员 + 同名默认资产库 |
| `team_detail` | GET `/api/teams/{team_id}` | 团队详情：成员/资产库/待审批申请（申请仅 owner/team_admin 可见） |
| `update_team` | PUT `/api/teams/{team_id}` | 编辑团队名称/描述（需 team:role 权限） |
| `invite_member` | POST `/api/teams/{team_id}/invite` | 邀请成员，生成 pending 邀请待对方确认（幂等） |
| `apply_join` | POST `/api/teams/{team_id}/apply` | 申请加入团队，生成 pending 申请待 owner 审批 |
| `update_member_role` | PUT `/api/teams/{team_id}/members/{member_user_id}` | 调整成员角色（owner 角色受保护） |
| `remove_member` | DELETE `/api/teams/{team_id}/members/{member_user_id}` | 移除成员（owner 不可被移除、不可移除自己） |

## 5. 通知中心 — backend/app/api/notices.py

| 函数 | 接口 | 作用 |
|---|---|---|
| `my_notices` | GET `/api/notices` | 我的待办：收到的 pending 邀请 ∪ 我有权审批的 pending 申请 |
| `resolve_notice` | POST `/api/notices/{notice_id}/resolve` | 处理邀请/申请（同意则同事务入团并授予角色，拒绝则关闭） |

## 6. 资产库 — backend/app/api/assets.py

| 函数 | 接口 | 作用 |
|---|---|---|
| `list_assets` | GET `/api/teams/{team_id}/assets` | 团队资产库列表，含每库任务数（需 asset:view） |
| `create_asset` | POST `/api/teams/{team_id}/assets` | 创建资产库（需 asset:create） |
| `get_asset` | GET `/api/assets/{asset_id}` | 资产库详情（含任务数） |
| `update_asset` | PUT `/api/assets/{asset_id}` | 编辑资产库（需 asset:edit） |
| `delete_asset` | DELETE `/api/assets/{asset_id}` | 删除资产库，级联删除库下任务（需 asset:delete） |
| `list_asset_tasks` | GET `/api/assets/{asset_id}/tasks` | 资产库下任务分页列表，支持状态/解析器/关键字筛选，每任务附 16 桶时序 spark |

## 7. 任务 — backend/app/api/tasks.py

| 函数 | 接口 | 作用 |
|---|---|---|
| `precheck` | POST `/api/tasks/precheck` | 解析预检：前端传日志前 512KB 切片，返回可解析条数与样例（不落盘不入队） |
| `upload_text` | POST `/api/tasks/upload-text` | 向导粘贴文本直传（≤10MB），落临时文件创建 analyze 任务并入队 |
| `upload` | POST `/api/tasks/upload` | 上传日志包（diagnosis/analyze/inspection 三类），含限流与文件类型校验，入队后立即返回 task_id |
| `list_tasks` | GET `/api/tasks` | 任务列表：普通用户看自己、管理员看全部，可按类型过滤 |
| `get_task` | GET `/api/tasks/{task_id}` | 任务详情（可见性：创建者/管理员/同团队成员） |
| `delete_task` | DELETE `/api/tasks/{task_id}` | 删除任务，连带清理报告/事件/上传文件（需 task:delete） |
| `cancel_task` | POST `/api/tasks/{task_id}/cancel` | 取消任务：pending 直接置 cancelled，running 由 Worker 监听取消标记停止 |

## 8. 解析结果 — backend/app/api/analysis.py

| 函数 | 接口 | 作用 |
|---|---|---|
| `list_events` | GET `/api/tasks/{task_id}/logs` | 原始日志分页多维筛选（severity/category/error_code/IP/关键字），SQL 侧过滤 |
| `task_stats` | GET `/api/tasks/{task_id}/stats` | 结果页聚合：KPI、时序桶、类别分布、错误码排行（含样例）、IP 聚合 |
| `task_report` | GET `/api/tasks/{task_id}/report` | 查看报告（兜底五段式，LLM 覆盖后含 llm 标记） |
| `start_llm` | POST `/api/tasks/{task_id}/llm` | 触发按需 LLM 报告生成：抢锁 → 生成 run_id → 入队（需 task:llm） |
| `llm_events` | GET `/api/tasks/{task_id}/llm/events` | LLM 报告流式 SSE，先补发历史再实时续流（支持 ?token= 认证） |

## 9. 任务实时流 — backend/app/api/sse.py

| 函数 | 接口 | 作用 |
|---|---|---|
| `task_events` | GET `/api/tasks/{task_id}/events` | 任务事件 SSE 流：分析进度/解析日志行/LLM token/结论，断线用 Last-Event-ID 重连补发 |

## 10. 审计 — backend/app/api/audit.py

| 函数 | 接口 | 作用 |
|---|---|---|
| `query_audit` | GET `/api/audit` | 审计日志分页查询：指定 team_id 需 audit:view；未指定只看「我的团队 ∪ 我自己」，管理员全库；支持动作/关键字筛选 |

## 11. 规则管理 — backend/app/api/rules.py

| 函数 | 接口 | 作用 |
|---|---|---|
| `list_rule_scripts` | GET `/api/rules/scripts` | 扫描脚本目录返回可用脚本（相对路径 + docstring），供前端下拉 |
| `list_rules` | GET `/api/rules` | 规则列表，可只看启用项 |
| `create_rule` | POST `/api/rules` | 创建规则（需 rule:manage）：含正则灾难性回溯校验、脚本路径防穿越校验、写规则审计日志 |
| `update_rule` | PUT `/api/rules/{rule_id}` | 更新规则：版本号自增供 Worker 热加载，记录新旧值审计 |
| `delete_rule` | DELETE `/api/rules/{rule_id}` | 删除规则（内置规则不可删只可停用） |

## 12. 指标与偏好 — backend/app/api/metrics.py

| 函数 | 接口 | 作用 |
|---|---|---|
| `query_metrics` | POST `/api/metrics/query` | 按主机/指标/时间范围查询时序点，interval_seconds>0 时按桶均值降采样 |
| `list_hosts` | GET `/api/metrics/hosts` | 可用主机列表 |
| `list_metric_names` | GET `/api/metrics/names` | 可用指标名列表（图表下拉动态选择） |
| `get_preference` | GET `/api/preferences/{pref_key}` | 读取用户视图偏好配置 |
| `save_preference` | PUT `/api/preferences/{pref_key}` | 保存用户视图偏好（图表配置持久化） |

## 13. 健康检查 — backend/app/main.py

| 函数 | 接口 | 作用 |
|---|---|---|
| `health` | GET `/health` | 服务健康检查（无前缀，不在 /api 下） |

---

**附注**：`backend/app/main.py` 中另有 lifespan 启动逻辑（Redis 初始化、schema guard、建表、种子数据 `seed_initial_data`/`seed_teams`/`seed_demo_tasks`/`seed_builtin_rules`/`seed_demo_metrics`），这些不是对外接口，仅启动时执行。
