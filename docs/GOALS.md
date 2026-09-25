# 项目目标文档

版本：2.2  
日期：2026-09-25  
项目定位：企业级质量工程平台，不是 Demo 或小型 MVP  
配套执行方式：[项目执行计划](PLAN.md)

## 1. 最终目标

建立一套可以在面试中完整讲解、在企业中持续维护的移动端质量工程平台，同时覆盖：

- 接口自动化
- SQL 与关系型数据库测试
- Redis 和 NoSQL 数据一致性测试
- Android Appium 自动化
- iOS Appium 自动化
- Android/iOS 跨平台 E2E
- 性能测试与性能工程
- 故障恢复
- AI 与 Agent 增强
- 缺陷管理与质量闭环
- CI/CD
- 可观测性

目标岗位包括：

- 移动端自动化测试工程师
- 自动化测试开发工程师
- 测试开发工程师
- 质量工程工程师
- SDET
- AI 增强型 SDET

## 2. 项目最终形态

项目必须是一个统一 monorepo：

```text
一个被测系统
+ 一个共享测试核心 qa_core
+ 接口自动化引擎
+ 数据库与数据一致性测试层
+ Android Appium 引擎
+ iOS Appium 引擎
+ 性能测试引擎
+ AI/Agent 增强层
+ 统一数据、环境、报告、观测和治理
```

不允许把项目做成三个互不关联的 `api_tests`、`appium_tests` 和 `performance_tests` 目录。

## 3. “项目够大”的定义

规模来自系统边界、故障和工程深度，不来自重复用例数量。

| 维度 | 目标 |
| --- | --- |
| 被测系统 | REST API、WebSocket、PostgreSQL、Redis、Android App、iOS App |
| 业务域 | 至少 6 个，例如认证、用户、团队、消息、文件、搜索、通知、管理 |
| 核心 API | 30 到 80 个 |
| API 测试 | 200 到 300 条 |
| 契约测试 | 30 条以上 |
| Android 测试 | 60 到 100 条 |
| iOS 测试 | 50 到 80 条 |
| 跨层 E2E | 30 条以上 |
| 性能用户旅程 | 8 到 10 条 |
| 性能档位 | 6 种以上 |
| 测试设备 | Android 和 iOS 各覆盖两个版本，并尽量各有一台真机或设备云 |
| 测试环境 | 本地、CI、性能环境，后续扩展预发布 |
| AI/Agent | 5 到 10 个受控任务 Agent |
| Agent Eval | 30 到 50 个 Golden Tasks |
| 数据库主线 | PostgreSQL + Redis |
| 数据库扩展 | MySQL 兼容、MongoDB/Elasticsearch 可选 |
| 数据库测试 | 80 到 150 条 SQL/数据一致性/缓存测试 |
| 缺陷闭环 | 测试结果、缺陷、修复和回归验证可追溯 |

## 4. 接口自动化深度目标

不能只会：

```python
response = requests.get(url)
assert response.status_code == 200
```

必须达到：

- 理解 HTTP、Keep-Alive、连接池、TLS、代理、超时和重定向。
- 设计 OAuth2/OIDC、JWT、Cookie、Refresh Token 和并发刷新。
- 使用 OpenAPI、JSON Schema、Pydantic 和兼容性检查。
- 覆盖正向、负向、边界、错误码、幂等和状态转换。
- 验证 PostgreSQL、Redis、队列、Webhook、WebSocket 和最终一致性。
- 使用 WireMock、responses/respx、Toxiproxy 做故障和依赖虚拟化。
- 覆盖 RBAC、BOLA/IDOR、限流、重放和输入安全基础。
- 管理测试数据、资源池、并行隔离、重试和清理。
- 将 Trace ID、请求 ID、日志和指标串联。
- 建立可以被 Appium 和 Locust 复用的 API SDK。

核心接口不能只验证响应，还要验证：

```text
协议行为
+ 认证和权限
+ 请求和响应契约
+ 业务状态变化
+ 数据库副作用
+ 事件和 WebSocket
+ 错误码
+ 幂等和重试
+ 并发
+ 可观测性
```

## 5. Android 自动化深度目标

必须掌握：

- Appium Python Client、Appium Server 和 UiAutomator2 Driver。
- UiAutomator2 Server、Instrumentation、ADB 和 Android 系统。
- UiAutomator2 与 Espresso Driver 的适用边界。
- AVD、真机、无线调试和多设备并行。
- APK 安装、覆盖安装、包名、Activity 和 session 生命周期。
- resource-id、accessibility id、UIAutomator 和 XPath 的稳定性取舍。
- 点击、长按、滑动、拖动、缩放和稳定手势。
- 权限、通知、输入法、返回键、HOME 键和系统弹窗。
- Activity、Fragment、Dialog、Toast、Popup 和 WebView。
- Hybrid context、ChromeDriver 和 WebView 调试。
- 深链接、后台恢复、进程死亡、文件和剪贴板。
- 多语言、深色模式、字体缩放和屏幕尺寸。
- `adb`、`logcat`、`dumpsys`、`am start -W` 和 Appium 日志联合诊断。

## 6. iOS 自动化深度目标

iOS 不是可选项。项目必须覆盖：

- macOS、Xcode、Simulator 和 XCTest。
- XCUITest Driver 和 WebDriverAgent。
- WDA 构建、启动、端口、DerivedData 和 session。
- Simulator 与真机 capabilities。
- Apple Team、证书、Provisioning Profile 和设备信任。
- 真机 UDID、设备注册和系统兼容性。
- 权限、系统弹窗、通知、深链接、键盘、文件和 WebView。
- 前台、后台、锁屏、进程终止和恢复。
- 多语言、RTL、深色模式、动态字体和大屏。
- 多 Simulator、多真机、WDA 端口和 DerivedData 隔离。
- Xcode、WDA、Simulator 和 Appium Server 日志联合诊断。

纯 Windows 不能完成本地 iOS Simulator、WDA 构建和真机签名。必须使用：

1. Mac mini 或 Mac 工作站。
2. macOS CI Runner。
3. Appium 2 设备云。

## 7. 跨平台目标

Android 和 iOS 应共享：

- 业务 Flow。
- Scenario 和 Step。
- 测试数据。
- 业务断言。
- API 建数和验证。
- 报告、日志和诊断接口。

必须隔离：

- capabilities。
- 定位器。
- 手势和键盘。
- 权限和系统弹窗。
- 深链接、文件和通知。
- 设备和日志采集。

统一通过 `PlatformAdapter` 或同等设计隔离平台差异。业务测试中不能到处散落 `if platform == ...`。

## 8. 性能工程深度目标

不能只会设置并发用户和输出 Locust HTML。

必须掌握：

- SLI、SLO、SLA、性能预算和容量目标。
- 并发、到达率、吞吐量和响应时间关系。
- Little's Law。
- 开环与闭环模型。
- Think Time、Pacing、Arrival Rate 和 Coordinated Omission。
- Smoke、Baseline、Load、Stress、Spike、Soak、Capacity 和 Failover。
- Locust User、TaskSet、Shape、自定义统计和 SLA 阈值。
- Locust Master、Worker、分布式压力机和压测机瓶颈。
- Prometheus、Grafana、Trace、PostgreSQL、Redis 和容器指标。
- Go Profile、GC、协程、数据库锁、连接池和队列。
- Android/iOS 冷启动、热启动、jank、内存、CPU、电量和弱网。

Appium 不是移动端性能测试工具。移动端性能使用 `am start -W`、`gfxinfo`、`meminfo`、Perfetto、Instruments、MetricKit 和 `xctrace`。

## 9. 数据与数据库测试深度目标

企业级系统通常是多存储并用，而不是只选关系型或非关系型数据库：

- 关系型数据库仍是核心交易、账户、权限、订单和业务状态的主力。
- Redis 常用于缓存、会话、限流、队列和临时状态。
- MongoDB 等文档数据库用于灵活结构、内容和大对象聚合。
- Elasticsearch 等搜索型存储用于检索、聚合和近实时索引。
- 时序数据库用于监控、指标和事件数据。

本项目的数据库测试主线：

```text
PostgreSQL
+ Redis
+ MySQL 兼容专题
+ MongoDB/Elasticsearch 可选专题
```

### 9.1 必须掌握

- SQL 不能停留在增删改查，要覆盖 JOIN、聚合、窗口函数、CTE、递归和批量操作。
- Schema、主键、外键、唯一约束、CHECK、默认值和级联行为。
- 索引设计、复合索引、覆盖索引、失效索引和查询计划。
- ACID、事务边界、提交与回滚、保存点和幂等写入。
- Read Committed、Repeatable Read、Serializable 等隔离级别。
- 行锁、表锁、间隙锁、死锁、锁等待和并发更新。
- 乐观锁、版本号、最后写入覆盖和并发业务冲突。
- 数据库迁移、种子数据、快照、重置和数据脱敏。
- API 测试的数据库准备、状态断言和精确清理。
- PostgreSQL 通过 `EXPLAIN ANALYZE`、`pg_stat_statements` 和系统视图分析。
- Redis 的 key、TTL、过期、淘汰、缓存命中、缓存穿透和一致性。
- NoSQL 的最终一致性、索引同步、文档版本和聚合查询。

### 9.2 API 与数据库联合测试

必须覆盖以下模式：

```text
API 写入
-> 数据库验证最终状态
-> API 读取验证

数据库准备
-> API 触发业务
-> 数据库验证副作用

两个 API 并发写
-> 数据库验证版本、锁和唯一约束

API 修改数据
-> 数据库确认
-> Redis/搜索索引验证最终一致性
```

关键场景：

- 创建、更新、删除后的数据库真实状态。
- 软删除、审计日志和 Outbox 事件。
- 重复请求的幂等和唯一约束。
- 并发更新、乐观锁和死锁。
- 事务失败后的完整回滚。
- 缓存与数据库的一致性和失效。
- 异步事件、搜索索引和最终一致性。
- 多租户和 workspace 数据隔离。

### 9.3 数据隔离和清理

- 每个 pytest worker 使用唯一用户、业务对象和命名前缀。
- 优先采用 tenant/workspace 隔离，降低全库重置成本。
- 可以使用数据库快照恢复，但必须评估并行和性能影响。
- 不能假设“测试事务回滚”一定有效，因为被测应用可能使用独立数据库连接。
- 清理必须幂等，并能够处理重试和部分失败。
- 功能测试数据与性能测试数据必须隔离。

### 9.4 数据库性能测试

- 慢查询、执行计划、索引命中和排序方式。
- 连接池大小、等待时间、连接泄漏和服务启动高峰。
- 行锁、死锁、长事务、锁等待和数据库 CPU。
- WAL、磁盘 IO、缓存命中率和 Autovacuum。
- Redis 延迟、命中率、内存、淘汰和大 key。
- 数据库指标必须与 API/Locust 指标按时间线关联。

### 9.5 明确不做

- 不直接写生产数据库。
- 不把测试事务回滚当作所有场景的隔离方案。
- 不依赖固定 `sleep` 等待最终一致性。
- 不用数据库内部实现细节替代公开 API 契约。
- 不只看 SQL 是否执行成功，必须验证业务状态。

## 10. E2E 与故障恢复目标

核心业务链路采用：

```text
API 创建用户和业务数据
-> Android 或 iOS Appium 登录并操作
-> API 验证服务端最终状态
-> Appium 验证刷新后的 UI
```

必须覆盖：

- API 成功但 UI 未刷新。
- UI 成功但服务端数据错误。
- 重复请求和幂等。
- WebSocket 延迟、乱序和重复。
- 网络延迟、丢包、限流和断连。
- Redis、数据库、对象存储和依赖服务异常。
- Android ADB 掉线、App 被杀。
- iOS WDA 失效、Simulator 中断和真机失联。
- 故障恢复、恢复时间和数据一致性。

## 11. AI 与 Agent 目标

AI 是增强层，不替代传统工程能力。

### 11.1 目标等级

| 等级 | 能力 | 项目目标 |
| --- | --- | --- |
| L0 | 个人聊天辅助 | 第一周达到 |
| L1 | 仓库感知助手 | API 阶段达到 |
| L2 | 只读任务 Agent | Appium/性能阶段达到 |
| L3 | 受控写入 Agent | CI 阶段达到 |
| L4 | 受限自治维护 | 完成设计和 Eval |

### 11.2 必须完成的 Agent

1. 需求到测试 Agent。
2. PR 变更影响分析 Agent。
3. API 契约审查 Agent。
4. 测试数据和边界 Agent。
5. Android/iOS 定位器顾问 Agent。
6. 失败分诊 Agent。
7. Flaky 聚类 Agent。
8. 性能指标分析 Agent。
9. CI 修复建议 Agent。
10. 每周测试维护 Agent。

### 11.3 必须掌握

- `AGENTS.md` 和仓库上下文。
- 工具调用、结构化输出和工具白名单。
- Plan、Act、Observe、Verify、Report 工作流。
- 检索优先使用文件和关键词，必要时再引入向量检索。
- 30 到 50 个 Golden Tasks 和历史失败评测集。
- 准确率、幻觉率、人工修改率、节省时间、Token、成本和延迟。
- Prompt Injection、Secret、脱敏和最小权限。

### 11.4 不能交给 Agent

- 生产数据库写操作。
- 生产压测。
- 发布和回滚。
- 自动合并。
- 自动修改权限。
- 读取和输出证书、私钥、真 Secret。
- 绕过测试和质量门禁。
- 用模型结论替代 Schema、日志、设备和性能事实。

## 12. 工程与 CI 目标

- 单一 monorepo 和共享 `qa_core`。
- 分层配置、类型校验和 Secret 隔离。
- 本地、CI、性能环境和设备云。
- Android、iOS、API 和性能流水线。
- 测试分片、设备池、报告归档和质量门禁。
- Allure、Grafana、Prometheus 和历史趋势。
- ADR、runbook、owner 和 quarantine。
- Git commit、App/API 版本、设备、session 和工件可追溯。

## 13. 缺陷管理与质量闭环目标

Jenkins 是开源 CI/CD 系统，不是缺陷管理系统。Allure 是测试报告和可视化系统，也不是缺陷管理系统。

必须明确三个系统的职责：

| 系统 | 职责 |
| --- | --- |
| Jenkins/GitLab CI | 触发、调度、执行、归档和门禁 |
| Allure/ReportPortal | 测试证据、历史、趋势、分类和分析 |
| Kiwi TCMS/TestLink | 测试用例、测试计划、测试运行和追踪 |
| GitLab Issues/OpenProject/MantisBT/Jira | 缺陷生命周期、负责人、优先级和修复状态 |

### 13.1 推荐开源组合

主学习方案：

```text
Jenkins
+ Allure
+ Kiwi TCMS
+ GitLab CE or OpenProject
+ PostgreSQL
```

轻量方案：

```text
Jenkins or GitLab CI
+ Allure
+ GitLab Issues
```

增强方案：

```text
Allure
+ ReportPortal
+ GitLab Issues/OpenProject/Jira
```

ReportPortal 适合测试结果聚合、失败分析和 flaky 趋势；Kiwi TCMS 更适合测试用例、计划、执行和追踪。两者职责有重叠，必须选择一个作为测试管理的事实来源。

### 13.2 缺陷生命周期

```text
New
-> Triage
-> Confirmed
-> In Progress
-> Ready for Verification
-> Verified
-> Closed
```

其他状态：

- Duplicate
- Rejected
- Deferred
- Won't Fix
- Reopened

缺陷必须包含：

- 测试 ID、Run ID 和运行链接。
- Git commit、API/App 版本和环境。
- Android/iOS 设备、系统版本和 Appium session。
- 失败步骤、截图、page source、日志和 Trace。
- 严重级别、优先级、owner 和截止时间。
- 关联需求、测试用例、修复 PR 和回归结果。

### 13.3 自动化闭环

```text
测试失败
-> 收集证据
-> 失败分类和去重
-> 生成缺陷草稿
-> 人工确认
-> 创建缺陷
-> 修复和关联 PR
-> 触发回归
-> 验证通过
-> 人工批准关闭
```

Agent 可以辅助分类、去重和生成草稿，但不能自动创建大量缺陷、自动关闭缺陷或绕过人工审批。

### 13.4 缺陷指标

- 缺陷发现时间。
- 缺陷确认时间。
- 平均修复时间 MTTR。
- 重开率。
- 重复缺陷率。
- Defect Leakage。
- 自动分诊准确率。
- 自动去重准确率。
- 缺陷关闭 SLA。
- 每个版本逃逸到生产的缺陷数量。

## 14. 面试证据目标

最终必须能够展示：

- 架构图和目录结构。
- API、Appium、性能和 AI 的完整调用链。
- Android/iOS capability matrix。
- 设备和系统版本矩阵。
- 至少 10 份 ADR。
- 至少 10 份 runbook。
- API、Android、iOS、性能和 CI 报告。
- flaky 趋势和 quarantine 治理。
- 性能拐点、容量和优化前后对比。
- 至少 8 个 STAR 项目故事。
- Agent Eval、Trace、成本、延迟和人工修改率。

必须能回答：

1. 为什么使用 monorepo？
2. API、Appium 和 Locust 如何共享认证与模型？
3. Android 和 iOS 如何共享业务测试？
4. 如何隔离并行测试的数据、设备和端口？
5. 如何定位只在并行时出现的失败？
6. 如何处理 token 并发刷新？
7. 如何设计 OpenAPI 契约测试？
8. 如何测试对象级越权？
9. 如何设计 API 写入后的数据库状态断言？
10. 为什么测试事务回滚不能替代所有数据库隔离方案？
11. 如何处理并发更新、锁等待和死锁测试？
12. 如何验证数据库、Redis 和搜索索引的最终一致性？
13. 如何分析慢查询、索引和执行计划？
14. 如何确定性能并发、持续时间和 SLO？
15. 如何找性能拐点并给出容量建议？
16. 如何区分产品、测试、设备和环境失败？
17. 如何治理 flaky test？
18. WDA、签名和 iOS 真机失败如何排查？
19. 如何让 Agent 参与失败分诊但不掩盖问题？
20. 如何控制 Agent 权限、成本、延迟和 Prompt Injection？
21. 如何评测 Agent 的准确率和业务收益？
22. 哪些步骤绝不能交给 Agent？

## 15. 最终验收

### 功能目标

- Android 和 iOS 都有可重复执行的测试链路。
- API、Appium、Locust 和 Agent 共享模型、数据和观测上下文。
- smoke 通过率达到 98% 以上。
- flaky rate 低于 2%。
- 每条测试可以独立运行，不依赖固定顺序。
- 所有失败报告包含分类和诊断材料。

### 数据与数据库目标

- PostgreSQL、Redis 和接口测试共享测试数据工厂与资源池。
- API 写入、数据库状态和 API 读取可以交叉验证。
- 覆盖事务回滚、幂等、唯一约束、并发更新、锁和死锁。
- 覆盖 Redis TTL、缓存失效、缓存穿透和数据库一致性。
- 至少完成一个 MySQL 兼容专题。
- 可选完成 MongoDB 或 Elasticsearch 的最终一致性专题。
- 可以用 `EXPLAIN ANALYZE` 和数据库指标解释性能问题。

### 性能目标

- 每个核心旅程有 SLO。
- 每次性能测试有 baseline 可比。
- 同时记录 p95、p99、错误率和吞吐量。
- 性能环境、数据池和压力机独立。
- 能给出系统拐点、容量和恢复时间结论。

### 工程目标

- 依赖有锁文件。
- 配置有类型校验。
- Secret 不进入 Git。
- 关键设计有 ADR。
- 常见故障有 runbook。
- CI 结果可追溯 commit 和 App/API 版本。

### AI/Agent 目标

- Agent 默认只读，写操作受控。
- 所有建议引用仓库、日志或指标证据。
- 有 Golden Tasks、准确率、幻觉率和人工修改率。
- 有 Token、成本和 P95 延迟。
- 至少展示一次 Agent 误判、修正和防护改进。

### 缺陷闭环目标

- 测试失败可以生成带完整证据的缺陷草稿。
- 缺陷可以关联测试用例、Run、PR 和回归结果。
- 修复后可以自动触发验证，但关闭需要人工批准。
- 可以按失败指纹聚类和识别重复缺陷。
- 可以统计 MTTR、重开率、重复率和缺陷泄漏。
- Jira、GitLab Issues 或 OpenProject 通过统一适配器接入，避免绑定单一厂商。

## 16. 明确不做

- 不用重复用例制造项目规模。
- 不做 Android 单端后宣称支持移动端。
- 不把 Appium 当性能工具。
- 不在公共生产服务上做压测。
- 不直接连接或修改生产数据库。
- 不用固定 `sleep` 等待数据库或索引最终一致。
- 不用统一重试掩盖 flaky。
- 不让 AI 生成未经评审、未执行、未失败验证的测试。
- 不给 Agent 生产写权限。
- 不用 LLM 结论替代确定性执行结果。
- 不为了展示技术而强行引入向量数据库、多 Agent 或 Kubernetes。
- 不把 Allure 当缺陷管理系统。
- 不用失败一次就自动创建大量重复缺陷。
- 不自动关闭缺陷。

## 17. 项目完成定义

只有同时满足以下条件，项目才算完成：

```text
Android 和 iOS 可运行
+ API/Appium/性能共享核心
+ PostgreSQL/Redis 数据验证和隔离
+ 设备、数据和环境可隔离
+ 有性能和容量结论
+ 有 CI、报告和趋势
+ 有 AI/Agent 及其 Eval
+ 有缺陷创建、修复、回归和关闭闭环
+ 有 ADR、runbook 和复盘
+ 能解释方案、取舍和失败
```
