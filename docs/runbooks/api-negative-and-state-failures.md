# 负向、幂等与状态机失败排查 / API Negative, Idempotency, and State Failure Triage

触发条件：负向用例返回意外状态码、幂等重放没有回放、状态转换被错误接受或拒绝、
429 与预期不符，或失败分类与实际责任方不一致。

## 1. 先读错误码，不看文本

断言永远基于状态码和 `error` 字段，不要匹配 `message`。先记录：

```text
method + path
status_code
error
字段路径（$.field）
Retry-After（仅 429）
```

## 2. 快速复现

```powershell
.\scripts\start_sut.ps1
.\.venv\Scripts\python.exe -m pytest `
  tests\api\test_negative_inputs.py `
  tests\api\test_boundary_inputs.py `
  tests\api\test_idempotency.py `
  tests\api\test_state_machine.py `
  tests\api\test_rate_limit.py `
  tests\api\test_auth_boundaries.py `
  -q -p no:cacheprovider
```

如果 API 测试因 SUT 未启动而 skip，先启动 Compose SUT 并等待 healthy。

## 3. 字段校验失败（422）

`ValidationErrorResponse.fields` 给出逐字段路径：

```text
$.sku          缺失或不符合 ^[A-Z0-9][A-Z0-9-]*$
$.name         为空或超过 120 字符
$.price_cents  小于 0 或大于 100000000
$.unexpected   出现未声明字段
```

如果 422 变成 400，通常是 body 不是合法 JSON，或 `Content-Type` 不是
`application/json`。这属于测试构造问题，不是产品缺陷。

## 4. 幂等排查

```text
同键同 body 未回放
-> 检查是否带了 Idempotency-Key
-> 检查存储键是否按 workspace 隔离
-> 检查 Redis 中 idem:* 是否仍在 TTL 内

同键不同 body 未返回 409
-> 检查 body 指纹是否包含全部影响结果的字段
```

注意：不带 `Idempotency-Key` 时重复请求会被唯一约束拒绝，这是预期的对照行为，
不是幂等失败。

## 5. 状态机排查

| 当前状态 / From | 目标状态 / To | 预期 / Expected |
| --- | --- | --- |
| active | archived | 200，状态变为 archived |
| active | active | 409 `invalid_state_transition` |
| archived | archived | 409 `invalid_state_transition` |
| archived | active | 409 `invalid_state_transition` |
| 任意 | 未知取值 | 422 `validation_failed`（`$.status`） |

若合法转换返回 409，先确认元素是否已经被归档；若未知取值返回 409 而非 422，
说明请求没有进入模型校验，检查是否命中了错误分支。

## 6. 限流排查（429）

- 每个测试使用独立 `X-QA-Client-Id`，否则会与同 IP 的其他用例共用预算。
- 阈值由 `QA_RATE_LIMIT_WRITE_MAX` 控制，窗口由
  `QA_RATE_LIMIT_WRITE_WINDOW_SECONDS` 控制。
- 429 必须带 `Retry-After`；缺失说明限流分支写错了。
- 限流计数在 SUT 进程内，重启即清零；不要用它验证生产限流精度。

## 7. 失败分类

`qa_core.api_errors.classify_response()` 的映射：

| 状态码 / Status | 错误码示例 / Codes | 分类 / Category |
| --- | --- | --- |
| 400 | invalid_request、unsupported_grant_type | test |
| 400 | invalid_grant | auth |
| 401 | authentication_required、invalid_token | auth |
| 403 | permission_denied | permission |
| 404、409、422 | 资源与规则冲突 | product |
| 429、5xx | rate_limited、database_unavailable | environment |

分类与真实责任方不一致时，先修映射表，再修用例，不要反过来放宽断言。

## 8. 证据采集

允许保存：

- 状态码、错误码和 `$.field` 字段路径。
- 幂等键的哈希、是否设置 `Idempotent-Replay`。
- 状态转换前后的状态和 `Retry-After`。
- 脱敏后的请求 body 结构。

禁止保存：

- access token、refresh token、Cookie。
- 密码、密钥和生产数据。
- 未脱敏的用户隐私或业务数据。

## 9. 修复顺序

1. 判断实现、契约和测试期望谁代表正确语义。
2. 如果实现错误，修实现并补一条负向或边界用例。
3. 如果契约错误，先评审兼容性，再同步模型、OpenAPI 和测试。
4. 如果测试期望错误，修测试，不要删除断言。
5. 重跑 Ruff、Mypy、单元、API 和 Linux 容器验收。

## 10. 关闭条件

- 已定位到具体状态码、错误码和字段路径。
- 幂等与状态转换行为与 ADR-0005 一致。
- 失败分类指向正确责任方。
- 测试运行后种子数据行数仍为 `workspaces=2`、`users=3`、`items=4`。
- 没有通过放宽断言或吞掉错误来让用例变绿。
