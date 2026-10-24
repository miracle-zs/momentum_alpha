# Momentum Alpha 架构评估与演进建议报告

- **最新更新**：2026-09-05（已吸收 Codex 架构复核意见与策略设计哲学澄清）
- **评估角色**：资深系统与量化架构师（双模型交叉复核：Antigravity Reviewer & Codex Peer Reviewer）
- **评估对象**：`momentum_alpha` 现行交易系统（Binance USDⓈ-M 永续合约动量轮动策略）
- **范围**：策略核心机、订单执行链路、交易所集成、双进程拓扑与持久化、看板及反事实复盘
- **验证基线**：全套自动化测试套件（678 个测试全部通过）

---

## 一、 架构总评与执行摘要 (Executive Summary)

**总体结论：系统是一个边界清晰、领域模型纯粹的“模块化单体 (Modular Monolith)”。策略算法与测试设计质量极高；当前不需要推倒重来的颠覆式重构，而应聚焦于真实执行链路脆弱点、调度器时钟稳健性与可观测性加固。**

Momentum Alpha 是一个在**策略核心算法与量化资金模型**上设计极其纯粹的量化交易系统。其基于“纯函数状态机 (Functional Core, Imperative Shell)”的设计理念，结合“交易所证据为权威真理 (Exchange Evidence as Truth)”的自愈哲学，让策略核心具备了极高的确定性与离线测试能力（678 个单元测试全部通过，且不依赖 Mock 框架）。

在策略资金模型上，系统明确确立了两个**有意特性 (Features by Design)**：
1. **纯固定风险预算 (Fixed Dollar Risk)**：不设人为最大名义仓位上限，通过紧止损自适应放大名义杠杆，以数学一致性保证单笔止损预算恒定；
2. **全天候长尾捕捉 (Continuous Right-Tail Capture)**：不设置组合级日内全局熔断，防止日内震荡磨损后被动停机，从而错过右侧极端单边大行情的肥尾收益。

系统当前真正需要优先解决的不是概念上的“架构重构”，而是四个务实的工程问题：
- **调度器存在漏 Tick 的真实 Bug**；
- **新仓开仓（Market）与挂止损（Stop）的两阶段顺序窗口与滑点冲击**；
- **双进程共享 SQLite 的写者串行竞争缺乏量化指标观测**；
- **异常分类粒度不足（未能细分保证金不足、限频与网络故障）**。

### 核心维度综合评估矩阵

| 维度 | 现状评估 | 架构判定与复核结论 |
| :--- | :--- | :--- |
| **策略核心 (Core)** | 纯函数状态机，与 I/O 完全解耦 | 🌟 **卓越**：`evaluate_minute_close` 边界极度清晰（注：内部嵌套 dict/list 依赖显式复制保障不可变）。 |
| **一致性哲学 (Consistency)** | 交易所证据为真，REST 覆盖对账兜底 | 🌟 **卓越**：抗断线与幽灵持仓自愈能力极强。 |
| **测试设计 (Testing)** | 678 个测试全部通过，不依赖 Mock 框架 | 🌟 **优秀**：测试质量极高（注：证明无断言失败，但尚未配置行/分支覆盖率度量）。 |
| **止损替换 (Stop Replacement)** | 挂新撤旧 (Stop-before-cancel) | 🌟 **优秀**：已有持仓更新止损时，最大限度压缩了保护空窗期。 |
| **新仓开仓 (New Entry Stop)** | 先市价开仓，再挂止损单 | ⚠️ **存在脆弱窗口**：物理上无法绝对杜绝裸仓。若入场成功而止损因限频/超时失败，需依赖后续修复。 |
| **资金模型 (Sizing & Risk)** | 纯固定风险预算（不设名义上限）、全天候捕捉（不设日内熔断） | 🎯 **有意特性 (Feature)**：低胜率超高盈亏比动量策略的标准数学设计，不能人为设限破坏策略一致性。 |
| **执行滑点 (Slippage)** | 入场采用裸市价单，无盘口冲击保护 | ⚠️ **需实测与保护**：模型预算不等于实际损失上限，大名义仓位可能因滑点、手续费与跳空导致超额亏损。 |
| **进程拓扑 (Topology)** | 双进程通过 SQLite 共享状态 | 💡 **模块化单体选择**：单进程会扩大故障爆炸半径；SQLite 属于整库级写者串行（非行锁），需通过指标决定是否演进。 |
| **时钟调度 (Scheduler)** | 依赖 `sleep(1)` + `second <= 2` 粗糙判定 | 🚨 **明确 Bug**：CPU/IO 抖动在第 3 秒后醒来会导致整分钟 Tick 永久跳过。 |
| **代码组织 (Modularity)** | 149 个微模块平铺在包下 | 💡 **有意设计**：系有意拆分的单一职责模块与兼容外观，文件数本身不是缺陷，应重点关注深模块接口。 |

---

## 二、 架构现状全景透视

系统目前采用两地一中心的双长效守护进程拓扑，辅以 systemd 定时任务：

```mermaid
flowchart TD
    subgraph External["外部交易所 (Binance USDⓈ-M Futures)"]
        REST["Binance REST API (/fapi/v1)"]
        WS["User Data Stream WebSocket"]
    end

    subgraph Process1["Poll 轮询进程 (momentum-alpha.service)"]
        Scheduler["Scheduler (1m Tick)"] --> MarketCache["MarketData Cache"]
        MarketCache --> REST
        Scheduler --> CoreEngine["纯状态机 Strategy Engine"]
        CoreEngine --> ExecPlan["Execution Planner"]
        ExecPlan --> Broker["Broker (Order / Stop)"]
        Broker --> REST
        Reconcile["REST 对账兜底"] --> REST
    end

    subgraph Process2["User-Stream 进程 (momentum-alpha-user-stream.service)"]
        WSClient["WebSocket Client"] --> WS
        WSClient --> EventParser["Event Parser & Deduplicator"]
        EventParser --> StreamCore["UserStream State Reducer"]
    end

    subgraph Storage["持久化与状态存储 (SQLite WAL)"]
        DB[("var/runtime.db (整库写者串行)")]
    end

    subgraph Monitoring["监控与投研 (独立进程 / 定时器)"]
        Dashboard["Dashboard Web Server (Port 8080)"]
        Sync["Trade Data Incremental Sync"]
        Review["Daily Review & ServerChan"]
    end

    Broker -.->|BEGIN IMMEDIATE / Write| DB
    Reconcile -.->|Update| DB
    StreamCore -.->|atomic_update / Merge Save| DB
    DB -.->|Poll Read State| CoreEngine
    DB -.->|Read| Dashboard
    DB -.->|Read & Write| Sync
    DB -.->|Read| Review
```

---

## 三、 策略设计哲学与核心亮点剖析

### 1. 纯固定风险预算与长尾保护（意图明确的核心特性）
- **特性一：不设人为最大名义价值上限 (Uncapped Nominal Size by Design)**
  - 策略严格遵循 **固定美元风险预算 (Fixed Dollar Risk Budget)**：
    $$\text{Quantity} = \frac{\text{Stop Budget}}{\text{Entry Price} - \text{Stop Price}}$$
  - 当开仓价格与小时低点非常接近时（止损距离极短），名义仓位自然放大。这符合动量突破的数学逻辑——**以最小的单笔试错成本（如 10 USDT），撬动最大的潜在趋势盈亏比**。若人为强加名义硬顶，反而会截断优质紧止损机会的盈利乘数，破坏固定风险模型的数学一致性。
- **特性二：不设日内全局熔断 (No Global Portfolio Circuit Breaker by Design)**
  - 领涨动量轮动策略在统计学上具备典型的**低胜率、超高盈亏比（Fat Right Tail / 肥尾收益）**特征。
  - 在全天 24 小时中，白天的假突破与震荡扫损是获取最终收益的必要摩擦成本。如果设置了日内累计亏损熔断停机，系统极易在“震荡期吃满亏损”后被停机，从而**彻底错过夜间走出的单日暴涨数倍的超级真领涨**。
- **系统的真实微观结构性防线**：
  系统并非没有风控，而是通过精细的微观结构控制磨损：
  1. 单笔独立止损单（固定预算）；
  2. 同币种当日信号槽限制（`daily_base_signal_times` 防止在同一个疲软标的上反复送人头）；
  3. 止损冷却期机制（`recent_stop_loss_exits`，刚止损标的 60 分钟内禁止重入）；
  4. 组合单币唯一持仓约束（`already_holding`）；

### 2. 函数式核心与命令式外壳 (Functional Core, Imperative Shell)
- **实现位置**：[`strategy.py`](file:///Users/zhangshuai/PycharmProjects/momentum_alpha/src/momentum_alpha/strategy.py)、[`models.py`](file:///Users/zhangshuai/PycharmProjects/momentum_alpha/src/momentum_alpha/models.py)
- **机制**：核心函数 `evaluate_minute_close` 为纯函数，签名清晰接收 `(now, state, market)`，产出明确的决策对象 `MinuteCloseDecision`。
- **细节复核**：虽然使用了 `@dataclass(frozen=True)`，但由于内部包含 `dict` / `list` 集合，系统在代码中通过显式浅拷贝保障不可变语义。策略决策完全与 I/O 隔离，可测试性极强。

### 3. 交易所证据为权威真理 (Exchange Evidence as Truth)
- **实现位置**：[`reconciliation.py`](file:///Users/zhangshuai/PycharmProjects/momentum_alpha/src/momentum_alpha/reconciliation.py)
- **机制**：交易所真实的仓位和挂单永远高于本地数据库缓存。每分钟的 REST 对账能够自动纠偏：清理本地幽灵仓位、自动补齐缺失的止损单，抗断线与自愈能力强。

### 4. 强幂等性与挂新撤旧 (Stop-before-cancel)
- **实现位置**：[`orders.py`](file:///Users/zhangshuai/PycharmProjects/momentum_alpha/src/momentum_alpha/orders.py)、[`broker.py`](file:///Users/zhangshuai/PycharmProjects/momentum_alpha/src/momentum_alpha/broker.py)
- **机制**：
  - `clientOrderId` 根据时间桶、标的、腿类型（`base`/`add_on`）和角色（`e`/`s`）确定性生成，天然防重入；
  - **已有持仓的止损替换**严格遵循“先挂新单并确认成功，再去撤销旧单”的时序，最大限度降低了保护空窗。

---

## 四、 真实工程痛点与技术复核

### 1. 定时调度器的时钟脆弱性（明确高危 Bug）
- **问题代码**：[`scheduler.py:18-32`](file:///Users/zhangshuai/PycharmProjects/momentum_alpha/src/momentum_alpha/scheduler.py#L18)
```python
now = now_provider()
minute_key = (now.year, now.month, now.day, now.hour, now.minute)
if now.second <= 2 and minute_key != last_seen_minute:
    run_once(now)
    last_seen_minute = minute_key
sleep_fn(1)
```
- **风险分析**：
  - 调度器依赖 `sleep_fn(1)` 结合 `now.second <= 2`。若进程因 CPU 争用、GC 或前序 I/O 耗时较长在第 3 秒后醒来（如 `00:03.050`），判定失败；
  - **该分钟被静默跳过**，当分钟的开仓和止损维护全部丢失。
- **复核修复要求**：
  - **语义定义**：对于实时动量策略，应采用**“补偿最近一个已收盘分钟”**的策略，严禁盲目全量补跑所有错过的历史分钟；
  - **接口规范**：**必须继续使用注入的 `now_provider` 和 `sleep_fn`**，绝不能在内部直接调用系统 `datetime.now()`，以保证 678 个时钟注入单测的完整性；
  - **测试覆盖**：必须增加“第 3 秒唤醒”、“第 20 秒唤醒”、“耗时 handler 恢复”等边界回归测试。

### 2. 新仓入场与止损挂单的顺序脆弱窗口
- **问题代码**：[`poll_worker_core_live.py`](file:///Users/zhangshuai/PycharmProjects/momentum_alpha/src/momentum_alpha/poll_worker_core_live.py)、[`broker.py`](file:///Users/zhangshuai/PycharmProjects/momentum_alpha/src/momentum_alpha/broker.py)
- **风险分析**：
  - “挂新撤旧”仅保障已有持仓的更新；但**新仓开仓必须先提交市价开仓单，成交后再提交止损单**；
  - 若开仓单成交后，止损单因 429 限频、超时断网或账户保证金耗尽而提交失败，持仓将短暂处于**无止损裸仓状态**；
  - 当前代码具备“预检查 + 修复 + 下一分钟对账”机制，但这属于事后补偿，不能宣称物理上“杜绝了裸仓”。
- **加固要求**：
  - 明确记录 `ENTRY_SUCCESS`、`STOP_FAILED`、`STOP_RECONCILE_FAILED` 三级细分状态；
  - 处理**部分成交 (Partially Filled)**：用订单实际成交数量（`executedQty`）动态挂止损，避免数量不匹配被拒；
  - 连续修复失败后提供硬告警与受控退出机制。

### 3. 入场滑点与模型预算脱节风险
- **问题代码**：[`sizing.py`](file:///Users/zhangshuai/PycharmProjects/momentum_alpha/src/momentum_alpha/sizing.py)、[`orders.py`](file:///Users/zhangshuai/PycharmProjects/momentum_alpha/src/momentum_alpha/orders.py)
- **风险分析**：
  - 模型计算的 `stop_budget` 仅为名义价差预算，未将滑点、手续费、资金费及极端穿价纳入；
  - 策略追逐暴涨小币种，盘口深度薄。如果紧止损导致名义仓位放大，市价单吃穿盘口的滑点可能直接消耗掉整笔止损预算。
- **复核纠偏**：
  - **币安的 `priceProtect` 不能用于此场景**：`priceProtect` 仅适用于条件单防标记价格刺穿，不是市价开仓单的滑点保护参数；
  - **可行路径**：
    1. **第一步（先测量）**：利用现有交易历史数据，统计“决策快照价”与“实际成交均价”的滑点分布；
    2. **第二步（保护机制）**：若滑点显著，采用带价格上限的 IOC 限价单（需妥善处理部分成交和未成交退避），或在发单前检测盘口买卖价差与深度冲击。

### 4. SQLite 锁机制与进程拓扑的客观评估
- **复核纠偏**：
  - **锁机制澄清**：SQLite 开启 WAL 后支持并发读，但在写操作时依然是**整库级的单写者串行排他锁**，绝非“行锁”；
  - **不可盲目重构为单进程**：
    - 当前“`poll` 策略轮询 + `user-stream` 状态收敛”的双进程设计属于**模块化单体方案**；
    - 双进程天然实现了**故障域隔离 (Fault Domain)**：流连接崩溃或重连不会直接打崩整点的定时策略计算；若激进合并为单进程，异步事件循环一旦阻塞，爆炸半径将成倍扩大；
  - **工程决策**：**不应该在没有真实锁指标时做单进程大手术**。短期应建立锁可观测性指标（记录锁等待耗时、写事务耗时、`database is locked` 频次），用真实数据驱动未来决策。

---

## 五、 落地路线图与任务清单 (Actionable Roadmap)

遵循 Codex 提出的**“深模块封装、先观测后演进、绝不大拆大建”**原则，重构路线分为两个阶段：

```mermaid
timeline
    title 落地演进路线
    阶段一 (立即处理 - P0/P1) : 修复 scheduler 漏 Tick (保持 now_provider 注入) : 完善新仓开仓-止损缝隙与部分成交处理 : 统一 SQLite 连接与添加锁耗时观测 : 统计历史实际成交滑点分布
    阶段二 (数据驱动演进 - P2)   : 根据滑点分布评估 IOC 限价单 : 根据锁指标决定是否收敛单进程 : 提速全市场 WebSocket 行情流 : 自动化高频表数据归档
```

### 阶段一：高优先级稳定性与执行层加固（建议立即执行）

#### 1. 修复 `scheduler.py` 窄时间窗口（P0）
- 保持 `now_provider` 与 `sleep_fn` 注入架构不变；
- 逻辑调整为计算精确睡眠时间至下一分钟整点，并在醒来时采用“补偿最近已收盘分钟”策略：
  ```python
  # 示例逻辑（保持依赖注入与测试兼容）
  now = now_provider()
  # 检查当前分钟是否已执行；若未执行且属于最近已收盘窗口（如 second <= 20），则触发
  minute_key = (now.year, now.month, now.day, now.hour, now.minute)
  if minute_key != last_seen_minute and now.second <= 20:
      run_once(now)
      last_seen_minute = minute_key
  ```
- 补充单测：第 3 秒唤醒、第 20 秒唤醒、长时间任务恢复等测试用例。

#### 2. 加固新仓开仓与止损链路（P0）
- **部分成交处理**：以实际成交数量 `executedQty`（若部分成交）挂出匹配数量的止损单；
- **错误分类**：精准解析交易所返回的错误码（`-2019 Margin is insufficient`、`-1003 Too many requests`、`-2021 Order would immediately trigger`），记录分类审计事件；
- **止损重试与告警**：入场后止损单多次重试仍失败时，触发强制告警，并视风控策略执行安全退出。

#### 3. SQLite 连接收敛与锁观测探针（P1）
- 全局扫描并替换零散的原生 `sqlite3.connect`，统一经由基础设施层连接工厂，配置 `timeout=30.0`、`PRAGMA busy_timeout=30000` 与 `WAL`；
- 所有只读查询（看板、历史分析）强制使用 `file:path?mode=ro`；
- **添加可观测性指标**：记录每次写事务的持锁耗时与冲突次数，让未来的数据库决策有据可查。

#### 4. 真实滑点测量（P1）
- 编写脚本统计最近 30 天实盘订单中，`MarketSnapshot.latest_price` 与实际成交价（`avgPrice`）的基点偏差（Bps）；
- 评估大名义仓位下的滑点是否显著超出预算，为后续是否引入限价 IOC 提供数据支撑。

---

### 阶段二：数据驱动的长期演进（P2）

1. **执行层滑点控制**：若滑点实测显示小币种冲击成本过高，设计带价格上限的 IOC 限价入场机制（需配套处理未成交撤单与实际成交对齐）；
2. **架构拓扑评估**：仅当阶段一的锁指标显示 SQLite 写竞争已切实影响实盘交易时，再评估是采用单进程异步核心、还是引入本地写入队列；
3. **行情提速**：在独立线程/进程中维护 `!miniTicker@arr` 全市场实时流，降低整点 REST 轮询延迟；
4. **存储生命周期管理**：为 `signal_decisions`、`dashboard_live_series` 等高频日志表设计定期滚动归档（Retention Pruning）策略。

---

## 六、 任务跟踪清单 (Action Items)

- [x] **[P0] 修复调度器时钟**：在保持 `now_provider` 注入的前提下修复 `scheduler.py` 漏 Tick 问题，补齐边界测试（已完成并通过 12 个调度器单元测试）。
- [x] **[P0] 止损数量对齐**：新仓入场挂止损时支持按 `executedQty` 动态对齐（覆盖部分成交），完善开仓后挂止损失败的细分类审计与错误码解析（已完成并通过全部 Broker 单元测试）。
- [x] **[P1] 统一数据库连接**：清理剩余裸 `sqlite3.connect`（覆盖 `health.py`、`dashboard_data_loader.py`、`stream_worker_loop.py`、`trade_data_sync.py`、`cli_backfill.py`、`cli_backfill_candidates.py`、`analytics_schema.py`），统一 WAL、30s 超时和 `readonly=True` 只读模式。
- [x] **[P1] 锁指标监控埋点**：在 `runtime_schema.py` 统一收敛 `begin_immediate_with_retry`，记录写锁获取总次数、锁竞争次数、总等待时长与最大等待时长（`get_sqlite_lock_stats()`），并闭环接入健康检查 `_check_sqlite_lock_health` 与 `poll_tick` 审计事件。
- [x] **[P1] 历史滑点统计**：新增 [`scripts/analyze_slippage.py`](../scripts/analyze_slippage.py) 及配套单测 [`tests/test_analyze_slippage.py`](../tests/test_analyze_slippage.py)，支持入场滑点（决策价 vs 实际成交均价）与止损出场滑点（触发价 vs 实际出场均价）的分位数统计、按仓位腿/币种拆解及 CSV/JSON 导出。
- [x] **[P2] 行情流提速**：新增 [`market_data_ticker_stream.py`](../src/momentum_alpha/market_data_ticker_stream.py) 接入 Binance `!miniTicker@arr` 全市场广播流，在 `LiveMarketDataCache` 中实现内存行情零延迟极速快查并自动透明降级至 REST（单元测试通过）。
- [x] **[P2] 存储生命周期管理**：在 [`runtime_cleanup.py`](../src/momentum_alpha/runtime_cleanup.py) 中支持 `signal_decisions` 与 `dashboard_live_series` 定期清理与 `PRAGMA optimize`，配套新增维护脚本 [`scripts/run_prune_runtime_db.sh`](../scripts/run_prune_runtime_db.sh) 及 systemd 定时任务 [`deploy/systemd/momentum-alpha-prune-runtime-db.timer`](../deploy/systemd/momentum-alpha-prune-runtime-db.timer)。
- [x] **[P2] 读写分离与专用读模型（OperationalReadModel）**：新增 [`operational_read_model.py`](../src/momentum_alpha/operational_read_model.py)，构建线程安全的纯内存预聚合读模型与后台异步刷新 Worker（Zero-I/O），将外部看板/API 访问的数据库毫秒级锁竞争降至接近 0，响应速度压降至亚毫秒/毫秒级。
- [x] **[P2] 状态按需懒加载（Lazy Loading）**：在 [`dashboard_data_loader.py`](../src/momentum_alpha/dashboard_data_loader.py)、[`dashboard_render_shell.py`](../src/momentum_alpha/dashboard_render_shell.py) 与 [`dashboard_server.py`](../src/momentum_alpha/dashboard_server.py) 中实现分级按需加载（按房间裁剪冷数据、懒渲染 HTML 面板、新增 `/api/dashboard/review` 独立冷数据按需路由），消除首屏 8 张重型历史表的无谓全量反序列化。
