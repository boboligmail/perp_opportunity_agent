# 规格文档：Perp Opportunity Agent（Binance 合约）

## 1. 目标
构建一套面向 Binance USDT 永续合约的机会扫描与执行建议系统，用 `100U` 小资金验证策略有效性。

系统定位：
- 高波动机会雷达
- 风险过滤器
- 执行建议器
- Paper 样本生成器

## 2. 交易边界
- 交易标的：Binance USDT 永续合约（非现货）
- 本金：`100U`
- 最大杠杆：`3x`
- 强信号最大保证金：`15U`
- 强信号最大名义仓位：`45U`
- 单笔最大风险预算：`2U`

执行原则：
- 真实建议只看强信号
- 普通信号仅观察
- Paper 对有效 setup 进行全量模拟，以积累统计样本

## 3. 策略结构
### 3.1 机会发现层（Opportunity）
- 24h 涨幅、成交活跃度、短周期动量、结构突破
- 社媒热度（Binance Square）和搜索热度（CoinGecko Trending）

### 3.2 衍生品确认层（Derivatives）
- Funding（是否拥挤）
- OI 1h / 6h 变化（是否有资金推动）
- 结合价格结构确认“趋势跟随”与“挤压反转”

### 3.3 风险惩罚层（Risk Penalty）
- 过热（heat score）
- 单根拉爆与冲高回落风险
- ATR 过宽导致风险超预算

### 3.4 执行层（Execution）
- 输出动作：`breakout_follow` / `wait_pullback` / `small_probe` / `observe`
- 当前 setup：`breakout_long` / `squeeze_long` / `avoid`

## 4. 数据产物
- `data/latest_run.json`：最新扫描快照
- `data/scan_history.jsonl`：历史扫描摘要
- `data/paper_positions.json`：当前 paper 持仓
- `data/paper_trades.jsonl`：paper 平仓记录
- `data/paper_stats_report.md`：paper 统计
- `data/alpha_watchlist.json`：事件观察清单

## 5. 模块清单
- `perp_opportunity_agent.py`：核心扫描与 paper 记账
- `alpha_event_watchlist.py`：公告/事件观察
- `analyze_paper_trades.py`：paper 统计分析
- `notify_telegram.py`：变化触发推送
- `run_scanner_loop.py`：历史循环扫描器

## 6. v0.5 新增（本次）
### 6.1 参数校准脚手架
- 新增 `calibrate_parameters.py`
- 基于 `paper_trades.jsonl` 做阈值网格扫描：
- `PAPER_SIGNAL_THRESHOLD`
- `LIVE_SIGNAL_THRESHOLD`
- `MAX_HEAT_SCORE`
- 输出：
- `data/calibration_report.json`
- `data/calibration_report.md`

### 6.2 统一调度脚本
- 新增 `run_pipeline.py`
- 默认串联流程：
- `scan -> calibrate -> alpha -> analyze -> notify`
- 支持循环调度：`--interval-seconds`、`--max-runs`
- 支持灰度验证：`--dry-run`、`--skip-*`

### 6.3 参数外置
- 新增 `env_utils.py`
- 新增 `.env.example` 与本地 `.env`
- 关键风险与阈值参数改为 `.env` 覆盖（保留默认值）

## 7. 下一步
- 累积至少 80~150 笔 paper 样本后再做第二轮阈值收敛
- 加入按市场阶段分组的参数集（trend_up / rotation / chaos）
- 在强信号稳定后，再考虑小规模真实执行联动
