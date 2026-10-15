# ADR-0008: 缓存旁路、TTL 与最终一致性策略 / Cache-Aside, TTL, and Eventual Consistency

- 状态 / Status: Accepted
- 日期 / Date: 2026-10-15
- 决策者 / Deciders: Quality Engineering Lab
- 替代 / Supersedes: None

## 背景 / Context

Week 8 解决了“每个测试有自己的命名空间”，Week 9 解决了“并发过程中数据库
中间状态长什么样”。Week 10 要验证的问题换了一层：**接口返回的答案，可能既不是
数据库的当前状态，也不是最终答案**。

- 读接口加了缓存后，`200 OK` 不再等价于“读到了数据库最新值”。
- 写接口改了数据库后，如果缓存没被清掉，下一个人读到的就是旧值。
- 不存在的 key 如果每次都穿透到数据库，缓存反而放大压力。
- 请求返回 `202` 只代表“已受理”，真正的结果要等后台任务跑完。
- 推送通道（WebSocket）意味着结果可能先于轮询到达，也可能因为客户端不读而被丢弃。

本地 SUT 是一个手写的 `http.server` 服务，已经有 Redis：刷新令牌与幂等记录都存在
那里。本计划要在同一套 Redis 上再加缓存和队列，并且**让测试能看见真实状态**，
而不是只相信接口自己声称的结果。

English: Week 10 must verify reads that may be stale, writes that must not leave
stale cache behind, missing keys that must not reach PostgreSQL every time, and
work that finishes after the request answered.

## 决策 / Decision

1. **读路径使用缓存旁路（cache-aside）。** `GET /api/v1/workspaces/{slug}/catalog`
   先读 Redis，未命中才查 PostgreSQL，再把结果写回 Redis。
   - 正缓存：`cache:catalog:{slug}`，TTL 由 `QA_CATALOG_CACHE_TTL_SECONDS`
     （默认 60 秒）控制。
   - 负缓存：`cache:catalog:{slug}:absent`，TTL 由
     `QA_CATALOG_CACHE_NEGATIVE_TTL_SECONDS`（默认 10 秒）控制，用于挡住对不存在
     工作区的重复请求（缓存穿透）。
2. **写路径失效缓存，而不是写穿（write-through）。** 创建、改状态、删除成功后，
   服务端先删除该工作区的缓存 key，再返回响应，因此“响应已到”就意味着“下一个
   读一定看到新值”。写路径不主动填充缓存，避免把没人读的数据塞进 Redis。
3. **Redis 是加速器，不是依赖。** Redis 不可用时，目录读回退到 PostgreSQL，
   响应头标记 `X-Cache: BYPASS`。缓存故障不应该变成 503（该分支由单元测试覆盖）。
4. **缓存命中情况是显式的可观察契约。** 每个响应带 `X-Cache`
   （`HIT`、`MISS`、`HIT-NEGATIVE`、`BYPASS`）和 `X-Cache-TTL`；同时服务端在
   Redis 里维护 `cache:stats:{slug}:{hit,hit_negative,miss,db_reads,invalidations}`
   计数器并带 TTL。测试断言真实计数，而不是断言“大概很快”。
5. **异步任务用 Redis 队列 + 延迟集合。** 立即任务进 `jobs:queue`（List），
   延迟任务进 `jobs:delayed`（Sorted Set），到点后提升到队列。任务记录存在
   `job:{job_id}`，状态机固定为 `queued -> running -> succeeded | failed`，
   `failed` 必须带可读错误文本。
6. **Worker 与 API 同进程但不共用请求线程。** `JobWorker` 是守护线程，在
   `main()` 启动；调用方拿到 `job_id` 后自己去轮询。这样“请求返回 ≠ 工作完成”
   成为可测试的事实，而不是口头约定。队列不持久化：容器重启丢队列是已知边界。
7. **等待一律是有界轮询。** 测试用 deadline + interval 轮询任务状态和 key 是否存在，
   不使用固定 `sleep` 当作同步手段；验证 TTL 过期时把 key 的 TTL 压到 1 秒，
   而不是空等 60 秒。
8. **推送通道用手写 RFC 6455 实现 + 进程内 broker。** 事件流
   `GET /api/v1/workspaces/{slug}/events` 需要认证并校验工作区归属；
   每个订阅者一个**有界队列**，客户端停止读取时丢弃事件并记录日志，绝不阻塞
   产生事件的请求线程。
9. **本计划不做 Webhook 出站投递。** 需要让被测服务主动回调测试机上的接收器，
   在 Windows + 容器场景要额外解决 `host.docker.internal` 与容器 IP 的可达性。
   先用 WebSocket 覆盖“推送 + 失败验证”，出站回调留到通知/E2E 阶段。

English: cache-aside with an explicit invalidation contract, short negative
caching, Redis as an accelerator with a PostgreSQL fallback, Redis counters and
headers as evidence, a Redis-backed job queue with a documented status machine,
bounded polling instead of sleeps, and a bounded-queue WebSocket fan-out.

## 结果 / Consequences

正向结果：

- “缓存改了、库没改”和“库改了、缓存没改”两类不一致都变成可复现实证：直接改库
  后读接口仍然返回旧值（`HIT`），清掉 key 或等到 TTL 过期后立刻返回新值。
- 缓存穿透有可量化证据：同一段代码对同一个不存在的 slug 连续读 3 次，
  `db_reads` 计数器只增加 1。
- 异步任务有完整证据链：`202 + job_id`、队列深度、`started_at`/`finished_at`、
  `processed`/`failed` 计数器、以及 Worker 写入的缓存 key。
- 推送通道可以在一条用例里同时验证写操作事件与任务完成事件，并覆盖
  401/403/426 三种拒绝路径。
- 测试等待时间稳定：全部缓存、任务、事件用例都不依赖固定 sleep。

代价和约束：

- Redis 里多了一组必须清理的测试状态。命名空间租约释放时会同时清理缓存 key 与
  计数器（`NamespacePool._purge_redis_state`），任务记录依赖 TTL 自行过期。
- 队列不持久：容器重启会丢掉排队中的任务。这是本地 SUT 接受的边界，不是生产方案。
- Worker 与 API 同进程，因此“后台任务”不会隔离 CPU；性能专题需要真正的独立
  Worker（Week 25+）。
- 事件 broker 是进程内的 best-effort：多副本部署时订阅者只能看到自己连到的那份
  事件。
- 停止读取的订阅者会丢事件且只在日志里可见，接口层没有提供丢弃计数。

## 备选方案 / Alternatives

| 方案 / Option | 未采用原因 / Why not |
| --- | --- |
| 写穿（write-through）：写库同时写缓存 | 写入方通常不知道下一个读的形状，且写放大 |
| 只靠 TTL 不主动失效 | 默认 TTL 内必然返回旧值，一致性窗口无法收敛到“写完即可读” |
| Redis 挂掉就返回 503 | 把加速器变成单点依赖，与“缓存是优化”的定位矛盾 |
| 用 Celery/RQ 做队列 | 为本地 SUT 引入 broker 服务与依赖，超出该阶段学习目标 |
| 用固定 `sleep` 等待任务或 TTL | 慢机器漏判、快机器浪费时间，且失败无法解释 |
| 用现成 WebSocket 库实现推送 | 需要给容器镜像加依赖；手写实现同时暴露握手、掩码、帧边界等测试点 |
| 本轮就做 Webhook 出站投递 | 需要额外解决容器到测试机的回调地址可达性，收益与风险不匹配，推迟到通知阶段 |
| 用 Redis 订阅发布替代进程内 broker | 当前只有一个 API 副本，多一跳网络只会增加不确定性 |

## 验证证据 / Verification

- `apps/compose/api/app.py`（缓存旁路、负缓存、失效、计数器、任务队列、Worker、
  WebSocket 事件流）
- `packages/qa_core/cache/catalog.py`、`packages/qa_core/jobs.py`、
  `packages/qa_core/events/websocket.py`
- `tests/integration/test_redis_cache.py`、`test_job_queue.py`
- `tests/api/test_cache_consistency.py`、`test_event_stream.py`
- `tests/unit/test_ws_frame_codec.py`、`test_cache_key_contract.py`、
  `test_sut_cache_fallback.py`
- `docs/runbooks/redis-cache-and-consistency-triage.md`
- `reports/weekly/WEEK-10.md`

## 重新评估条件 / Revisit Triggers

- API 从单副本变成多副本：进程内 broker 与 Worker 需要换成真正的消息中间件。
- 需要重启不丢任务（durable queue），或需要任务重试/超时回收。
- 需要验证出站通知（Webhook、邮件、消息推送）的投递与重试。
- 失效范围从单工作区扩展到多 key 派生视图（例如按状态聚合的列表缓存）。
- Redis 故障需要熔断、降级开关或指标化，而不再只是逐请求回退 PostgreSQL。
- 需要断言“事件不丢”而不是“事件尽力送达”：那时要引入持久化事件表与游标。
