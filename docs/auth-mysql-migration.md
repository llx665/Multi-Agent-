# 认证库迁移到 MySQL

## 1. 前提

- 已创建目标 MySQL 数据库，例如 `testdb`
- 已安装项目依赖
- `.env` 中的 `DATABASE_URL` 已指向目标 MySQL

## 2. 迁移现有 SQLite 用户

```powershell
$env:DATABASE_URL = (Get-Content .env | Select-String '^DATABASE_URL=').ToString().Split('=', 2)[1]
D:\agentlearn\miniconda\envs\test3\python.exe backend/scripts/migrate_auth_sqlite_to_mysql.py --source data/auth/app.db --database-url $env:DATABASE_URL
```

## 3. 创建或修复种子账户

```powershell
$env:DATABASE_URL = (Get-Content .env | Select-String '^DATABASE_URL=').ToString().Split('=', 2)[1]
D:\agentlearn\miniconda\envs\test3\python.exe backend/scripts/seed_auth_users.py --database-url $env:DATABASE_URL --password ChangeMe123!
```

## 4. 默认种子账户

- `super_admin1` / `ChangeMe123!`
- `admin1` / `ChangeMe123!`
- `operator1` / `ChangeMe123!`
- `user1` / `ChangeMe123!`

首次验收完成后应立即修改这些密码。
