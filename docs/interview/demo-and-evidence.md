# 演示脚本与证据索引 / Demo and Evidence Guide

## 15 分钟演示顺序

| 时间 | 展示内容 | 要证明的能力 |
| --- | --- | --- |
| 0-2 min | `docs/architecture/project-overview.md` | Monorepo、共享核心、执行面边界 |
| 2-5 min | OpenAPI、Pydantic、HTTP client、API 测试 | 契约、认证、错误、数据库状态 |
| 5-7 min | Android/iOS adapter、Simulator、设备日志 | 跨平台业务复用和平台隔离 |
| 7-9 min | Locust、Prometheus、Grafana、SLO 结果 | 性能模型、拐点、可观测性 |
| 9-11 min | 统一 GitHub Actions run 和 artifact | 一个 commit 触发完整质量链路 |
| 11-13 min | Golden Tasks、误判回归、Agent registry | Agent 证据和权限边界 |
| 13-15 min | Issue #16、回归和人工关闭边界 | 缺陷创建、修复、验证、关闭 |

## 现场命令

### 质量与 Agent

```powershell
uv run pytest tests/unit -q
uv run ruff check .
uv run mypy packages tests performance ai
uv run python -m ai.evals.run_golden_tasks
```

### 本地 SUT

```powershell
docker compose -f apps/compose/compose.yaml up `
  --detach --wait --wait-timeout 120 --build
uv run python scripts/check_sut.py --wait-seconds 120
uv run pytest tests/api/test_negative_inputs.py::test_unsupported_method_returns_the_json_error_contract -q
docker compose -f apps/compose/compose.yaml down --volumes --remove-orphans
```

### 完整 CI

```powershell
gh workflow run week31-quality-pipeline.yml `
  --ref study/week-32-comprehensive-acceptance
```

## 演示时先说什么

“这个项目的核心不是‘有多少条测试’，而是同一份业务意图能在 API、数据库、两个
移动平台和负载模型里复用，同时每个真实环境保留独立证据。”

## 证据索引

| 主题 | 源码 / 测试 | 执行证据 | 说明 |
| --- | --- | --- | --- |
| API 契约 | `packages/qa_core/contracts/` | Quality/SUT run | OpenAPI + Pydantic |
| 认证 | `packages/qa_core/clients/` | integration unit | 并发刷新和轮换 |
| 数据隔离 | `packages/qa_core/concurrency/` | API/integration | namespace、资源池 |
| Android | `tests/android/` | `week31-android` | Linux API 35 emulator |
| iOS | `tests/ios/` | `week31-ios-simulator` | macOS 15 Simulator |
| 云设备 | `tests/ios/test_cloud_session.py` | `week31-ios-cloud-optional` | 可选；当前 quota `BLOCKED` |
| 性能 | `performance/`、`configs/` | `week31-performance` | 隔离 SUT + smoke |
| 趋势 | `packages/qa_core/reporting/` | `week31-trends` | JUnit/JSON + bounded cache |
| Agent Eval | `ai/golden_tasks/`、`ai/evals/` | `week32-ai-eval` | 30 个 Golden Tasks |
| 权限 | `ai/agents/registry.yaml` | Quality/unit | 5 个只读 Agent |
| 缺陷 | Issue #16、`apps/compose/api/app.py` | SUT 目标测试 + CI | JSON 405 回归 |

## GitHub 证据

- Week31 最终统一 pipeline：
  `https://github.com/htb123-maker/quality-engineering-lab/actions/runs/44563937821`
- Week32 最终 run：以 `reports/weekly/WEEK-32.md` 记录的 Run ID 为准。
- Issue #16：
  `https://github.com/htb123-maker/quality-engineering-lab/issues/16`

## 现场追问的回答边界

- 如果问“iOS 真机是否全部通过”，回答：必需 Simulator 已通过，BrowserStack
  是可选且当前被额度阻断；不能宣称所有 iOS 真机矩阵通过。
- 如果问“Agent 是不是准确率 100%”，回答：这是 30 个确定性 Golden Tasks 的
  基线准确率，不是未知任务或 LLM 泛化准确率。
- 如果问“性能有没有生产容量结论”，回答：有隔离测试环境的容量/拐点候选，不做
  生产压测，也不把测试环境数字直接外推生产。
- 如果问“缺陷为什么还没自动关闭”，回答：关闭必须人工审核修复、回归、影响和
  关联 Run；这是项目的安全契约，不是流程遗漏。

## 证据包最小清单

```text
reports/weekly/WEEK-32.md
.github/workflows/week31-quality-pipeline.yml
ai/golden_tasks/week32.jsonl
artifacts/ai/week32/agent-eval.json
docs/adr/0014-comprehensive-acceptance-evidence-and-agent-guardrails.md
Week32 GitHub Actions run
Issue #16 regression evidence
```
