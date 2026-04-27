#!/usr/bin/env python3
import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from perp_opportunity_agent import DATA_DIR, PAPER_TRADES_PATH, SCAN_HISTORY_PATH

REPORT_JSON_PATH = DATA_DIR / "calibration_report.json"
REPORT_MD_PATH = DATA_DIR / "calibration_report.md"


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def safe_div(numerator: float, denominator: float) -> float:
    if not denominator:
        return 0.0
    return numerator / denominator


def trade_metric(trades: list[dict[str, Any]]) -> dict[str, float]:
    if not trades:
        return {"count": 0, "win_rate": 0.0, "avg_pnl_pct": 0.0, "expectancy_pct": 0.0}
    wins = [item for item in trades if float(item.get("pnl_pct", 0)) > 0]
    losses = [item for item in trades if float(item.get("pnl_pct", 0)) <= 0]
    avg_win = safe_div(sum(float(item.get("pnl_pct", 0)) for item in wins), len(wins))
    avg_loss = safe_div(sum(float(item.get("pnl_pct", 0)) for item in losses), len(losses))
    win_rate = safe_div(len(wins), len(trades))
    expectancy = win_rate * avg_win + (1 - win_rate) * avg_loss
    avg_pnl = safe_div(sum(float(item.get("pnl_pct", 0)) for item in trades), len(trades))
    return {
        "count": len(trades),
        "win_rate": round(win_rate * 100, 2),
        "avg_pnl_pct": round(avg_pnl, 4),
        "expectancy_pct": round(expectancy, 4),
    }


def sweep_thresholds(
    trades: list[dict[str, Any]],
    paper_thresholds: list[int],
    live_thresholds: list[int],
    heat_limits: list[int],
) -> dict[str, Any]:
    paper_rows = []
    live_rows = []

    for threshold in paper_thresholds:
        subset = [item for item in trades if float(item.get("score", 0)) >= threshold]
        row = {"paper_signal_threshold": threshold, **trade_metric(subset)}
        paper_rows.append(row)

    for score_threshold in live_thresholds:
        for heat_limit in heat_limits:
            subset = [
                item
                for item in trades
                if float(item.get("score", 0)) >= score_threshold and float(item.get("heat_score", 999)) <= heat_limit
            ]
            row = {
                "live_signal_threshold": score_threshold,
                "max_heat_score": heat_limit,
                **trade_metric(subset),
            }
            live_rows.append(row)

    best_paper = max(paper_rows, key=lambda item: (item["expectancy_pct"], item["win_rate"], item["count"])) if paper_rows else {}
    live_candidates = [item for item in live_rows if item["count"] >= 5]
    best_live = (
        max(live_candidates, key=lambda item: (item["expectancy_pct"], item["win_rate"], item["count"]))
        if live_candidates
        else {}
    )
    return {"paper_grid": paper_rows, "live_grid": live_rows, "best_paper": best_paper, "best_live": best_live}


def summarize_scan_history(scan_history: list[dict[str, Any]]) -> dict[str, Any]:
    if not scan_history:
        return {"runs": 0, "avg_candidates": 0.0, "avg_live_signals": 0.0, "regimes": {}}
    runs = len(scan_history)
    avg_candidates = safe_div(sum(float(item.get("candidate_count", 0)) for item in scan_history), runs)
    avg_live = safe_div(sum(float(item.get("live_signal_count", 0)) for item in scan_history), runs)
    regimes: dict[str, int] = {}
    for item in scan_history:
        regime = str(item.get("regime", "unknown"))
        regimes[regime] = regimes.get(regime, 0) + 1
    return {
        "runs": runs,
        "avg_candidates": round(avg_candidates, 2),
        "avg_live_signals": round(avg_live, 2),
        "regimes": regimes,
    }


def render_md(report: dict[str, Any]) -> str:
    lines = [
        "# 参数校准报告（脚手架）",
        "",
        f"- 扫描样本数: {report['scan_summary']['runs']}",
        f"- 纸面平仓样本数: {report['trade_summary']['count']}",
        f"- 当前纸面胜率: {report['trade_summary']['win_rate']}%",
        f"- 当前纸面平均PnL: {report['trade_summary']['avg_pnl_pct']}%",
        "",
        "## 建议参数",
    ]
    best_paper = report["grid"].get("best_paper", {})
    best_live = report["grid"].get("best_live", {})
    if best_paper:
        lines.append(
            f"- `PAPER_SIGNAL_THRESHOLD={best_paper['paper_signal_threshold']}` "
            f"(expectancy={best_paper['expectancy_pct']}%, samples={best_paper['count']})"
        )
    else:
        lines.append("- `PAPER_SIGNAL_THRESHOLD` 暂无建议（样本不足）")
    if best_live:
        lines.append(
            f"- `LIVE_SIGNAL_THRESHOLD={best_live['live_signal_threshold']}` + "
            f"`MAX_HEAT_SCORE={best_live['max_heat_score']}` "
            f"(expectancy={best_live['expectancy_pct']}%, samples={best_live['count']})"
        )
    else:
        lines.append("- `LIVE_SIGNAL_THRESHOLD`/`MAX_HEAT_SCORE` 暂无建议（样本不足）")

    lines.extend(["", "## Paper 阈值网格"])
    for row in report["grid"]["paper_grid"]:
        lines.append(
            f"- score>={row['paper_signal_threshold']}: "
            f"count={row['count']}, win={row['win_rate']}%, avg={row['avg_pnl_pct']}%, exp={row['expectancy_pct']}%"
        )
    lines.extend(["", "## Live 阈值网格（score + heat）"])
    for row in report["grid"]["live_grid"]:
        lines.append(
            f"- score>={row['live_signal_threshold']}, heat<={row['max_heat_score']}: "
            f"count={row['count']}, win={row['win_rate']}%, avg={row['avg_pnl_pct']}%, exp={row['expectancy_pct']}%"
        )
    lines.append("")
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Parameter calibration scaffold")
    parser.add_argument("--paper-thresholds", default="55,58,60,62,65,68,70")
    parser.add_argument("--live-thresholds", default="68,70,72,74,76,78,80")
    parser.add_argument("--heat-limits", default="75,80,85,90,95,100")
    return parser.parse_args()


def parse_int_list(raw: str) -> list[int]:
    out = []
    for chunk in raw.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        out.append(int(chunk))
    return out


def main() -> None:
    args = parse_args()
    paper_thresholds = parse_int_list(args.paper_thresholds)
    live_thresholds = parse_int_list(args.live_thresholds)
    heat_limits = parse_int_list(args.heat_limits)

    scan_history = load_jsonl(SCAN_HISTORY_PATH)
    trades = load_jsonl(PAPER_TRADES_PATH)

    report = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "scan_summary": summarize_scan_history(scan_history),
        "trade_summary": trade_metric(trades),
        "grid": sweep_thresholds(trades, paper_thresholds, live_thresholds, heat_limits),
    }

    REPORT_JSON_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    REPORT_MD_PATH.write_text(render_md(report), encoding="utf-8")
    print(f"wrote {REPORT_JSON_PATH}")
    print(f"wrote {REPORT_MD_PATH}")


if __name__ == "__main__":
    main()
