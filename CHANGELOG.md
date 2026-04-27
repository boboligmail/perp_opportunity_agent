# 版本记录

## v0.3.0 - 2026-04-27

- 新增 `alpha_event_watchlist.py`，用于扫描 Binance 公告并生成事件观察列表
- 将事件流定义为侧边观察模块，不直接进入主交易触发链路
- 更新中文 `README.md`、`SPEC.md` 和 `PROCESS_FLOW.md`
- 将项目推进到步骤 8 的第一阶段：事件模块已接入

## v0.2.0 - 2026-04-27

- 将核心扫描器重写为干净的 ASCII 代码，并抽出 `run_scan()` 供循环器复用
- 新增 `data/scan_history.jsonl`，记录每次扫描摘要
- 新增 `run_scanner_loop.py`，支持循环扫描
- 新增 `analyze_paper_trades.py`，统计模拟交易表现
- 新增中文 `SPEC.md`，沉淀这轮对话里的策略约束与产品方向
- 新增 `PROCESS_FLOW.md`，用流程图记录当前推进阶段
- 明确真实交易建议只看强信号，paper 模式则覆盖所有有效基线 setup

## v0.1.0 - 2026-04-27

- 完成 Binance USDT 永续合约机会扫描器初版
- 接入热度、市场、衍生品三层打分
- 新增模拟持仓跟踪与最近一次运行输出
