## 现状回顾
- 仅通过`admin_user_id`硬编码区分管理员，普通用户与“角色”用`users.is_character`布尔值标识。
- 无统一RBAC/ACL、无路由级鉴权装饰器、无JWT签发与校验、无权限缓存。

## 改造目标
- 引入标准RBAC：`roles`、`permissions`与用户多对多绑定；提供细粒度API/动作权限。
- 建立统一鉴权中间件与异常处理，支持外部令牌与内部会话令牌。

## 数据模型
- 新增集合：`roles(name, description, parent_id?)`、`permissions(key, description)`、`user_roles(user_id, role_id)`、`role_permissions(role_id, permission_key)`。
- `users`保留`is_character`用于区分“角色型用户”，不再承担权限语义。

## 鉴权中间件
- 在Flask层引入装饰器：`@requires_role("admin")`、`@requires_permission("output:publish_pyq")`。
- 统一拦截：解析请求身份→加载用户角色→汇总权限→判定访问。
- 异常处理：403（Forbidden）与401（Unauthorized）分流，返回结构化错误。

## 令牌与会话
- 兼容外部E云`Authorization`；内部服务对管理与工具接口签发JWT（`access_token`、可选`refresh_token`）。
- 身份解析优先顺序：内部JWT→外部代理标识→匿名（受限）。

## 缓存策略
- 以内存或Redis缓存`user→roles→permissions`映射（TTL与主动失效）。
- 针对高频接口（消息入站）使用只读缓存，后台变更时清理。

## 迁移步骤
1. 建表脚本与DAO：`roles`、`permissions`、`user_roles`、`role_permissions`。
2. 管理入口：创建默认角色（admin/character/user）与基础权限集。
3. 将`admin_user_id`迁移为`user_roles`中`admin`绑定；下线硬编码判断。
4. 为关键路由加装饰器（消息入站、朋友圈发布、图片上传）。
5. 引入JWT模块、统一错误返回与日志审计。
6. 添加缓存层与失效策略；压测与灰度上线。

## 里程碑
- M1：数据层与管理入口可用
- M2：路由鉴权与异常处理到位
- M3：令牌与缓存上线，完成切换