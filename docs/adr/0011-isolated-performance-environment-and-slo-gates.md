# ADR-0011: 独立性能环境与机器可判定 SLO / Isolated Performance Environment and Machine-Checkable SLO Gates

- 状态 / Status: Accepted
- 日期 / Date: 2026-10-29
- 阶段 / Phase: Week 25

## 背景 / Context

接口、数据库和移动端测试共用本地 SUT 能减少环境维护成本，但性能结果不能被
其他测试的写入、缓存命中变化、容器重启或并发数据准备污染。性能测试还需要
比“命令执行完成”更明确的通过条件：只有请求成功、样本量足够且延迟目标满足
时，结果才可作为基线。

当前 Windows 主机不能运行 iOS，因此性能主线是环境无关的继续路径。性能阶段
不能借用这个理由降低 SLO，也不能用一次短 smoke 代替 Stress、Soak 或容量结论。

## 决策 / Decision

1. 使用独立 Docker Compose project name 和独立宿主机端口启动性能 SUT。
2. 每个性能运行使用 `configs/` 下的 YAML profile，固定用户数、spawn rate、
   duration、目标工作区和阈值。
3. Locust 执行结束后，由 `events.quitting` 统一计算请求数、错误率、p95 和
   p99；任一阈值失败时进程以非零状态退出。
4. Week 25 只执行读路径 smoke。Stress、Spike、Soak 仍属于 Week 28 到 29。
5. 性能服务只使用本地测试数据和非生产凭据；独立环境不能连接 staging 或生产。

## 原因 / Rationale

- 独立端口和 Compose 卷避免与功能测试互相修改缓存和数据库状态。
- YAML profile 让负载模型可审查、可版本化，避免靠聊天记录中的命令行参数。
- 机器可判定退出码能接入 CI，避免把未达标结果人工解释成“波动”。
- 先做只读 smoke 能验证 SUT、Locust、指标输出和阈值链，而不提前宣称容量结论。

## 后果 / Consequences

- 本地会多一套可选 Compose 服务，默认端口为 `28000`、`25432` 和 `36379`。
- 项目新增 `locust` 运行时依赖，用于负载生成、CSV/HTML 结果和阈值事件。
- 每个负载档位需要独立 profile；以后新增写旅程时必须提供幂等数据准备和清理。
- 本机单进程 Locust 的瓶颈不能代表服务容量，Week 26 需要独立的压力机或
  分布式 Master/Worker。

## 未采用方案 / Alternatives Rejected

- 直接压日常功能环境：状态污染严重，结果不可重复。
- 只用 shell 循环发请求：缺少并发模型、统计聚合和稳定的负载形状。
- 默认所有请求都必须低于固定毫秒数：未区分健康检查、缓存命中和写路径。
- 用一次 Week 25 smoke 直接给出容量结论：证据不足，违反阶段验收。
