# MultiTaskQAAssistant

基于 FastAPI + LangChain 的多模块智能客服项目，当前包含用户前台、统一后台管理系统、三层记忆能力、知识库与运行参数管理、用户认证和角色权限控制。

如果你只想快速启动项目，直接看 [V3_QUICKSTART.md](./V3_QUICKSTART.md)。

## 当前阶段

截至 2026-04-16，项目主线已完成：

- Phase 1：统一后台骨架、角色权限、记忆管理后台、只读前台设置摘要、知识库基础显隐控制
- Phase 2：知识库后台完整流程
- Phase 3：知识库版本历史与安全回滚
- 账号管理 Phase 2：账号详情、状态启停、角色调整
- 系统设置 Phase 2：运行参数、前台展示策略、权限说明

当前后台知识库模块已经支持：

- 稳定 `document_id` 文档主键
- 文档列表、详情、筛选
- 新文档上传
- 元数据编辑
- 文件替换且保留同一 `document_id`
- 版本历史查看
- 基于历史版本生成新的安全回滚版本
- 软删除与恢复
- `chunk_count`、`checksum` 等运行指标展示
- 前台只读知识库按角色、发布状态和显隐策略过滤

## 系统结构

- 用户 API：`http://localhost:8000`
- 后台 API：`http://localhost:8001`
- 用户前台：`http://localhost:5173`
- 后台前端：`http://localhost:5174/admin.html`

主要模块：

- 用户前台
  - 登录、对话、只读知识库、只读设置摘要
- 后台管理系统
  - 总览、记忆管理、知识库管理、系统设置、账号管理
- 记忆系统
  - 短期记忆、中期摘要、长期偏好画像
- 权限系统
  - Token 鉴权、角色判定、后台路由守卫、服务端权限校验

## 环境准备

推荐使用 Conda：

```bash
conda create -n test3 python=3.10 -y
conda activate test3
pip install -r requirements.txt -r backend/requirements.txt
```

如果还没有 `.env`，先复制：

```bash
# Windows PowerShell
Copy-Item .env.example .env

# Linux / macOS
cp .env.example .env
```

至少确认这些变量已经填写：

- `OPENAI_API_KEY`
- `DEEPSEEK_API_KEY`
- `AMAP_API_KEY`
- `TAVILY_API_KEY`
- `DATABASE_URL`

默认数据库：

```env
DATABASE_URL=mysql+pymysql://root:your_mysql_password_here@127.0.0.1:3306/testdb?charset=utf8mb4
```

For SQLite auth migration steps, see `docs/auth-mysql-migration.md`.

## 启动方式

### 1. 启动双后端

在项目根目录执行：

```bash
python backend/run_backends.py
```

启动成功后可访问：

- 用户 API 文档：`http://localhost:8000/docs`
- 用户健康检查：`http://localhost:8000/api/v1/health`
- 后台 API 文档：`http://localhost:8001/docs`
- 后台健康检查：`http://localhost:8001/health`

### 2. 启动用户前台

```bash
cd frontend
npm install
npm run dev
```

访问地址：`http://localhost:5173`

### 3. 启动后台前端

仍然在 `frontend` 目录执行：

```bash
npm run admin
```

访问地址：`http://localhost:5174/admin.html`

说明：

- `npm run admin` 使用 Vite 在 `5174` 端口启动后台页面
- 开发态下，`/api` 代理到 `8000`，`/api/admin` 代理到 `8001`

## 角色说明

- `super_admin`
  - 全部后台能力
  - 可调整账号角色与系统运行参数
- `admin`
  - 可管理记忆、知识库、设置、账号
- `operator`
  - 可进入后台查看总览、记忆、知识库
  - 知识库模块只读，不可执行上传、替换、删除、恢复和保存
- `user`
  - 仅可访问用户前台

## 核心接口

### 用户认证

- `POST /api/v1/auth/register`
- `POST /api/v1/auth/login`
- `GET /api/v1/auth/me`
- `GET /api/v1/auth/memory`
- `POST /api/v1/auth/memory/resolve`

### 用户前台知识库

- `GET /api/v1/knowledge-base`
- `GET /api/v1/knowledge-base/{document_id}`
- `GET /api/v1/knowledge-base/params`

说明：

- 列表和详情都要求登录
- 前台只返回当前角色允许访问且满足“未删除 + 已发布 + 前台可见”的文档
- 返回的 `id` 即后台稳定 `document_id`

### 后台接口

- 总览
  - `GET /api/admin/dashboard/summary`
- 记忆管理
  - `GET /api/admin/memory/users`
  - `GET /api/admin/memory/users/{user_id}`
  - `POST /api/admin/memory/users/{user_id}/preferences`
  - `DELETE /api/admin/memory/users/{user_id}/context`
  - `DELETE /api/admin/memory/users/{user_id}`
- 知识库管理
  - `GET /api/admin/knowledge/documents`
  - `GET /api/admin/knowledge/documents/{document_id}`
  - `POST /api/admin/knowledge/documents`
  - `PATCH /api/admin/knowledge/documents/{document_id}`
  - `POST /api/admin/knowledge/documents/{document_id}/replace`
  - `GET /api/admin/knowledge/documents/{document_id}/versions`
  - `GET /api/admin/knowledge/documents/{document_id}/versions/{version_id}`
  - `POST /api/admin/knowledge/documents/{document_id}/rollback`
  - `DELETE /api/admin/knowledge/documents/{document_id}`
  - `POST /api/admin/knowledge/documents/{document_id}/restore`
- 系统设置
  - `GET /api/admin/settings/summary`
  - `POST /api/admin/settings/runtime`
  - `POST /api/admin/settings/frontend-policy`
- 账号管理
  - `GET /api/admin/users`
  - `GET /api/admin/users/{user_id}`
  - `PATCH /api/admin/users/{user_id}/status`
  - `PATCH /api/admin/users/{user_id}/role`

更详细的接口说明见 [docs/admin-api.md](./docs/admin-api.md)。

## 知识库后台说明

知识库后台当前采用文件系统 + JSON 注册表方案：

- 活动文件目录：`data/docs/`
- 回收目录：`data/knowledge/trash/`
- 历史目录：`data/knowledge/history/`
- 注册表：`data/knowledge/registry.json`

每条文档记录至少包含：

- `document_id`
- `filename`
- `checksum`
- `chunk_count`
- `description`
- `tags`
- `published`
- `visible_to_frontend`
- `allowed_roles`
- `deleted`

恢复策略：

- 恢复后默认 `published=false`
- 恢复后默认 `visible_to_frontend=false`

版本回滚策略：

- 会回滚：文件内容、`filename`、`description`、`tags`
- 不会自动回滚：`published`、`visible_to_frontend`、`allowed_roles`、`deleted`
- 回滚会基于目标历史版本生成一个新的当前版本，不会直接改写旧版本

## 文档

- 后台 API 文档：[docs/admin-api.md](./docs/admin-api.md)
- 用户手册：[docs/admin-user-guide.md](./docs/admin-user-guide.md)
- 管理员指南：[docs/admin-admin-guide.md](./docs/admin-admin-guide.md)
- Phase 1 测试报告：[docs/reports/2026-04-14-admin-backoffice-foundation-test-report.md](./docs/reports/2026-04-14-admin-backoffice-foundation-test-report.md)
- Phase 2 测试报告：[docs/reports/2026-04-15-admin-knowledge-phase2-test-report.md](./docs/reports/2026-04-15-admin-knowledge-phase2-test-report.md)
- Phase 3 测试报告：[docs/reports/2026-04-15-admin-knowledge-phase3-test-report.md](./docs/reports/2026-04-15-admin-knowledge-phase3-test-report.md)

## 测试与验证

本阶段知识库后端验证：

```bash
D:\agentlearn\miniconda\envs\test3\python.exe -m unittest tests.admin.test_knowledge_admin_registry -v
D:\agentlearn\miniconda\envs\test3\python.exe -m unittest tests.admin.test_knowledge_admin_phase2_api -v
D:\agentlearn\miniconda\envs\test3\python.exe -m unittest tests.admin.test_knowledge_visibility -v
D:\agentlearn\miniconda\envs\test3\python.exe -m unittest tests.admin.test_knowledge_admin_versioning_service -v
D:\agentlearn\miniconda\envs\test3\python.exe -m unittest tests.admin.test_knowledge_admin_versioning_api -v
```

后台前端验证：

```bash
cd frontend
npm run test:admin
npm run build
```

## 数据目录

- 认证数据库：`data/auth/app.db`
- 记忆上下文：`data/memory/session_context/`
- 长期画像：`data/memory/long_term/`
- 知识文件：`data/docs/`
- 知识文件回收区：`data/knowledge/trash/`
- 知识历史版本：`data/knowledge/history/`
- 知识注册表：`data/knowledge/registry.json`
- 后台审计日志：`logs/admin_audit.jsonl`

## 常见问题

### `ModuleNotFoundError: No module named 'app'`

优先在项目根目录执行：

```bash
python backend/run_backends.py
```

### 后台页面可以打开，但接口失败

确认以下三项：

- `python backend/run_backends.py` 已正常启动
- `http://localhost:8001/docs` 可访问
- 后台前端是通过 `npm run admin` 启动，而不是直接打开静态文件

### 端口被占用

默认端口：

- 后端：`8000`、`8001`
- 前端：`5173`、`5174`

请先结束占用端口的进程，再重新启动。
# 2026-04-16 Update

新增后台系统设置 Phase 2 能力：

- 运行参数治理增加服务层校验与 `400` 错误映射
- 后台新增 `POST /api/admin/settings/frontend-policy`
- 后台设置页升级为“运行参数 + 前台展示策略 + 权限说明”三段结构
- 前台知识库和前台设置摘要改为消费正式 `frontend_policy`

当前系统设置模块边界：

- 系统设置：运行参数、前台展示策略、权限模型只读说明
- 知识库模块：单文档发布、前台显隐、允许角色、版本历史、回滚
- 记忆管理模块：用户长期偏好与上下文

相关验证命令：

```bash
D:\agentlearn\miniconda\envs\test3\python.exe -m unittest tests.admin.test_settings_admin_service tests.admin.test_settings_admin_api tests.admin.test_knowledge_visibility -v
cd frontend
npm run test:admin -- src/admin/__tests__/settings-admin-page.test.js src/admin/__tests__/knowledge-admin-page.test.js src/admin/__tests__/admin-nav.test.js src/admin/__tests__/admin-shell.test.js src/components/__tests__/knowledge-base-panel.test.js src/components/__tests__/settings-panel.test.js
npm run build
```
