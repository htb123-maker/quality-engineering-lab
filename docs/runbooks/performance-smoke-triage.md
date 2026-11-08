# 性能 Smoke 失败排查 / Performance Smoke Triage

## 1. 先看失败发生在哪一层

```text
SUT 不可用
-> Locust 负载形状错误
-> 请求功能失败
-> SLO 阈值失败
-> 压测机或容器资源不足
```

不要先调高阈值。先确认是哪一层产生了证据。

## 2. 环境检查

```powershell
docker compose `
  -p quality-engineering-lab-performance `
  --env-file .env.performance.example `
  -f apps/compose/compose.yaml ps

.\.venv\Scripts\python.exe scripts\check_sut.py `
  --api-base-url http://127.0.0.1:28000 `
  --postgres-dsn postgresql://qa:qa@127.0.0.1:25432/qa `
  --redis-url redis://127.0.0.1:36379/0
```

如果 readiness 失败，不要执行下一次负载。

## 3. Locust 启动失败

常见原因：

- `.venv` 中没有 Locust：重新执行 `uv sync`。
- `PYTHONPATH` 未包含 `packages`：使用 `scripts/run_performance_smoke.ps1`。
- profile YAML 不合法：先运行 `tests/unit/test_performance_profile.py`。
- profile 地址和独立环境端口不一致：确认 `base_url` 是 `28000`。

## 4. 请求失败

| 现象 / Symptom | 首先检查 / First Check |
| --- | --- |
| 连接拒绝 | Compose API 容器和 `28000` 端口 |
| 404 catalog | 工作区 slug、种子数据初始化 |
| 500 / 503 | API 日志、PostgreSQL 和 Redis readiness |
| 大量超时 | 容器资源、Locust 主机负载、网络代理 |
| 错误率很高但延迟很低 | 响应错误分类，不要只看耗时 |

## 5. SLO 失败

查看：

- `artifacts/performance/week25/smoke_stats.csv`
- `artifacts/performance/week25/smoke_stats_history.csv`
- `artifacts/performance/week25/smoke.html`
- Locust 标准输出中的 `SLO PASS/FAIL` 行

先确认样本量。少于 profile 要求时是证据不足，不是性能通过。若错误率和样本量
正常、仅 p95 超限，再检查 SUT 日志、容器 CPU、数据库连接和宿主机资源。

## 6. 清理

```powershell
.\scripts\stop_performance_sut.ps1
```

需要同时删除独立性能数据卷时：

```powershell
.\scripts\stop_performance_sut.ps1 -RemoveVolumes
```

删除卷前确认项目名是 `quality-engineering-lab-performance`，不要对日常环境
误用该命令。

## 7. Week 26 Baseline/Load 运行

### 准备数据池

```powershell
.\scripts\prepare_performance_data.ps1 `
  -RunId week26-local `
  -WorkspaceSlug qa-perf-week26-local `
  -ItemCount 100 `
  -AccountCount 16
```

重复执行应保持 `workspaces=1, users=16, items=100`。如果计数增加，先停止运行，
不要继续采集性能数据。

双 run 隔离与选择性清理：

```powershell
.\scripts\verify_performance_data_pool_isolation.ps1 `
  -RunPrefix week26-isolation
```

通过标准是清理 run A 后 run B 保持原计数，随后清理 run B 全部归零，两个
`runtime.json` 都被删除。

### 执行 profile

```powershell
.\scripts\run_performance_profile.ps1 `
  -Profile configs\performance-baseline.yaml `
  -Label baseline `
  -OutputDir artifacts\performance\week26\week26-local `
  -DataFile artifacts\performance\week26\data\week26-local\runtime.json `
  -WarmupSeconds 15 `
  -MeasuredRuns 3
```

Load 使用同一命令，只替换 profile 和 label。每次运行保存 Locust CSV、HTML、
`result.json`、`manifest.json` 和 `resources.csv`。

### 单主机分布式拓扑

```powershell
.\scripts\run_distributed_locust.ps1 `
  -DataFile artifacts\performance\week26\data\week26-local\runtime.json `
  -OutputDir artifacts\performance\week26\week26-local\distributed-local `
  -RunId week26-distributed-local `
  -Role local `
  -ExpectedWorkers 1
```

worker 只负责生成负载，最后由 master 读取聚合统计并执行 SLO gate。不要根据
worker 的空统计设置退出码。

### 比较

```powershell
.\scripts\compare_performance_runs.ps1 `
  -BaselineDir artifacts\performance\week26\week26-local\baseline `
  -LoadDir artifacts\performance\week26\week26-local\load `
  -OutputDir artifacts\performance\week26\week26-local
```

结果写入 `comparison.json` 和 `report.html`。先看错误率和样本量，再看延迟；
单次负载升高不能直接证明容量或产品回归。

### 清理

```powershell
.\scripts\cleanup_performance_data.ps1 `
  -RunId week26-local `
  -WorkspaceSlug qa-perf-week26-local
.\scripts\stop_performance_sut.ps1
```

清理应同时满足：

- PostgreSQL `workspaces/users/items` 全部为 0。
- Redis cache key 已删除。
- `runtime.json` 已删除。
- `docker compose ps` 不再显示 performance 服务。

### 常见新问题

| 现象 | 检查 |
| --- | --- |
| Docker 输出 `1e+03kB` 之类科学计数法 | 资源解析器必须支持指数形式 |
| worker 返回 1 但 master 为 0 | worker 不应执行最终 SLO gate |
| profile 与 runtime workspace 不一致 | 检查 `-WorkspaceSlug` 和 YAML `workspace` |
| `resources.csv` 只有表头 | 检查 Docker daemon、container ID 和 `docker stats` |
| 运行后数据池计数增加 | 停止测试，检查 provisioning 的幂等键 |
