# Perp Opportunity Agent

面向 Binance USDT 永续合约的机会扫描、风险过滤、执行建议与样本验证工具。

## 账户假设
- 总本金：`100U`
- 最大杠杆：`3x`
- 强信号最大保证金：`15U`
- 强信号最大名义仓位：`45U`
- 单笔风险预算：`2U`

## 项目结构
- `perp_opportunity_agent.py`：核心扫描 + paper 持仓更新
- `calibrate_parameters.py`：参数校准脚手架（网格扫描）
- `run_pipeline.py`：统一调度入口（单轮/循环）
- `run_scanner_loop.py`：旧版循环扫描器（保留）
- `alpha_event_watchlist.py`：Binance 公告事件观察
- `analyze_paper_trades.py`：paper 统计分析
- `notify_telegram.py`：变化触发式 Telegram 推送
- `env_utils.py`：`.env` 参数加载
- `SPEC.md`：中文策略规格
- `CHANGELOG.md`：版本记录
- `PROCESS_FLOW.md`：流程图与当前进度

## 快速开始
1. 复制参数模板并填写：
```bash
copy .env.example .env
```
2. 本地单轮联调（不发真实通知）：
```bash
python run_pipeline.py --dry-run
```
3. 循环扫描（每 15 分钟）：
```bash
python run_pipeline.py --interval-seconds 900 --dry-run
```

## 常用命令
```bash
python perp_opportunity_agent.py
python alpha_event_watchlist.py
python analyze_paper_trades.py
python calibrate_parameters.py
python notify_telegram.py --dry-run
python run_pipeline.py --dry-run
python run_pipeline.py --interval-seconds 900 --dry-run
```

## 参数配置（.env）
关键可配置项：
- 账户与风险：`TOTAL_EQUITY`、`LIVE_LEVERAGE`、`LIVE_MARGIN_MAX`、`LIVE_RISK_USD`
- 市场过滤：`MIN_QUOTE_VOL`、`MIN_TRADE_COUNT`、`MIN_OI_USD`
- 候选范围：`SHORTLIST_VOL_TOP`、`SHORTLIST_MOVE_TOP`、`SOCIAL_CHECK_TOP`
- 信号阈值：`PAPER_SIGNAL_THRESHOLD`、`LIVE_SIGNAL_THRESHOLD`、`MAX_HEAT_SCORE`
- 推送参数：`TG_BOT_TOKEN`、`TG_CHAT_ID`
