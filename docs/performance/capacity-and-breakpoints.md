# Stress、Spike、容量与拐点 / Stress, Spike, Capacity, and Breakpoints

## 1. 计划边界

Week 28 使用已经可查询的 Prometheus/Grafana/Tempo 观测链，寻找当前单机性能
环境中的退化拐点。它不承诺生产 SLA，也不把一次过载结果写成最终容量。

```text
Baseline / Load 已验证
-> Stress 阶梯增加负载
-> Spike 短时突增并恢复
-> 对齐请求、资源和 Trace
-> 识别拐点候选
-> 给出下一轮实验，而不是最终因果
```

## 2. Stress 与 Spike

| 档位 | 形状 | 主要问题 |
| --- | --- | --- |
| Stress | 4 / 8 / 12 / 16 / 24 users，每阶段 20 秒 | 吞吐何时不再增长，延迟和错误是否快速恶化 |
| Spike | 4 users -> 32 users 10 秒 -> 4 users | 突增时错误与 p95/p99 如何变化，恢复是否及时 |

两者都复用认证读取旅程和独立 workspace。账号、token 和 catalog 数据必须来自
test-only 数据池；不能压公共环境或固定种子数据。

## 3. 拐点判断

单个指标升高不足以证明瓶颈。至少组合以下证据：

| 证据 | 观察 |
| --- | --- |
| 吞吐 | 用户数继续增加但 RPS 不再增长 |
| p95 / p99 | 延迟随负载非线性上升 |
| 错误率 | 超时、5xx、连接失败或限流开始增长 |
| API CPU | 是否接近容器或主机瓶颈 |
| PostgreSQL | 活动连接、事务、锁等待和 CPU |
| Redis | 客户端、内存、命令处理和 CPU |
| cAdvisor | API/数据库/缓存的内存和容器资源 |
| Tempo | 典型慢请求的耗时和调用上下文 |

结论只能写成“候选瓶颈层”，除非有可重复实验和代码/配置证据支持因果。

## 4. Little's Law 校核

稳定系统中的平均关系为：

```text
concurrency = arrival_rate x response_time
```

例如 20 requests/s、平均停留 0.1 秒，平均并发约为 2。若观察到的并发、
吞吐和延迟明显不满足该关系，应先检查测量窗口、压测机瓶颈、Coordinated
Omission 或统计口径，而不是直接归因应用。

## 5. 通过标准

Week 28 完成至少需要：

1. Stress 和 Spike 各自真实执行，保留 Locust CSV/HTML 和结果 JSON。
2. Prometheus 中的 run ID、请求延迟、吞吐、错误和资源时间线可查询。
3. 各阶段的结果能按时间窗口对齐，而不是只看总中位数。
4. 保留失败、过载和恢复证据，不用重跑覆盖失败。
5. 输出容量和拐点报告，明确适用环境与不能外推的范围。

配置文件存在、单元测试通过或 collect-only 都不能替代真实执行。

## 6. Week 28 实测结论

2026-11-14 在单机 Windows + Docker Desktop 性能环境中完成：

| 结果 | Stress | Spike |
| --- | ---: | ---: |
| Requests | 3584 | 1553 |
| Overall p95 | 22 ms | 25 ms |
| Overall p99 | 37 ms | 180 ms |
| Error rate | 0% | 0% |
| SLO | PASS | PASS |

Stress 在 24 个持续用户时约为 47.43 Prometheus req/s、p95 19.07 ms，
API CPU 28.86%、PostgreSQL CPU 8.26%、Redis CPU 2.73%。16 -> 24 users
时 RPS 仍增长 35%，没有出现吞吐停止，因此测试范围内
`breakpoint_observed = false`。

Spike 的 32 用户阶段 Locust p95 中位数为 109.5 ms、单时间片峰值 180 ms，
整体错误率为 0%；下一阶段 p95 为 26.55 ms。Recovery 阶段的 RPS 包含积压
排空，并不代表新的稳态容量。

Little's Law 在最高 Stress 档位给出约 `47.43 x 0.00649 = 0.308` 个请求
并发，观测 Gauge 均值 0.818。由于请求延迟只有约 5-10 ms，而 Prometheus
scrape 为 5 秒，只能确认两者都在“单请求以下并发”量级，不能声称精确等式
通过。该结论说明 Locust 用户大部分时间在 think time，而非服务端排队。
