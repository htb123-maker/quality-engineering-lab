# STAR 故事 / STAR Stories

每个故事都可回到仓库文件、周报或 GitHub Run。没有可靠数字的地方不补造数字。

## 1. Android 与 iOS 跨平台重构

**背景：** 两个平台分别维护 locator、等待和系统操作，业务 Flow 容易复制后漂移。

**目标：** 让同一业务场景共享意图，同时保留平台差异和可诊断性。

**约束：** 不把所有差异塞进一个万能 page object；Android 用 UiAutomator2，iOS 用
XCUITest/WDA；测试失败仍需保留平台原始证据。

**方案：** 建立 PlatformAdapter、Screen、Locator Set 和公共 Flow，平台 adapter
实现定位、等待和系统交互。

**实施：** 先补契约单测，再把已有 Android/iOS 业务场景迁移到共享 Flow。

**失败：** iOS WDA、定位器和设备启动属于平台层，不能仅靠业务 Flow 修复。

**指标：** 用跨平台契约单测、Android smoke、iOS Simulator smoke 和平台原有测试
共同验证；不以代码复用率代替执行结果。

**结果：** 业务场景可以复用，平台失败仍落在独立 adapter/runner 和日志中。

**复盘：** 抽象边界应是“业务意图”而不是“所有手势和 selector 完全一致”。

## 2. 并行状态污染定位

**背景：** pytest-xdist 并发后出现单独运行通过、并行偶发失败。

**目标：** 证明失败是否来自共享 namespace、数据、端口或设备状态。

**约束：** 不能靠重跑掩盖问题，也不能把并发失败都归因 flaky。

**方案：** 为 worker 分配唯一 namespace、数据前缀和资源；比较串行和受控并发。

**实施：** 固定用例、worker 和资源池，记录数据库键、端口、session 和清理日志。

**失败：** 仅看最终响应无法区分状态污染和环境竞争。

**指标：** 用隔离单测、全量并行回归和重复失败指纹验证。

**结果：** 并行资源有明确 owner 和清理策略，失败可以定位到数据或设备边界。

**复盘：** 隔离是资源协议问题，不只是测试代码加一个随机后缀。

## 3. 并发刷新认证竞态

**背景：** 多个请求同时发现 access token 过期，触发 refresh token rotation 竞态。

**目标：** 避免并发 refresh 导致一部分请求拿到已撤销 token。

**约束：** 本地验证不连接生产身份系统；refresh 仍保持轮换和撤销语义。

**方案：** single-flight 合并刷新，统一处理成功、失败和并发等待。

**实施：** 用可控延迟和同时发起请求覆盖竞态，再验证普通顺序刷新没有回归。

**失败：** 最初只测单请求刷新，没有覆盖同一时刻的多个 refresh。

**指标：** 并发 refresh 请求数、失败请求恢复、旧 token 撤销和单测通过。

**结果：** 认证客户端共享并发刷新边界，Appium 和 Locust 也能复用。

**复盘：** 认证状态机需要并发测试，不能只测 happy path。

## 4. 契约兼容性回归

**背景：** SUT 演进时可能改变字段必填、类型或错误码，消费者测试才会晚发现。

**目标：** 在合同层发现破坏性变更，并保留运行时模型验证。

**约束：** 不能依赖手写字段列表；OpenAPI 和 Pydantic 要各司其职。

**方案：** OpenAPI 作为契约源，Pydantic 验证请求/响应，兼容器检查删除和类型变化。

**实施：** 为正常、边界和错误响应都建立模型，再补旧/新 schema 对比测试。

**失败：** 只验证 200 响应会漏掉错误码和状态机兼容性。

**指标：** 契约单测、负向 API 测试和失败测试定位路径。

**结果：** 契约破坏可以在 SUT 部署测试前被明确分类。

**复盘：** 契约测试应覆盖错误面，不把 JSON 能解析当成兼容。

## 5. 数据库锁与死锁定位

**背景：** 并发更新在 CI 中偶发超时，仅看 API 504 无法判断锁竞争还是业务慢。

**目标：** 构造可重复锁等待，并验证超时、重试和最终状态。

**约束：** 不使用固定 sleep 判断锁；数据库访问限制在测试 schema。

**方案：** 两个连接按受控顺序持有行锁，记录等待和数据库错误；对死锁保留原始
`SQLSTATE`。

**实施：** 把事务、隔离级别、timeout 和清理写成可重复测试，再补查询计划证据。

**失败：** 早期只测 API 返回，无法说明是数据库等待还是应用层延迟。

**指标：** 锁等待时间、错误分类、事务最终状态和相关单测。

**结果：** 数据库失败可以定位到锁、隔离或连接边界。

**复盘：** 数据库测试必须控制连接和提交语义，不能只套用单元测试写法。

## 6. Redis 与数据库最终一致性

**背景：** cache-aside 逻辑在写入后短时间可能返回旧值，固定 sleep 既慢又不稳定。

**目标：** 用带超时的条件轮询验证缓存、数据库和事件的最终状态。

**约束：** Redis 不冒充持久数据库，测试不能无限等待。

**方案：** API 写入，检查数据库，抛出缓存刷新，再记录 Redis 可见时间和 TTL。

**实施：** 覆盖命中、失效、失败回退和一致性问题，保存状态 JSON 与日志。

**失败：** 最初用固定 sleep 导致慢机器偶发失败、快机器掩盖问题。

**指标：** 最终可见时间、TTL、条件轮询上限和一致性测试结果。

**结果：** 一致性问题有明确证据，超时保持失败而不是“可能已一致”。

**复盘：** 最终一致性测试是“有限等待和证据”，不是随机等待。

## 7. 性能拐点与容量结论

**背景：** 单次压测只能给出请求数和延迟，无法说明系统在哪个负载档开始退化。

**目标：** 在独立环境中建立 baseline、load、stress、spike、soak 和容量证据。

**约束：** 不压生产，不共享性能数据池，不在监控缺失时只报 Locust 数字。

**方案：** 固定 profile 和资源，逐档增加并发，同时采集 p50/p95/p99、吞吐、错误、
数据库和 Redis 指标。

**实施：** 统一 run label、时间线和结果 JSON，再把异常档位做成复盘。

**失败：** 早期只看 API 响应时间，无法区分数据库、缓存或压测机瓶颈。

**指标：** 各档 latency、throughput、error、SLO、资源饱和和恢复时间。

**结果：** 周报可以描述拐点候选和容量边界，而不是宣称无限并发。

**复盘：** 性能结论必须绑定环境、数据、版本和运行窗口。

## 8. iOS WDA、签名与设备云边界

**背景：** iOS 在 Windows 本机无法启动 XCUITest，云 provider 又受额度和配置影响。

**目标：** 把环境失败、WDA 构建、签名和测试断言分层，至少保留一条必需 iOS 实跑。

**约束：** 没有 Mac 本机；BrowserStack Free Trial 可能到期；不能把 cloud `BLOCKED`
写成 iOS 通过。

**方案：** macOS GitHub Runner 执行 Simulator smoke，云 provider 作为可选证据；
分别收集 Xcode、simctl、Appium、WDA 和 JUnit。

**实施：** 选择 iOS 18.5 runtime、构建 fixture、安装 App、启动 Appium，再跑最小
session 和核心 smoke。

**失败：** 早期 cloud 额度耗尽，曾出现“本地框架看起来对了但设备没有执行”的风险。

**指标：** Week31 最终 iOS Simulator 4 条 smoke 通过；cloud 保留 `BLOCKED` 证据。

**结果：** 必需 iOS 路径由 macOS Runner 实际执行，设备云仍有清晰独立状态。

**复盘：** 外部供应商是环境依赖，必须有本地/自有 runner 的降级路径。

## 9. Android Linux CI emulator 稳定性

**背景：** Android 本地 smoke 通过不代表 Linux Runner 能稳定启动 emulator。

**目标：** 让 Android emulator 成为统一 pipeline 的可重复 job。

**约束：** Runner 资源、KVM、Appium driver 和动画设置都会影响启动。

**方案：** 固定 API 35 AOSP ATD、Pixel 6、x86_64、Appium 2.19.0 和
UiAutomator2 4.2.9，先启动 emulator 再跑最小 smoke。

**实施：** 加 KVM 规则、Appium driver 安装、fixture build、artifact 上传和明确
timeout。

**失败：** Week31 第一轮 Android 长步骤未完成，没有把未执行写成 pass。

**指标：** 最终 Run `44563937821` 的 Android job 通过 6 条 smoke。

**结果：** Android 由 Linux CI 执行并保留 JUnit、日志和 Appium 证据。

**复盘：** 设备 job 的通过条件应包括 emulator boot 和 Appium session，而不是只看
脚本启动。

## 10. Flaky 治理与质量门禁

**背景：** 偶发失败容易被无界重试隐藏，导致趋势和 owner 失真。

**目标：** 把失败指纹、owner、quarantine、趋势和门禁关联起来。

**约束：** Quarantine 不能自动隐藏结果；到期必须失败；缺陷不能自动关闭。

**方案：** 治理配置要求 exact node ID、owner、原因、到期日和证据；趋势从 JUnit
和状态 JSON 构建，不解析不可信控制台文本。

**实施：** 增加 governance 校验、quality trends、必需 job 失败合成和 cache 历史。

**失败：** 早期没有记录失败 job 的合成状态，失败可能从趋势中消失。

**指标：** 387 个 unit、45 个 integration、238 个 API 和最终 Trend PASS；quarantine
保持空数组。

**结果：** 重跑存在也不改变原始失败证据，门禁状态可追溯。

**复盘：** Flaky 治理的目标是减少不确定性，而不是让红色变绿色。

## 11. Agent 无证据误判与修正

**背景：** 初始分诊草案只看是否出现 `FAILED`，空证据集会被分类为 `PASS`。

**目标：** 让 Agent 在证据不足时 fail closed，并保留可回归的安全语义。

**约束：** Agent 不执行测试、不读生产 Secret、不自动写仓库或关闭缺陷。

**方案：** 先检查 evidence 非空、信号非空、状态已知，再分类 failed/blocked/pass；
无证据返回 `INSUFFICIENT_EVIDENCE`。

**实施：** 写 30 个 Golden Tasks，覆盖正常、失败、阻断、未知和空证据；记录回归。

**失败：** `GT-025` 到 `GT-030` 专门守住原始 false-pass 风险。

**指标：** 当前确定性基线 `tasks=30`、accuracy `1.0`、evidence-reference `1.0`、
Token `0`、cost `0`；这些是实测属性，不是 LLM 收益。

**结果：** 证据缺失有显式状态，人工审批标记为必需。

**复盘：** Agent 最小可信能力不是“回答像专家”，而是“没有证据时敢说不知道”。

## 12. 真实 SUT 缺陷修复与人工关闭边界

**背景：** SUT 对不支持 HTTP method 返回 HTML 501，破坏统一 JSON 错误契约。

**目标：** 返回 JSON 405、明确 `Allow` header，并保留 Issue 证据。

**约束：** 必须先复现真实行为；修复不能自动关闭 GitHub Issue；所有回归要可追溯。

**方案：** 在 handler 层增加 unsupported methods，统一调用 `_method_not_allowed`，
移除 strict xfail，改为精确断言。

**实施：** 启动 Compose SUT，执行目标 API 测试，再把结果写入周报和 Issue 评论。

**失败：** 只改测试或只做静态检查不能证明 SUT 契约修复。

**指标：** 目标测试真实 HTTP 405、JSON error code `method_not_allowed` 和 `Allow`
header；最终关闭需人工批准。

**结果：** 修复代码、测试、Issue 和回归证据形成闭环，关闭动作仍保留人工 owner。

**复盘：** 缺陷闭环不等于自动关单；正确状态转换和证据审阅更重要。
