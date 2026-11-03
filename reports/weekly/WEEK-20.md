# WEEK-20 - iOS 设备矩阵、WDA 并行与 DerivedData 隔离 / iOS Device Matrix, Parallel WDA, and DerivedData Isolation

- 计划 / Plan: Week 20，iOS 设备矩阵与并行能力
- 日期范围 / Date Range: 2026-11-03 to 2026-11-09
- 分支 / Branch: codex/ios-week20-device-matrix-20261101
- 基线提交 / Base Commit: a5d913e（Week 19 cloud acceptance）
- 计划提交 / Plan Commit: 本文件首次提交 / Initial commit for this file
- 远端分支 / Remote Branch: `origin/codex/ios-week20-device-matrix-20261101`
- Pull Request: 尚未创建 / Not created
- 状态 / Status: **当前版本并行隔离通过，矩阵范围未闭合 / PARTIAL PASS**

## 计划目标 / Plan Goal

Week 20 对应课表中的 iOS 设备与并行能力，目标是在 Week 19 单设备、单
Simulator 基线上建立可重复的 iOS 设备矩阵：

1. 用 YAML 描述当前主版本 Simulator、前一主版本 Simulator 和可选云真机。
2. 让 pytest-xdist worker 与设备 profile 一一绑定，避免两个 session 共用设备。
3. 为每个 worker 分配唯一 WDA 本地端口，并在启动前检查冲突。
4. 为每个 worker 分配独立 DerivedData 目录，避免并行 WDA/Xcode 构建串扰。
5. 在 macOS Runner 上并行运行两个 Simulator session，并保存每台设备的证据。
6. 保留 BrowserStack 云真机路径，验证 capability 和证据采集没有被本地矩阵破坏。
7. 形成设备、Xcode、WDA、Appium 和 pytest 的联合诊断方法。

English summary: introduce an explicit iOS device matrix, bind xdist workers to
distinct Simulator/cloud profiles, allocate isolated WDA ports and DerivedData
directories, and prove parallel session isolation on macOS plus a retained real
cloud-device path.

## 完成状态 / Completion Status

**部分通过 / PARTIAL PASS**

当前主版本 Simulator 的并行隔离已经通过：

- Xcode 16.4 + iOS 18.5，两台不同 Simulator：iPhone 16、iPhone 16 Plus。
- 两个 xdist worker 真实并行，测试结果 `2 passed in 120.44s`。
- 两个 session 时间重叠 `98.28s`。
- Appium Server 端口为 `4723` / `4724`。
- WDA 本地端口为 `8100` / `8101`。
- DerivedData 分别为 `artifacts/ios-derived/41317497880/<device-id>`。
- 资源校验脚本确认设备、UDID、Appium 端口、WDA 端口和 DerivedData 均唯一。
- 最终 Run：[41317497880](https://github.com/htb123-maker/quality-engineering-lab/actions/runs/41317497880)。

以下范围仍未完成，不能写成 `PASS`：

- 前一主版本 Simulator 兼容矩阵。
- BrowserStack 多真机并行矩阵。
- Week 21 的 50 条 iOS 测试和长期稳定性。

### Week 19 入口核对 / Week 19 Entry Audit

Week 19 为 **PARTIAL PASS**，不是完整通过：

- 真实 iPhone 15 / iOS 17 cloud run 成功，`9 passed, 1 xfailed`。
- 外部冷启动深链接、权限跨运行重置和通知授权/调度已通过。
- WKWebView context 等待 70 秒后仍只暴露 `NATIVE_APP`。
- 通知中心展示和通知点击跳转仍未执行。
- Windows 验收分支 unit tests 为 `297 passed`；10 条 iOS 用例已实际执行。

Week 19 的单设备基础足以开始 Week 20 的矩阵基础设施，但 Week 20 最终收口
必须继续携带上述缺口，不能通过切换计划默认将其视为完成。

## 完成范围 / Scope

### 1. iOS 设备矩阵配置

计划新增 `configs/ios-device-matrix.yaml`，至少包含：

```yaml
version: 1
devices:
  - id: simulator-current-primary
    provider: local
    role: primary-simulator
    runtime: current
    device_name_env: QA_IOS_SIM_DEVICE_CURRENT
    required: true
  - id: simulator-previous-compat
    provider: local
    role: compatibility-simulator
    runtime: previous-major
    device_name_env: QA_IOS_SIM_DEVICE_PREVIOUS
    required: false
  - id: cloud-iphone
    provider: browserstack
    role: real-device-cloud
    device_name_env: QA_IOS_CLOUD_DEVICE_NAME
    required: false
```

最终字段以实现时的校验规则为准，不在计划阶段虚构未实现能力。加载器必须
拒绝以下情况：

- 重复的逻辑设备 ID 或 UDID。
- worker 数量超过可用设备 profile 数量。
- 必选 profile 缺少 UDID、runtime、设备名或 provider 配置。
- 同一设备被两个 xdist worker 同时占用。
- WDA 端口或 DerivedData 目录重复。

### 2. Worker 与设备绑定

- 复用 Android 设备矩阵中已经验证的思路，但保持 iOS 模块和配置独立。
- `gw0`、`gw1` 映射到不同设备 profile，不在业务测试中散落索引判断。
- Session 级 fixture 记录 logical device、provider、UDID、runtime、WDA 端口
  和 DerivedData 路径。
- 每个测试仍负责恢复自身 App 状态，不把“设备不共享”误当成“App 状态隔离”。

### 3. WDA 端口分配

- 从矩阵配置或 worker 顺序生成唯一 `wdaLocalPort`。
- 创建 session 前检查端口是否被监听；冲突时给出 profile、端口和占用线索。
- Appium Server 端口与 WDA 本地端口是两个不同概念，文档和日志必须分开记录。
- 默认串行运行继续使用现有 `8100`，并行时不允许两个 worker 使用同一端口。

### 4. DerivedData 隔离

- 每个 worker 使用独立构建目录，例如：
  `artifacts/ios-derived/<run-id>/<device-id>/`。
- 目录必须位于项目工作区内，便于 CI 上传和清理。
- 不把删除 DerivedData 当作默认修复手段；先记录路径、构建时间和错误证据。
- 如果当前 XCUITest Driver 版本无法直接通过 capability 指定构建目录，则在
  runner/Appium 启动边界实现隔离，并用实际版本验证后再写文档。

### 5. 并行 Simulator 验收

- 在 macOS Runner 上发现并启动两个不同 Simulator profile。
- 当前主版本必须实际执行；前一主版本缺失时明确记录 `BLOCKED`，不得用同一
  runtime 的两个设备冒充“双版本兼容性通过”。
- 两个 xdist worker 并行创建、执行最小 fixture flow 并退出 session。
- 验证两个 session 的 UDID、WDA 端口和 DerivedData 路径互不重复。
- 测试结束后检查 `/sessions` 为空，并保留每个 worker 的日志和截图。

### 6. 云真机链路

- 保留 Week 19 已通过的 BrowserStack fixture 构建、上传和 session 路径。
- 云设备 capability 生成继续由 `qa_core.driver.ios` 负责。
- 至少执行一条 Week 20 云 smoke，验证矩阵重构没有破坏真实设备路径。
- 多台云真机并行取决于账号并发额度；额度不足时记录 `DEFERRED`，不能用
  Simulator 结果替代真实设备证据。

### 7. 日志与证据

每个 session 至少记录：

- logical device id、role、provider。
- 设备名、iOS 版本和 UDID 的脱敏策略。
- Appium endpoint、WDA 本地端口和 DerivedData 路径。
- Appium、Xcode/WDA 和 pytest worker 日志。
- 失败截图、page source 和 session 创建/退出时间。

Allure 结果名称必须包含 logical device id，避免多个 worker 的同名结果混淆。

## 不在本周范围 / Out of Scope

- Week 21 的 50 条 iOS 阶段验收和完整稳定性矩阵。
- 为追求版本数量下载不受控的大型 Simulator runtime。
- 自动修改 Apple 证书、Provisioning Profile 或设备信任设置。
- 生产设备云凭据写入仓库或日志。
- 用 Android 设备矩阵实现替代 iOS 平台隔离。
- 用单设备串行结果冒充并行、双版本或云真机矩阵通过。

## 术语解释 / Glossary

| 名词 / Term | 简单解释 / Plain Meaning | 作用 / Purpose | 在本项目中的位置 / Position |
| --- | --- | --- | --- |
| Device Matrix | 一张列出要跑哪些设备的配置表 | 把覆盖目标变成可重复输入 | `configs/ios-device-matrix.yaml` |
| Simulator Profile | 一个设备类型与 iOS runtime 的组合 | 区分主回归和兼容性环境 | macOS Runner + XCUITest |
| UDID | 每个 Simulator 或设备的唯一标识 | 防止 session 连错设备 | `appium:udid` |
| WDA | WebDriverAgent，XCUITest Driver 在 iOS 上启动的代理 | 接收元素和手势操作 | XCUITest Driver / iPhone / Simulator |
| WDA Local Port | Appium 与 WDA 在本机通信的端口 | 并行时避免端口冲突 | `appium:wdaLocalPort` |
| DerivedData | Xcode 保存 WDA 等构建中间产物的目录 | 隔离并行构建和诊断缓存 | Xcode/WDA 构建层 |
| xdist Worker | pytest-xdist 启动的并行执行进程 | 每个 worker 绑定一份设备资源 | `gw0`、`gw1` |
| Session | Appium 与一台设备建立的一次自动化连接 | 承载一次独立测试运行 | XCUITest session |
| Profile Binding | 给 worker 固定分配设备、端口和目录 | 防止并行任务互相抢占 | iOS device fixture / matrix loader |

## 通俗解读 / Plain-Language Guide

设备矩阵像排班表，xdist worker 像两名测试员；如果排班表只写“用手机”，
两个人可能同时拿同一台设备。Week 20 要给每个人分配独立工位、独立门禁卡
和独立工具箱，分别对应 UDID、WDA 端口和 DerivedData。

```mermaid
flowchart LR
    P["pytest-xdist"] --> W0["gw0"]
    P --> W1["gw1"]
    W0 --> M0["iOS profile A<br/>UDID A + port A + DerivedData A"]
    W1 --> M1["iOS profile B<br/>UDID B + port B + DerivedData B"]
    M0 --> S0["Appium session A"]
    M1 --> S1["Appium session B"]
    S0 --> E["每设备截图 / 日志 / Allure"]
    S1 --> E
```

**一句话理解：** 并行不是把同一个环境同时开两次，而是让每个执行者拿到一套
互不重叠的设备、端口和构建目录。

## 计划在整体路线中的位置 / Plan Position

```mermaid
flowchart LR
    W17["Week 17<br/>macOS / WDA 环境"] --> W18["Week 18<br/>iOS 框架"]
    W18 --> W19["Week 19<br/>系统交互<br/>PARTIAL PASS"]
    W19 --> W20["Week 20<br/>设备矩阵与并行"]
    W20 --> W21["Week 21<br/>50 条 iOS 阶段验收"]
    W20 -. "保留云真机" .-> CLOUD["BrowserStack / physical-device gate"]
    class W20 current
    classDef current fill:#2d7ff9,color:#fff,stroke:#1b4f9c,stroke-width:2px
```

Week 20 依赖 Week 18 的 capability、locator、等待和 Screen/Flow 骨架，也依赖
Week 19 已验证的单设备 fixture 与云真机链路。它为 Week 21 的测试规模、
稳定性分析和版本兼容性提供设备证据。

## 实施顺序 / Implementation Order

1. 定义并加载 iOS matrix，补齐配置校验和单元测试。
2. 建立 worker 到 profile 的确定性绑定。
3. 实现 WDA 端口分配和冲突检查。
4. 实现 DerivedData 路径隔离。
5. 让 XCUITest options 消费解析后的 profile，不直接读取散落环境变量。
6. 在 macOS Runner 上先串行验证两个 profile，再启用 `-n 2`。
7. 运行云真机 smoke，确认未破坏 Week 19 路径。
8. 汇总 artifacts、Allure、环境和 runbook，形成阶段结论。

## 质量检查 / Quality Checks

| 检查项 / Check | 结果 / Status | 执行环境 / Environment | 证据 / Evidence |
| --- | --- | --- | --- |
| Ruff | 通过 / PASS | Windows | `All checks passed!` |
| Mypy | 通过 / PASS | Windows | 165 source files |
| Matrix unit tests | 通过 / PASS | Windows | 15 matrix/selector tests |
| Full unit regression | 通过 / PASS | Windows | `309 passed in 8.53s` |
| Xcode/runtime compatibility | 通过 / PASS | macOS Runner | Xcode 16.4 + SDK/runtime 18.5 |
| WDA prewarm | 通过 / PASS | macOS Runner | 两个 profile 顺序构建 |
| Dual-profile parallel smoke | 通过 / PASS | macOS Runner | `2 passed in 120.44s` |
| Resource uniqueness/overlap | 通过 / PASS | macOS Runner | `98.28s` overlap |
| Cloud real-device regression | 通过 / PASS | BrowserStack | Run `41278734330`，`9 passed, 1 xfailed` |
| Previous-major Simulator | 未执行 / NOT RUN | macOS Runner | 当前 Run 只覆盖一个 runtime |
| Multi-device cloud matrix | 延期 / DEFERRED | BrowserStack | 本轮保留双 Simulator 基线 |

## 验收方式 / Acceptance Method

### 前置条件 / Preconditions

- 使用项目 `.venv` 和 Python 3.12。
- Windows 本机完成静态检查和单元测试。
- macOS Runner 安装 Xcode、Appium 2.19.0 和 XCUITest Driver 8.4.3。
- 至少两个可用 iOS Simulator profile；前一主版本缺失时如实记录。
- 云真机验收需要测试账号、最小权限凭据和可用 BrowserStack 额度。
- 所有 App、设备和账号均为测试资源，不读取生产凭据。

### Windows 静态验证 / Windows Static Verification

```powershell
$env:PYTEST_DEBUG_TEMPROOT="$PWD\.tmp-pytest"
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m mypy packages tests
.\.venv\Scripts\python.exe -m pytest tests\unit -q -p no:cacheprovider
.\.venv\Scripts\python.exe -m pytest tests\ios -q -p no:cacheprovider -rs
```

预期结果：

- Ruff 和 Mypy 通过。
- 矩阵、端口、路径和 capability 单元测试通过。
- 全量 unit tests 通过。
- Windows 上 iOS 运行测试可以显式跳过，但 skip 不增加 iOS 通过数量。

### macOS 双 Simulator 并行验收 / macOS Parallel Simulator Acceptance

```bash
xcrun simctl list devices available -j
.venv/bin/python -m pytest \
  tests/ios/test_week20_device_matrix.py \
  -q -n 2 --dist=each \
  --alluredir=artifacts/allure-results
.venv/bin/python scripts/verify_ios_parallel_resources.py \
  --run-dir artifacts/ios-week20/<run-id> \
  --expected-workers 2
```

如果实现时选择独立的 matrix smoke 文件，命令可聚焦该文件，但最终必须至少
证明两个不同 Simulator profile 并行完成 session 创建、最小交互和退出。

预期结果：

- 两个 worker 分别绑定不同 logical device id 和 UDID。
- 两个 worker 使用独立 Appium Server 端口。
- 两个 worker 的 WDA 本地端口不同且启动成功。
- 两个 worker 的 DerivedData 路径不同。
- 两个 session 在时间轴上有真实重叠。
- Allure 中能从设备元数据区分两个 worker。

### 云真机验收 / Cloud Real-Device Acceptance

```bash
.venv/bin/python -m pytest tests/ios/test_cloud_session.py -q \
  --alluredir=artifacts/week20-cloud-allure-results
```

预期结果：

- 至少一条真实 iPhone session 通过。
- 设备名、平台版本和 provider 出现在证据中。
- 凭据不出现在日志、Allure、page source 或报告正文。
- 多设备并发未获额度时保持 `DEFERRED`，不写成 `PASS`。

### 证据路径 / Evidence

- Matrix: `configs/ios-device-matrix.yaml`
- Matrix loader: `packages/qa_core/platforms/ios/devices.py`
- Matrix evidence: `artifacts/ios-week20/41317497880/`
- Appium logs: `artifacts/appium-ios-matrix-4723.log`、`4724.log`
- DerivedData: `artifacts/ios-derived/41317497880/<device-id>/`
- Allure: `artifacts/allure-results/`
- JUnit: `artifacts/week20-junit.xml`
- Final GitHub Run: `41317497880`
- Cloud regression Run: `41278734330`
- Architecture: `docs/architecture/ios-device-matrix.md`
- Runbook: `docs/runbooks/ios-parallel-wda-deriveddata-triage.md`

### 未验证项 / Unverified Items

- 前一主版本 Simulator 尚未实际执行；本轮只验证当前 SDK/runtime 18.5。
- BrowserStack 多真机并行尚未执行，只保留 Week 19 云单设备回归。
- 当前 XCUITest Driver 对 DerivedData capability 已由运行证据验证，但仍需
  多 runtime 场景确认。
- 本地 Apple 签名、Provisioning 和设备信任仍不属于云真机基线已证明内容。
- Week 19 的 10 条测试规模和 WebView context 缺口仍未闭合。

## 变更文件 / Files Changed

实现阶段：

- `configs/ios-device-matrix.yaml`
- `packages/qa_core/config/settings.py`
- `packages/qa_core/driver/ios.py`
- `packages/qa_core/platforms/ios/devices.py`
- `packages/qa_core/platforms/ios/__init__.py`
- `tests/unit/test_ios_device_matrix.py`
- `tests/ios/conftest.py`
- `tests/ios/test_week20_device_matrix.py`
- `tests/unit/test_select_ios_simulator_matrix.py`
- `.github/workflows/ios-week20-matrix.yml`
- `scripts/select_ios_simulator_matrix.py`
- `scripts/prewarm_ios_wda.py`
- `scripts/verify_ios_parallel_resources.py`
- `docs/architecture/ios-device-matrix.md`
- `docs/runbooks/ios-parallel-wda-deriveddata-triage.md`
- `reports/weekly/WEEK-20.md`

实际文件以最小实现和测试边界为准，不为匹配清单创建空模块。

## 环境 / Environment

- Windows + PowerShell 7
- Python 3.12，项目 `.venv`
- Appium 2.19.0
- XCUITest Driver 8.4.3
- macOS Runner: GitHub `macos-15`
- Xcode: 16.4 / iOS Simulator SDK 18.5
- Device cloud: BrowserStack App Automate
- 已通过的云设备: iPhone 15 / iOS 17（Week 19 regression）
- Parallel Simulators: iPhone 16 + iPhone 16 Plus / iOS 18.5
- Appium servers: 4723 / 4724
- WDA ports: 8100 / 8101
- 本地 iOS host: 未提供
- Self-hosted iOS device runner: 未使用

## 风险与限制 / Risks and Limitations

- Windows 不能本地构建 WDA、启动 iOS Simulator 或执行真机签名。
- macOS Runner 的 Xcode 与 runtime 组合会变化，前一主版本不保证预装。
- Xcode 16.4 默认可能看到更高版本 CoreSimulator runtime，必须按 SDK 版本过滤；
  否则会生成 SDK 与 deployment target 不匹配的 WDA 构建。
- 两个 Simulator 并行仍共享宿主机 CPU、内存和 Xcode 工具链；Appium、WDA
  端口和 DerivedData 已隔离，但不等于完整资源隔离。
- WDA 端口空闲检查与最终绑定之间存在时间窗口，仍可能被其他进程抢占。
- 云真机网络、排队和设备可用性会放大 session 创建时间，需要明确超时上限。
- DerivedData 隔离会增加磁盘占用，必须生成到项目 `artifacts/` 并有界清理。
- Week 19 未闭环的测试数量和 WebView 约束不能因 Week 20 开工而消失。

## 下一步 / Next Plan

下一阶段：

1. 增加前一主版本 Simulator 兼容性任务，使用独立 job 或独立 workflow。
2. 在不影响当前双 Simulator 基线的前提下，增加 Cloud 双设备矩阵。
3. 把 prewarm 和并行证据接入 Week 21 的稳定性测试。
4. 为 WDA 缓存失效、端口占用和 runtime 不匹配补充故障注入测试。

当前并行 Session 验收已经通过；Week 20 的剩余工作是多版本和多云设备覆盖，
不是重新证明当前两个 Simulator 能否并行。
