# ADR-0004: OpenAPI 契约来源与兼容性判定 / OpenAPI Contract Source and Compatibility Rules

- 状态 / Status: Accepted
- 日期 / Date: 2026-10-12
- 决策者 / Deciders: Quality Engineering Lab
- 替代 / Supersedes: None

## 背景 / Context

Week 5 已经让 API Client 具备统一请求和认证行为，但接口响应仍然主要由
`dict` 和局部断言描述。这样会产生三个问题：

- 测试只验证当前用到的字段，遗漏的字段和错误类型不会被发现。
- OpenAPI 文档如果手工维护，会逐渐与运行时代码不一致。
- 新增、删除或修改字段时，无法明确判断变化是否破坏调用方。

English: Week 6 needs one executable contract source for response validation,
OpenAPI documentation, and compatibility decisions.

## 决策 / Decision

1. `qa_core.contracts.api` 中的 Pydantic 模型是本地 SUT 响应的共享事实来源。
2. 运行时响应必须通过对应模型构造或校验，不能继续把关键响应写成无类型字典。
3. `/openapi.json` 从同一批模型生成，固定使用 OpenAPI `3.1.0`。
4. 每个模型默认 `extra="forbid"`。新增响应字段必须显式进入契约、OpenAPI、
   兼容性评估和测试，不能静默漂移。
5. `validate_contract()` 将 Pydantic 错误转换成 `$.field` 形式的稳定 JSON 路径，
   便于失败分诊。
6. `compare_json_schemas()` 从调用方视角比较旧 Schema 和新 Schema：
   - 删除响应字段为破坏性变更。
   - 新增必填响应字段为破坏性变更。
   - 将可选响应字段改为必填为破坏性变更。
   - 修改字段类型为破坏性变更。
   - 删除枚举值为破坏性变更。
   - 新增可选响应字段和新增枚举值标记为非破坏性变化，但仍保留报告。
7. 本地 SUT Docker 镜像复制同一套 `qa_core.contracts`。容器实现和测试不能
   各自维护一份字段定义。
8. `check_sut.py` 把 `/openapi.json` 纳入启动验收。

English: one shared response model set drives runtime validation, OpenAPI 3.1,
field-path diagnostics, and response compatibility rules.

## 结果 / Consequences

正向结果：

- API 测试可以直接把真实响应解析为强类型模型。
- OpenAPI 与运行时响应来自同一份模型，减少文档漂移。
- 契约错误可以定位到具体字段，而不是只有笼统的 ValidationError。
- 兼容性和破坏性变化有确定性规则，可以用单元测试证明。
- Appium E2E、数据库准备和后续 Locust 可以复用同一批响应模型。

代价和约束：

- 本地 SUT 镜像新增 Pydantic 运行时依赖。
- 严格 `extra="forbid"` 会在服务端新增字段时让旧测试立即失败，必须同步更新
  契约和兼容性评估。
- 当前兼容性比较器覆盖响应 Schema 的常用结构，不替代完整 OpenAPI Diff 工具。
- 当前 OpenAPI 请求体仍以内联 JSON Schema 描述，没有全部转成 Pydantic Request
  Model。
- 复杂 `allOf`、`discriminator`、条件 Schema 和跨文件 `$ref` 仍需后续扩展。

## 备选方案 / Alternatives

| 方案 / Option | 未采用原因 / Why not |
| --- | --- |
| 手工维护独立 OpenAPI YAML | 容易和运行时代码漂移 |
| 只做 Pydantic 解析，不生成 OpenAPI | 无法给外部调用方稳定契约 |
| 直接引入 Schemathesis | 属于后续扩展，Week 6 先建立自我可控的核心 |
| 所有模型允许额外字段 | 无法发现未评审的响应变化 |
| 只比较文本或字段数量 | 无法判断兼容性语义 |
| 在测试文件里重复定义字段 | 测试和实现会产生两套契约 |

## 验证证据 / Verification

- `packages/qa_core/contracts/api.py`
- `packages/qa_core/contracts/validation.py`
- `packages/qa_core/contracts/compatibility.py`
- `packages/qa_core/contracts/openapi.py`
- `apps/compose/api/app.py`
- `tests/unit/test_contracts.py`
- `tests/api/test_contracts.py`
- `reports/weekly/WEEK-06.md`

## 重新评估条件 / Revisit Triggers

- 引入 Schemathesis、OpenAPI Diff 或独立契约仓库。
- API 开始包含 `oneOf`、`discriminator`、条件 Schema 或复杂分页。
- 需要兼容多个已发布客户端版本。
- 请求体、WebSocket 事件或异步消息也需要统一契约。
- 外部消费者要求生成 TypeScript、Java 或移动端 SDK。
- 严格新增字段策略阻碍经过评审的向后兼容演进。
