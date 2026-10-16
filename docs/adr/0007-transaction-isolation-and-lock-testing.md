# ADR-0007: 事务、隔离级别与锁测试策略 / Transaction, Isolation-Level, and Lock Testing Strategy

- 状态 / Status: Accepted
- 日期 / Date: 2026-10-15
- 决策者 / Deciders: Quality Engineering Lab
- 替代 / Supersedes: None

## 背景 / Context

Week 8 的所有数据库访问都是自动提交的单条语句：种子、断言、清理。Week 9 要
验证的东西恰好相反——提交与回滚的边界、隔离级别的可见性差异、行锁等待和死锁。
这些行为只有在“多个连接同时持有打开的事务”时才存在，因此测试模型必须换一套：

- SUT API 每个请求打开自己的连接并立即提交，接口层看不到事务中间态。
- 一个连接做不了阻塞实验：必须有一个持锁方、一个等待方，通常还需要一个旁观者
  去读 `pg_locks`。
- 并发用例很容易写成 flaky：固定 `sleep`、依赖调度顺序、或者断言“谁成为死锁
  牺牲者”都会让结果不稳定。
- 本地 Schema 由 `docker-entrypoint-initdb.d` 在空卷上执行一次，此时数据库
  可能已经和 `001_schema.sql` 漂移，而所有数据库测试都假设它没有漂移。

English: Week 9 needs multi-connection transaction, isolation, lock, and plan
evidence, plus a way to detect schema drift on a database that was initialised
once and never migrated again.

## 决策 / Decision

1. 一个 `DatabaseClient` 只持有一个连接。需要阻塞对时打开两个客户端，需要
   旁观视角时再打开第三个。测试通过 `ConnectionFactory` 统一申请连接，teardown
   负责回滚并关闭，避免失败的用例把行锁留到下一次运行。
2. 事务与隔离级别是显式连接参数：`autocommit=False` 关闭自动提交，
   `isolation_level` 取 `read_committed`、`repeatable_read`、`serializable`。
   在事务进行中修改隔离级别直接抛错，而不是静默生效到下一轮。
3. 并发用例使用“有界轮询 + 超时失败”：等待阻塞对出现、等待线程结束都用超时
   上限，超时即测试失败，而不是跳过或视为环境噪声。锁证据取自
   `pg_locks` + `pg_stat_activity`（阻塞方 pid、被阻塞方 pid、锁模式、
   `wait_event`），不解析日志文本。
4. 只断言可观察行为：
   - 提交前对其他会话不可见，提交后可见。
   - `40001` 表示需要重试，`55P03` 表示 `NOWAIT`/`lock_timeout` 主动放弃，
     `40P01` 表示死锁。
   - 死锁测试只断言“恰好一方以 `40P01` 失败、另一方提交、计数器 +1”，不指定
     哪个事务被牺牲；牺牲者由 PostgreSQL 决定。
   - `READ UNCOMMITTED` 只断言“读不到未提交数据”，因为 PostgreSQL 明确把它
     当作 `READ COMMITTED` 处理，断言 GUC 文本没有行为意义。
5. Schema 只做只读契约检查（`qa_core.db.schema` + `scripts/check_schema.py`），
   期望契约与 `001_schema.sql` 同源维护。本计划不引入 Alembic/Flyway：本地
   SUT 的 Schema 只有一份初始脚本，引入迁移工具会先解决一个尚未出现的问题。
6. 查询计划断言使用 `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)`，并通过构造足量
   数据让规划器自然选择复合索引；同时保留“关闭索引扫描后退化为 Seq Scan”的
   对照实验，避免在小数据集上强行断言索引而产生的假阴性。

English: one connection per client, explicit isolation levels, bounded polling
with hard timeouts, SQLSTATE-based assertions, read-only schema contracts, and
plan assertions backed by a controlled volume plus a negative control.

## 结果 / Consequences

正向结果：

- 事务、隔离级别、锁等待和死锁结论都有第一手证据：SQLSTATE、锁模式、阻塞 pid
  对、`pg_stat_database.deadlocks` 计数。
- 并发用例可在本地与 Linux 容器重复运行，失败时能区分“产品并发缺陷”“测试
  设计问题”“环境超时”。
- Schema 漂移从“隐性风险”变成一条会红的门禁。
- 查询计划工具与 Schema 内省函数可以被 Week 10 缓存一致性、Week 26+ 慢查询
  专题直接复用。

代价和约束：

- 测试需要数据库连接数预算：并发用例会额外打开 2 到 4 个连接。xdist 下
  `tests/api` 的并发写用例也会为每个线程各开一个会话。
- 死锁用例会真实产生一个被回滚的事务，并且会让 `pg_stat_database.deadlocks`
  永久 +1；断言必须用“前后差值”，不能用绝对值。
- 索引断言依赖数据量：`bulk_catalog` 夹具会插入 200 个工作区、20000 行目录
  数据，并在用例结束后级联删除；测试耗时因此略增。
- 只读契约检查不会修复漂移，它只报告；修复方式仍是重建本地卷或人工迁移。

## 备选方案 / Alternatives

| 方案 / Option | 未采用原因 / Why not |
| --- | --- |
| 继续用单连接 + 自动提交验证事务 | 无法观察提交前不可见、锁等待和死锁 |
| 每个测试用一个事务包裹并回滚 | SUT 走独立连接提交，测试事务覆盖不到被测写入 |
| 固定 `sleep` 等待锁出现 | 慢机器漏判、快机器浪费时间，失败不可解释 |
| 断言具体哪个事务死锁失败 | PostgreSQL 决定牺牲者，断言实现细节会不稳定 |
| 断言 `SHOW transaction_isolation` 反映 `READ UNCOMMITTED` | 该级别在 PostgreSQL 中等价于读已提交，文本断言没有行为意义 |
| 现在就引入 Alembic/Flyway | 本地只有一个初始脚本，先引入工具再找问题不划算 |
| 在小数据集上直接断言索引被使用 | 规划器可能合理选择顺序扫描，导致用例假阴性 |

## 验证证据 / Verification

- `packages/qa_core/db/client.py`、`schema.py`、`locks.py`、`plans.py`
- `scripts/check_schema.py`
- `tests/integration/conftest.py`、`test_transactions.py`、
  `test_isolation_levels.py`、`test_locks_and_deadlock.py`、`test_query_plans.py`、
  `test_schema_contract.py`
- `tests/api/test_api_db_state.py`
- `tests/unit/test_schema_contract_rules.py`、`test_plan_analysis.py`
- `docs/runbooks/database-lock-and-deadlock-triage.md`
- `reports/weekly/WEEK-09.md`

## 重新评估条件 / Revisit Triggers

- SUT 改为在一个事务里处理请求，或引入连接池后需要新的可见性模型。
- 需要验证真实的业务并发缺陷（乐观锁、丢失更新），而不仅是数据库语义。
- PostgreSQL 连接数或权限收紧，并发用例无法再开多个连接。
- Schema 进入真正的版本化迁移阶段（多份脚本、回滚脚本、生产对齐）。
- 查询计划用例在更大数据集上出现规划器抖动，需要固定统计信息或使用
  `pg_hint_plan` 之类的辅助手段。
