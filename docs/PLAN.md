# 项目执行计划

版本：2.2  
日期：2026-09-25  
周期：32 周，建议每周 10 到 12 小时  
主线：接口自动化 + 数据库/缓存测试 + Android/iOS Appium 2 + 性能测试 + 缺陷闭环 + AI/Agent 增强  
开发环境：Windows + PyCharm，iOS 使用 macOS、macOS CI 或设备云

配套稳定性目标、能力边界和最终验收标准，统一见 [项目目标文档](GOALS.md)。

## 目录

1. 计划用途
2. 学习原则
3. 设备、软件和账号准备
4. 企业级项目蓝图
5. 32 周总课表
6. 分阶段详细计划
7. 核心测试方向深度标准
8. Android 与 iOS 双生态要求
9. PyCharm 学习与调试方法
10. 每周学习节奏
11. Git、文档和知识管理
12. 质量指标与验收标准
13. 面试准备与证据包
14. 风险与应对
15. 第一周行动清单
16. AI 与 Agent 融合方案
17. 缺陷管理与质量闭环方案
18. 配套文档

## 1. 计划用途

本文件只负责“如何执行”，记录环境准备、工程结构、技术栈、数据库与缺陷管理方案、32 周课表、阶段任务、学习节奏和第一周行动。项目目标、能力深度、规模目标和验收标准见 [项目目标文档](GOALS.md)。

执行前先阅读目标文档。计划中的每周任务必须服务于目标文档中的能力和验收标准，不能为了完成周数而跳过失败验证、设备覆盖、性能分析或文档证据。

## 2. 学习原则

### 2.1 先最小闭环，再增加复杂度

顺序必须是：

```text
能启动
-> 能调试
-> 能稳定运行
-> 能并行
-> 能诊断
-> 能进 CI
-> 能扩展到 Android/iOS 双生态
-> 能执行性能测试和分析
```

不要一开始同时研究所有 Driver、所有测试框架和所有监控组件。

### 2.2 每个能力都要经过失败验证

只跑通正向流程，仍然是 Demo。每个专题都必须制造至少一种失败：

- API：超时、token 过期、权限不足、重复提交、服务依赖失败。
- Android：系统弹窗、元素不可点击、ADB 掉线、应用被杀。
- iOS：WDA 失败、签名失败、系统权限、Simulator 端口冲突。
- 性能：压测机瓶颈、数据库锁、连接池耗尽、Coordinated Omission。
- CI：设备失联、报告缺失、Secret 失效、测试分片不均。

### 2.3 每一层都必须可调试

PyCharm 断点必须能够进入：

- pytest collection 和 fixture。
- 配置加载和 capability 合并。
- API Client 和认证刷新。
- Appium Python Client。
- Driver Factory 和页面交互。
- Locust User 和负载 Shape。
- 自定义 pytest 插件和失败 hook。

### 2.4 每个关键决策都要留下证据

一个专题结束至少要留下以下一种材料：

- ADR。
- runbook。
- 调用链图。
- 最小复现。
- 故障复盘。
- 性能对照报告。
- 稳定性趋势。
- 面试用 STAR 描述。

### 2.5 不用用例数量制造“大项目”

项目规模来自：

- 多接口和多业务域。
- 多端和多设备。
- 多环境。
- 多测试类型。
- 并发和数据隔离。
- 故障和恢复。
- 性能建模和分析。
- CI 和质量治理。

重复 1000 条同类点击，不会变成企业级项目。

### 2.6 AI 是加速器，不是事实来源

- 传统协议、系统、调试、并发和性能分析能力必须保留。
- AI 可以帮助理解、生成候选、分诊和总结，不能替代真实执行。
- 测试是否通过由 pytest、Appium、Locust 和设备结果决定。
- AI 生成的内容必须经过评审、运行、失败验证和人工批准。
- Agent 默认只读，写操作只能进入受控分支和 PR。
- 任何 Agent 都必须有权限边界、评测数据、Trace 和成本指标。

## 3. 设备、软件和账号准备

### 3.1 必需环境

| 类别 | 要求 |
| --- | --- |
| Windows | 16 GB 内存起步，建议 32 GB |
| CPU | 支持虚拟化，BIOS 中开启 VT-x 或 AMD-V |
| Android | Android Studio、SDK、ADB 和至少两个 AVD |
| iOS | Mac、Xcode、Simulator、真机或设备云 |
| Python | 3.11 或 3.12 |
| IDE | PyCharm Professional 或 Community |
| Node.js | LTS，通过 nvm-windows 管理 |
| Appium | Appium 2.x |
| Android Driver | UiAutomator2 |
| iOS Driver | XCUITest + WebDriverAgent |
| 报告 | Allure CLI |
| 容器 | Docker Desktop 或独立 Docker 环境 |
| 性能监控 | Prometheus + Grafana |
| 网络故障 | Toxiproxy |
| 接口调试 | Postman、Insomnia 或 HTTP Client |
| App 调试 | Appium Inspector |

### 3.2 iOS 的三种可选路径

1. 本地 Mac mini 或 Mac 工作站。
2. macOS CI Runner。
3. Appium 2 兼容的设备云。

纯 Windows 不能完成本地 iOS Simulator、WDA 构建和真机签名链路。

### 3.3 账号和设备建议

- Apple Developer 账号，真机测试通常需要签名能力。
- Android 真机一台，中低端机优先，比只使用旗舰模拟器更有价值。
- iPhone 真机一台，或准备稳定的设备云配额。
- 至少 60 GB 可用磁盘空间。
- 性能环境必须与日常功能测试环境隔离。

## 4. 企业级项目蓝图

### 4.1 推荐仓库结构

```text
quality-engineering-lab/
├── AGENTS.md
├── pyproject.toml
├── uv.lock
├── pytest.ini
├── .env.example
├── apps/
│   ├── compose/
│   ├── fixtures/
│   └── seed/
├── packages/
│   └── qa_core/
│       ├── config/
│       ├── auth/
│       ├── http/
│       ├── ws/
│       ├── contracts/
│       ├── models/
│       ├── db/
│       │   ├── clients/
│       │   ├── repositories/
│       │   ├── queries/
│       │   ├── schema/
│       │   └── fixtures/
│       ├── cache/
│       ├── integrations/
│       │   ├── test_management/
│       │   └── defect_tracking/
│       ├── platforms/
│       │   ├── android/
│       │   └── ios/
│       ├── data_factories/
│       ├── resource_pools/
│       ├── reporting/
│       ├── observability/
│       ├── diagnostics/
│       └── plugins/
├── tests/
│   ├── contract/
│   ├── api/
│   ├── database/
│   ├── cache/
│   ├── integration/
│   ├── mobile/
│   ├── e2e/
│   ├── resilience/
│   └── security_lite/
├── performance/
│   ├── locustfiles/
│   ├── workloads/
│   ├── profiles/
│   ├── data/
│   ├── thresholds/
│   └── listeners/
├── infra/
│   ├── docker/
│   ├── database/
│   ├── devices/
│   ├── device_farms/
│   ├── monitoring/
│   ├── fault_injection/
│   └── ci/
├── ai/
│   ├── agents/
│   ├── prompts/
│   ├── policies/
│   ├── tools/
│   ├── evals/
│   ├── knowledge/
│   └── runs/
├── governance/
│   ├── defect_policy/
│   ├── owner_mapping/
│   └── quality_metrics/
├── configs/
├── testdata/
├── scripts/
├── docs/
│   ├── adr/
│   └── runbooks/
└── artifacts/
```

### 4.2 技术栈

| 领域 | 主选 | 后续扩展 |
| --- | --- | --- |
| 测试框架 | pytest 8 | pytest 插件开发 |
| API Client | httpx | requests 对照 |
| 数据建模 | Pydantic | dataclass |
| API 契约 | OpenAPI + JSON Schema | Schemathesis |
| 关系型数据库 | PostgreSQL + psycopg 3 | MySQL、SQL Server、Oracle |
| 缓存 | Redis | Valkey、Memcached |
| 文档/搜索 | 可选 MongoDB/Elasticsearch | Cassandra、HBase |
| 数据库迁移 | Alembic | Flyway、Liquibase |
| SQL 运维工具 | `psql`、`pg_dump`、`pg_restore` | `mysql`、`redis-cli` |
| 移动端 | Appium 2 + Python Client | Flutter、Espresso |
| Android Driver | UiAutomator2 | Espresso |
| iOS Driver | XCUITest + WDA | 设备云 |
| 报告 | Allure | 历史趋势 |
| 测试分析 | Allure + ReportPortal | 自研质量看板 |
| 测试管理 | Kiwi TCMS | TestLink、自研平台 |
| 缺陷管理 | GitLab Issues + OpenProject | MantisBT、Jira、Bugzilla |
| 并发 | pytest-xdist | 自研调度插件 |
| 日志 | structlog | OpenTelemetry |
| 性能 | Locust | k6、JMeter、Gatling 对比 |
| 监控 | Prometheus + Grafana | Tempo、Loki |
| 故障注入 | Toxiproxy | Chaos Mesh |
| 环境 | Docker Compose | Kubernetes |
| CI/CD | Jenkins | GitHub Actions、GitLab CI |

### 4.3 被测系统

推荐顺序：

1. 小型 Demo App，用于理解基本 Appium 机制。
2. WordPress Server + WordPress Android/iOS，用于建立完整闭环。
3. Mattermost Server + Mattermost Android/iOS，用于大型企业级实战。

不要求覆盖整个 App。选择 6 到 8 个业务域，建立完整、稳定、可诊断的测试体系。

## 5. 32 周总课表

每周固定产出：代码、测试、调试记录、文档和改进项。验收标准以“可以独立解释并处理失败”为准。

| 周 | 阶段 | 学习与实现重点 | 本周交付 |
| --- | --- | --- | --- |
| 1 | 基础设施 | Git、uv、pyproject、pytest、PyCharm、目录规范 | 可运行工程骨架 |
| 2 | 基础设施 | Docker SUT、PostgreSQL、Redis、`psql`、健康检查和 Secrets | 一键启动测试环境 |
| 3 | 基础设施 | Android/iOS 最小 Appium session、CI 骨架 | 双平台 Hello Test |
| 4 | 接口 | httpx、配置、超时、重试、日志、Allure | API Client v1 |
| 5 | 接口 | OAuth2/OIDC、JWT、Cookie、并发刷新 | 认证 SDK |
| 6 | 接口 | Pydantic、JSON Schema、OpenAPI、兼容性 | 契约测试 |
| 7 | 接口 | 负向、边界、错误码、幂等和状态机 | API P0/P1 测试集 |
| 8 | 接口 | 数据工厂、数据库种子、清理、资源池、并行隔离 | 120 条 API 测试 |
| 9 | 数据库 | Schema、事务、隔离级别、锁、死锁、索引和查询计划 | API + DB 集成测试 |
| 10 | 数据一致性 | Redis TTL、缓存失效、WebSocket、异步任务和最终一致性 | 一致性测试集 |
| 11 | 接口 | RBAC、BOLA/IDOR、限流、输入安全、失败分类 | 安全基础测试集 |
| 12 | 质量闭环 | 并行、隔离、Mock、Toxiproxy、缺陷生命周期和追踪 | 220 条 API 测试 |
| 13 | Android | Appium 架构、UiAutomator2、ADB、PyCharm 调试 | Android 调用链文档 |
| 14 | Android | Locator、等待、手势、Page/Screen/Component/Flow | Android 框架骨架 |
| 15 | Android | 权限、系统弹窗、Hybrid、文件、深链接、后台恢复 | Android 业务测试 |
| 16 | Android | 双 AVD、真机、设备矩阵、日志和 Allure | 60 条 Android 测试 |
| 17 | iOS | macOS、Xcode、XCUITest、WDA、签名和 Simulator | iOS 环境 runbook |
| 18 | iOS | iOS capabilities、定位、键盘、手势和调试 | iOS 框架骨架 |
| 19 | iOS | 权限、系统弹窗、通知、深链接、文件和 WebView | iOS 业务测试 |
| 20 | iOS | 真机、设备云、WDA 并行和 DerivedData 隔离 | iOS 设备矩阵 |
| 21 | iOS | 稳定性、版本矩阵、失败诊断和重构 | 50 条 iOS 测试 |
| 22 | 跨平台 | PlatformAdapter、公共 Flow、Locator Set | 跨平台框架 v1 |
| 23 | E2E | API 建数、UI 操作、API 验证、缺陷证据和追踪链接 | 30 条 E2E |
| 24 | 恢复 | 网络、服务、App、WDA、ADB 故障、恢复和缺陷闭环 | 故障注入测试集 |
| 25 | 性能 | SLI、SLO、负载模型、Locust 和独立环境 | 性能方案和 Smoke |
| 26 | 性能 | Baseline、Load、数据库数据池、分布式 Locust | Baseline/Load 报告 |
| 27 | 性能 | Prometheus、Grafana、Trace、PostgreSQL/Redis 指标 | 性能监控面板 |
| 28 | 性能 | Stress、Spike、容量、Little's Law | 容量和拐点报告 |
| 29 | 性能 | Soak、Failover、慢查询、锁、连接池、WAL 和缓存分析 | 长稳和恢复报告 |
| 30 | 移动性能 | 启动、jank、内存、CPU、电量、弱网 | 移动性能报告 |
| 31 | CI | Android/iOS/性能流水线、缺陷系统集成、门禁和趋势 | 完整质量流水线 |
| 32 | 验收 | 综合链路、缺陷闭环、面试证据、架构图、ADR 和复盘 | 可演示的完整项目 |

数据库主线不额外增加项目周期，直接嵌入 Week 2、8、9、10、12、26、27 和 29。由于你已有 SQL 基础，目标是在现有 32 周内完成 PostgreSQL、Redis、API + DB 和数据库性能专题。若后续决定加入完整 MongoDB、Elasticsearch 或多种关系型数据库深挖，可额外预留 1 到 2 周。

缺陷管理不单独增加一套框架，直接嵌入 Week 11、12、23、24、31 和 32。先跑通轻量闭环 `Jenkins/GitLab CI + Allure + GitLab Issues`，再接入 `Kiwi TCMS + OpenProject/ReportPortal` 等开源增强组件。任何新增平台都必须能通过 API 适配器接入，不能把核心测试代码绑定到单一缺陷系统。

AI/Agent 不作为独立第四门课程抢走传统测试时间。每周用 1 到 2 小时，把 Agent 嵌入当前正在学习的真实任务：

| 周 | AI/Agent 融入 |
| --- | --- |
| 1-3 | `AGENTS.md`、仓库 map、只读代码与文档助手 |
| 4-8 | OpenAPI 契约审查、测试场景草稿、结构化输出 |
| 9-12 | 失败分诊、PR 变更影响分析、Eval v1 |
| 13-16 | Android page source、定位器顾问、日志分诊 |
| 17-21 | iOS WDA/签名日志分析、跨平台覆盖缺口 |
| 22-24 | E2E 影响分析、跨层失败归因、flaky 聚类 |
| 25-30 | 性能指标关联、报告生成、瓶颈实验建议 |
| 31-32 | CI Agent、定时维护、Trace、成本和质量看板 |

## 6. 分阶段详细计划

### 6.1 第一阶段：基础设施，Week 1 到 3

#### 目标

- 建立唯一可信的 Python 环境。
- 用 PyCharm 打开并调试整个工程。
- 启动 SUT、数据库、缓存和监控。
- Android 和 iOS 各跑通一条最小测试。

#### 核心任务

- 初始化 Git、pyproject、uv 和目录。
- PyCharm 指向项目虚拟环境。
- 建立 pytest Run Configuration。
- Docker Compose 启动 SUT。
- 配置 `.env.example` 和本地 Secret。
- 安装 Appium 2、UiAutomator2 和 XCUITest Driver。
- 建立 Android AVD 和 iOS Simulator。
- 写 Driver、配置、日志和 Allure 的最小实现。

#### 本周级验收

- `uv sync` 后测试可运行。
- 终端和 PyCharm 使用同一个解释器。
- Android/iOS 各有一条 smoke。
- 失败时能附加截图、page source 和日志。
- 能画出 Client、Server、Driver、设备端组件的关系图。

### 6.2 第二阶段：接口自动化，Week 4 到 12

#### 目标

从 HTTP 调用封装升级到完整接口测试平台。

#### 核心任务

- HTTP 协议和 Client 设计。
- OAuth2/OIDC、JWT、Cookie 和并发刷新。
- OpenAPI、JSON Schema 和 Pydantic。
- 正负向、边界、错误码、幂等和状态转换。
- 数据工厂、数据库种子、资源池、并行隔离和幂等清理。
- PostgreSQL Schema、事务、隔离级别、锁、死锁和查询计划。
- API 写入后的数据库状态断言和数据库预置后的 API 验证。
- Redis key、TTL、缓存失效、缓存穿透和数据库一致性。
- 队列、WebSocket、Webhook 和最终一致性。
- RBAC、BOLA/IDOR、限流和输入安全。
- Mock、Toxiproxy、超时、重试和降级。
- 失败分类、Allure、日志和 Trace。

#### 阶段验收

- 220 条以上 API 测试。
- 30 条以上契约测试。
- 20 条以上权限和安全基础测试。
- 至少 20 条负向和边界测试。
- 至少 80 条数据库、事务、并发或数据一致性测试。
- 至少 20 条 API + DB 联合状态验证。
- 覆盖一个真实死锁或锁等待案例。
- 覆盖 Redis TTL 和缓存失效案例。
- 完成一个 MySQL 兼容专题，MongoDB/Elasticsearch 作为可选扩展。
- 可以由 Appium 和 Locust 复用统一 SDK。
- 多 worker 运行无数据污染。
- 失败报告能区分产品、测试、环境和基础设施问题。

### 6.3 第三阶段：Android 深度，Week 13 到 16

#### 目标

掌握 Android 从 Python Client 到 UiAutomator2、ADB 和系统生态的完整链路。

#### 核心任务

- UiAutomator2、Espresso Driver 和 WDA 对比。
- capabilities、APK 安装和 Activity。
- Locator、显式等待、手势和输入。
- 权限、系统弹窗、通知、文件和 Hybrid。
- App 后台、进程死亡、深链接和恢复。
- 双 AVD、真机和设备云。
- `adb`、`logcat`、`dumpsys` 和 Appium 日志。

#### 阶段验收

- 60 条以上 Android 测试。
- 两个 Android 设备并行。
- 至少一条真机或设备云测试链路。
- 至少 3 份 Android runbook。
- 能解释 Android 元素可见但不可点击的原因。

### 6.4 第四阶段：iOS 深度，Week 17 到 21

#### 目标

掌握 XCUITest、WebDriverAgent、Simulator、真机签名和 iOS 特有交互。

#### 核心任务

- macOS、Xcode 和 Simulator。
- XCUITest Driver、WDA 和 XCTest。
- Simulator 与真机 capabilities。
- Apple Team、证书、Provisioning Profile 和设备信任。
- 权限、系统弹窗、通知、深链接、键盘和 WebView。
- 多 Simulator、WDA 端口和 DerivedData。
- 真机或 iOS 设备云。
- Xcode、WDA、Simulator 和 Appium 日志。

#### 阶段验收

- 50 条以上 iOS 测试。
- 两个 iOS Simulator 版本。
- 至少一台真机或设备云真机。
- 至少 5 份 iOS runbook。
- 能解释 Simulator 和真机失败的差异。

### 6.5 第五阶段：跨平台与 E2E，Week 22 到 24

#### 目标

让 Android 和 iOS 共享业务语义，同时保留真实平台差异。

#### 核心任务

- 建立 `PlatformAdapter`。
- 建立公共 Flow、Locator Set 和业务断言。
- API 建数，Appium 操作，API 验证。
- 测试数据、账号、设备、端口和 session 隔离。
- 网络、服务、App、WDA 和 ADB 故障注入。
- 恢复、重试、幂等和最终一致性。

#### 阶段验收

- 30 条以上跨层 E2E。
- Android 和 iOS 都可运行核心旅程。
- 平台分支集中，不散落在业务测试中。
- 一次失败可以回溯到 API、UI、设备和报告。
- 至少 5 条故障恢复测试。

### 6.6 第六阶段：性能工程，Week 25 到 30

#### 目标

不仅执行压测，还能设计负载模型、发现瓶颈并给出容量建议。

#### 核心任务

- SLI、SLO、SLA 和性能预算。
- Locust 用户模型、TaskSet、Shape 和数据池。
- 开环、闭环、Little's Law 和 Coordinated Omission。
- Smoke、Baseline、Load、Stress、Spike、Soak 和 Capacity。
- 分布式 Locust、Master、Worker 和压力机。
- Prometheus、Grafana、PostgreSQL、Redis 和容器指标。
- Go Profile、`EXPLAIN ANALYZE`、`pg_stat_statements`、慢查询、锁和连接池。
- WAL、磁盘 IO、Autovacuum、Redis 内存和缓存命中率。
- Android/iOS 启动、jank、内存、CPU 和弱网。

#### 阶段验收

- 8 到 10 条性能用户旅程。
- 6 种以上负载档位。
- 有独立性能环境和数据池。
- 有 SLO 和阈值。
- 有明确拐点和容量报告。
- 能把 API 延迟、数据库指标和 Redis 指标对齐到同一时间线。
- 能区分应用、数据库、网络和压测机瓶颈。

### 6.7 第七阶段：CI 与综合验收，Week 31 到 32

#### 目标

把项目变成可以持续运行和面试展示的完整质量平台。

#### 核心任务

- PR、Main、Nightly 和 Weekly 流水线。
- Android Linux Runner。
- iOS macOS Runner 或设备云。
- 性能独立 Runner。
- 测试分片、设备池、报告归档和 Secrets。
- 质量门禁、quarantine、owner 和趋势。
- 综合业务链路演示。
- 面试证据包和 STAR 故事。

#### 阶段验收

- 一个 commit 可以触发完整质量流水线。
- 报告可以直接定位失败。
- 性能结果有历史趋势。
- 所有关键决策有 ADR。
- 所有常见故障有 runbook。

## 7. 核心测试方向深度标准

### 7.1 接口自动化

不能只会：

```python
response = requests.get(url)
assert response.status_code == 200
```

必须掌握：

- HTTP 和连接层行为。
- 认证状态机。
- 契约和兼容性。
- 业务状态和副作用。
- 数据生命周期。
- 并发和隔离。
- 故障和降级。
- 可观测性。
- 与 Appium 和 Locust 的复用。

### 7.2 Appium

不能只会：

- 单设备。
- 固定 XPath。
- `sleep`。
- 单条登录测试。
- 只跑 Android Simulator。

必须掌握：

- Android UiAutomator2。
- iOS XCUITest 和 WebDriverAgent。
- 双平台 Simulator、真机和设备云。
- 定位、等待、手势和系统交互。
- Hybrid、文件、通知和深链接。
- 多设备并行。
- 跨平台抽象。
- 完整诊断链。

### 7.3 性能测试

不能只会：

- 设置 1000 用户。
- 压一个 GET 接口。
- 输出 Locust HTML。

必须掌握：

- 业务和负载建模。
- SLO 和容量目标。
- 开环、闭环和排队。
- 分布式压测。
- 监控和瓶颈定位。
- Stress、Spike、Soak 和容量。
- 移动端性能指标。
- 性能优化和容量建议。

### 7.4 数据与数据库测试

不能只会：

```sql
SELECT * FROM users WHERE id = 1;
```

必须掌握：

- 多表 JOIN、聚合、窗口函数、CTE 和批量操作。
- 主键、外键、唯一约束、CHECK、默认值和级联。
- 索引、复合索引、覆盖索引、失效索引和查询计划。
- ACID、事务边界、提交、回滚、保存点和幂等。
- 隔离级别、读取异常、行锁、死锁和锁等待。
- 乐观锁、版本冲突、并发更新和唯一约束竞争。
- Schema 迁移、Seed、快照、重置和脱敏。
- API + DB 联合状态验证和精确清理。
- Redis TTL、缓存失效、缓存穿透和数据库一致性。
- `EXPLAIN ANALYZE`、`pg_stat_statements`、连接池和慢查询分析。
- MongoDB/Elasticsearch 最终一致性、索引和文档版本。

## 8. Android 与 iOS 双生态要求

### 8.1 Android 设备矩阵

| 类型 | 最低要求 |
| --- | --- |
| AVD 新版本 | 主回归 |
| AVD 旧版本 | 兼容性 |
| Android 真机 | 系统生态和小版本差异 |
| 设备云 Android | CI 扩展 |

### 8.2 iOS 设备矩阵

| 类型 | 最低要求 |
| --- | --- |
| iOS Simulator 当前主版本 | 主回归 |
| iOS Simulator 前一主版本 | 兼容性 |
| iPhone 真机 | WDA、签名和真实系统行为 |
| 设备云 iOS | CI 和真实设备扩展 |

### 8.3 跨平台共享边界

共享：

- 业务 Flow。
- Scenario。
- 测试数据。
- 业务断言。
- API 建数和验证。
- 报告和诊断接口。

隔离：

- capabilities。
- 定位器。
- 手势和键盘。
- 权限和系统弹窗。
- 深链接、文件、通知。
- 设备和日志采集。

## 9. PyCharm 学习与调试方法

### 9.1 基础设置

1. 项目解释器选择 `.venv\Scripts\python.exe`。
2. 工作目录设置为项目根目录。
3. 建立 pytest Run Configuration。
4. 添加 `--alluredir=artifacts/allure-results`。
5. 测试环境变量通过本地 `.env` 或系统 Secret 注入。
6. 配置单个测试、测试文件、marker、xdist 和 Locust 的运行模板。

### 9.2 必设断点

- 配置加载。
- capability 合并。
- Driver 创建。
- fixture setup 和 teardown。
- 认证和 token refresh。
- API Client 发送和响应。
- 页面交互和显式等待。
- Allure 附件。
- pytest failure hook。
- Locust User 和 Load Shape。

### 9.3 调试顺序

API：

```text
pytest
-> fixture
-> config
-> auth
-> request
-> response
-> model
-> business assertion
-> report
```

Appium：

```text
pytest
-> fixture
-> capabilities
-> Appium Client
-> Server
-> Driver
-> device
-> locator
-> action
-> assertion
-> diagnostics
```

性能：

```text
Locust
-> User
-> TaskSet
-> auth
-> data pool
-> request
-> metrics
-> backend
-> database/cache
-> bottleneck
```

### 9.4 调试技巧

- Conditional Breakpoint 只暂停指定 worker、设备或测试。
- Evaluate Expression 检查最终 capabilities 和响应对象。
- Exception Breakpoint 捕获被框架包装的真实异常。
- Watch 观察 worker、UDID、session id、context 和 token。
- 先单 worker 复现，再恢复并行。
- 同时观察 PyCharm、Appium Server、ADB、logcat、WDA 和 Xcode。

## 10. 每周学习节奏

建议每周安排：

| 时间 | 内容 |
| --- | --- |
| 周一 | 官方文档、源码和问题定义 |
| 周二 | 最小 experiment 和断点调试 |
| 周三 | 融入共享平台 |
| 周四 | 制造失败、并发或故障 |
| 周五 | 报告、重构、测试稳定性 |
| 周六 | 回归、性能或设备矩阵 |
| 周日 | ADR、runbook 和周复盘 |

每天结束时回答：

1. 今天解决了什么具体问题？
2. 哪个断点帮助最大？
3. 哪个假设立场被推翻？
4. 今天新增了什么可复现证据？
5. 明天最小任务是什么？

每天不要只记录“学习了什么”，要记录“验证了什么”。

## 11. Git、文档和知识管理

### 11.1 分支策略

建议按学习主题创建短分支：

```text
study/week-04-http-client
study/week-05-auth
study/week-14-android-locators
study/week-18-ios-capabilities
study/week-25-locust-baseline
```

每个分支完成后合并，保持主干始终可运行。

### 11.2 提交要求

每个提交尽量保持单一目的：

```text
feat(core): add layered settings loader
test(api): add contract validation for login
fix(mobile): isolate android app state per worker
perf(locust): add baseline load shape
docs(adr): record ios wda signing strategy
```

### 11.3 每阶段文档

- `docs/adr`：架构决策。
- `docs/runbooks`：故障处理。
- `docs/architecture`：架构和调用链。
- `docs/test-strategy`：测试策略。
- `docs/interview`：STAR 故事。
- `artifacts`：测试和性能制品。

## 12. 质量指标与验收标准

### 12.1 功能自动化指标

- Smoke 通过率大于等于 98%。
- flaky rate 低于 2%。
- 单条测试可以独立运行。
- 全量测试不依赖固定顺序。
- 失败报告 100% 包含分类和诊断材料。
- Android/iOS 核心业务覆盖率有矩阵，不只统计代码行。

### 12.2 性能指标

- 每个核心旅程有 SLO。
- 每次性能测试有基线可比。
- p95、p99、错误率和吞吐量必须同时记录。
- 性能环境、数据池和压力机独立。
- 性能结果必须关联服务端资源指标。
- 有容量、拐点和恢复时间结论。

### 12.3 数据与数据库指标

- 数据库测试和 API 测试共享数据工厂与资源池。
- 每条数据写入都有唯一命名、owner 和清理策略。
- 不依赖固定顺序或固定 `sleep`。
- API 写入后能验证真实数据库状态。
- 覆盖事务回滚、并发更新、锁等待、死锁和幂等。
- 覆盖 Redis TTL、缓存失效和数据库一致性。
- 数据库性能指标可以与 API/Locust 结果对齐。
- 不直接连接生产数据库。

### 12.4 工程指标

- 依赖有锁文件。
- 配置有类型校验。
- Secret 不进入 Git。
- 关键设计有 ADR。
- 常见故障有 runbook。
- CI 结果可追溯 commit 和 App/API 版本。

### 12.5 AI/Agent 指标

- Golden Task 完成率和准确率。
- 幻觉率和错误建议率。
- 人工修改比例。
- 平均节省时间。
- 单任务 Token、成本和 P95 延迟。
- 工具调用成功率和写操作回滚率。
- Agent 结论的证据引用完整率。

### 12.6 缺陷闭环指标

- 缺陷发现、确认和修复时间。
- MTTR 和关闭 SLA。
- 重开率和重复缺陷率。
- Defect Leakage。
- 自动分诊准确率和自动去重准确率。
- 关联测试用例、Run、PR 和回归结果的完整率。
- 自动创建草稿和人工审批比例。
- 自动关闭数量必须为 0。

## 13. 面试准备与证据包

### 13.1 必须准备的架构题

1. 为什么用 monorepo，而不是三个仓库？
2. API、Appium 和 Locust 如何共享认证与模型？
3. Android 和 iOS 如何共享业务测试？
4. 如何隔离 pytest-xdist 的数据和设备？
5. 如何定位并行时才出现的问题？
6. 如何处理 token 并发刷新？
7. 如何设计契约测试？
8. 如何测试对象级越权？
9. 如何设计 API 写入后的数据库状态断言？
10. 为什么测试事务回滚不能替代所有数据库隔离方案？
11. 如何测试并发更新、锁等待和死锁？
12. 如何验证数据库、Redis 和搜索索引的最终一致性？
13. 如何用执行计划解释慢查询？
14. 如何设计性能负载模型？
15. 如何找系统拐点？
16. 如何区分产品、测试、设备和环境失败？
17. 如何治理 flaky test？
18. iOS WDA 和签名失败如何排查？
19. 如何让 CI 在 Android 和 iOS 上稳定运行？
20. 如何让 Agent 参与失败分诊但不自动掩盖问题？
21. 如何控制 Agent 工具权限和 Prompt Injection？
22. 如何评测测试 Agent 的准确率和收益？
23. 为什么小仓库可能不需要向量数据库？
24. 哪些质量步骤不能交给 Agent？
25. 如何量化 Agent 节省的时间和成本？

### 13.2 STAR 故事模板

```text
背景：
目标：
约束：
方案选择：
实施过程：
遇到的失败：
指标变化：
最终结果：
复盘和改进：
```

至少准备：

- 一次 Android/iOS 跨平台重构。
- 一次并行状态污染定位。
- 一次认证并发问题。
- 一次契约兼容性回归。
- 一次数据库并发、锁或死锁定位。
- 一次缓存与数据库一致性排查。
- 一次性能拐点分析。
- 一次 iOS WDA 或签名故障。
- 一次 CI 设备稳定性治理。
- 一次 flaky test 治理。
- 一次 Agent 误判、Eval 和权限修正。
- 一次 AI 失败分诊带来的效率提升。

### 13.3 面试演示材料

- 架构图。
- 目录结构。
- 一条完整业务链路。
- API 测试报告。
- Android 测试报告。
- iOS 测试报告。
- Locust 和 Grafana 性能报告。
- CI 运行记录。
- ADR 和 runbook。
- 失败复盘和优化前后对比。

## 14. 风险与应对

| 风险 | 应对 |
| --- | --- |
| 没有 Mac | 使用 macOS CI 或设备云，先完成 iOS 框架和 Simulator 设计 |
| 设备云成本高 | 本地 Android 为主，iOS 使用临时配额或分阶段执行 |
| Docker 环境过重 | 先启动 SUT、数据库、缓存，再逐步增加监控 |
| 学习范围过大 | 每周只执行课表任务，不在周中临时换工具 |
| 测试频繁 flaky | 先单 worker 复现，收集证据，再治理根因 |
| 性能环境不稳定 | 固定版本、数据、资源和运行窗口 |
| 用例多但质量低 | 用业务覆盖、失败分类和趋势替代数量崇拜 |
| 只看文档不动手 | 每个专题必须留下 experiment 和断点记录 |
| 代码只在本机可跑 | 每个阶段都加入 CI 或可重复脚本 |
| 过度依赖 AI | AI 只生成候选，测试执行和人工评审决定结果 |
| Agent 权限过大 | 默认只读、工具白名单、分支写入和审批 |
| AI 幻觉和技术债 | 用 Eval、证据引用、复现和人工修改率控制 |
| Prompt Injection | 将日志、页面和网页视为不可信输入，隔离工具权限 |
| 数据库测试污染 | 每个 worker 使用唯一命名空间，清理必须幂等 |
| 事务回滚隔离失效 | 验证被测应用是否使用独立连接，必要时使用快照或租户隔离 |
| 直接连接生产库 | 数据库账号只授予测试环境最小权限 |
| 最终一致性误判 | 使用带超时的条件轮询和事件证据，不用固定 sleep |
| 缺陷重复创建 | 使用测试 ID、错误签名、堆栈、设备和版本构成缺陷指纹 |
| 缺陷流程绑定单一平台 | 核心代码只依赖统一 Defect Adapter，平台通过 Adapter 接入 |
| Agent 自动关闭缺陷 | 缺陷关闭必须人工审批，保留修复和回归证据 |
| Allure 被误当缺陷系统 | Allure 只负责证据和可视化，缺陷状态由 Issue/测试管理平台负责 |

## 15. 第一周行动清单

### Day 1

- 初始化 Git。
- 创建 `pyproject.toml`。
- 创建 `AGENTS.md` 和 `ai/` 目录骨架。
- 使用 uv 创建 Python 3.12 环境。
- 在 PyCharm 中选择项目虚拟环境。

### Day 2

- 创建基础目录。
- 加入 pytest、Allure、HTTP Client、Pydantic、psycopg 和 Redis Client。
- 建立第一条单元测试和第一条 smoke 测试。
- 配置 PyCharm pytest Run Configuration。

### Day 3

- 安装并验证 Appium 2。
- 安装 UiAutomator2 Driver。
- 启动 Android AVD。
- 在 PyCharm 中调试 Driver 创建。

### Day 4

- 准备 macOS CI 或设备云。
- 安装并验证 XCUITest Driver。
- 启动 iOS Simulator。
- 建立 iOS 最小 session experiment。
- 让只读 Agent 分析一次 Driver 创建调用链。

### Day 5

- 创建 Docker Compose SUT。
- 验证 API、PostgreSQL 和 Redis。
- 使用 `psql` 验证 Schema、种子数据和只读查询。
- 建立健康检查和 SUT 启动脚本。

### Day 6

- 建立第一份 ADR。
- 建立第一份 runbook。
- 确定缺陷生命周期、缺陷指纹和 Allure 链接规范。
- 让 Android、iOS 和 API 三类 smoke 都能执行。

### Day 7

- 连续运行 smoke 10 次。
- 检查 session、进程和端口是否泄漏。
- 生成第一份 Allure 报告。
- 写下本周最难的 3 个问题和最小复现。

第一周结束时必须达到：

```text
PyCharm 可调试
+ Android smoke 可运行
+ iOS smoke 可运行
+ API smoke 可运行
+ SUT 可启动
+ Allure 有报告
+ 无 session 泄漏
```

## 16. AI 与 Agent 融合方案

AI 与 Agent 的目标、等级、边界和最终验收标准见 [项目目标文档](GOALS.md)。

### 16.1 目标层级

| 层级 | 能力 | 项目目标 |
| --- | --- | --- |
| L0 | 个人聊天辅助 | 第一周达到 |
| L1 | 仓库感知助手 | API 阶段达到 |
| L2 | 只读任务 Agent | Appium/性能阶段达到 |
| L3 | 受控写入 Agent | CI 阶段达到 |
| L4 | 受限自治维护 | 完成设计和 Eval，不追求全面自治 |

### 16.2 必须实现的 Agent

1. 需求到测试 Agent。
2. PR 变更影响分析 Agent。
3. API 契约审查 Agent。
4. 测试数据和边界 Agent。
5. Android/iOS 定位器顾问 Agent。
6. 失败分诊与缺陷草稿 Agent。
7. Flaky 聚类 Agent。
8. 性能指标分析 Agent。
9. CI 修复建议 Agent。
10. 每周测试维护 Agent。

### 16.3 Agent 技术栈

- 仓库上下文：`AGENTS.md`、OpenAPI、测试目录、ADR 和 runbook。
- 工具调用：Git、pytest、Appium、ADB、XCUITest、Allure、Locust、Docker、Prometheus。
- 结构化输出：Pydantic 或 JSON Schema。
- 检索：优先文件、`rg` 和测试索引，确有需要再引入向量检索。
- 编排：先确定性工作流，再考虑状态机、LangGraph、Temporal 等方案。
- 可观测性：Agent Trace、工具调用、Token、成本、延迟和结果。
- Eval：30 到 50 个 Golden Tasks 和历史失败集。
- 安全：只读默认、工具白名单、Secret 隔离、Prompt Injection 防护和人工审批。

### 16.4 不能交给 Agent 的操作

- 生产数据库写操作。
- 生产压测。
- 发布和回滚。
- 自动合并。
- 自动修改权限。
- 读取和传输证书、私钥、真 Secret。
- 绕过测试或质量门禁。
- 自动创建大量重复缺陷。
- 自动修改缺陷优先级或自动关闭缺陷。

### 16.5 AI 项目验收

- 每个 Agent 都有输入、工具、输出、权限和失败兜底。
- 每个 Agent 都有 Eval，不靠演示判断好坏。
- 所有建议都引用仓库、日志或指标证据。
- 写操作只能进入受控分支或 PR。
- 有人工修改率、准确率、成本、延迟和节省时间。
- 至少展示一次 Agent 误判、修正和防护改进。

第一周需要额外完成：

- 创建 `AGENTS.md`。
- 创建 `ai/` 目录骨架。
- 建立一个只读仓库问答或代码解释流程。
- 记录一次 AI 建议被验证或推翻的案例。

## 17. 缺陷管理与质量闭环方案

### 17.1 系统边界

Jenkins 是开源 CI/CD，不是缺陷管理系统。它可以执行任务、触发测试、展示结果和调用缺陷系统 API，但不负责缺陷状态、owner、优先级、重复判定和关闭流程。

Allure 是测试报告和可视化系统，不是测试管理或缺陷管理系统。它可以展示测试用例、失败分类、附件和历史，但不能替代缺陷生命周期。

职责划分：

```text
Jenkins/GitLab CI
-> 执行、调度、归档和质量门禁

Allure/ReportPortal
-> 测试证据、历史、趋势和失败分析

Kiwi TCMS/TestLink
-> 测试用例、计划、运行和可追溯性

GitLab Issues/OpenProject/MantisBT/Jira
-> 缺陷状态、负责人、优先级和修复验证
```

### 17.2 开源方案选择

| 方案 | 组件 | 适用阶段 |
| --- | --- | --- |
| 轻量闭环 | Jenkins + Allure + GitLab Issues | Week 11 到 12 |
| 测试管理增强 | Jenkins + Allure + Kiwi TCMS + GitLab Issues | Week 23 到 24 |
| 质量分析增强 | Allure + ReportPortal + GitLab Issues/OpenProject | Week 31 |
| 企业兼容 | 统一 Adapter + Jira/GitLab/OpenProject/MantisBT | 后续扩展 |

ReportPortal 和 Kiwi TCMS 有功能重叠，必须选择一个作为测试结果和测试资产的事实来源：

- Kiwi TCMS：测试用例、计划、执行、Bug 关联和测试追踪。
- ReportPortal：测试结果聚合、失败分类、flaky 和趋势分析。
- GitLab Issues/OpenProject：缺陷流程和负责人。
- Jira：企业常见商业方案，通过 Adapter 接入，不绑定核心代码。

### 17.3 闭环流程

```text
测试失败
-> Allure 保存证据
-> 失败指纹和分类
-> 查询疑似重复缺陷
-> 创建缺陷草稿
-> 人工确认
-> 创建缺陷并关联 Run/TestCase
-> 修复和关联 PR
-> Jenkins 触发回归
-> Allure 保存验证证据
-> 人工批准关闭
```

缺陷状态：

```text
New
-> Triage
-> Confirmed
-> In Progress
-> Ready for Verification
-> Verified
-> Closed
```

异常状态：

- Duplicate
- Rejected
- Deferred
- Won't Fix
- Reopened

### 17.4 统一适配器

在 `qa_core/integrations/defect_tracking` 中实现统一接口：

```text
find_similar
create_draft
create_issue
update_issue
add_comment
attach_evidence
link_test_case
link_pull_request
transition
close
```

后端适配器：

- GitLab
- OpenProject
- MantisBT
- Jira
- GitHub Issues

业务测试和 CI 只能依赖统一接口，不能直接调用某个平台的 SDK。

### 17.5 缺陷指纹和去重

候选指纹：

```text
test_id
+ failure_type
+ top_stack_frames
+ error_signature
+ platform
+ device_class
+ app_version_bucket
+ environment
```

去重流程：

1. 先按测试 ID 和错误签名查询。
2. 再按堆栈、设备和版本聚类。
3. 由 Agent 生成相似度说明。
4. 人工确认复用还是新建。

不能只按失败文本去重，因为相同文本可能来自不同根因。

### 17.6 Allure 追踪

测试代码至少使用：

```python
import allure

@allure.testcase("TC-123")
@allure.issue("BUG-456")
@allure.link("https://jenkins.example/job/123", name="Jenkins Run")
def test_login_success():
    ...
```

缺陷创建后，将缺陷 ID、Run ID、Jenkins URL、设备和 commit 回写到 Allure 结果与测试管理平台。

### 17.7 自动化审批边界

允许自动化：

- 收集失败证据。
- 失败分类。
- 查询重复缺陷。
- 生成缺陷草稿。
- 更新已有缺陷的复现次数和回归结果。
- 在修复 PR 上添加验证结果。

必须人工审批：

- 创建正式缺陷。
- 修改优先级和 owner。
- 拒绝、延迟或关闭缺陷。
- 处理生产或安全缺陷。

禁止：

- 每次失败自动创建新缺陷。
- 自动关闭缺陷。
- 自动修改生产系统。
- 将 Secret、个人信息或生产数据写入缺陷。

### 17.8 缺陷闭环指标

- Defect Detection Time。
- Defect Confirmation Time。
- MTTR。
- Reopen Rate。
- Duplicate Rate。
- Defect Leakage。
- Automatic Triage Precision。
- Automatic Deduplication Precision。
- Link Completeness。
- Manual Approval Rate。

## 18. 配套文档

- [项目目标文档](GOALS.md)

执行原则：

```text
计划书负责方向
课表负责节奏
每阶段验收负责质量
Git 和文档负责证据
面试目标负责深度
AI 负责提效
执行结果负责真相
```
