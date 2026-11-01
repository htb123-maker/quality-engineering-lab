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
