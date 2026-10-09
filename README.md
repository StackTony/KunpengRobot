# KunpengRobot · 鲲鹏运维平台

基于 Python 的轻量级智能运维平台，支持部署到 **ARM（鲲鹏）/ x86** 架构的 **Linux 与 Windows** 环境，提供 Web 端访问。

> 当前为项目骨架阶段（v0.1）：核心链路（认证 / 上传 / 队列 / SSE / 规则 / 指标）已打通，界面为空数据预览状态。

## 功能特性

- **用户权限控制**：JWT + RBAC（管理员 / 普通用户），令牌黑名单登出
- **故障诊断**：被动上传日志包（zip/tar/文本），后台并发解析 + 规则匹配 + LLM 智能总结，SSE 实时流式输出
- **智能巡检**：检查项插件化（`Checker` 注册制），复用规则引擎，支持定时触发
- **规则管理**：管理员对巡检规则增删改查，正则安全校验、版本化热加载、变更审计
- **性能图表**：ECharts 时序图表，数据持久化于 PostgreSQL 时间分区表，刷新 / 切页签不丢失
- **高并发设计**：API 与分析层解耦，Redis Stream 任务队列 + 事件总线，支持 100+ QPS 并发上传

## 界面预览

| 登录 | 总览 |
|------|------|
| ![登录页](docs/screenshots/01-login.png) | ![总览](docs/screenshots/02-dashboard.png) |

| 故障诊断 | 智能巡检 |
|----------|----------|
| ![故障诊断](docs/screenshots/03-diagnosis.png) | ![智能巡检](docs/screenshots/06-inspection.png) |

| 性能图表 | 规则管理 |
|----------|----------|
| ![性能图表](docs/screenshots/04-metrics.png) | ![规则管理](docs/screenshots/05-rules.png) |

## 技术栈

| 层 | 技术 |
|----|------|
| 后端 | Python 3.11+ · FastAPI · SQLAlchemy(async) · APScheduler |
| 中间件 | PostgreSQL（元数据 + 时间分区指标）· Redis（任务队列 / 事件总线 / 限流） |
| 前端 | Vue 3 · Element Plus · Pinia · ECharts · Vite |
| LLM | OpenAI 兼容 API（可选，未配置时自动降级为纯规则分析） |

## 快速开始

### 1. 环境准备

- Python 3.11+、Node.js 18+
- PostgreSQL 15+、Redis 7+（本机或容器均可）

### 2. 后端

```bash
cd backend

# 安装依赖（建议先创建虚拟环境）
pip install -r requirements.txt

# 配置环境
copy .env.example .env      # Windows
# cp .env.example .env      # Linux，并修改数据库/Redis/LLM 连接信息

# 启动 API 服务（首次启动自动建表并初始化 admin 账号）
uvicorn app.main:app --reload --port 8000

# 另开终端，启动分析 Worker
python -m app.worker
```

默认管理员账号：`admin / admin123`（首次登录后请修改）。

API 文档：http://localhost:8000/docs

### 3. 前端

```bash
cd frontend
npm install
npm run dev          # 开发模式，http://localhost:5173
npm run build        # 生产构建，产物在 dist/
```

开发模式下接口请求由 Vite 代理至 `http://localhost:8000`。

### 4. Docker Compose 一键部署

```bash
cd deploy/docker
docker compose up -d       # 拉起 postgres / redis / api / worker / web
```

双架构镜像支持：`docker buildx build --platform linux/amd64,linux/arm64 ...`

### 5. 裸机部署

- **Linux（systemd）**：`deploy/linux/install.sh`
- **Windows（NSSM 服务）**：`deploy/windows/install-nssm.ps1`
- **Nginx 反代**：`deploy/nginx/nginx.conf`（含 SSE 专用配置 `proxy_buffering off`）

## 项目结构

```
KunpengRobot/
├── backend/
│   └── app/
│       ├── api/            # 认证 / 任务上传 / SSE / 规则 / 指标
│       ├── core/           # 配置 / 安全 / 数据库 / 依赖注入
│       ├── models/         # 用户-角色-权限 / 任务 / 规则 / 指标
│       ├── queue/          # Redis Stream 任务队列
│       ├── events/         # 事件总线（Pub/Sub + Stream 留存）
│       ├── modules/        # 诊断流水线 / 巡检 / 解析器与检查项插件
│       ├── worker/         # Worker 消费循环 + 定时调度
│       └── metrics/        # 指标分区管理
├── frontend/               # Vue3 + Element Plus
├── deploy/                 # docker-compose / Nginx / 裸机脚本
└── docs/                   # 框架设计文档 / 界面截图
```

## 后续规划

- [ ] 具体服务器类型的日志解析器插件（Drain3 模板化解析）
- [ ] 巡检模板与定时巡检任务管理界面
- [ ] 用户管理界面（目前仅种子数据 admin）
- [ ] Alembic 数据库迁移（目前为 create_all）
- [ ] 诊断报告证据链（findings 关联原始日志行号）

详细架构设计见 [docs/框架设计.md](docs/框架设计.md)。

## License

MIT
