# ADR-0002: HTTP 客户端超时与重试边界 / HTTP Client Timeout and Retry Boundaries

- 状态 / Status: Accepted
- 日期 / Date: 2026-10-05
- 决策者 / Deciders: Quality Engineering Lab
- 替代 / Supersedes: None

## 背景 / Context

Week 4 开始建立共享 API Client。后续 API 测试、数据准备、Appium E2E 建数和
Locust 用户旅程都需要经过同一套 HTTP 行为。如果每条测试直接调用 `httpx`
并各自设置超时和重试，会出现请求无限等待、重复创建资源、重试掩盖产品缺陷，
以及报告缺少统一日志字段等问题。

English: the shared HTTP layer must make timeout and retry behavior explicit
before API, mobile E2E, and performance workloads start depending on it.

## 决策 / Decision

`qa_core.http.HttpClient` 使用同步 `httpx.Client` 和分层超时：

1. `connect` 默认 2 秒，`read` 和 `write` 默认 5 秒，`pool` 默认 2 秒。
2. 默认最多尝试 3 次，指数退避从 0.25 秒开始，最大 2 秒。
3. 退避加入有上限的抖动，降低多个 worker 同时重试造成的同步冲击。
4. 默认只自动重试幂等方法：`GET`、`HEAD`、`OPTIONS`、`PUT`、`DELETE` 和
   `TRACE`。
5. `POST` 和 `PATCH` 默认不重试；调用方只有在业务确实幂等或具备幂等键时，
   才能显式传入 `retry=True`。
6. 自动重试的状态码为 `429`、`500`、`502`、`503` 和 `504`。
7. 如果响应包含 `Retry-After`，客户端优先采用服务端等待时间，但仍受最大
   退避上限约束，防止测试永久停住。
8. 所有尝试记录结构化字段：方法、请求路径、尝试序号、耗时、状态码或传输错误
   类型。日志不记录查询字符串、请求头和请求体，避免未来的 token、Cookie 或
   个人信息泄漏。
9. Allure 属于测试报告层。API 测试负责附加经过选择的响应证据，HTTP 核心不
   直接依赖 Allure。

## 结果 / Consequences

正向结果：

- 超时和重试策略由配置统一控制，可以被 PyCharm、CI 和后续 Locust 复用。
- 非幂等请求不会因为基础设施抖动而被静默重复执行。
- 429 和服务端错误有统一的退避行为，并保留最后一次真实响应。
- 结构化日志可以支持后续失败分诊和 Trace 关联。
- 测试报告可以选择性保存证据，而不会把敏感请求头写入核心日志。

代价和约束：

- 默认 Client 是同步实现；高并发 Locust 场景后续需要评估异步或连接池方案。
- 自动重试可能增加失败请求的总耗时；测试必须为超时预算和最大尝试次数负责。
- 重试不是缺陷修复。最终失败仍必须进入失败分类和产品、测试、环境边界判断。
- 显式 `retry=True` 表示调用方确认操作可安全重复，不能满足于“多试一次”。

## 备选方案 / Alternatives

| 方案 / Option | 未采用原因 / Why not |
| --- | --- |
| 不做应用层重试，只关闭连接 | 无法统一处理瞬时连接错误和受控服务端退避 |
| 对所有方法自动重试 | 可能重复创建订单、用户或其他非幂等资源 |
| 使用无限重试 | 会把产品缺陷和环境故障隐藏成长时间等待 |
| 每条测试自己封装 `httpx` | 超时、日志和重试语义会分叉，无法共享 |
| 在 HTTP 核心直接写 Allure 附件 | 核心层与测试报告耦合，复用到性能任务时负担过重 |

## 验证证据 / Verification

- `packages/qa_core/http/client.py`
- `packages/qa_core/config/settings.py`
- `tests/unit/test_http_client.py`
- `tests/api/test_sut_smoke.py`
- `artifacts/allure-report-week4/index.html`

## 重新评估条件 / Revisit Triggers

- 需要 OAuth2/OIDC 并发刷新、请求签名或复杂认证链路。
- 需要流式上传、下载或大文件传输。
- 性能场景证明同步连接池模型不足。
- 服务端引入标准幂等键协议，可以安全地扩大 POST 自动重试范围。
- Trace 和指标要求升级到 OpenTelemetry。

重新评估时新增 ADR，不修改本决策的历史结论。
