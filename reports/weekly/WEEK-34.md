# WEEK-34 - Agent 监控运行时加固 / Agent Monitoring Runtime Hardening

- 计划 / Plan: Week34，真实 artifact Agent Monitor、required evidence、人工审查门禁
- 日期范围 / Date Range: 2026-11-23
- 分支 / Branch: `study/week-34-agent-monitoring-hardening`
- 基线提交 / Base Commit: `a779cd1`
- 计划提交 / Plan Commit: `c35771a`
- 证据保留提交 / Evidence Commit: `4f4f6b2`
- Pull Request: Not opened

## 计划目标 / Plan Goal

按 `docs/PLAN.md` 第 19 节的优先级，把 Agent 层从静态 Golden Task 规则基线
推进到真实 CI artifact 驱动：

```text
collected JUnit / JSON
-> artifact monitor
-> ci-monitor + performance-monitor findings
-> required evidence validation
-> quality trend
```

本轮只让 CI 和 Performance 成为阻塞运行时 Agent。Flaky、iOS 环境和每周维护
仍保持后续接入，不伪装成已完成。

## 完成状态 / Completion Status

本地实现、Agent runtime 和主要平台验证为 **通过 / PASS**。

仓库级最终状态为 **部分通过 / PARTIAL**：

- Run `45202168815` 在 `c35771a` 上全部必需 job PASS，Agent Monitor 与
  required evidence 已验证。
- 后续证据保留提交 `4f4f6b2` 的 Run `45205912718` 中，Agent、SUT、Android、
  Performance 和 AI Eval 均 PASS；iOS Simulator 在 macOS Runner 上冷启动超时，
  fail-closed Trend 正确失败。只重跑失败 job 时同一 iOS 步骤再次长时间卡住，
  因此取消并保留 `PARTIAL`。

## 按优先级完成 / Priority Order

| 优先级 | 项目 | 状态 | 结果 |
| --- | --- | --- | --- |
| P1-A | Performance `slo_passed` 归一化 | PASS | Trend 可识别真实 Performance result |
| P1-B | Required evidence profile | PASS | 缺失证据显式变成 `NOT RUN` |
| P1-C | 真实 artifact Agent Monitor | PASS | 生成 `agent-monitor.json` |
| P2-A | Eval 门禁、review hash、有效期 | PASS | 过期或任务集不匹配会失败 |
| P2-B | CI + Performance 运行时 Agent | PASS | `ci-monitor` 与 `performance-monitor` 已接 workflow |
| P3 | BrowserStack 403 降噪 | PASS | 403 写 `BLOCKED` artifact |
| P4 | 文档与 CI | PARTIAL | Agent 链路 CI PASS；最终 commit 被 iOS Runner 超时阻塞 |

## 质量检查 / Quality Checks

| 检查项 / Check | 结果 / Status | 证据 |
| --- | --- | --- |
| Ruff | PASS | `All checks passed!` |
| Mypy | PASS | `241 source files` |
| Unit tests | PASS | `409 passed` |
| Agent-focused tests | PASS | `21 passed` |
| Full API tests | PASS | `254 passed` |
| Integration tests | PASS | `46 passed` |
| AI Eval strict review | PASS | `accuracy=1.0`、`evidence=1.0`、`false_pass=0` |
| Workflow YAML parse | PASS | Quality Pipeline + iOS cloud workflow |
| Real artifact monitor | PASS | 真实 artifacts 缺失 iOS 时正确返回 `INSUFFICIENT_EVIDENCE` |
| Trend replay | PASS | Performance 出现；缺失 iOS 与 collected evidence 为 `NOT RUN` |
| Agent runtime CI | PASS | Run `45202168815`；`agent-monitor status=PASS missing=0` |
| Final commit CI | PARTIAL | Run `45205912718`；iOS Simulator 超时，其余 job PASS |

## 术语解释 / Glossary

| 名词 / Term | 简单解释 | 在本项目中的作用 |
| --- | --- | --- |
| Required evidence | 一个 required job 必须提供的机器可读证据 | 防止 job 绿但报告没上传 |
| Artifact Monitor | 把 JUnit/JSON 转成 Agent signal 的只读适配器 | 让 Agent 读取真实 CI 事实 |
| Runtime Agent | 在每次 CI 收集 artifacts 后执行的监控逻辑 | 本轮接入 CI 与 Performance |
| Task set hash | Golden Task 文件内容的 SHA-256 | 阻止旧人工审查套到新任务集 |

## 证据路径 / Evidence

- Plan：`docs/PLAN.md` 第 19 节
- Artifact Monitor：`ai/agents/artifact_monitor.py`
- Quality Trend：`packages/qa_core/reporting/quality_trends.py`
- Agent Eval：`ai/evals/run_golden_tasks.py`
- Human review：`ai/evals/week32-human-review.json`
- Workflow：`.github/workflows/week31-quality-pipeline.yml`
- Cloud boundary：`.github/workflows/ios-fixture-cloud.yml`
- Local JUnit：`artifacts/week34-agent/unit-junit-final.xml`
- Local AI Eval：`artifacts/week34-agent/agent-eval.json`
- Real replay：`artifacts/week34-agent/real-monitor.json`

## 未验证项 / Unverified Items

- 最终证据保留 commit 的 iOS Simulator：`FAILED`，实际为 macOS Runner 冷启动
  超时；同 commit 其他 job 为 PASS。
- `flaky-monitor`：仍为声明式注册，尚未接 Allure/history。
- `ios-environment-monitor`：尚未接 preflight 与 Runner 日志。
- `weekly-maintenance`：仍为 manual/weekly 后续能力。
- BrowserStack 403 的真实 blocked run：本地只验证 workflow 契约，需外部 provider
  返回 403 才能形成真实 `BLOCKED` artifact。

## 风险与限制 / Risks and Limitations

- Trend 的 required check 名称依赖 CI artifact 合并后的稳定命名；本轮为
  `quality-junit`、`sut-junit`、`api-junit`、`android-junit`、
  `android-business-junit`、`ios-simulator-junit`、`performance/result`、
  `agent-eval` 和 `agent-monitor`。
- Performance artifact 可能包含 warmup 与 measured result；Trend 按名称去重，
  保留排序后的第一条 Performance result。
- Agent Monitor 仍是确定性规则，不调用 LLM，也不修改仓库、阈值或缺陷。
- 真实 CI artifact 的体积较大；本地只下载了必要的轻量证据，没有下载完整 iOS
  DerivedData。

## 下一步 / Next Plan

1. 优化 iOS Simulator job 的构建缓存与 WDA 预热，解决 Runner 冷启动超时。
2. 在稳定 Runner 或 self-hosted Mac 上重跑最终证据 commit。
3. 最终 commit CI 全绿后，再把 Week34 从 `PARTIAL` 提升为 `PASS`。
4. 下一阶段再接 `flaky-monitor` 与 `ios-environment-monitor`。
