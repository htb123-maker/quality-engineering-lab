# 并行数据隔离失败排查 / Parallel Data-Isolation Failure Triage

触发条件：`pytest -n` 下用例互相干扰、断言偶发失败、清理后仍有残留数据、
`check_sut.py` 的 `Namespace leftovers` 检查失败，或某个 worker 的命名空间被
另一个 worker 删除。

## 1. 先确认是隔离问题还是产品问题

串行复现是第一步，它决定这次失败是否与并行相关：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\api -q -p no:cacheprovider
.\scripts\run_api_parallel.ps1 -Workers 4
```

```text
串行失败、并行失败 -> 产品、测试或环境问题，与并行无关
串行通过、并行失败 -> 数据隔离或共享状态问题，继续下面步骤
```

## 2. 检查命名空间归属

```powershell
docker compose -f apps\compose\compose.yaml exec -T postgres `
  psql -U qa -d qa -c "SELECT id, slug FROM workspaces ORDER BY id;"
```

```text
只有 atlas 与 orbit            -> 运行前后都干净，问题在断言本身
出现 qa-ns-<run>-<tag>-<hex>   -> 运行中断或清理未执行，见第 3 步
出现 qa-ns-<旧 token>-...      -> 历史运行的残留，下一次会话开始会被回收
```

slug 里的 `<run>` 段是所有 worker 共享的 `PYTEST_XDIST_TESTRUNUID` 前缀。
如果两个 worker 的命名空间互相覆盖，说明 `run_id()` 没有复用同一个值。

## 3. 运行后仍有残留

```powershell
.\.venv\Scripts\python.exe scripts\check_sut.py
```

```text
FAIL Namespace leftovers: test_namespaces=N
```

处理顺序：

1. 该检查本来就意味着“运行后必须为 0”。若刚跑完就非 0，说明某个 teardown
   没有执行（`KeyboardInterrupt`、进程被杀、断电）。
2. 下一次 API 会话开始时会调用 `pool.purge_stale()`，只保留当前 run 前缀，
   历史残留会被自动删除。重新跑一次 API 会话即可。
3. 需要人工清理时，只删除带测试前缀的工作区，不要动 `atlas`/`orbit`：

```sql
DELETE FROM workspaces WHERE starts_with(slug, 'qa-ns-') RETURNING slug;
```

## 4. 断言在全库总数上失败

```text
counts={'workspaces': 9, 'users': 15, 'items': 21}
```

并行运行时全库总数必然大于种子数量，这是正常的。断言“种子未被污染”必须使用
身份计数（`namespace_factory.seed_counts()` 或 `check_sut.py` 的
`PostgreSQL seed` 行），而不是全表 `COUNT(*)`。

## 5. 同一测试内的跨命名空间断言失败

```text
403 permission_denied        -> 用 A 的会话写 B 的工作区，这是预期行为
404 item_not_found           -> 用 A 的 item id 访问 B 的工作区，这也是预期行为
409 sku_conflict             -> 误以为 SKU 全局唯一；实际唯一约束是 (workspace_id, sku)
```

跨工作区用例必须显式获取对端会话，`tests/api/conftest.py` 的
`owner_session(peer.owner_email, settings)` 就是为此准备的。

## 6. 限流相关偶发失败

限流预算按 `X-QA-Client-Id` 计数，且状态在 SUT 进程内存中：

```text
同一 client id 被多个测试复用 -> 预算被别的测试提前耗尽
用固定 client id                -> 换成 unique_client_id("tag")
预算已耗尽后想验证正向路径      -> 用新的 client id，或重启 SUT 清空计数
```

## 7. 幂等键跨轮次回放

```text
第二轮运行拿到上一轮的 201 响应 -> Redis 里 idem:<workspace_id>:* 未被清理
```

`NamespacePool` 在释放租约时会调用 `purge_idempotency_keys()`。若绕过资源池
直接使用 `NamespaceFactory`，需要自己保证该工作区的幂等键被清理。

## 8. 仍需报告的证据

```text
串行与并行的完整命令与结果
失败用例的命名空间 slug 与 worker 名
check_sut.py 的输出（含 leftovers 行）
workspaces 表的 slug 列表
```

并行问题不能用“重跑一次绿了”收口。需要说明是哪一类共享状态、如何被隔离、
以及清理为何能阻止它再次出现。
