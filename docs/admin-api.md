# 后台 API 文档

## 基础信息

- 用户 API 基础路径：`/api/v1`
- 后台 API 基础路径：`/api/admin`
- 认证方式：`Authorization: Bearer <token>`

角色边界：

- `super_admin`：全部后台权限
- `admin`：总览、记忆、知识库、设置、账号管理
- `operator`：总览、记忆管理、知识库查看
- `user`：无后台权限

## 用户前台接口

### `GET /api/v1/knowledge-base`

说明：

- 需要登录
- 返回当前角色允许访问的只读知识库列表
- 列表过滤条件为：`deleted=false`、`published=true`、`visible_to_frontend=true`、`allowed_roles` 包含当前角色

响应字段：

- `documents`
  - `id`：稳定文档标识，等于后台 `document_id`
  - `filename`
  - `file_path`
  - `file_type`
  - `chunk_count`
  - `size`
  - `upload_time`
  - `update_time`
- `total`

### `GET /api/v1/knowledge-base/{document_id}`

说明：

- 需要登录
- 使用稳定 `document_id` 获取详情
- 如果文档未发布、前台隐藏、已删除或当前角色无权访问，返回 `404`

### `GET /api/v1/knowledge-base/params`

说明：

- 需要登录
- 返回当前 RAG 运行参数摘要、缓存统计和运行指标

## 后台总览

### `GET /api/admin/dashboard/summary`

权限：

- `operator`
- `admin`
- `super_admin`

## 后台记忆管理

### `GET /api/admin/memory/users`

权限：

- `operator`
- `admin`
- `super_admin`

查询参数：

- `query`：按 `user_id` 或 `username` 搜索
- `active_only`：按上下文活跃状态筛选

### `GET /api/admin/memory/users/{user_id}`

权限：

- `operator`
- `admin`
- `super_admin`

### `POST /api/admin/memory/users/{user_id}/preferences`

权限：

- `operator`
- `admin`
- `super_admin`

请求体示例：

```json
{
  "key": "preferred_channel",
  "value": "wechat",
  "confidence": 0.8
}
```

### `DELETE /api/admin/memory/users/{user_id}/context`

权限：

- `operator`
- `admin`
- `super_admin`

### `DELETE /api/admin/memory/users/{user_id}`

权限：

- `operator`
- `admin`
- `super_admin`

## 后台知识库管理

知识库后台以稳定 `document_id` 为主键，所有写操作都会写入审计日志，并维护 `chunk_count`、`checksum`、`deleted` 等运行指标。

### `GET /api/admin/knowledge/documents`

权限：

- `operator`
- `admin`
- `super_admin`

查询参数：

- `keyword`：按文件名、描述、标签搜索
- `status`：`active`、`deleted`、`all`
- `published`：可选布尔值
- `visible_to_frontend`：可选布尔值

响应字段：

- `document_id`
- `filename`
- `file_type`
- `storage_name`
- `storage_path`
- `size`
- `checksum`
- `chunk_count`
- `description`
- `tags`
- `published`
- `visible_to_frontend`
- `allowed_roles`
- `deleted`
- `created_at`
- `created_by`
- `updated_at`
- `updated_by`
- `deleted_at`
- `deleted_by`
- `upload_time`
- `update_time`

### `GET /api/admin/knowledge/documents/{document_id}`

权限：

- `operator`
- `admin`
- `super_admin`

说明：

- 返回单个文档完整元数据
- 支持获取已删除文档详情

### `POST /api/admin/knowledge/documents`

权限：

- `admin`
- `super_admin`

请求类型：

- `multipart/form-data`

表单字段：

- `file`：必填，支持 `.txt`、`.pdf`、`.docx`
- `description`：可选
- `tags`：可选，JSON 数组字符串
- `allowed_roles`：可选，JSON 数组字符串
- `published`：可选，布尔值
- `visible_to_frontend`：可选，布尔值

行为：

- 上传新文件到 `data/docs/`
- 写入向量库并刷新 `chunk_count`
- 生成新的稳定 `document_id`
- 写入知识库注册表 `data/knowledge/registry.json`

常见错误：

- `400`：文件名或类型非法
- `409`：同名活动文档已存在

### `PATCH /api/admin/knowledge/documents/{document_id}`

权限：

- `admin`
- `super_admin`

请求体示例：

```json
{
  "description": "产品 FAQ",
  "tags": ["faq", "release"],
  "visible_to_frontend": true,
  "published": true,
  "allowed_roles": ["user", "operator", "admin", "super_admin"]
}
```

说明：

- 仅更新元数据
- 不替换文件内容
- 兼容旧调用方式：仍允许部分历史逻辑按文件名进入服务层

### `POST /api/admin/knowledge/documents/{document_id}/replace`

权限：

- `admin`
- `super_admin`

请求类型：

- `multipart/form-data`

表单字段：

- `file`：必填，新文件

行为：

- 保留原有 `document_id`
- 删除旧文件分块并覆盖活动文件
- 重新生成 `checksum`、`size`、`chunk_count`
- 已发布文档替换后保留原发布状态

常见错误：

- `400`：文档已删除，不能直接替换
- `409`：新文件名与其他活动文档冲突

### `GET /api/admin/knowledge/documents/{document_id}/versions`

权限：

- `operator`
- `admin`
- `super_admin`

说明：

- 返回指定文档的版本历史列表
- 列表按 `version_no` 倒序返回，便于后台优先查看最新版本
- 响应包含 `current_version_id`，并在每条版本记录上标记是否为当前版本

响应字段：

- `document_id`
- `current_version_id`
- `versions`
  - `version_id`
  - `version_no`
  - `action`
  - `source_version_id`
  - `filename`
  - `checksum`
  - `chunk_count`
  - `created_at`
  - `created_by`
  - `is_current`

### `GET /api/admin/knowledge/documents/{document_id}/versions/{version_id}`

权限：

- `operator`
- `admin`
- `super_admin`

说明：

- 返回单个历史版本的完整快照详情
- 用于后台右侧版本详情面板展示

常见错误：

- `404`：文档不存在，或该版本不存在

### `POST /api/admin/knowledge/documents/{document_id}/rollback`

权限：

- `admin`
- `super_admin`

请求体示例：

```json
{
  "target_version_id": "ver_123456",
  "reason": "restore stable release"
}
```

说明：

- 基于指定历史版本生成一个新的当前版本
- 不会原地覆盖或修改旧历史版本
- 成功后返回最新文档详情，并额外包含 `target_version_id` 与 `new_version_id`

回滚行为边界：

- 会回滚：文件内容、`filename`、`description`、`tags`
- 不会自动回滚：`published`、`visible_to_frontend`、`allowed_roles`、`deleted`
- 已删除文档不能直接回滚，必须先恢复再回滚

常见错误：

- `400`：目标版本不属于当前文档
- `404`：目标文档或目标版本不存在
- `409`：文档已删除，或历史快照不可用于回滚

### `DELETE /api/admin/knowledge/documents/{document_id}`

权限：

- `admin`
- `super_admin`

行为：

- 软删除文档
- 文件从 `data/docs/` 移动到 `data/knowledge/trash/`
- 删除对应向量分块
- 将注册表状态更新为 `deleted=true`

### `POST /api/admin/knowledge/documents/{document_id}/restore`

权限：

- `admin`
- `super_admin`

行为：

- 从回收目录恢复文件
- 重新建立向量分块
- 恢复后强制设置：
  - `deleted=false`
  - `published=false`
  - `visible_to_frontend=false`

## 后台系统设置

### `GET /api/admin/settings/summary`

权限：

- `admin`
- `super_admin`

### `POST /api/admin/settings/runtime`

权限：

- `admin`
- `super_admin`

请求体示例：

```json
{
  "chunk_size": 400,
  "chunk_overlap": 50,
  "top_k": 5,
  "similarity_threshold": 0.3,
  "enable_cache": true,
  "enable_rerank": true,
  "enable_hybrid": true,
  "enable_self_rag": false
}
```

## 后台账号管理

### `GET /api/admin/users`

权限：

- `admin`
- `super_admin`

查询参数：

- `q`
- `role`
- `status`

返回字段：

- `users[].user_id`
- `users[].username`
- `users[].role`
- `users[].status`
- `users[].created_at`
- `users[].updated_at`

### `GET /api/admin/users/{user_id}`

权限：

- `admin`
- `super_admin`

返回字段：

- `user_id`
- `username`
- `role`
- `status`
- `created_at`
- `updated_at`
- `last_login_at`
- `password_updated_at`

常见错误：

- `404`：目标账号不存在

### `PATCH /api/admin/users/{user_id}/status`

权限：

- `admin`
- `super_admin`

请求体示例：

```json
{
  "status": "disabled"
}
```

行为：

- 仅支持 `active` 和 `disabled`
- 成功后写入审计日志，动作名为 `update_status`
- 成功响应：`{"user_id":"...","status":"disabled"}`

权限规则：

- `admin` 只能操作 `user` 和 `operator`
- `admin` 不能操作自己的账号状态
- `super_admin` 不能操作自己的账号状态

常见错误：

- `400`：`status` 非法
- `403`：无权限或命中状态操作限制
- `404`：目标账号不存在

### `PATCH /api/admin/users/{user_id}/role`

权限：

- `super_admin`

请求体示例：

```json
{
  "role": "operator"
}
```

行为：

- 仅支持 `user`、`operator`、`admin`、`super_admin`
- 成功后写入审计日志，动作名为 `update_role`
- 成功响应：`{"user_id":"...","role":"operator"}`

权限规则：

- 仅 `super_admin` 可调用
- 不能修改自己的角色

常见错误：

- `400`：`role` 非法
- `403`：无权限或尝试修改自己的角色
- `404`：目标账号不存在

## 审计日志

默认文件：

- `logs/admin_audit.jsonl`

当前知识库相关写入场景：

- `create_document`
- `replace_document`
- `knowledge.version.rollback`
- `update_document`
- `update_access`
- `delete_document`
- `restore_document`

其他主要写入场景：

- 后台总览访问
- 记忆偏好更新
- 记忆清理
- 运行参数更新
# 2026-04-16 Admin Settings Phase 2 Addendum

## `GET /api/v1/knowledge-base/params`

说明：

- 需要登录
- 返回当前 RAG 运行参数摘要、缓存统计、运行指标
- 新增 `frontend_policy` 字段，供前台知识库和前台设置摘要页消费正式展示策略

响应新增字段：

- `frontend_policy.knowledge_base.intro_text`
- `frontend_policy.knowledge_base.empty_state_text`
- `frontend_policy.knowledge_base.readonly_notice`
- `frontend_policy.knowledge_base.show_document_metrics`
- `frontend_policy.settings.show_summary`
- `frontend_policy.settings.show_runtime_overview`
- `frontend_policy.settings.show_permission_notice`
- `frontend_policy.settings.readonly_notice`

## `POST /api/admin/settings/frontend-policy`

权限：

- `admin`
- `super_admin`

说明：

- 更新系统级前台展示策略
- 不修改知识库单文档访问规则
- 不修改用户个人偏好
- 非法字段或非法类型返回 `400`

请求体示例：

```json
{
  "knowledge_base": {
    "intro_text": "这里只展示当前角色允许访问的知识文件。",
    "empty_state_text": "暂无可展示的知识文件。",
    "readonly_notice": "前台只读，编辑请前往后台。",
    "show_document_metrics": true
  },
  "settings": {
    "show_summary": true,
    "show_runtime_overview": true,
    "show_permission_notice": true,
    "readonly_notice": "如需修改配置，请由管理员在后台操作。"
  }
}
```

补充说明：

- `GET /api/admin/settings/summary` 现在返回 `runtime_params`、`frontend_policy`、`permission_model`
- `POST /api/admin/settings/runtime` 对无效参数组合返回 `400`

# 2026-05-07 Async Tasks Addendum

Slow knowledge operations can now return an accepted task response:

```json
{
  "success": true,
  "task_id": "task_...",
  "status": "queued",
  "message": "knowledge reload queued"
}
```

Operators can inspect queued work:

- `GET /api/admin/tasks`
- `GET /api/admin/tasks?status=queued`
- `GET /api/admin/tasks/{task_id}`
- `POST /api/admin/tasks/{task_id}/retry`

Task statuses:

- `queued`: waiting for a worker
- `running`: claimed by a worker
- `succeeded`: handler completed
- `failed`: reserved for adapters that keep failed tasks retryable
- `dead`: max attempts exhausted

The first queued handlers cover knowledge document indexing and knowledge reload. Chat remains synchronous; user-facing answer generation is not queued.
