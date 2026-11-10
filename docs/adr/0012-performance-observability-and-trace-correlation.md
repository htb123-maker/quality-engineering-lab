# ADR-0012: 性能指标、Trace 与监控栈边界 / Performance Metrics, Trace, and Monitoring Boundaries

- 状态 / Status: Accepted for Week 27 implementation
- 日期 / Date: 2026-11-10
- 阶段 / Phase: Week 27

## Context

Week 26 用 Docker CLI 保存了 API、PostgreSQL 和 Redis 的资源样本，并完成了
Baseline/Load 对照。这个方案足以证明短时间窗口的趋势，但不能提供连续时间序列、
跨数据源查询、Trace 或稳定 Dashboard。

直接把所有请求路径、workspace slug、item id 和 run id 写成指标 label 会产生高
基数；把 Grafana 截图当成事实来源也会让阈值和结论无法复查。

## Decision

1. SUT 暴露 Prometheus text format `/metrics`。
2. HTTP Counter 只使用 `method`、归一化 `route` 和 `status`。
3. Histogram 只使用 `method` 和归一化 `route`。
4. 请求返回 `X-Request-Id` 和 `X-Trace-Id`，并入站接受 W3C Trace Context。
5. OpenTelemetry OTLP HTTP 导出到 Tempo，但只在 `monitoring` profile 开启。
6. Prometheus 抓取 SUT、PostgreSQL exporter、Redis exporter 和 cAdvisor。
7. Grafana 由文件 provisioning 数据源和 Dashboard，不依赖手工点击配置。
8. 监控栈使用独立 Compose profile，不改变 Week 25/26 默认启动行为。
9. 真实验收必须包含 API metrics、Prometheus targets、Grafana health、Tempo
   readiness 和按精确 Trace ID 查询。

## Consequences

优点：

- Week 26 的 Locust、资源数据和 Week 27 时间序列使用同一时间窗口。
- 指标标签可控，不会因业务数据数量膨胀。
- Dashboard 和 datasource 可以版本化、重建和审查。
- Trace 缺失时不会把业务响应失败误报为监控通过。

代价：

- 新增 Prometheus、Grafana、Tempo、exporter 和 OTLP 依赖。
- 首次启动需要下载多个镜像，网络不可用会阻塞真实验收。
- 当前只对 SUT HTTP 请求做 Trace，数据库和 Redis 客户端仍是后续工作。
- Grafana 匿名管理员只适用于本机隔离测试，不能复制到共享或生产环境。

## Rejected Alternatives

- 继续只用 Docker CLI：没有连续时间序列和跨源查询。
- 直接抓取宿主机总数：无法区分 API、数据库和 Redis。
- 给每个真实路径打标签：高基数和存储膨胀。
- 用日志文本代替 Trace：可以做关联，但不能替代结构化 span。
- 用 Grafana up 作为唯一通过条件：Dashboard 存在不代表指标已抓到。
