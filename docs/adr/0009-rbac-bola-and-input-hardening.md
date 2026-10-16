# ADR-0009: RBAC 能力矩阵、BOLA 与输入加固 / RBAC Capability Matrix, BOLA, and Input Hardening

- 状态 / Status: Accepted
- 日期 / Date: 2026-10-16
- 决策者 / Deciders: Quality Engineering Lab
- 替代 / Supersedes: 部分替代 ADR-0005 的限流章节（新增 principal 桶与预算响应头）
- 相关 / Related: ADR-0003（认证与刷新）、ADR-0005（错误语义与幂等）、ADR-0006（命名空间隔离）

## 背景 / Context

Week 7 证明了“写接口会对错误输入说不”，Week 8 证明了“并行测试不互相污染”，
Week 10 证明了“缓存和异步任务的答案可能是旧的”。到 Week 11，问题变成：

**认证解决“你是谁”，授权才解决“你能碰什么”。**

- SUT 已经有 `owner/admin/member/viewer` 四种角色，但授权判断散落在各个 handler 里，
  用 `role not in {"owner","admin","member"}` 这种字面量比较。加一个角色或一个接口，
  就得靠人肉扫描所有分支。
- 对象 id 是连续自增的。跨租户猜 id 能不能读到别人的数据（BOLA/IDOR）？
  读不到的时候，返回码会不会反而告诉攻击者“这个对象确实存在”？
- 限流键是调用方自己传的 `X-QA-Client-Id`。改一个 header 就能重置预算的话，
  限流只是仪式感。
- 错误语义只有 400/422：body 太大、媒体类型不对、JSON 解析失败都被塞进同一个抽屉，
  失败分类也就无法指出责任方。

English: Week 11 must turn scattered role checks into one capability matrix, prove
that object ids do not cross tenants, make the write budget resist header
rotation, split request-shape failures into 400/413/415/422, and throttle
password-grant brute force.

## 决策 / Decision

1. **授权只认能力（capability），不认角色字符串。**
   `ROLE_CAPABILITIES` 是唯一的权限事实来源，handler 只调用
   `has_capability(user["role"], "catalog:write")`。
   - 能力表：`catalog:read`、`catalog:write`、`catalog:refresh`、`members:read`、
     `members:write`、`audit:read`、`events:read`、`jobs:read`。
   - 角色映射：`owner == admin`（全部能力），`member` 少了 `audit:read` 与
     `members:write`，`viewer` 只有 `catalog:read`、`events:read`、`jobs:read`。
   - 测试侧 `qa_core.security.roles` 复制同一份矩阵，并用单元测试断言两份完全相等；
     否则“按角色断言”的用例只是复述服务端的回答。
2. **新增 `GET /api/v1/auth/permissions` 让权限自描述。**
   服务端返回调用者的角色与能力列表，权限用例只比对“能力列表 vs 镜像矩阵”。
3. **成员管理是一个真实业务面，而不是布尔开关。**
   `GET/POST /api/v1/workspaces/{slug}/members`、
   `PATCH/DELETE /api/v1/workspaces/{slug}/members/{user_id}` 复用 `users` 表，
   不动数据库 schema。
   - **owner 不可通过接口指派**：`MemberCreate.role` / `MemberRoleUpdate.role` 的
     契约只允许 `admin|member|viewer`，请求 `owner` 直接 422。
   - **admin 不能造 admin**：admin 只能授予 `member|viewer`，越级返回
     403 `role_escalation_forbidden`。
   - **owner 行受保护**：改角色或删除 owner 返回 403 `owner_protected`。
   - **不能改自己**：改/删自己的成员记录返回 403 `self_modification_forbidden`
     （防止最后一个管理员自降级把自己锁在门外）。
4. **租户可见性规则：同一个 slug 空间内讲角色，跨租户讲存在性。**
   - 对象在自己的租户里但角色不够 → 403 `permission_denied`。
   - 对象属于别的租户 → 同样是 403 `permission_denied`；响应体只含
     `error` 与 `message`，不含对方的工作区标识、成员邮箱或数据。
   - 唯一例外是**自增 id 的读接口**：`GET .../catalog/items/{item_id}` 与
     `PATCH/DELETE .../members/{user_id}` 对“别的租户的 id”和“不存在的 id”
     都返回 404（`item_not_found` / `member_not_found`），否则 403/404 的差异
     就是一个免费的对象枚举 oracle。
   - 跨租户**写**接口保持 403（沿用 Week 7 起的既有契约）：工作区 slug 本来就能通过
     公开目录读接口枚举，403 与 404 的差异不泄露新信息。这条取舍写进了
     `tests/api/test_bola_idor.py::test_write_paths_refuse_another_tenants_workspace`。
5. **工作区 slug 在进入数据库之前先做词法校验。**
   路径段必须匹配 `^[a-z0-9](?:[a-z0-9-]{0,58}[a-z0-9])?$`；
   `%2f`、`..`、大写、`%00` 等一律 400 `invalid_workspace_slug`。
   slug 是唯一来自 URL 且会进 SQL 的路径段，校验放在最外层而不是依赖参数化查询兜底。
6. **请求形状失败分成四类，各归各家。**
   - 400 `invalid_request`：body 无法解析（坏 JSON、非 UTF-8、JSON 不是对象、
     嵌套过深触发 `RecursionError`）。
   - 413 `payload_too_large`：超过 `QA_MAX_REQUEST_BYTES`（默认 64 KiB），
     只 drain 有界字节并显式 `Connection: close`。
   - 415 `unsupported_media_type`：JSON API 收到非 `application/json`。
     OAuth2 端点保持 RFC 6749 习惯，仍返回 400 `invalid_request`。
   - 422 `validation_failed`：JSON 合法但字段违反契约（含文本字段里的控制字符）。
7. **限流改成双桶 + Redis 固定窗口。**
   - `ratelimit:write:client:{sha256(client_id)}`：`QA_RATE_LIMIT_WRITE_MAX`
     （默认 20 / 60 秒），调用方可以换 `X-QA-Client-Id`。
   - `ratelimit:write:principal:user:{user_id}`：`QA_RATE_LIMIT_PRINCIPAL_MAX`
     （默认 40 / 60 秒），换 header 也绕不过去。
   - 每个受限响应都回 `X-RateLimit-Limit`、`X-RateLimit-Remaining`、
     `X-RateLimit-Reset`、`X-RateLimit-Scope`；429 另带 `Retry-After`。
   - 计数器放 Redis 而不是进程内存：多副本共享同一个预算，且测试侧
     `NamespacePool` 在释放租约时可以删掉该工作区用户的 principal 桶——否则
     复用的 owner 用户会把上一个用例花掉的预算带进下一个用例。
   - Redis 不可用时**失败开放**并记录日志：本地 SUT 不应因为缓存故障变成不可写。
8. **密码授予有独立的失败计数器。**
   `auth:signin-failures:{sha256(client|email)}` 按 `(客户端, 账号)` 计数，
   TTL 等于 `QA_AUTH_SIGNIN_FAILURE_WINDOW_SECONDS`；累计
   `QA_AUTH_SIGNIN_FAILURE_MAX`（默认 10）次失败后返回 429 `rate_limited` +
   `Retry-After`，登录成功即清零。锁的是账号，不是整个客户端或整个 API。
9. **恶意文本是数据，不是代码。** `<script>`、`DROP TABLE`、`../../etc/passwd`
   这类字符串会被原样存储和原样返回（控制字符除外，它们 422）；用例证明
   响应头不会被反射、目录接口仍然可用、schema 与种子行保持不变。

English: one capability registry, a self-describing permissions endpoint, owner-safe
membership rules, 404-not-403 for id-based reads across tenants, slug validation
before SQL, four distinct request-shape failures, a Redis-backed dual write
budget, a per-account password-grant throttle, and hostile text treated as data.

## 结果 / Consequences

正向结果：

- 角色矩阵变成可执行断言：`tests/api/test_rbac_matrix.py` 对四个角色 × 六个动作
  逐个比对 `qa_core.security.roles`，`tests/unit/test_role_matrix.py` 再锁死镜像与
  SUT 注册表一致。
- 越权读取无法用 id 枚举：别的租户的 `item_id` 和随手编的 id 返回完全同形状的 404。
- 限流不再依赖调用方自觉：41 次写请求即便每次都换 `X-QA-Client-Id`，第 41 次
  仍会被 principal 桶拦下（`X-RateLimit-Scope: principal`）。
- 失败分类能指出责任方：413/415/400 归 test，403 系列归 permission，
  429 归 environment，都有 `_EXACT` 映射与单元测试。
- 暴力破解有可观测证据：Redis 计数器数值、TTL、`Retry-After` 三者可同时断言。

代价和约束：

- **契约变更**：JSON API 的媒体类型错误从 400 变成 415；
  `GET .../catalog/items/{item_id}` 从“无路由”变成需要认证的读接口。
  两处都更新了 Week 7 的既有用例，并在 `reports/weekly/WEEK-11.md` 里登记。
- 每次写请求多两次 Redis 往返。本地 SUT 可以接受；性能阶段要用真实压测决定是否需要
  本地预聚合或令牌桶。
- 限流失败开放意味着 Redis 长时间不可用时限流失效；这是可用性优先的显式取舍。
- 成员接口用的是明文测试口令 + 共享密码，不是生产身份方案；SUT 仍然只是本地实验床。
- 公开的目录读接口 `GET /api/v1/workspaces/{slug}/catalog` 依旧不需要认证。
  它是 Week 2 起的既有契约，Week 11 不改动，只在风险章节记录为已知边界。

## 备选方案 / Alternatives

| 方案 / Option | 未采用原因 / Why not |
| --- | --- |
| 继续用 `role in {"owner","admin"}` 字面量判断 | 权限事实分散，加接口必然漏判；也无法自描述 |
| 引入 Casbin/OPA 做策略引擎 | 对四种角色八个能力过重，且会把权限事实搬出仓库 |
| 跨租户一律 403 | 自增 id 场景下 403/404 的差异就是免费的对象枚举 oracle |
| 跨租户一律 404 | 会推翻 Week 7/8/10 已固化的写路径契约；slug 本身并非秘密 |
| 只按 `X-QA-Client-Id` 限流 | 调用方自报家门，换 header 即绕过 |
| 用进程内存计数限流 | 多副本不共享，且复用的测试命名空间会把预算带进下一个用例 |
| 限流时 Redis 不可用就返回 503 | 把缓存故障升级成写接口故障，与 Week 10 的降级策略不一致 |
| 依赖参数化查询“顺便”挡注入 | 参数化只保证值安全；非法标识符应当更早、更明确地被拒绝 |
| 对 `<script>` 等内容做转义或黑名单 | 转义是输出侧责任，黑名单永远漏；此处只需证明不执行、不反射 |
| 给 owner 也开放“转让所有权”接口 | 所有权转移需要独立流程与审计，不属于本周范围 |

## 验证证据 / Verification

- `apps/compose/api/app.py`（能力表、成员接口、item 读接口、双桶限流、登录失败计数、
  请求体加固）
- `packages/qa_core/security/roles.py`、`members.py`、`limits.py`、`probes.py`
- `packages/qa_core/contracts/api.py`、`openapi.py`、`packages/qa_core/api_errors.py`
- `packages/qa_core/config/settings.py`、`.env.example`、`apps/compose/compose.yaml`
- `packages/qa_core/resource_pools/namespaces.py`（租约释放时清理 principal 预算桶）
- `tests/api/test_rbac_matrix.py`、`test_bola_idor.py`、`test_rate_limit_boundaries.py`、
  `test_auth_lockout.py`、`test_input_security.py`
- `tests/integration/test_membership_rbac_db.py`
- `tests/unit/test_role_matrix.py`、`test_rate_budget_window.py`、
  `test_security_classification.py`、`test_input_hardening_contract.py`
- `docs/runbooks/authorization-and-input-security-triage.md`
- `reports/weekly/WEEK-11.md`

## 重新评估条件 / Revisit Triggers

- 角色模型扩张（团队、项目、组织级角色，或按资源的 ACL）：需要真正的策略引擎与
  策略版本管理，而不是一张常量表。
- 需要所有权转让、邀请链接、邀请过期或二次确认：成员接口要升级为邀请流程。
- 需要跨租户返回一致的 404（例如对外多租户 SaaS）：届时把写路径也改成 404，
  并同步更新 Week 7 起的契约与用例。
- 需要审计每一次拒绝：403/404 需要落审计表并关联请求 id，而不是只写日志。
- 限流要求从“防误用”升级为“防滥用”：需要令牌桶、按端点配额、分布式滑窗
  与真实的客户端身份（API key / mTLS），而不是可伪造的 header。
- 登录失败计数需要账号锁定、告警或验证码：要引入真正的身份策略与解封流程。
- 输入侧出现文件上传、压缩包或富文本：需要独立的解析加固与资源限额专题。
- 目录读接口改为需要认证：会同时影响 Week 2 起的 smoke 与文档用例。
