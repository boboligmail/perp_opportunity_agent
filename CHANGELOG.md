# 版本记录

## v0.5.0 - 2026-04-27
- 新增 `calibrate_parameters.py`（参数校准脚手架）
- 新增 `run_pipeline.py`（统一调度入口，支持单轮与循环）
- 新增 `env_utils.py`（`.env` 解析加载）
- 新增 `.env.example` 与本地 `.env` 模板
- `perp_opportunity_agent.py` 改为支持 `.env` 覆盖关键参数
- `notify_telegram.py` 改为支持 `.env` 读取 Telegram 配置
- 文档重写为中文：`SPEC.md`、`PROCESS_FLOW.md`、`README.md`

## v0.4.0 - 2026-04-27
- 新增 `notify_telegram.py`，支持变化触发式推送
- 推送条件覆盖：强信号变化、平仓新增、市场阶段变化、事件新增
- 新增 `data/notify_state.json`，避免重复推送

## v0.3.0 - 2026-04-27
- 新增 `alpha_event_watchlist.py`，用于 Binance 公告事件观察
- 引入事件观察侧边链路，不直接改动主交易打分

## v0.2.0 - 2026-04-27
- 新增 `run_scanner_loop.py`（循环扫描）
- 新增 `analyze_paper_trades.py`（paper 统计）
- 新增 `data/scan_history.jsonl`（扫描历史）
- 引入 `SPEC.md`、`PROCESS_FLOW.md`

## v0.1.0 - 2026-04-27
- 完成 Binance USDT 永续机会扫描器初版
- 接入市场、热度、衍生品三层评分
- 支持 paper 持仓与平仓记录
