# ADR-0003: 本地 OAuth2/OIDC 认证与刷新轮换边界 / Local OAuth2/OIDC Authentication and Refresh Rotation

- 状态 / Status: Accepted
- 日期 / Date: 2026-10-08
- 决策者 / Deciders: Quality Engineering Lab
- 替代 / Supersedes: None

## 背景 / Context

Week 4 已经建立统一 HTTP Client，但 API、Android/iOS E2E 建数、数据库准备和后续
Locust 还没有共享认证 SDK。如果每条测试自己登录、解析 token 和刷新，会产生以下
问题：

- token 过期判断不一致。
- 并发请求同时刷新，导致 refresh token 被重复使用或互相覆盖。
- 测试日志可能意外记录 Bearer、Cookie、refresh token 或密码。
- 401、403 和登录失败缺少统一错误边界。
- 移动端和性能测试无法复用同一套认证状态。

English: Week 5 needs one reusable authentication boundary before authentication
logic spreads across API, mobile E2E, and performance tests.

## 决策 / Decision

1. 本地 SUT 提供轻量 OAuth2/OIDC 契约：
   `/.well-known/openid-configuration`、`/oauth/token` 和 `/oauth/revoke`。
2. `/oauth/token` 支持本地 SUT 的 `password` 和 `refresh_token` grant。
   `password` 只用于隔离测试环境，不代表生产推荐流程。
3. 访问令牌使用 HS256 JWT，包含 `iss`、`sub`、`role`、`iat`、`exp` 和唯一
   `jti`。即使同一用户在同一秒刷新两次，访问令牌也不会相同。
4. 刷新令牌是随机不透明字符串，不进入 URL。Redis 只保存其 SHA-256 摘要，
   并设置有限 TTL。
5. 刷新采用轮换语义：服务端用 Redis 原子 `GETDEL` 消费旧刷新令牌，再签发
   新访问令牌和刷新令牌。旧令牌重放必须得到 `invalid_grant`。
6. `AuthClient` 在 Bearer 模式添加 Authorization 头；Cookie 模式依赖 `httpx`
   Cookie Jar。本地 SUT 把访问令牌同时放入 `HttpOnly`、`SameSite=Lax` Cookie。
7. SDK 使用线程锁实现单飞刷新：
   - 访问令牌距到期不足安全窗口时，主动刷新。
   - 请求收到 401 时，最多执行一次被动刷新和一次请求重放。
   - 多个线程使用同一个旧访问令牌时，只允许一个线程完成刷新，其他线程复用
     新令牌。
8. 刷新请求不自动重试。刷新令牌会轮换，重复 POST 可能让测试把有效会话误判为
   失效。
9. SDK 本地解码 JWT claims 只用于到期调度和诊断，不把未验证 claims 当作
   授权事实。真正的签名、issuer、角色和用户状态校验仍由 SUT 完成。
10. API、Appium E2E 和 Locust 必须复用 `qa_core.auth.AuthClient`，不能复制
    token 和刷新逻辑。

English: use short-lived signed access tokens, rotating opaque refresh tokens
stored as Redis digests, one SDK-level single-flight refresh path, and explicit
Bearer/Cookie transports.

## 结果 / Consequences

正向结果：

- 登录、刷新、注销和受保护请求有统一 SDK。
- 并发刷新不会因多线程重复消费同一个 refresh token。
- Bearer 和 Cookie 都能用于测试真实接口边界。
- Redis TTL 可以模拟会话过期，`GETDEL` 提供真实轮换和重放保护。
- 小范围密码 grant 足以学习 token 生命周期，不建设不必要的授权服务器集群。
- 刷新失败会清除本地 token，后续请求明确报 `AuthenticationRequired`。

代价和约束：

- 当前 SUT 的密码 grant 是测试实现，不是生产级 Authorization Code + PKCE。
- 当前没有接入外部 IdP、JWKS、RS256、客户端注册、同意页或 MFA。
- SDK 的单飞刷新只保护单个进程。多进程测试仍依赖服务端刷新令牌轮换规则。
- 本地 SUT 使用固定测试密码和测试 JWT 密钥；它们不能进入生产环境。
- 刷新令牌状态保存在 Redis。Redis 丢失或清空会使已有会话失效。

## 备选方案 / Alternatives

| 方案 / Option | 未采用原因 / Why not |
| --- | --- |
| 每条测试自己调用登录接口 | token、刷新和错误处理会分叉 |
| 访问令牌永不过期 | 无法测试 401、刷新窗口和并发恢复 |
| 所有线程收到 401 后都刷新 | 会造成 refresh token 轮换竞态和重复失效 |
| 把 refresh token 明文保存进 PostgreSQL | 增加泄露面，Redis TTL 已满足本地会话需求 |
| 只支持 Bearer | 不能覆盖浏览器、移动 WebView 和 Cookie 边界 |
| 立即接入完整 Keycloak | Week 5 目标是 SDK 和协议边界，不是运维授权服务器 |
| 在 SDK 内把 JWT claims 当授权事实 | 客户端解码不等于服务端验签 |

## 验证证据 / Verification

- `packages/qa_core/auth/client.py`
- `packages/qa_core/http/client.py`
- `apps/compose/api/app.py`
- `tests/unit/test_auth_client.py`
- `tests/api/test_auth.py`
- `reports/weekly/WEEK-05.md`
- Linux container: `10 passed`
- Windows API: `6 passed`

## 重新评估条件 / Revisit Triggers

- 接入 Keycloak、Auth0、Okta 或其他真实 OIDC Provider。
- 需要 Authorization Code + PKCE、设备授权流、MFA 或客户端凭据流。
- 需要使用 JWKS、RS256/ES256 或离线签名验证。
- 多进程和多设备并发证明进程内锁不足。
- 需要刷新令牌重用检测、设备会话管理或服务端强制注销。
- 移动端 WebView、Cookie 域和 SameSite 行为需要独立策略。
- Locust 高并发需要异步认证、连接池拆分或 token 池。
