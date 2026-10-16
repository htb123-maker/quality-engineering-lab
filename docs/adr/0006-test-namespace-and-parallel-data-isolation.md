# ADR-0006: 测试命名空间与并行数据隔离 / Test Namespaces and Parallel Data Isolation

- 状态 / Status: Accepted
- 日期 / Date: 2026-10-14
- 决策者 / Deciders: Quality Engineering Lab
- 替代 / Supersedes: None

## 背景 / Context

Week 7 的写接口测试全部落在种子工作区 `atlas`：SKU 唯一约束是
`(workspace_id, sku)`，冒烟用例还断言 `atlas` 只有 3 条目录数据。一旦用
`pytest-xdist` 并行，就会出现三类互相干扰：

- 两个 worker 同时对 `atlas` 写入，冒烟断言和幂等键互相影响。
- 限流按 `X-QA-Client-Id` 计数，多个 worker 抢同一个预算，失败不可复现。
- 一次中断运行会留下脏数据，下次运行结果取决于上一次是否跑干净。

Week 8 的目标是 120 条 API 测试、多 worker 无数据污染、清理可重复执行。因此
必须回答：测试数据写到哪里、谁负责清理、并行 worker 之间如何互不越界。

English: Week 7 wrote into the shared ``atlas`` seed workspace, which cannot
survive parallel workers, repeatable cleanup, or a 120-test suite.

## 决策 / Decision

1. 每个写入型测试使用独立命名空间工作区，slug 形如
   `qa-ns-<run_token>-<tag>-<hex>`。种子工作区 `atlas`、`orbit` 及其用户和
   目录数据只读，任何写入型用例都不再触碰它们。
2. 命名空间通过 PostgreSQL 直接种子化，而不是新增产品接口：
   `qa_core.db.WorkspaceRepository` 负责 SQL 层 upsert，
   `qa_core.data_factories.NamespaceFactory` 负责构造工作区、owner、viewer
   和可选基线目录数据。所有写入都以自然键（`slug`、
   `(workspace_id, email)`、`(workspace_id, sku)`）做 `ON CONFLICT` 更新，
   所以重复种子化不会产生重复行。
3. 资源池 `qa_core.resource_pools.NamespacePool` 每个 worker 只保留一个空闲
   命名空间：顺序测试复用它，租约结束时重置。嵌套租约按需创建，释放时销毁。
   资源池由 `NamespaceProvider` 协议约束，便于单元测试替换为内存实现。
4. 清理分三级，全部幂等：
   - `reset(identity)`：删除该工作区的目录数据，保留工作区和用户，供复用。
   - `purge(identity)`：删除工作区，依赖行由 `ON DELETE CASCADE` 一并删除。
   - `purge_stale(keep_run=...)`：会话开始时删除历史运行留下的命名空间，但
     保留当前 `run_token` 的命名空间，避免先启动的 worker 删掉后启动 worker
     正在使用的数据。
5. `reset` 同时清理 Redis 幂等键 `idem:<workspace_id>:*`。键本身有 TTL，但
   可重复运行不能依赖 TTL，否则同一 `Idempotency-Key` 的第二轮运行会回放上
   一轮的响应。
6. `scripts/check_sut.py` 改为按身份校验种子数据（`atlas`/`orbit`、三个种子
   用户、四个种子 SKU），并单独检查“是否存在遗留测试命名空间”。遗留检查失败
   即整体失败，因此“跑完必须干净”变成可执行的门禁，而不只是口头约定。
7. 断言“种子未被污染”的测试通过身份计数实现，而不是断言全库总数，这样并行
   worker 的活跃命名空间不会让断言变红。

English: seed test-owned namespaces through PostgreSQL, lease them through a
per-worker pool, reset catalog and idempotency state between leases, and make
leftover namespaces a hard gate.

## 结果 / Consequences

正向结果：

- 多 worker 并行运行无数据污染，串行与并行结果一致。
- 种子数据只读，冒烟断言与 `verify_day5` 视图继续成立。
- 清理可重复执行：中断运行留下的命名空间会在下一次会话开始时被回收。
- 数据工厂与资源池不依赖 pytest，后续 Appium、Locust 和 E2E 可以复用同一套
  建数与清理逻辑。

代价和约束：

- 测试需要数据库写权限（当前只针对本地测试 schema）。这是刻意的取舍：用
  SQL 种子化换取确定性，而不是靠产品接口堆测试数据。
- SUT 目前没有“创建工作区”的产品接口，因此命名空间只能从数据库种子化。
- 每个 worker 复用一个命名空间，测试必须保证租约结束时目录数据被清空；同事
  依赖 `reset` 和 teardown，而不是依赖运行顺序。
- 会话开始时清理历史命名空间会删除其他历史运行的数据，包括人工调试留下的
  数据；前缀 `qa-ns-` 因此是测试专用约定。
- Redis 中登录产生的 `auth:refresh:*` 仍依赖 TTL，不在本决策范围内。

## 备选方案 / Alternatives

| 方案 / Option | 未采用原因 / Why not |
| --- | --- |
| 所有测试继续写 `atlas`，只靠随机 SKU 避让 | 冒烟断言、限流预算和目录总数仍会互相干扰 |
| 每个测试串行运行，取消 xdist | 无法满足并行与后续性能、CI 分片需求 |
| 给 SUT 增加工作区管理接口 | 扩大产品表面，且把测试建数需求写进被测系统 |
| 每个测试新建独立工作区，不复用 | 400 条测试将产生上千次建删往返，成本高于收益 |
| 用事务回滚隔离（每个测试一个事务） | 目前 SUT 通过独立连接写入，测试侧事务无法覆盖其提交 |
| 用固定 slug 池，只清目录数据 | 残留用户/工作区会累积，且 slug 冲突不可诊断 |
| 依赖 Redis TTL 处理幂等键 | 同一 key 的第二轮运行会回放上一轮响应，测试不可重复 |

## 验证证据 / Verification

- `packages/qa_core/db/client.py`、`packages/qa_core/db/repositories.py`
- `packages/qa_core/data_factories/namespaces.py`、`catalog.py`
- `packages/qa_core/resource_pools/namespaces.py`
- `packages/qa_core/cache/idempotency.py`
- `tests/api/conftest.py`
- `tests/api/test_data_factory.py`、`test_namespace_isolation.py`、
  `test_parallel_isolation.py`
- `tests/unit/test_namespace_pool.py`、`test_data_factories.py`、
  `test_cache_idempotency.py`
- `scripts/run_api_parallel.ps1`、`scripts/check_sut.py`
- `docs/runbooks/parallel-data-isolation-failures.md`
- `reports/weekly/WEEK-08.md`

## 重新评估条件 / Revisit Triggers

- SUT 提供正式的工作区/租户管理接口，可以改用产品接口建数。
- 测试需要跨 worker 共享数据或做分布式锁、并发一致性实验（Week 9、Week 12）。
- 出现必须保留的调试命名空间，或前缀约定需要区分自动化与人工。
- 数据库权限收紧，测试不再允许直接写入。
- 资源池需要覆盖 Appium 设备、Locust 压测账号等更多资源类型。
