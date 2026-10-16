# API 契约失败排查 / API Contract Failure Triage

触发条件：Pydantic 响应解析失败、OpenAPI 引用失败、响应字段缺失、字段类型变化
或兼容性比较报告破坏性变化。

## 1. 先区分失败类型

```text
网络或认证失败
-> 状态码不是预期
-> JSON 无法解析
-> 必填字段缺失或类型错误
-> 未批准的新字段
-> 兼容性规则判定破坏
-> 测试期望本身错误
```

契约失败不等于产品缺陷，也不等于测试缺陷。必须先确定契约来源和变化意图。

## 2. 快速复现

```powershell
.\.venv\Scripts\python.exe -m pytest `
  tests\unit\test_contracts.py `
  tests\api\test_contracts.py `
  -q -p no:cacheprovider
```

期望结果：

```text
11 passed
```

如果 API 测试因 SUT 未启动而 skip，先启动 Compose SUT。

## 3. 查看具体字段

`ContractValidationError.violations` 会提供：

```text
path
error_type
message
```

例如：

```text
$.refresh_token: Field required
$.status: Input should be 'live'
$.unexpected: Extra inputs are not permitted
```

不要只查看异常字符串，必须保留字段路径和原始响应快照。

## 4. 检查 OpenAPI 与运行时

```powershell
Invoke-RestMethod http://127.0.0.1:18000/openapi.json
```

检查：

- `openapi` 是否为 `3.1.0`。
- 路由是否出现在 `paths`。
- `$ref` 是否都能解析到 `components.schemas`。
- 响应字段是否包含 `additionalProperties: false`。

## 5. 兼容性判定

| 变化 / Change | 响应侧判定 / Response Verdict |
| --- | --- |
| 新增可选字段 | 非破坏 / Non-breaking |
| 新增必填字段 | 破坏 / Breaking |
| 删除已有字段 | 破坏 / Breaking |
| 可选字段改为必填 | 破坏 / Breaking |
| 修改字段类型 | 破坏 / Breaking |
| 删除枚举值 | 破坏 / Breaking |
| 新增枚举值 | 非破坏但需评审 / Non-breaking, review required |

兼容性报告保留非破坏性发现，不能因为命令退出成功就忽略变化。

## 6. 证据采集

允许保存：

- 状态码、错误码和字段路径。
- OpenAPI 路由和 component 名称。
- 脱敏后的响应结构。
- 兼容性报告。
- 触发变化的提交和需求。

禁止保存：

- access token、refresh token 和 Cookie。
- 密码、密钥和生产数据。
- 未脱敏的用户隐私或业务数据。

## 7. 修复顺序

1. 判断运行时代码和契约谁代表正确业务语义。
2. 如果实现错误，修实现并补负向测试。
3. 如果契约错误，先评审兼容性，再同时修改模型、OpenAPI、测试和消费者。
4. 如果是破坏性变化，记录版本策略和迁移方式。
5. 重跑 Ruff、Mypy、单元、API 和 Linux 容器验收。

## 8. 关闭条件

- 已定位到具体字段路径。
- 已确认变化是兼容还是破坏。
- OpenAPI 和运行时响应一致。
- 真实 API 测试通过。
- 没有通过放宽模型、删除断言或吞掉额外字段来掩盖问题。
