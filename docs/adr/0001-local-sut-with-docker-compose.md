# ADR-0001: 本地 SUT 使用 Docker Compose / Local SUT with Docker Compose

- 状态 / Status: Accepted
- 日期 / Date: 2026-10-01
- 决策者 / Deciders: Quality Engineering Lab
- 替代 / Supersedes: None

## 背景 / Context

Day 5 需要一套 API、PostgreSQL 和 Redis 都可重复启动的本地被测系统。
当前开发机是 Windows，已有 Redis 占用 `6379`，Docker Desktop 的宿主代理
也曾在访问镜像仓库时失败。如果依赖人工安装服务或使用随机的临时端口，后续
API、数据库、缓存和移动端 E2E 测试会缺少稳定边界。

本项目还要求本地凭据不能进入生产环境、数据库初始化可以重复执行，并且
失败时能查看每个服务的日志。

English: the project needs a reproducible local system under test across
Windows and Ubuntu CI without relying on machine-specific services or ports.

## 决策 / Decision

本地 SUT 使用源码内的 `apps/compose/compose.yaml` 和 Docker Compose 管理：

1. 使用一个 Compose project 同时编排 API、PostgreSQL 16 和 Redis 7。
2. API 由仓库内的 `apps/compose/api` 构建，保持小型、只读和可诊断。
3. PostgreSQL 使用 `001_schema.sql` 和 `002_seed.sql` 初始化空 volume。
4. 宿主机端口固定为 API `18000`、PostgreSQL `15432`、Redis `16379`。
5. PostgreSQL 和 Redis 使用命名 volume，普通停止不删除测试数据。
6. 为三个服务设置 health check，启动脚本等待服务真正可用。
7. `.env.example` 只保存本地测试凭据，Compose 默认值也不得复用于生产。
8. 日志、只读查询和健康检查是首选的诊断入口，不通过修改数据库绕过问题。

## 结果 / Consequences

正向结果：

- 任意安装 Docker Compose 的机器可以使用同一套拓扑。
- API、数据库和缓存共享稳定网络名称和健康检查。
- 本地端口与机器已有 Redis 隔离。
- CI 可以复用同一份 Compose 文件完成集成验收。
- Volume 保留数据，同时提供显式重建路径。

代价和约束：

- 开发机必须运行 Docker daemon 和 WSL2。
- 修改 init SQL 后需要显式删除数据库 volume 才能重放。
- 固定端口降低了并行启动多套本地 SUT 的便利性。
- Compose 适合本地和轻量 CI，不代表生产编排方案。

## 备选方案 / Alternatives

| 方案 / Option | 未采用原因 / Why not |
| --- | --- |
| 直接在 Windows 安装 PostgreSQL 和 Redis | 机器状态不可重复，端口和版本难隔离 |
| 完全使用内存 Mock | 无法验证 Schema、SQL、约束和真实连接行为 |
| 每条测试使用 Testcontainers | 启动成本和实现复杂度高于当前本地 SUT 需求 |
| Kubernetes | 对 Week 1 到 3 的基础设施目标过重 |
| 使用随机端口 | 命令、报告和 runbook 难以稳定复现 |

## 验证证据 / Verification

- `apps/compose/compose.yaml`
- `scripts/start_sut.ps1`
- `scripts/check_sut.py`
- `scripts/verify_sut_database.ps1`
- `tests/api/test_sut_smoke.py`
- `tests/integration/test_sut.py`
- `.github/workflows/sut-integration.yml`
- `reports/daily/DAY-05.md`

## 重新评估条件 / Revisit Triggers

- 需要多租户并行启动多套 SUT。
- 测试需要消息队列、对象存储或多个数据库类型。
- 本地 Compose 启动时间或资源消耗阻碍日常开发。
- 性能测试需要独立环境、资源限额和可观测性栈。

重新评估时新增 ADR，不修改本决策的历史结论。
