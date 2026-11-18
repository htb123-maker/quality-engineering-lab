# 监控栈失败排查 / Monitoring Stack Triage

## 1. 适用范围

用于 Week 27 的 Prometheus、Grafana、Tempo、PostgreSQL/Redis exporter 和
cAdvisor。只针对本地隔离测试环境，不用于生产监控变更。

## 2. 启动

```powershell
.\scripts\start_performance_sut.ps1 -WaitSeconds 240 -Monitoring
.\scripts\verify_observability.ps1 -WaitSeconds 90
```

预期结果：

```text
PASS API trace headers
PASS API Prometheus metrics
PASS Prometheus scrape targets
PASS Grafana health
PASS Grafana dashboard provisioning
PASS Tempo readiness
PASS Tempo trace retrieval
Observability ready: True
```

证据写入 `artifacts/performance/week27/observability.json`，该目录被 Git 忽略。

## 3. 快速定位

```powershell
docker compose -p quality-engineering-lab-performance `
  --env-file .env.performance.example `
  -f apps\compose\compose.yaml `
  --profile monitoring ps

docker compose -p quality-engineering-lab-performance `
  --env-file .env.performance.example `
  -f apps\compose\compose.yaml `
  --profile monitoring logs --tail 100 prometheus grafana tempo api
```

### 镜像拉取超时

症状：

```text
Get "https://registry-1.docker.io/v2/": context deadline exceeded
```

处理：

1. 先确认 Docker engine 正常：`docker info`。
2. 记录失败镜像、时间和完整错误，状态保持 `BLOCKED`。
3. 不要用配置解析成功替代真实启动。
4. 网络恢复后重新执行同一启动命令，不能改写历史失败记录。
5. 使用镜像缓存或镜像站时必须确认来源可信，不得随意使用未知镜像。

### Prometheus target 为 down

- `sut-api`：先访问 API `/health/live` 和 `/metrics`。
- `postgres`：检查 `postgres-exporter` 的 `DATA_SOURCE_NAME`。
- `redis`：检查 `REDIS_ADDR` 和 Redis 健康状态。
- `cadvisor`：确认 Docker Desktop Linux engine 和挂载权限。

### Grafana 没有 Dashboard

检查 provisioning 挂载：

```text
infra/monitoring/grafana/provisioning
infra/monitoring/grafana/dashboards
```

再访问 `/api/search?query=Week%2027`，必须包含 `week27-sut-overview`。

### 有 Trace ID 但 Tempo 查不到

- 确认 `QA_OTEL_ENABLED=1`。
- 确认 API 能访问 `http://tempo:4318/v1/traces`。
- 等待 BatchSpanProcessor flush 至少一个导出周期。
- 使用 API 响应中的精确 `X-Trace-Id` 查询，不凭时间窗口猜。
- Tempo 不可用时，API 仍应返回业务响应，但 Trace 验收为 `FAILED` 或
  `BLOCKED`，不能报 `PASS`。

## 4. 指标基数检查

```powershell
$metrics = Invoke-WebRequest 'http://127.0.0.1:28000/metrics'
$metrics.Content -split "`n" |
  Select-String 'qa_sut_http_requests_total'
```

`route` label 必须使用 `{slug}`、`{item_id}`、`{job_id}` 模板。出现完整
workspace slug、item id 或任意用户输入时，应停止运行并修复。

## 5. 清理

```powershell
.\scripts\stop_performance_sut.ps1
```

需要删除性能监控卷时：

```powershell
.\scripts\stop_performance_sut.ps1 -RemoveVolumes
```

删除卷前确认 Compose project 是 `quality-engineering-lab-performance`。
