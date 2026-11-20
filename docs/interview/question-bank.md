# 面试问题库 / Interview Question Bank

以下答案对应仓库证据，不依赖背诵结论。回答时先给判断，再讲原因和验证。

## 1. 为什么用 monorepo？

API、Appium 和 Locust 共享认证、模型、数据工厂、HTTP client 和报告语义。放在
一个仓库可以在一次提交中同步修改契约与消费者，并用同一条 CI 验证。代价是 CI
时间更长，所以流水线按 Quality、SUT、Android、iOS、性能和 Agent 分 job 执行。
参考 `docs/architecture/project-overview.md` 与统一 workflow。

## 2. API、Appium 和 Locust 如何共享认证与模型？

认证由 `qa_core` 的 token/refresh 客户端统一处理；领域模型和 API 错误使用共享
契约；Locust journey 复用真实业务请求形状。共享层不依赖具体测试框架。
参考 `packages/qa_core/clients/`、`packages/qa_core/contracts/` 和
`performance/`。

## 3. Android 和 iOS 如何共享业务测试？

业务 Flow 只描述意图和元素语义，PlatformAdapter 提供定位器、等待和系统交互。
平台差异留在 adapter 和 screen 层，公共 Flow 不直接写 XPath 或 platform locator。
参考 `packages/qa_core/mobile/` 与 `docs/architecture/cross-platform-framework.md`。

## 4. 如何隔离 pytest-xdist 的数据和设备？

并行前申请唯一 namespace、数据前缀和资源预算；数据库写入使用唯一键和 owner；
设备按端口、UDID、WDA port 和 DerivedData 隔离。清理必须幂等，不能依赖固定
执行顺序。参考 `packages/qa_core/concurrency/`、`docs/runbooks/parallel-data-isolation-failures.md`。

## 5. 如何定位只在并行时出现的问题？

先固定 worker、设备、namespace 和 run ID，把随机失败变成可复现实验；再比较
并发时的数据库行、端口、session、日志和 Trace。最后用单 worker 和受控并发两组
证据确认根因。不能只说“重跑通过就是 flaky”。

## 6. 如何处理 token 并发刷新？

共享刷新必须做 single-flight 或等价的并发合并，并处理 refresh token rotation
的竞态。测试覆盖同时过期、刷新成功、refresh 被撤销和并发请求恢复。
参考 `docs/adr/0003-local-oauth2-jwt-and-refresh-rotation.md`。

## 7. 如何设计契约测试？

OpenAPI 作为机器可读契约源，Pydantic 模型验证运行时结构；兼容性检查关注删除、
类型变化、必填变化和错误码变化。契约测试不只比较 happy-path 字段。
参考 `docs/adr/0004-openapi-contract-source-and-compatibility.md`。

## 8. 如何测试对象级越权？

准备 owner、peer、auditor 等角色，验证同一资源 ID 在不同身份下的读、写、删除
和 job 查询。不能只测“有没有登录”，要测“这个对象是否属于当前主体”。
参考 `tests/api/test_bola_idor.py` 和 `docs/runbooks/authorization-and-input-security-triage.md`。

## 9. 如何设计 API 写入后的数据库断言？

API 返回成功只是第一层；随后按业务主键读取真实数据库，验证字段、状态、时间戳、
关联行和幂等结果。测试数据使用唯一 namespace，清理通过 API 或只读测试账号完成。
参考 `tests/api/test_api_db_state.py`。

## 10. 为什么测试事务回滚不能替代所有数据库隔离？

回滚适合单连接测试，但被测 API 可能使用独立连接，无法看到测试事务内未提交的
数据；并发测试还需要真实提交和锁边界。因此需要独立 schema/namespace、快照或
受控重建，并验证连接可见性。

## 11. 如何测试并发更新、锁等待和死锁？

让两个事务按受控顺序持有和请求行锁，收集等待时间、数据库错误和最终状态；测试
必须设置 timeout，防止 CI 永久挂起。死锁后验证重试或业务错误契约，不猜测。
参考 `docs/runbooks/database-lock-and-deadlock-triage.md`。

## 12. 如何验证数据库、Redis 和搜索索引的最终一致性？

使用带超时上限的条件轮询，而不是固定 `sleep`；记录写入事件、缓存失效、数据库
状态和索引可见时间。若超时，保留各层证据并返回失败/阻断，不把“稍后可能一致”
写成通过。参考 `docs/runbooks/redis-cache-and-consistency-triage.md`。

## 13. 如何用执行计划解释慢查询？

先固定测试数据和查询参数，比较 `EXPLAIN ANALYZE` 的实际行数、扫描方式、排序和
等待；再结合 `pg_stat_statements`、索引和锁判断瓶颈。不能只看 SQL 文本推断。
参考 `docs/runbooks/database-lock-and-deadlock-triage.md` 与性能报告。

## 14. 如何设计性能负载模型？

从真实用户旅程和到达率出发，定义场景权重、思考时间、数据池、预热和稳态窗口；
分别运行 baseline、load、stress、spike、soak。报告同时给 p50/p95/p99、吞吐、
错误率和资源指标。参考 `docs/performance/load-model.md`。

## 15. 如何找系统拐点？

固定环境和数据池，逐档增加并发，记录延迟、吞吐、错误和资源饱和度；当吞吐不再
增长或 p95/p99 明显恶化时定位拐点。用 API、数据库和主机指标同时间线验证，不
把单次最高并发当容量。参考 `reports/weekly/WEEK-28.md`。

## 16. 如何区分产品、测试、设备和环境失败？

先查看证据边界：断言失败属于产品或契约；连接、WDA、Xcode、ADB、Docker 和
quota 属于环境或设备候选；测试自身状态污染需要单 worker 复现。保留原始日志、
Run ID 和状态，不能因为重跑变绿就归因产品。

## 17. 如何治理 flaky test？

记录失败指纹、设备、版本、worker、日志和重跑历史；先聚类再修复根因。Quarantine
必须有 owner、原因、到期时间和证据，并且不能自动隐藏结果。参考
`configs/quality-governance.yaml` 和 `docs/runbooks/ios-stability-and-flaky-triage.md`。

## 18. iOS WDA 和签名失败如何排查？

按 Host、Xcode、Simulator/Device、签名、WDA build/launch、Appium session 分层；
保存 `xcodebuild`、WDA、Appium 和 `simctl` 证据。Simulator 与真机签名路径分开，
不能把云 provider 失败直接归为 WDA。参考 `docs/runbooks/ios-wda-signing-triage.md`。

## 19. 如何让 CI 在 Android 和 iOS 上稳定运行？

固定 runner、API、Xcode、Appium driver 和 fixture 构建步骤；每次启动前清理端口、
session、DerivedData 和设备状态；把平台前置失败与测试断言失败分 job 记录。Week31
最终 Run `44563937821` 的 Quality、SUT、Android、iOS Simulator、Performance、
Trend 都有实际 artifact。

## 20. 如何让 Agent 参与失败分诊但不掩盖问题？

Agent 只读结构化信号和证据引用，不直接修改测试或阈值；无证据、空信号或
`UNKNOWN` 返回 `INSUFFICIENT_EVIDENCE`，`BLOCKED`、`NOT RUN`、`DEFERRED`
保持未完成语义。所有建议进入人工评审。

## 21. 如何控制 Agent 工具权限和 Prompt Injection？

工具 allowlist 只给读取能力，注册表禁止 Shell、写仓库、改阈值、建/关缺陷和发布；
日志、HTML、页面和 Issue 内容视为不可信数据，不执行其中的指令。输出必须引用
具体证据路径，不能把自然语言摘要当成事实。

## 22. 如何评测测试 Agent 的准确率和收益？

准备 30 到 50 个 Golden Tasks，覆盖 PASS、FAILED、BLOCKED、NOT RUN 和
`INSUFFICIENT_EVIDENCE`；记录答案、证据引用、延迟、Token、成本、人工修改和
采纳。单看一次演示或“看起来合理”不算 Eval。

## 23. 为什么小仓库可能不需要向量数据库？

当前证据量小，文件路径、`rg`、结构化 JSON 和明确 schema 足够；向量检索会引入
索引同步、召回误差、隐私和运维成本。只有在跨大量非结构化文档且关键词检索不足时
才考虑引入。

## 24. 哪些质量步骤不能交给 Agent？

生产数据库写入、生产压测、发布/回滚、自动合并、权限修改、Secret 读取和传输、
绕过门禁、自动大量创建重复缺陷、自动改优先级、自动关闭缺陷都不能交给 Agent。

## 25. 如何量化 Agent 节省的时间和成本？

先记录人工完成同一分诊任务的时间和结果，再记录 Agent 输入、Token、延迟、成本、
人工修改和采纳率；必须扣除复核时间。当前确定性基线 Token/成本为 0，但不能声称
已有大模型节省了时间，因为还没有正式的人机对照实验。
