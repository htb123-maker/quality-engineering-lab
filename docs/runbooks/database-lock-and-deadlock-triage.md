# 数据库锁等待与死锁排查 / Database Lock-Wait and Deadlock Triage

触发条件：某个用例一直不返回直至超时、出现 `55P03`（`lock_timeout`/`NOWAIT`）
或 `40P01`（死锁）、`tests/integration/test_locks_and_deadlock.py` 失败，或者
运行结束后数据库里仍有会话在等锁。

## 1. 先分清三类结果

```text
55P03 lock_not_available  -> 我们主动放弃等待，说明锁冲突真实存在
40P01 deadlock_detected   -> PostgreSQL 检测到互相等待并牺牲了一方
用例超时但无报错          -> 某个事务一直没提交或回滚，锁没有被释放
```

前两类是数据库语义的正常体现；第三类几乎总是测试侧写错了事务边界。

## 2. 看谁在等谁

最快的一条查询，直接回答“被阻塞的 pid、阻塞的 pid、锁模式、等待事件”：

```powershell
docker compose -f apps\compose\compose.yaml exec -T postgres psql -U qa -d qa -c "
SELECT blocked.pid AS blocked_pid,
       blocking.pid AS blocking_pid,
       blocked_locks.mode AS blocked_mode,
       blocking_locks.mode AS blocking_mode,
       blocked.wait_event_type,
       blocked.wait_event,
       left(blocked.query, 80) AS blocked_query
FROM pg_stat_activity AS blocked
JOIN pg_locks AS blocked_locks
  ON blocked_locks.pid = blocked.pid AND NOT blocked_locks.granted
JOIN pg_locks AS blocking_locks
  ON blocking_locks.locktype = blocked_locks.locktype
 AND blocking_locks.relation IS NOT DISTINCT FROM blocked_locks.relation
 AND blocking_locks.transactionid IS NOT DISTINCT FROM blocked_locks.transactionid
 AND blocking_locks.pid <> blocked_locks.pid AND blocking_locks.granted
JOIN pg_stat_activity AS blocking ON blocking.pid = blocking_locks.pid;"
```

同一个查询在 Python 里是 `qa_core.db.locks.blocking_pairs()`；用例里等待特定
一对 pid 出现则用 `wait_for_blocking_pair(..., timeout=...)`。

## 3. 看事务开在哪里

```powershell
docker compose -f apps\compose\compose.yaml exec -T postgres psql -U qa -d qa -c "
SELECT pid, state, xact_start, now() - xact_start AS age, application_name,
       left(query, 60) AS query
FROM pg_stat_activity
WHERE datname = current_database() AND xact_start IS NOT NULL
ORDER BY xact_start;"
```

```text
application_name 以 qa-week9 开头 -> 测试连接，说明是测试侧未提交
age 很大                          -> 事务忘记提交/回滚，或断点停在了 BEGIN 后
只有 idle in transaction 状态      -> 业务代码没结束事务，不是锁本身的问题
```

## 4. 死锁计数与日志

```powershell
docker compose -f apps\compose\compose.yaml logs --tail 50 postgres | Select-String "deadlock"
```

```sql
SELECT deadlocks FROM pg_stat_database WHERE datname = current_database();
```

死锁计数只会增加、不会回零，所以测试断言必须使用“运行前后的差值”。容器日志
里的 `deadlock detected` 与 `DETAIL: Process N waits for ...` 是报告里最有说服
力的证据。

## 5. 常见原因与处理

| 现象 / Symptom | 原因 / Cause | 处理 / Fix |
| --- | --- | --- |
| 阻塞对长期存在，`blocked_query` 是普通 UPDATE | 持锁方事务未结束 | 找到持锁方连接，提交或回滚；检查用例是否漏了 `commit()`/`rollback()` |
| 用例结束后仍有人在等锁 | 用例失败后 teardown 没执行 | `ConnectionFactory` 会在 teardown 回滚所有连接，不要在用例里手工 `psycopg.connect` |
| `55P03` 出现在正向路径用例 | 并发用例之间的锁窗口重叠 | 并发用例使用独立的 `db_namespace`，不要共享同一行 |
| 死锁用例偶发变成“两边都超时” | 两个线程没有先各自拿到第一把锁 | 用 `threading.Barrier` 保证第一把锁都拿到后再抢第二把 |
| 死锁用例断言“A 一定失败” | 牺牲者由 PostgreSQL 决定 | 只断言恰好一方 `40P01`，另一方提交 |
| 计划用例断言索引失败 | 数据量太小，规划器合理选择顺序扫描 | 使用 `bulk_catalog` 夹具，或改用“关闭索引扫描退化”的对照断言 |

## 6. 复现命令

```powershell
docker compose -f apps\compose\compose.yaml up --detach --wait --wait-timeout 180
.\.venv\Scripts\python.exe -m pytest tests\integration -q -p no:cacheprovider -k "lock or deadlock"
.\.venv\Scripts\python.exe -m pytest tests\integration -q -p no:cacheprovider
```

## 7. 需要保留的证据

```text
失败用例的完整报错与 SQLSTATE
blocking_pairs() 的输出（两侧 pid、锁模式、wait_event）
pg_stat_database.deadlocks 的前后次数
postgres 容器日志中的 deadlock detected 片段
当时是否有 qa-week9-* 的 application_name 会话残留
```

不要用“重跑一次就绿了”收口。需要说明锁冲突是哪两方、谁没有结束事务、
以及修改后为什么冲突会消失。
