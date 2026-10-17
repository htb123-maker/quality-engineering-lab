# ADR-0010: 并行连接预算、故障注入与缺陷草稿 / Parallel Budgets, Fault Injection, and Defect Drafts

- 状态 / Status: Accepted
- 日期 / Date: 2026-10-17
- 决策者 / Deciders: Quality Engineering Lab
- 相关 / Related: ADR-0002（HTTP 超时与重试）、ADR-0006（测试命名空间隔离）、
  ADR-0009（限流与失败分类）

## 背景 / Context

Week 8 到 Week 11 已经证明测试数据可以按 worker 隔离、缓存故障可以降级、
权限失败可以分类。Week 12 还需要回答三个运行期问题：

1. `pytest -n 4` 和 API 的多线程请求叠加后，PostgreSQL 连接有没有硬上限？
2. 超时、断连、限速这类网络故障是否能真实注入，而不是只在 Mock 中模拟？
3. 测试失败后，能不能生成足够的复现证据，同时保证不会自动创建或关闭正式缺陷？

English: parallel execution needs a hard database connection budget, real
transport faults, and a defect-draft boundary that keeps human approval explicit.

## 决策 / Decision

### 1. PostgreSQL 连接预算放在 SUT 内

`apps/compose/api/app.py` 中所有数据库访问统一经过 `_postgres_connection()`。
它先获得 `ConnectionBudget` 的槽位，再建立连接；容量由
`QA_POSTGRES_MAX_CONNECTIONS` 控制，等待上限由
`QA_POSTGRES_CONNECTION_TIMEOUT_SECONDS` 控制。

- 容量默认 16，低于本地 PostgreSQL 的连接上限，也给 psql、测试夹具和后台任务留余量。
- 等待超时会抛出 `ConnectionBudgetExhausted`，现有 handler 把它归入
  `503 database_unavailable`，而不是让请求无限堆积。
- `ConnectionBudget` 记录 `capacity`、`active`、`peak`，便于单测和后续监控证明
  并发期间没有越过上限。
- 并发写用例在同一个命名空间内同时发 8 个请求，断言 SKU 唯一且全部写入成功。

### 2. Toxiproxy 是可选故障注入平面

Compose 增加 `fault-injection` profile 中的 Toxiproxy 服务。它不改变正常 SUT
启动路径，也不把 PostgreSQL 或 Redis 默认串进代理；测试通过控制 API 临时创建
API 代理，在代理上注入 latency、timeout 或 reset-peer。

- 控制 API：`127.0.0.1:18474`。
- 每个 xdist worker 使用 `18100 + worker_index` 的独立代理端口，避免并行测试
  争用同一个监听端口。
- 代理在测试结束后删除；故障不能泄漏到下一轮。
- `tests/api/test_fault_injection.py` 验证关闭代理后的快速连接失败，以及恢复后
  的健康检查；latency 用例验证客户端重试次数有上限且每次 transport error 可观测。
- 未启动 Toxiproxy 时，故障用例明确 skip，不把 skip 写成 pass。

### 3. 失败只生成草稿，正式缺陷必须人工批准

pytest 插件 `qa_core.plugins.defect_drafts` 在 call phase 失败时生成
`DefectDraft`，写入 `artifacts/defect-drafts/defects.jsonl`。

- 指纹沿用 `DefectFingerprint` 的八字段规范化与 SHA-256。
- 草稿固定带 `requires_human_approval=true` 和
  `automatically_created_issue=false`。
- 证据包含 pytest node id、commit、环境、复现命令、Allure 结果路径、
  CI Run（可用时）和第一段失败文本。
- JSONL 追加使用 Windows `msvcrt` 或 POSIX `fcntl` 文件锁，保证多个 xdist
  进程同时失败时一行仍是一个完整 JSON 对象。
- 状态迁移集中在 `qa_core.integrations.defect_tracking.lifecycle`。每一次迁移都
  要求 `approved_by`，不存在自动进入 `closed` 的路径。

## 结果 / Consequences

正向结果：

- 连接数不再只靠 PostgreSQL 自己“兜底”，SUT 在入口处就有明确预算和超时。
- 故障注入有真实 TCP 层证据，同时仍可用 `httpx.MockTransport` 做确定性的单元测试。
- 失败证据自动落盘，但不会自动创建正式 Issue，也不会自动关闭缺陷。
- 并发写、xdist 隔离和缺陷草稿存储都有针对共享状态的测试。

代价与限制：

- Toxiproxy 是额外容器和镜像；本地拉取失败时故障用例只能 skip。
- 当前只代理测试到 SUT 的 HTTP 入口，没有把 SUT 到 PostgreSQL/Redis 的依赖默认
  串进代理。数据库超时和 Redis 故障的真实注入仍需后续扩展代理拓扑。
- 连接预算使用进程内信号量。单副本 SUT 的硬上限成立；多副本部署时每个副本各有
  一份预算，必须用 PostgreSQL 侧连接池或统一网关重新核算总量。
- pytest 草稿只覆盖 call phase 失败；setup/teardown 失败需要后续扩展证据字段。
- JSONL 草稿是本地交换格式，不是 Issue Tracker。正式流程仍需适配 GitHub Issues、
  GitLab Issues 或其他平台。

## 备选方案 / Alternatives

| 方案 / Option | 未采用原因 / Why not |
| --- | --- |
| 只依赖 PostgreSQL `max_connections` | 超限时错误更晚、更难归因，也缺少 API 侧预算证据 |
| 每个请求无限新建连接 | 并行下会话数和文件描述符会失控 |
| 在进程内维护长连接池 | 当前 SUT 是教学用轻量 ThreadingHTTPServer，先把上限和可观测性做对 |
| 直接把所有数据库/Redis 流量默认接入 Toxiproxy | 会让正常启动依赖额外服务；先做按需 profile |
| 失败后自动创建 GitHub Issue | 与项目审批边界冲突，且容易制造重复缺陷 |
| 只保存 pytest 终端日志 | 缺少稳定指纹、结构化证据和去重入口 |

## 验证证据 / Verification

- `apps/compose/api/app.py`、`apps/compose/compose.yaml`、`.env.example`
- `packages/qa_core/resilience/toxiproxy.py`
- `packages/qa_core/reporting/defect_draft.py`
- `packages/qa_core/integrations/defect_tracking/lifecycle.py`
- `packages/qa_core/plugins/defect_drafts.py`
- `tests/unit/test_connection_budget.py`、`test_toxiproxy_client.py`、
  `test_defect_draft.py`
- `tests/api/test_fault_injection.py`、`test_parallel_isolation.py`
- `docs/runbooks/fault-injection-and-defect-drafts.md`
- `reports/weekly/WEEK-12.md`

## 重新评估条件 / Revisit Triggers

- SUT 改为多副本部署：连接预算必须改为共享池或由数据库/网关统一限制。
- Toxiproxy 故障测试变为每次 PR 必跑：需要固定镜像版本、启动健康检查和清理脚本。
- 引入正式 Issue Adapter：必须保留草稿到人工批准之间的状态边界，并记录审批人和
  Run/TestCase 关联。
- 失败证据需要包含截图、page source 或 SQL 结果：扩展 `DefectEvidence`，同时做
  Secret 与个人信息过滤。
