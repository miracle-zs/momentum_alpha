# Momentum Alpha 代码检查报告

- **日期**:2026-07-26
- **范围**:`src/momentum_alpha/` 全部 140 个模块、`tests/`、`deploy/`(systemd 单元与启动脚本)、`scripts/`
- **方法**:6 路并行子系统审查(策略核心、执行下单、交易所集成、进程编排与 CLI、持久化、看板与报表),全部高危与绝大多数中危发现均经人工回读源码逐条核实,其中 1 项用脚本实际复现;交叉比对后驳回 1 项误报
- **测试基线**:`python -m unittest discover -s tests` — **554 个测试全部通过**

## 总体结论

项目整体工程质量高于同类个人交易系统:纯函数策略层、幂等键设计、WAL + `BEGIN IMMEDIATE` 原子读改写、"先挂新止损再撤旧"的安全顺序、数量向下取整保证风险不超预算、每分钟 REST 对账兜底等,都是正确且用心的设计。554 个测试全过。

但仍发现 **6 个高危问题**(有真实资金风险或核心状态破坏)、约 **20 个中危问题**、约 20 个低危问题。最值得关注的三类根因:

1. **订单幂等恢复的两个漏洞**(把"查询失败"当"订单不存在"、不校验恢复到的订单状态)——极端网络条件下可能双倍建仓或整小时静默丢单;
2. **双进程对共享状态的字段归属约定已经被打破**——user-stream 进程整体覆写 `recent_stop_loss_exits`,会抹掉止损冷却,导致刚被止损的币种被过早重新买入;
3. **风险模型无护栏**——定仓公式 `预算 ÷ 止损距离` 在距离极小时名义仓位无上界,市价单滑点可使单笔实际亏损达预算的数倍到数十倍。

---

## 一、高危问题(HIGH)

### H1. 入场单幂等恢复把"查询失败"当成"订单不存在",可能用同一 clientOrderId 重复下市价单 → 仓位翻倍
- **位置**:[broker.py:110-116](src/momentum_alpha/broker.py:110)、[broker.py:130-144](src/momentum_alpha/broker.py:130)
- **问题**:提交入场单遇瞬时错误后,`_fetch_existing_entry_order` 查询恢复;但该函数对"确认不存在(-2013)"和"查询本身失败(网络错误)"都返回 `None`,调用方无法区分,于是在状态未知时继续重发。
- **失败场景**:① POST 下单因网络抖动超时,但请求实际已到达交易所并成交(MARKET 单立即成交);② 紧随其后的恢复查询因同一抖动失败(非 -2013),返回 None;③ 0.2 秒后重试用**同一 clientOrderId** 重发——币安期货的 `newClientOrderId` 只要求在未结订单中唯一,已成交的市价单不再是未结订单,重发被接受 → **仓位为计划的 2 倍**,而止损只按 1 倍数量挂出(下一分钟覆盖对账会补齐止损数量,但敞口已翻倍)。网络抖动恰恰会让两个请求相关联地一起失败,该场景在抖动期间概率不低。
- **建议**:只有恢复查询**明确返回 -2013** 时才允许重发;查询失败(状态未知)时记为 retryable 失败留给下一 tick——下一 tick 提交前的 pre-check(broker.py:85-88)天然能安全恢复。

### H2. 幂等恢复不校验订单状态:EXPIRED/CANCELED 的死单被当作"已提交成功"
- **位置**:[broker.py:130-137](src/momentum_alpha/broker.py:130)、[broker.py:85-88](src/momentum_alpha/broker.py:85)
- **问题**:`_fetch_existing_entry_order` 把 `fetch_order` 返回的任何订单(不看 `status`/`executedQty`)都当作已提交成功直接返回。
- **失败场景**:加仓单的 clientOrderId 按小时桶稳定(execution.py:47-50)。若某次加仓市价单被交易所置为 `EXPIRED`(撮合过载、价格保护、零成交),本小时内每次重试都会在 pre-check 命中这张死单并跳过真实下单 → **整小时加仓静默丢失**;同时代码认为 entry 成功,继续挂对应止损单(仓位不存在,reduceOnly 止损被拒,再触发一轮无意义修复)。因为死单算"成功响应"而非失败,`last_add_on_hour` 照常前移、base 信号槽也不释放。
- **建议**:恢复时校验状态——`FILLED`/`PARTIALLY_FILLED`/`NEW` 视为已存在;`EXPIRED`/`CANCELED`/`REJECTED` 且 `executedQty==0` 视为未成交,允许重发。

### H3. 用户流事件去重 ID 碰撞:币安对非成交事件发送 `"t":0`,同一订单的 NEW 与 CANCELED 生成相同 ID
- **位置**:[user_stream_event_ids.py:15-16](src/momentum_alpha/user_stream_event_ids.py:15)、[user_stream_event_parser.py:52](src/momentum_alpha/user_stream_event_parser.py:52)
- **问题**:`if event.trade_id is not None: return f"...:trade:{event.trade_id}"`,而币安 USDⓈ-M 的 `ORDER_TRADE_UPDATE` 对 NEW/CANCELED/EXPIRED 等非成交事件始终携带 `"t":0`。`0 is not None` 为真,同一订单的所有非成交生命周期事件都生成同一个 ID `ORDER_TRADE_UPDATE:{orderId}:trade:0`;按 `execution_type:order_status:event_time` 区分的 state 分支在真实报文里几乎永远走不到。现有测试构造的报文不含 `t` 字段,恰好掩盖了此 bug。
- **失败场景**:订单先推 NEW(ID 记入已处理集合,保留 24h),随后同一订单被撤销推 CANCELED(ID 相同)→ 在 stream_worker_core.py:188-190 被当作已处理直接丢弃。后果:`order_statuses` 中该订单永久停留在 `NEW`(直到下次重连全量重建);① 已撤销的止损单被 `_is_strategy_stop_order_for_symbol` 视为活跃 → 之后任何持仓归零(含手动平仓)都被误判为止损离场,错误写入冷却;② `resolve_stop_price_from_order_statuses` 会把已撤销的旧止损价恢复到新持仓上。
- **建议**:把 `t==0` 视同缺失(改为 `if event.trade_id:`),让非成交事件走 state 分支;补一条带 `"t":0` 的 NEW→CANCELED 测试。

### H4. user-stream 保存状态时整体覆写 `recent_stop_loss_exits`,抹掉 poll 写入的止损冷却 → 刚止损的币种被过早重新买入
- **位置**:[stream_worker_core.py:102](src/momentum_alpha/stream_worker_core.py:102)(对照 poll 侧合并语义 [poll_worker_core_state.py:37-38](src/momentum_alpha/poll_worker_core_state.py:37))
- **问题**:stream 的 updater 返回 `recent_stop_loss_exits=state.recent_stop_loss_exits`——用自己的内存快照整体覆写,不与数据库中现值合并;而 stream 的内存状态只在**进程启动时**读一次库,重连也不回读。poll 侧则是合并语义。三路审查独立发现同一问题,并经人工回读确认。
- **失败场景**:stream 断线期间止损单成交 → poll 对账检测到持仓消失,写入冷却时间(`_apply_restored_stop_loss_cooldowns`,这个兜底恰是为漏事件设计的)→ stream 重连后处理任意一条事件即保存 → **冷却条目被删**。对隔夜仓(当日信号槽已随日切重置,`daily_repeat_base` 不拦截),该币种若再登顶领涨,60 分钟冷却(strategy.py:85)完全失效,立即重新入场——真实资金层面的过早重入。
- **建议**:stream 的 updater 对 `recent_stop_loss_exits` 改为与 existing 按 symbol 取较大时间戳合并(与 positions 的合并方式一致);`order_statuses` 同样建议改为合并语义。

### H5. 定仓无名义价值上限、市价成交无滑点护栏:止损距离极小时,单笔实际风险可达预算的数倍到数十倍
- **位置**:[sizing.py:14-21](src/momentum_alpha/sizing.py:14)、[execution.py:35-44](src/momentum_alpha/execution.py:35)、[orders.py:41-59](src/momentum_alpha/orders.py:41)
- **问题**:`数量 = 止损预算 ÷ (入场价 − 止损价)`,只有下限检查(minQty/minNotional),没有任何名义价值上限或最小止损距离阈值;入场是无保护的 MARKET 单,数量按快照价计算。
- **失败场景**:领涨切换时价格恰好略高于上一小时低点(如 entry=1.0005、stop=1.0000,距离 0.05%)→ 名义仓位 = 10/0.0005 = **20,000 USDT**。该策略专挑当日暴拉的小币,薄簿上市价单入场滑点 + 止损市价单穿价滑点,单笔实际亏损轻松达到预算(10 USDT)的数倍到数十倍;若数量超过交易所 maxQty 则整笔机会被静默放弃(另一种失真)。这是全系统最大的单点资金风险。
- **建议**:增加 `max_notional_usdt` 配置(超限缩量或拒单并记录原因);对 `距离/入场价` 设最小相对止损距离阈值;考虑用保护性限价(如 `latest × (1+x%)` 的 LIMIT IOC)替代裸市价单。

### H6. 分析重建在单个长写事务内全历史重算,三个调度源并发,SQLite 默认 5 秒锁超时且全部写方无重试 → 实盘状态保存失败、用户流断连
- **位置**:[runtime_analytics_rebuild.py:274-329](src/momentum_alpha/runtime_analytics_rebuild.py:274)(DELETE 后在同一事务内做全表 JSON 解析与重算)、[runtime_schema.py:264](src/momentum_alpha/runtime_schema.py:262)(`sqlite3.connect(path)` 未设 timeout/busy_timeout)
- **问题**:重建先 `DELETE FROM trade_round_trips`(开启写事务),随后在**持有写锁**的状态下对全部 `broker_orders`/`signal_decisions` 历史逐行 `json.loads` 并重算。并发源有三:stream worker 每笔成交后 30 秒防抖触发、systemd timer 每 15 分钟一次、每日复盘脚本一次。数据量随运行时长单调增长(见 M13),持锁时间必然超过 5 秒。
- **失败场景**:重建持锁期间,poll worker 恰好**已向币安提交真实订单**、随后调用 `_save_strategy_state` → `BEGIN IMMEDIATE` 等 5 秒后抛 `database is locked`,异常被 run_loop 吞掉 → **订单已发但状态未保存**(`last_add_on_hour` 不推进、当日信号丢失,下一 tick 依赖 clientOrderId 碰撞才不重复下单);stream 侧同样的锁错误会令事件回调抛异常 → 整条 websocket 断开重连,币安不重放事件,该成交只能靠 15 分钟后的 REST 回补。
- **建议**:(a) `_connect` 设 `timeout=30` 并执行 `PRAGMA busy_timeout=30000`;(b) 重建改为"事务外完成全部计算 → 短事务内 DELETE+批量 INSERT";(c) 三个调度源收敛为一个或加文件锁互斥;(d) 关键状态写入增加有界重试。

---

## 二、中危问题(MEDIUM)

### A. 双进程状态一致性

**M1. stream 每次保存把整个内存持仓表合并回库,会复活 poll 刚删除的仓位**
[stream_worker_core.py:81-85](src/momentum_alpha/stream_worker_core.py:81)。stream 漏收平仓事件时,poll 经 REST 对账把持仓 X 从库中删除;stream 随后任一无关事件的保存又把内存中的 X 合并回去(每分钟一删一加振荡,直到 stream 重连)。期间 `already_holding` 可能错误拦截合法入场、看板显示幽灵持仓。建议:stream 只写本事件涉及的 symbol,而非整个内存表。

**M2. user-stream 入场成交事件把整仓止损价清零(已复现)**
[user_stream_state.py:88](src/momentum_alpha/user_stream_state.py:88) `stop_price = event.stop_price if ... else Decimal("0")` — MARKET 入场单事件无 stopPrice → 0;[execution.py:150](src/momentum_alpha/execution.py:150) `position.with_stop_price(stop_price)` 把仓位及全部腿的止损写成 0。**每笔实盘成交都走此路径**,依赖下一次 poll 对账从交易所挂单恢复;poll 停止期间持续为 0,看板风险显示错误,`_has_strategy_stop_evidence` 由此失真。建议:事件无 stopPrice 时保留原止损价,不要传 0。

**M3. `run-once-live` 会写共享状态(干跑也写)且从不恢复持仓——文档推荐的排查命令会干扰实盘服务**
[cli_commands_live.py:43-52](src/momentum_alpha/cli_commands_live.py:43)、[poll_worker_core_live.py:414-444](src/momentum_alpha/poll_worker_core_live.py:414)。CLAUDE.md 推荐的干跑命令若与实盘服务共用 runtime.db:干跑会覆写 `previous_leader_symbol` 与当日信号表 → 实盘服务下一 tick 被 `leader_unchanged`/`daily_repeat_base` 拦截,**真实入场被一次"只是看看"的干跑吞掉**;带 `--submit-orders` 手动执行时因不恢复持仓、不加载冷却,可对服务已持有的币种重复建仓。建议:run-once-live 默认恢复持仓;非 `--submit-orders` 时跳过状态保存。

**M4. 实盘下单模式不强制持仓恢复:`poll --submit-orders` 缺 `--restore-positions` 时风控全部静默失效**
[poll_worker_core_live.py:237-242](src/momentum_alpha/poll_worker_core_live.py:237)。restore_positions=False 时 positions/冷却恒为空且不读存储 → `already_holding`、止损冷却、加仓、止损棘轮全部失效(仅 `daily_repeat_base` 兜底防同日重复)。生产脚本 run_poll.sh 固定带全套旗标所以标准部署安全,但 CLI 完全允许危险组合。建议:`submit_orders=True` 强制隐含持仓恢复,或拒绝启动。

**M5. 空市场快照把 `previous_leader_symbol` 清成 None → 数据恢复后把"未变的领涨"误判为切换而入场**
[strategy.py:64-72](src/momentum_alpha/strategy.py:64)、[runtime.py:88-93](src/momentum_alpha/runtime.py:88)。行情接口某分钟返回空数组(HTTP 200,非异常路径)→ 该 tick 持久化 previous_leader=None → 下一分钟持续领涨的 X 与 None 比较判为"切换",凭空触发 base 入场,违背"仅在领涨易主时入场"的设计。建议:leader 为 None 时保留原 previous_leader 不写库。

**M6. `poll --previous-leader X` 把对比基准永久钉死**
[poll_worker_loop.py:105](src/momentum_alpha/poll_worker_loop.py:105)(闭包参数每 tick 原样传入)、[poll_worker_core_live.py:234-235](src/momentum_alpha/poll_worker_core_live.py:234)(仅参数为 None 才回读存储)。带该旗标长期运行时,任何 ≠X 的领涨每天都被判定为"切换"并入场一次(含从未易主的标的)。建议:该值只用于首 tick,之后强制用存储值;或从 poll 命令移除该旗标。

### B. 交易执行链路

**M7. 限频异常在 entry 成交后、止损挂出前中断整个 tick,且退避期内所有 tick 被跳过 → 裸仓位最长可达整个退避窗口**
[broker.py:77-79](src/momentum_alpha/broker.py:77)(止损提交遇 418/429 直接 raise)、[poll_worker_loop.py:93-95](src/momentum_alpha/poll_worker_loop.py:93)(退避期完全跳过 tick)。entry 已成交 → 止损遇 429 → 异常上抛,同 tick 修复与状态保存全部跳过;429 兜底退避 120 秒(418 可达数十分钟),期间覆盖对账也不运行。追暴拉币的策略在这种时刻恰恰最需要止损。建议:退避结束后的首个动作优先补挂止损;或对"entry 已成交但止损未挂"的 symbol 做进程内标记,退避一结束立即单独补挂。

**M8. 止损覆盖修复在"价格已跌破候选止损价"时静默放弃 → 裸仓窗口出现在最需要保护的暴跌时刻**
[reconciliation.py:196-201](src/momentum_alpha/reconciliation.py:196)。入场后价格快速下砸、止损单被拒(-2021),修复时上一小时低点与当前小时低点都 ≥ 现价 → 修复计划为空,持仓完全无保护直到某分钟出现合法价位。建议:找不到合法止损价时直接市价平仓或按"现价下一档"挂保护性止损,并强制告警。

**M9. broker 的交易规则缓存永不刷新:tickSize/stepSize 变更后,止损替换将持续失败直到进程重启**
[broker.py:167-173](src/momentum_alpha/broker.py:167) `if self._exchange_symbols is None` 只拉一次。币安不时调整合约价格精度;此后替换单用旧 tick 网格生成触发价被拒 → 每小时替换失败、止损再也无法上移(每 tick 刷新的 LiveMarketDataCache 与 broker 私有缓存互相独立)。建议:替换失败(价格过滤类错误)时置空缓存强制重拉,或复用每 tick 刷新的映射。

**M10. base 入场的瞬时失败既不重试也不释放当日信号槽 → 当天机会静默丢失**
[broker.py:118-127](src/momentum_alpha/broker.py:118)(耗尽重试记 retryable=True)、[poll_worker_core_live.py:114-122](src/momentum_alpha/poll_worker_core_live.py:114)(仅释放 `retryable is False`)。加仓有对称重试机制(不推进 last_add_on_hour),base 没有:previous_leader 已更新 → 此后被 `leader_unchanged`/`daily_repeat_base` 拦到次日。信号分钟遇上几秒网络抖动,当天入场就没了(仅审计有记录)。建议:retryable 的 base 失败下一 tick 用同一 clientOrderId 重试(幂等已具备)。

**M11. `last_add_on_hour` 仅存内存:进程在小时中段重启会静默吞掉该小时的加仓评估**
[poll_worker_loop.py:60,96-97](src/momentum_alpha/poll_worker_loop.py:96)。01:55 崩溃、02:30 重启 → 播种为当前小时 → 02:00 边界的加仓被认定"已执行"。止损棘轮有 stale 对账兜底,加仓机会本身丢失。建议:持久化该值,或重启时查询本小时是否已有加仓订单。

### C. 网络与连接健壮性

**M12. 重连循环中 `_prewarm_state()` 位于退避保护之外:一次 REST 瞬时故障即杀死 user-stream 进程,systemd 10 秒重启循环撞墙**
[stream_worker_loop.py:433-435](src/momentum_alpha/stream_worker_loop.py:433)。断网触发重连 → 循环顶部的 prewarm 里 `fetch_position_risk()` 无异常保护 → 异常冒出进程退出;网络未恢复期间每 10 秒崩一次,每次重启都发多个签名请求,限频期间等于绕过精心实现的封禁退避。建议:把 prewarm 移入与流周期相同的退避结构。

**M13. WebSocket 无死连接检测(`ping_interval=0`),心跳与看门狗都存在"永久满足"漏洞**
[user_stream_client.py:173](src/momentum_alpha/user_stream_client.py:173);看门狗门控 [stream_worker_loop.py:107-122](src/momentum_alpha/stream_worker_loop.py:107)。NAT 静默丢弃连接后 recv 永久阻塞;心跳线程独立运行仍每 60 秒上报 `stream_active: True`;看门狗只在"本轮流周期内有 broker 动作且晚于最后事件"时才判定异常——最后动作之后收到过一个事件即永久满足。止损成交事件全部丢失,仅靠 poll 分钟级对账兜底,`trade_fills` 遥测永久缺失。建议:`run_forever(ping_interval=..., ping_timeout=...)`;心跳纳入"最后消息年龄"。

**M14. 生产 REST 客户端零重试 + 调度器把失败分钟标记为已消费:单次瞬时网络错误丢弃整个交易 tick(含止损维护)**
[cli.py:57-64](src/momentum_alpha/cli.py:57)(从不传 `retry_delays`,默认空)、[scheduler.py:11-19](src/momentum_alpha/scheduler.py:11)。任一行情请求瞬时 5xx → 整个 tick 异常放弃,60 秒后才有下一次机会;keepalive 单次 PUT 失败也会触发整条流拆除重建。客户端明明实现了完善的重试/封禁解析,生产路径从未启用。建议:对幂等 GET 启用小额重试(勿对 POST 启用,见 D8)。

### D. 运维、部署与监控

**M15. 生产部署从不执行任何清理,`prune_runtime_db` 也只覆盖 3 张表 → 数据库无界增长,与 H6 的锁冲突概率复利式上升**
[runtime_cleanup.py:23-58](src/momentum_alpha/runtime_cleanup.py:23);deploy/systemd 全目录无任何单元调用 prune。`signal_decisions` 每分钟至少一行(约 1440 行/天)、`broker_orders`/`trade_fills`/`account_flows`/`trade_round_trips` 永不清理。注意:一旦给 `trade_fills` 设保留期,必须先解除"round trips 每次从全量 fills 重算"的耦合(见 D5)。

**M16. 看板在"数据库文件存在但表未建/单行损坏"时全站不可用——而启动脚本恰好保证文件存在**
[scripts/run_dashboard.sh:18](scripts/run_dashboard.sh)(`touch` 建空文件)、[dashboard_data_loader.py:97](src/momentum_alpha/dashboard_data_loader.py:97)(第一个无保护查询先于任何 bootstrap)、[dashboard_server.py:40-88](src/momentum_alpha/dashboard_server.py:40)(do_GET 无异常处理,且快照加载先于 404 分发)。新部署时若 poll 服务启动失败(如 API key 错误),监控恰在最需要时整体死掉;单行损坏的 payload_json 也会永久打死所有页面。建议:do_GET 顶层兜底 500;逐 fetch 降级为警告;分发路径先于快照加载。

**M17. systemd 定时器使用无效的 `Timezone=` 键:每日复盘在系统时区 08:30 运行(UTC 主机上晚 8 小时)**
[deploy/systemd/momentum-alpha-daily-review-report.timer](deploy/systemd/momentum-alpha-daily-review-report.timer)。systemd [Timer] 无 `Timezone=` 选项,被忽略。修复:`OnCalendar=*-*-* 08:30:00 Asia/Shanghai`(systemd ≥235)。

**M18. 告警管道在"健康检查自身崩溃"时静默失败——系统最坏的状态反而不发通知**
[serverchan.py:26-30](src/momentum_alpha/serverchan.py:26)(输出缺 `overall=` 行时直接 raise)。健康检查脚本崩溃输出 traceback → 通知器解析失败退出非零,无人监控通知器自身。建议:解析失败视为 FAIL 并把原始文本作为通知体发送。

### E. 分析与报表正确性

**M19. 回放 K 线缓存把"不完整的当日"永久落盘,此后的回放静默使用残缺数据**
[skipped_base_replay_data.py:292-300](src/momentum_alpha/skipped_base_replay_data.py:292)。缓存键为 `symbol:日期`,抓取当前(未走完的)UTC 日只存下已过去的分钟;当天后续运行(默认不刷新)全部复用残缺数据,表现为莫名的 `missing_previous_hour_candles`、漏判止损、错的截止标记价——PnL 悄悄失真。建议:当日数据不落盘或标记为 partial 强制重取。

**M20. 一个未解析的种子会永久压制该币之后的全部影子机会**
[skipped_base_replay.py:554-577](src/momentum_alpha/skipped_base_replay.py:554)。未解析结果(`exit_at=None`)被记入 `active_by_symbol` 后,同币后续种子(哪怕几天后)全部判为 `overlap_existing_shadow` 不再回放,"按拦截原因统计的 PnL" 系统性低估。建议:unresolved 结果不进 active 表。

**M21. 每日复盘的反事实计算在缺出场价时按 0 计算 → 单腿贡献巨额负收益且无警告**
[daily_review.py:207-212,251](src/momentum_alpha/daily_review.py:207)。`weighted_avg_exit_price` 缺失时回退 "0",每个回放加仓腿贡献 `(0−入场价)×数量`,污染 counterfactual 与看板"累计过滤影响"。建议:出场价 ≤0 时跳过该笔回放并追加 `missing_exit_price` 警告。

**M22. 看板范围标签(1M/1Y/ALL)与底层数据覆盖严重不符**
快照保留 7 天([runtime_cleanup.py:12](src/momentum_alpha/runtime_cleanup.py:12))但权益/回撤面板提供 1M/1Y/ALL 档;领涨历史只扫最近 ~100 行(约 50 分钟);滑点/止损统计固定取最近 20 条。用户读到的"1Y 轮换次数"实际是不足一小时的数据。建议:范围感知查询 + 标注实际数据覆盖。

**M23. 持仓一旦脱离跟踪列表/快照宇宙即被静默弃管**
[market_data_snapshots.py:24](src/momentum_alpha/market_data_snapshots.py:24)(只为 `symbols` 列表构建快照)、[strategy.py:160-161](src/momentum_alpha/strategy.py:160)。`--symbols` 白名单不含某持仓币、或该币被摘牌(exchange_info 过滤 `status != TRADING`)时:无止损追踪、无加仓、无任何告警,只剩交易所侧静态止损单。建议:把持仓 symbol 并入快照构建集合;无法取得行情的持仓发显式告警。

---

## 三、低危问题(LOW)

| # | 位置 | 问题 | 影响 |
|---|------|------|------|
| L1 | [strategy.py:238-241](src/momentum_alpha/strategy.py:238) | 小时评估未过滤 `has_previous_hour_candle=False`(低点取 0) | K 线缺失时加仓沿用旧止损价,定仓仍守预算,语义偏离 |
| L2 | [config.py:18-25](src/momentum_alpha/config.py:18) | `STOP_BUDGET_USDT` 非法/非正时静默回退 10,无日志 | 配置写错时以错误预算实盘运行;其余字段完全无校验 |
| L3 | [poll_worker_core_state.py:11-18](src/momentum_alpha/poll_worker_core_state.py:11) | 时间比较抛 TypeError/ValueError 时按"未重开"处理并**删除**存储持仓 | 失败方向不安全;遗留 naive 时间戳数据会误删腿历史 |
| L4 | [models.py:18](src/momentum_alpha/models.py:18) | `current_hour_low` 默认 `Decimal("0")` | 现有两条构造路径均安全(已核实),未来漏传该字段会产生 stop=0 委托 |
| L5 | [strategy.py:34-38](src/momentum_alpha/strategy.py:34) | naive datetime 被 `astimezone` 按本地时区解释,与 `_as_utc` 语义不一致 | 仅影响以 naive 时间调用纯函数的回测/脚本 |
| L6 | run_poll.sh / [cli_commands_ops.py:216](src/momentum_alpha/cli_commands_ops.py:216) | `SUBMIT_ORDERS` 三处解析不一致(`=="1"` vs 扩展真值集 vs 不读) | `SUBMIT_ORDERS=true` 时服务实际干跑而看板显示 LIVE |
| L7 | [health.py:84-85](src/momentum_alpha/health.py:84) | 新鲜度查询自身失败时 strategy_state 返回 OK | 监控假阳性 |
| L8 | [cli_env.py:74-78](src/momentum_alpha/cli_env.py:74) | 工厂函数内部的 TypeError 被吞并降级为不带 testnet 重建客户端 | 潜在把"testnet 运行"静默指向生产 |
| L9 | [broker.py:244-252](src/momentum_alpha/broker.py:244) | 撤旧止损失败仅日志,不入失败列表,且吞掉 418/429 | 双止损残留污染覆盖对账的数量合计;限频期间继续发撤单请求 |
| L10 | [execution.py:43](src/momentum_alpha/execution.py:43) | MIN_NOTIONAL 只按入场价校验,止损单名义价值(qty×stop)未校验 | `price>3×stop` 时止损名义价值可跌破 5 USDT(交易所对 reduceOnly 条件单是否强制该过滤存在不确定性) |
| L11 | [execution.py:35-40](src/momentum_alpha/execution.py:35) | 定仓用取整前的止损价;normalize 向下取整最多多 1 tick 风险 | 止损距离仅几个 tick 时超预算比例可观;K 线低点天然对齐网格,实际罕见 |
| L12 | [poll_worker_core_live.py:225-233](src/momentum_alpha/poll_worker_core_live.py:225) | 双向持仓模式探测失败静默按单向模式下单 | 对冲模式账户该 tick 全部被 -4061 拒单,下一 tick 自愈 |
| L13 | [execution.py:32-44,101-102](src/momentum_alpha/execution.py:32) | 四处 `return None` 静默丢弃入场意图,无审计事件 | "有信号无订单"时无法排障(信号槽有释放补偿) |
| L14 | [reconciliation.py:69](src/momentum_alpha/reconciliation.py:69) | REST 恢复用 positionRisk.updateTime 当 opened_at | 无存量历史时首次加仓 30 分钟门槛从恢复时刻重算 |
| L15 | [user_stream_account_positions.py:23,42](src/momentum_alpha/user_stream_account_positions.py:23) | 负持仓量(手动翻空)既非 flat 也非 positive,残留幽灵多头 | 状态错误直到 poll 对账;reduceOnly 保证不超卖 |
| L16 | [binance_client.py:224-239](src/momentum_alpha/binance_client.py:224) | 响应体读取超时(`TimeoutError`)绕过重试与 BinanceHttpError 包装 | 行情路径日志/重试不一致;下单路径 broker 侧已防护 |
| L17 | [user_stream_account_positions.py:52-71](src/momentum_alpha/user_stream_account_positions.py:52) | 止损价恢复取插入序第一个活跃止损 | 替换窗口内(新旧并存)可能恢复旧价;正常事件流自愈 |
| L18 | [stream_worker_loop.py:356-368](src/momentum_alpha/stream_worker_loop.py:356) | 重连重建常规订单快照漏存 `client_order_id`(algo 分支有) | 常规止损单重启后无法用于止损价恢复/离场分类 |
| L19 | [runtime_schema.py:359](src/momentum_alpha/runtime_schema.py:359) | 迁移中 `CREATE UNIQUE INDEX` 无 `IF NOT EXISTS`(其余均有)+ 列检查 check-then-act | 双服务同时冷启升级时一侧首个动作报错崩溃,靠重启自愈 |
| L20 | [runtime_schema.py:60-61](src/momentum_alpha/runtime_schema.py:60) | `broker_orders.quantity/price` 用 REAL,违反全库 TEXT-Decimal 约定 | 止损触发价经 float 往返形式漂移,滑点统计微小偏差 |
| L21 | [stream_worker_core.py:150-190](src/momentum_alpha/stream_worker_core.py:150) | 幂等去重检查位于遥测写入之后 | 重复投递事件产生重复 audit/broker_orders 行(trade_fills 有唯一索引兜底) |
| L22 | [runtime_reads_events_audit.py:10-12](src/momentum_alpha/runtime_reads_events_audit.py:10) | 读路径执行 bootstrap,配错路径时静默创建空库 | 掩盖配置错误 |
| L23 | [user_stream_event_extractors.py:70-75](src/momentum_alpha/user_stream_event_extractors.py:70) | 仅止损成交从 order_statuses 移除,其余终态永驻状态 JSON | 状态 blob 缓慢膨胀,重连时收敛 |
| L24 | [runtime_reads_history_overview.py:94-99](src/momentum_alpha/runtime_reads_history_overview.py:94) | 审计汇总用"最近 max(limit,500) 条"近似时间窗 | 活跃时段统计偏低;应改为按时间过滤(索引已存在) |
| L25 | [dashboard_render_panels_account.py:80](src/momentum_alpha/dashboard_render_panels_account.py:80) | 内嵌 JSON script 块未做 `</` 转义(相邻面板做了) | 潜在 XSS 载体(当前数据源为币安 symbol,不可利用) |
| L26 | [serverchan.py:61,105](src/momentum_alpha/serverchan.py:61) / check_health_and_notify.sh | sendkey 经命令行参数传递(本机 `ps` 可见);stdin 模式只读一行 | 本机凭据暴露面;通知正文丢失详情行 |
| L27 | [logging_config.py:9-31](src/momentum_alpha/logging_config.py:9) | 两种日志格式都不带时间戳,而服务用文件追加(无 journald 前缀) | 生产日志无法定位时间,事故取证困难 |
| L28 | [dashboard_view_model_metrics.py:86-140](src/momentum_alpha/dashboard_view_model_metrics.py:86) | "Today Net PnL" 实为"最新数据日 PnL"(窗口锚定最新数据而非 now) | 数据断流时昨日盈亏被标为今日 |
| L29 | [dashboard_server.py:47-57](src/momentum_alpha/dashboard_server.py:47) | 所有请求(含 404/favicon)先执行全量 ~20 查询快照加载;页面每 5 秒全量自刷 | 纯浪费,随库增长线性变慢 |
| L30 | [dashboard_server.py:31-32](src/momentum_alpha/dashboard_server.py:31) | 看板显示默认入场窗口/预算而非 poll 实际环境配置 | 配置改动后系统面板显示失真 |

---

## 四、设计层面观察

**D1. 双进程共享单行 JSON blob,正确性依赖"字段归属约定",而约定已经出现裂缝。**
`atomic_update`(BEGIN IMMEDIATE)保证单次读改写原子,但 poll 与 stream 各自的 merge 函数手工决定哪些字段覆盖、哪些合并(poll:[poll_worker_core_state.py](src/momentum_alpha/poll_worker_core_state.py);stream:[stream_worker_core.py:74-103](src/momentum_alpha/stream_worker_core.py:74))。H4/M1 都是该约定的违反;任何新增字段默认落入"最后写者赢"。且 stream 内存态在整个流周期内从不与存储重同步,每次写都是潜在的旧值覆写。建议:按字段拆分所有权(poll_state/stream_state 两行),或所有状态变更收敛到单一进程。

**D2. 风险模型假设"按快照价成交、止损不穿价"(与 H5 同根)。**
固定止损预算在市价滑点、跳空、极小止损距离三种情况下都不封顶;系统没有最大名义、最大杠杆占用、最小止损距离任何一种护栏。这是最值得优先补的安全网。

**D3. 实盘安全依赖 CLI 旗标组合而非模式内在属性。**
`--submit-orders` 可以脱离 `--restore-positions`/`--execute-stop-replacements` 运行(M3/M4);裸仓修复等兜底也挂在这些旗标下。安全默认应当是:实盘下单自动隐含持仓恢复与止损维护,旗标只用于显式关闭。

**D4. UTC 午夜锚定 + 领涨记忆 + 北京 9 点封锁叠加出系统性盲区。**
"日涨幅"以 UTC 00:00 首根 1m K 线开盘价为基准(内部一致,非 bug;但与币安 UI 的 24h 滚动涨幅不同,须知悉)。00:00 全场涨幅归零,leader 由噪声决定,而 previous_leader 跨午夜保留、北京 9 点(=UTC 01:00-01:59,恰为入场窗口第一小时)封锁又会消费领涨切换事件——净效果:**凡在 UTC 00:00-01:59 建立且保持的领涨地位,当日永远无法触发 base 入场**(除非中途易主再回归)。若这是有意行为,应写进文档;否则考虑在封锁小时不更新 previous_leader。

**D5. 分析重建 = 全历史擦除重算,ID 不稳定,与数据保留策略结构性矛盾。**
`round_trip_id = symbol:sequence` 在任何历史成交增删后整体漂移;重建的多条 SELECT 分属不同快照,读集不一致(下次重建自愈);因为每次都从原始 fills 重算,任何对 fills 的裁剪都会静默改写历史分析——而不裁剪又与无界增长(M15)矛盾。建议:已闭合交易固化为事实表 + 增量重建 + 确定性 ID(如首笔 entry 的 trade_id)。

**D6. 回放与实盘的逻辑漂移是结构性的。**
影子回放按止损价精确出场、零滑点(实盘止损平均滑点为负),反事实系统性乐观;加仓资格依赖整点分钟的 signal_decisions 行,实盘一次 :00 tick 延迟就变成回放里的 `missing_leader_data`。建议:回放与实盘共享同一决策模块,滑点用实测分布注入。

**D7. 看板无鉴权、单管道、线程无上限。**
全部账户/持仓/订单数据仅靠 `127.0.0.1` 默认绑定保护,`DASHBOARD_HOST=0.0.0.0` 一个环境变量即全暴露;ThreadingHTTPServer 每连接一线程无上限;所有端点共享一个 `load_dashboard_snapshot`,任一数据缺陷全站失效(M16)。至少:非回环绑定要求 token;按面板拆分加载与错误隔离。

**D8. 传输层对非幂等 POST 的盲重试是潜伏的重复下单脚枪。**
[binance_client.py:244-315](src/momentum_alpha/binance_client.py:244):一旦任何调用方以非空 `retry_delays` 构造客户端,`POST /fapi/v1/order` 会在 5xx/URLError 后以同一 clientOrderId 盲目重发(执行状态未知)。当前生产未启用(默认空),但 M14 的修复若不慎对 POST 开启重试,会绕过 broker 层的幂等防护。建议:在 send 层把重试限定为幂等方法,永久排除下单 endpoint。

**D9. 无信号处理。**
SIGTERM(`systemctl restart`)可落在 entry 提交与 stop 提交之间、或状态保存之前,收敛完全依赖下一 tick 的恢复。一个小的 SIGTERM 处理器(完成在途止损单再退出)即可消除约 1 分钟的裸仓窗口。

**D10. 每次遥测写入都新建连接并跑全量 DDL bootstrap。**
每条遥测 = 2 个新连接 + 全量建表脚本 + 7 次 `PRAGMA table_info`。应进程启动时 bootstrap 一次、复用长连接,可显著降低延迟与锁通道占用(与 H6 联动)。

---

## 五、文档与代码漂移

1. CLAUDE.md 写"Entry Window: UTC 01:00 onwards",实际默认 `blocked_base_entry_hour_beijing=9` 恰好封锁 UTC 01:00-01:59,**有效 base 入场从 UTC 02:00 开始**。
2. CLAUDE.md 列出的 `leader_unchanged` 拦截原因实际已被 [strategy.py:135](src/momentum_alpha/strategy.py:135) 压制(领涨未变时 blocked_reason 归 None),不再上报。
3. CLAUDE.md 的 run-once-live `--submit-orders` 示例未带 `--restore-positions`,该组合存在 M3(b) 的重复建仓风险,文档不应示范。
4. 加仓 clientOrderId 的 sequence 依赖"每 tick 至多一个意图"(base 与加仓互斥)这一隐式不变量;当前成立,但应在代码中显式断言,防止未来策略改动打破幂等键稳定性。

---

## 六、已核查确认安全的方面

- **定仓与过滤器**:数量向下取整(ROUND_DOWN),风险只会 ≤ 预算;低于 minQty 直接放弃而非补足;无除零;Decimal 全程无浮点污染;`format(value,"f")` 无科学计数法问题。
- **止损替换顺序**:先挂新、成功后再撤旧——出现的是"双止损窗口"而非"无保护窗口",且 reduceOnly/positionSide 保证不超卖。
- **入场幂等键**:加仓按小时截断、base 按分钟,提交前后各有一次 fetch_order 恢复(缺陷见 H1/H2,机制方向正确)。
- **并发原语**:WAL + `synchronous=NORMAL` + `BEGIN IMMEDIATE` 读改写事务;trade_fill 与状态同事务落库;`(symbol, trade_id)` 唯一索引 + INSERT OR IGNORE 幂等。
- **SQL 注入**:全库参数化绑定,f-string 仅用于内部白名单表名/列名——无注入。
- **XSS**:渲染路径普遍 `html.escape`(唯一缺口 L25)。
- **时间处理**:全链路 aware-UTC(REST 恢复、用户流事件、信号时间、序列化往返);小时窗口 `[H-1:00, H:00-1ms]` 无 off-by-one;毫秒时间戳一致;日切重置在 `process_runtime_tick` 正确执行。
- **快照回退**:`current_hour_low` 缺失时回退 previous_hour_low(而非 0),配合 `invalid_stop_price` 拦截,实盘路径不会产生 stopPrice=0 的委托。
- **调度器**:分钟去重、异常隔离、时钟回拨重 tick 有 `leader_unchanged` + 存储幂等防重复下单。
- **部署**:run_poll.sh 固定 `--restore-positions --execute-stop-replacements`;看板默认 127.0.0.1;env 模板默认 `SUBMIT_ORDERS=0` + testnet;凭据日志脱敏(signature/listenKey 过滤)。
- **listenKey keepalive**:30 分钟 PUT 符合币安 60 分钟有效期要求;流结束时 DELETE 清理。
- **部分成交**:按累计量/累计均价(`z`/`ap`)合并为单腿,trade 级去重 ID 唯一。
- **签名**:HMAC-SHA256 签名串与发送串一致;418/429 解析 ban 时长并等待;重试时重签时间戳。

## 七、审查中提出但被驳回的疑点(避免误修)

1. **"加仓重试时 sequence 漂移导致幂等键变化、重复成交"** — 驳回:base 需要"领涨易主且未持仓",加仓需要"持仓且恰为当前领涨",二者互斥,每 tick 至多一个意图,sequence 恒为 0。(但据此在代码中加显式断言是值得的,见五-4。)
2. **"日涨幅误用币安 24h 滚动窗口"** — 不成立:代码自建 UTC 日开盘价基准,语义自洽(与 UI 显示不同属预期,见 D4)。
3. **"主路径 naive/aware 时间混用"** — 不成立:生产路径全 aware(遗留数据风险归入 L3/L5)。
4. **"poll 状态保存会清掉 stream 刚写入的新仓位"** — 不成立:`_save_strategy_state` 的 updater 以库内现值为基合并,仅显式删除相等匹配的 removed_positions。
5. **"限频退避不生效(异常类型不匹配)"** — 不成立:`BinanceHttpError` 继承自 `urllib.error.HTTPError`,poll 循环的 418/429 捕获有效。

## 八、修复优先级建议

**P0(建议立即,均为小改动)**
1. H3:`if event.trade_id:` 一行修复 + 补测试。
2. H4:stream updater 对 `recent_stop_loss_exits`(及 `order_statuses`)改合并语义。
3. H1/H2:幂等恢复区分 -2013 与查询失败;恢复时校验订单状态。
4. H6(a):`_connect` 加 `timeout=30` + `PRAGMA busy_timeout=30000`(一行防住大部分锁冲突)。
5. M17:定时器时区写法修正。

**P1(短期)**
6. H5:加 `max_notional_usdt` 上限与最小止损距离阈值。
7. H6(b,c):重建改"事务外计算+短事务写入",调度源收敛。
8. M2/M5/M6:止损价 0 不覆写;空市场保留 previous_leader;--previous-leader 只用于首 tick。
9. M12/M13/M14:prewarm 入退避;开启 ws ping/ping_timeout;幂等 GET 启用小额重试。
10. M7/M8:限频后优先补挂止损;修复无合法止损价时市价离场+告警。
11. M3/M4:submit 隐含 restore;run-once-live 干跑不写状态。
12. M15:增加 prune 定时任务(先解除 D5 的重算耦合)。

**P2(中期)**
13. D1:状态按所有权拆行。
14. M16 + D7:看板错误隔离与鉴权。
15. M19/M20/M21/M22:分析与回放正确性修复。
16. 低危表按顺手程度批量清理;文档漂移(五)同步修正。
