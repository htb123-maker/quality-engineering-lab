# ADR-0005: 错误分类、幂等与状态机契约 / Error Taxonomy, Idempotency, and State-Machine Contract

- 状态 / Status: Accepted
- 日期 / Date: 2026-10-13
- 决策者 / Deciders: Quality Engineering Lab
- 替代 / Supersedes: None

## 背景 / Context

Week 6 让响应有了强类型契约，但正向字段正确不代表行为正确。Week 7 需要回答四个
问题，否则负向测试会变成一堆没有统一语义的断言：

- 同一个失败应该用哪个状态码和错误码表达。
- 幂等重试要在哪里裁决，测试才能看到真实的重放语义。
- 非法状态转换由谁判定，测试如何稳定复现。
- 一条红色用例该由产品、测试、认证、权限还是环境负责。

English: Week 7 needs a single, testable decision for error semantics, idempotent
retries, state transitions, and failure ownership.

## 决策 / Decision

1. 错误响应继续复用 `qa_core.contracts` 的 `ApiError` 和
   `OAuthErrorResponse`；新增 `ValidationErrorResponse` 与 `FieldError` 表达
   逐字段校验失败。字段路径统一为 `$.field`，例如 `$.price_cents`。
2. 状态码语义固定为：
   - `400` 请求本身损坏：`invalid_request`、`unsupported_grant_type`。
   - `400` 凭据或刷新令牌被拒：`invalid_grant`。
   - `401` 无凭证或凭证无效：`authentication_required`、`invalid_token`。
   - `403` 已认证但无权：`permission_denied`。
   - `404` 资源不存在：`not_found`、`workspace_not_found`、`item_not_found`。
   - `409` 冲突：`sku_conflict`、`idempotency_conflict`、
     `invalid_state_transition`。
   - `422` 字段规则不满足：`validation_failed`。
   - `429` 超出请求预算：`rate_limited`，并带 `Retry-After`。
   - `503` 依赖不可用：`database_unavailable`。
3. 幂等由服务端裁决：`Idempotency-Key` 与请求 body 指纹一起存入 Redis，
   键为 `workspace_id` 与 key 摘要的组合。
   - 同键同 body：回放首次的响应状态和 body，并返回 `Idempotent-Replay: true`。
   - 同键不同 body：返回 `409 idempotency_conflict`，不产生第二条记录。
   - 无键：按普通请求处理，重复请求由唯一约束拒绝，用于对照。
4. 状态机由服务端裁决。当前只允许 `active -> archived`；其余转换
   （`archived -> archived`、`archived -> active`、`active -> active`）一律
   返回 `409 invalid_state_transition`。
5. 失败分类是测试侧职责，不进入响应体。
   `qa_core.api_errors.classify_error()` 与 `classify_response()` 把
   “状态码 + 错误码”映射为 `product`、`test`、`auth`、`permission`、
   `environment` 五类，供 Allure 附件和后续失败分诊复用。
6. 限流为固定窗口，按 client id（`X-QA-Client-Id` 请求头，缺省回退到来源地址）
   计数，阈值和窗口由 `QA_RATE_LIMIT_WRITE_MAX` 与
   `QA_RATE_LIMIT_WRITE_WINDOW_SECONDS` 控制。
7. 写接口只属于本地测试 SUT。`DELETE` 接口用于测试数据清理，保证种子行数
   `workspaces=2`、`users=3`、`items=4` 在测试后不变。

English: server-side decides error codes, idempotent replay, transitions, and
rate budget; the test side decides failure ownership.

## 结果 / Consequences

正向结果：

- 负向、边界、幂等和状态转换都有稳定、可断言的语义。
- 失败可以自动归因到产品、测试、认证、权限或环境，报告不再只说“红了”。
- 幂等重放可以证明“只执行一次”，而不是靠再次 409 推断。
- 测试写入不污染种子数据，`check_sut.py` 与集成测试继续成立。

代价和约束：

- SUT 新增写接口、Redis 幂等存储和内存限流计数器，本地实现复杂度上升。
- 幂等存储当前不处理并发写同一 key 的竞态，属于后续并行与一致性专题。
- 限流是进程内固定窗口，SUT 重启即清零，不追求生产级精度。
- 状态机只有一条合法转换，是刻意选择的可判定性而非真实业务建模。
- 失败分类是约定，不是自动真理；错误码变化时必须同步维护映射表。

## 备选方案 / Alternatives

| 方案 / Option | 未采用原因 / Why not |
| --- | --- |
| 把失败分类写进响应体 | 会破坏 Week 6 已发布契约，并把测试关注点耦合进产品响应 |
| 只用数据库唯一约束表达幂等 | 只能发现重复，无法回放首次结果，测不到真实重试语义 |
| 让测试自己实现幂等缓存 | 测的是测试代码，不是服务行为 |
| 允许 `archived -> active` | 状态机失去唯一可判定的非法转换，负向用例变弱 |
| 用真实阈值把限流压满 | 请求量大且易 flaky，优先用可隔离的 client id |
| 为 429/5xx 只做契约断言 | 无法证明限流真的会触发并给出 `Retry-After` |

## 验证证据 / Verification

- `packages/qa_core/contracts/api.py`（`CatalogItemCreate`、
  `CatalogItemStatusUpdate`、`FieldError`、`ValidationErrorResponse`）
- `packages/qa_core/api_errors.py`
- `apps/compose/api/app.py`
- `tests/unit/test_error_taxonomy.py`
- `tests/api/test_negative_inputs.py`
- `tests/api/test_boundary_inputs.py`
- `tests/api/test_idempotency.py`
- `tests/api/test_state_machine.py`
- `tests/api/test_rate_limit.py`
- `tests/api/test_auth_boundaries.py`
- `reports/weekly/WEEK-07.md`

## 重新评估条件 / Revisit Triggers

- 幂等需要在多实例或并发场景下保证原子性。
- 需要跨进程或生产级限流。
- 状态机需要引入新的合法转换或终态。
- 错误码集合变化，映射表需要重新评审。
- 写接口需要进入 CI 之外的共享环境。
