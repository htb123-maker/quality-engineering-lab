# 认证失败排查 / Authentication Failure Triage

触发条件：登录、JWT、Bearer、Cookie、refresh token、401 或 403 测试失败。

本 runbook 不允许记录真实 token、Cookie、密码、私钥或生产凭据。只保存状态码、
非敏感错误码、token 生命周期、用户角色和最小复现。

## 1. 先判断失败层

```text
测试配置
-> OIDC discovery
-> 登录 / password grant
-> access token 校验
-> refresh token 轮换
-> Bearer 或 Cookie 传递
-> 角色和资源权限
-> 测试断言
```

不要在未确认层级前直接修改断言或增加重试。

## 2. 快速检查

### SUT 和发现文档

```powershell
Invoke-RestMethod http://127.0.0.1:18000/health/ready
Invoke-RestMethod http://127.0.0.1:18000/.well-known/openid-configuration
```

预期：readiness 为 `ready`，discovery 包含 `/oauth/token`、
`/api/v1/auth/me` 和 `/oauth/revoke`。

### 本地测试凭据

```powershell
$env:QA_AUTH_TEST_USERNAME
$env:QA_AUTH_TEST_PASSWORD
```

如果未设置，使用 `.env.example` 中明确标注的本地测试默认值。不要把任何真实
密码复制进仓库或聊天记录。

### Linux 容器认证契约

```powershell
.\scripts\run_integration_linux.ps1 -SkipSutStart
```

预期：`10 passed`。该命令覆盖健康检查、PostgreSQL、Redis、API smoke 和认证
契约。

## 3. 常见症状和边界

| 症状 / Symptom | 可能层 / Likely Layer | 检查 / Check | 不应怎么做 / Do Not |
| --- | --- | --- | --- |
| discovery 404 | SUT 镜像未重建 | 重建 `api`，检查 `.well-known` 路由 | 不要跳过 discovery 测试 |
| `invalid_grant` 登录失败 | 测试账号、密码或用户状态 | 检查用户名、测试密码、`users.status` | 不要打印密码 |
| 首次 `/me` 200，稍后 401 | access token 到期 | 检查 `exp`、SDK skew、刷新日志 | 不要关闭 JWT 过期 |
| 刷新后再次刷新失败 | token 已轮换或重放 | 使用最新 refresh token | 不要自动重试 refresh POST |
| viewer 收到 403 | 权限边界正确 | 检查角色和路由预期 | 不要把 403 改成跳过 |
| Cookie 模式 401 | Cookie 未保存或未携带 | 检查 `Set-Cookie`、域名、Path、httpx Cookie Jar | 不要同时强行加 Bearer 掩盖问题 |
| 并发时只有一次刷新成功 | 服务端轮换正常 | 检查 SDK 是否单飞 | 不要让每个线程独立刷新 |
| Redis 重启后 refresh 失效 | 会话存储丢失 | 重新登录 | 不要把失效当产品缺陷 |

## 4. 证据采集

允许保存：

- HTTP 状态码和非敏感 OAuth `error`。
- 用户 ID、workspace、role。
- JWT `iss`、`iat`、`exp`、`jti` 的存在性和生命周期，不保存完整 token。
- SDK 中 refresh attempt 次数和结果。
- Redis key 是否存在的布尔结果，不保存 key 中的完整摘要。
- Allure 中的 discovery、用户信息和 403 响应。

禁止保存：

- Authorization 头。
- Cookie 值。
- access token 或 refresh token 原文。
- 密码、JWT 密钥、私钥和生产凭据。

## 5. 最小复现

```powershell
.\.venv\Scripts\python.exe -m pytest `
  tests\unit\test_auth_client.py `
  tests\api\test_auth.py `
  -q -p no:cacheprovider
```

预期：`12 passed`。如果单元测试通过、API 失败，问题通常在 SUT 契约或容器
状态；如果两者都失败，先检查 SDK 和配置。

## 6. 并发刷新判定

只有以下现象可以判定为 SDK 单飞正常：

```text
多个线程同时需要刷新
+ 服务端只消费一次旧 refresh token
+ 所有线程最终使用同一个新 access token
```

如果服务端记录多次消费、旧 token 被第二个线程再次使用，或线程收到不同的
`invalid_grant`，先检查锁是否覆盖“重新读取 token + 刷新”的完整临界区。

## 7. 关闭条件

只有以下条件同时满足才能关闭认证故障：

1. 有明确失败层和最小复现。
2. 修复后单元测试和真实 API 测试通过。
3. 401、403、refresh replay 中至少一个负向边界被验证。
4. 不通过无限重试、延长 token、关闭鉴权或跳过测试掩盖问题。
5. 报告不包含 token、Cookie、密码或密钥。
