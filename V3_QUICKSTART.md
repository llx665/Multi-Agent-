# ChatService V3 快速启动

这份文档只保留“最快跑起来”的必要步骤，适合第一次启动仓库时使用。

## 1. 安装依赖

在项目根目录 `test2langchain` 执行：

```bash
conda create -n test3 python=3.10 -y
conda activate test3
pip install -r requirements.txt -r backend/requirements.txt
```

前端依赖：

```bash
cd frontend
npm install
cd ..
```

## 2. 准备环境变量

如果还没有 `.env`：

```bash
# Windows PowerShell
Copy-Item .env.example .env
```

至少确认以下变量存在：

- `OPENAI_API_KEY`
- `DEEPSEEK_API_KEY`
- `AMAP_API_KEY`
- `TAVILY_API_KEY`
- `DATABASE_URL`

默认数据库可直接使用：

```env
DATABASE_URL=mysql+pymysql://root:your_mysql_password_here@127.0.0.1:3306/testdb?charset=utf8mb4
```

For SQLite auth migration steps, see `docs/auth-mysql-migration.md`.

## 3. 启动后端

```bash
python backend/run_backends.py
```

启动后：

- 用户 API：`http://localhost:8000`
- 后台 API：`http://localhost:8001`

健康检查：

- `http://localhost:8000/api/v1/health`
- `http://localhost:8001/health`

## 4. 启动用户前台

新开一个终端：

```bash
cd frontend
npm run dev
```

访问：`http://localhost:5173`

## 5. 启动后台前端

再开一个终端：

```bash
cd frontend
npm run admin
```

访问：`http://localhost:5174/admin.html`

## 6. 默认访问边界

- 用户前台
  - 对话
  - 只读知识库
  - 只读设置摘要
- 后台管理
  - 总览
  - 记忆管理
  - 知识库管理
  - 系统设置
  - 账号管理

角色模型：

- `super_admin`
- `admin`
- `operator`
- `user`

说明：

- 普通 `user` 无后台访问权限
- 前台知识库只显示“已发布 + 前台可见 + 角色允许访问”的文件
- 知识文件的发布、隐藏和角色范围统一在后台维护

## 7. 验证命令

后端：

```bash
D:\agentlearn\miniconda\envs\test3\python.exe -m unittest \
  tests.admin.test_auth_role_foundation \
  tests.admin.test_admin_access_and_audit \
  tests.admin.test_user_admin_api \
  tests.admin.test_memory_admin_api \
  tests.admin.test_knowledge_visibility \
  tests.admin.test_settings_admin_api \
  tests.test_memory_admin_localization -v
```

前端：

```bash
cd frontend
npm run test:admin
npm run build
```

## 8. 常见问题

### 后台接口请求失败

通常是以下原因之一：

- 后台 API 没有启动
- 后台前端不是通过 `npm run admin` 启动
- Token 登录态已经失效

### 端口冲突

默认端口：

- 用户 API：`8000`
- 后台 API：`8001`
- 用户前端：`5173`
- 后台前端：`5174`
