# Perp Opportunity Agent

面向 Binance USDT 永续合约的最小可运行机会雷达。

## 这套东西做什么

- 只扫描 Binance USDT 永续合约
- 结合市场阶段、Binance Square 热度、CoinGecko Trending、Funding、Open Interest 和短周期结构
- `live` 只保留强信号建议
- `paper` 会对所有达到基线阈值的有效 setup 开模拟仓，持续积累样本
- 暂时不自动下单
- 暂时不做空

## 账户假设

- 总本金：`100U`
- 最大杠杆：`3x`
- 强信号最大保证金：`15U`
- 强信号最大名义仓位：`45U`
- 单笔真实建议最大风险：`2U`

说明：

- `15U` 不是每笔都必须这么下，而是当前的强信号上限
- 如果按 ATR 推导出来的止损距离，会让 `45U` 名义仓位的预估亏损超过 `2U`，该信号会自动降级为观察

## 文件结构

- `perp_opportunity_agent.py`：单次扫描 + 模拟持仓更新
- `run_scanner_loop.py`：循环扫描器
- `analyze_paper_trades.py`：模拟交易统计脚本
- `alpha_event_watchlist.py`：Binance 公告事件观察侧边模块
- `SPEC.md`：中文策略规格文档
- `CHANGELOG.md`：中文版本记录
- `PROCESS_FLOW.md`：流程图与当前进度标记
- `data/latest_run.json`：最近一次完整扫描结果
- `data/scan_history.jsonl`：扫描历史快照
- `data/paper_positions.json`：当前模拟持仓
- `data/paper_trades.jsonl`：模拟平仓记录
- `data/paper_stats_report.md`：模拟统计摘要
- `data/alpha_watchlist.json`：事件观察列表

## 使用方式

```bash
python perp_opportunity_agent.py
python run_scanner_loop.py --interval-seconds 900
python run_scanner_loop.py --interval-seconds 900 --max-runs 4
python analyze_paper_trades.py
python alpha_event_watchlist.py
```

## 当前设计取舍

- `s3_accumulation_radar.py` 的思路主要映射到热度发现层和市场发现层
- `s2_oi_funding_rate_scanner.py` 的思路主要映射到衍生品确认层
- `s1_binance_alpha_monitor.py` 已先简化接入为 `alpha_event_watchlist.py`，当前作为事件侧边观察模块运行，暂不直接参与主打分
