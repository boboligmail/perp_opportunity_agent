#!/usr/bin/env python3
import json
from collections import Counter, defaultdict
from pathlib import Path

from perp_opportunity_agent import DATA_DIR, PAPER_TRADES_PATH

REPORT_PATH = DATA_DIR / "paper_stats_report.md"
JSON_REPORT_PATH = DATA_DIR / "paper_stats_report.json"


def load_trades() -> list[dict]:
    if not PAPER_TRADES_PATH.exists():
        return []
    trades = []
    with PAPER_TRADES_PATH.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                trades.append(json.loads(line))
    return trades


def safe_pct(numerator: float, denominator: float) -> float:
    if not denominator:
        return 0.0
    return round(numerator / denominator * 100, 2)


def band_for_score(score: float) -> str:
    if score >= 80:
        return "80+"
    if score >= 70:
        return "70-79"
    if score >= 60:
        return "60-69"
    return "55-59"


def summarize_group(trades: list[dict], key: str) -> list[dict]:
    grouped: defaultdict[str, list[dict]] = defaultdict(list)
    for trade in trades:
        grouped[str(trade.get(key, "unknown"))].append(trade)

    rows = []
    for group_key, items in sorted(grouped.items(), key=lambda item: len(item[1]), reverse=True):
        wins = sum(1 for item in items if item.get("pnl_pct", 0) > 0)
        avg_pnl = round(sum(item.get("pnl_pct", 0) for item in items) / len(items), 3)
        rows.append(
            {
                "key": group_key,
                "count": len(items),
                "win_rate": safe_pct(wins, len(items)),
                "avg_pnl_pct": avg_pnl,
            }
        )
    return rows


def build_report(trades: list[dict]) -> dict:
    total = len(trades)
    wins = sum(1 for trade in trades if trade.get("pnl_pct", 0) > 0)
    losses = sum(1 for trade in trades if trade.get("pnl_pct", 0) <= 0)
    avg_pnl = round(sum(trade.get("pnl_pct", 0) for trade in trades) / total, 3) if trades else 0.0
    close_reasons = Counter(trade.get("close_reason", "unknown") for trade in trades)

    for trade in trades:
        trade["score_band"] = band_for_score(float(trade.get("score", 0)))

    report = {
        "total_trades": total,
        "win_rate": safe_pct(wins, total),
        "loss_rate": safe_pct(losses, total),
        "avg_pnl_pct": avg_pnl,
        "close_reasons": dict(close_reasons),
        "by_setup_type": summarize_group(trades, "setup_type"),
        "by_regime": summarize_group(trades, "regime"),
        "by_score_band": summarize_group(trades, "score_band"),
        "by_in_cg": summarize_group(trades, "in_cg"),
    }
    return report


def render_markdown(report: dict) -> str:
    lines = [
        "# Paper Trade Stats",
        "",
        f"- Total trades: {report['total_trades']}",
        f"- Win rate: {report['win_rate']}%",
        f"- Loss rate: {report['loss_rate']}%",
        f"- Average pnl: {report['avg_pnl_pct']}%",
        f"- Close reasons: {report['close_reasons']}",
        "",
        "## By setup type",
    ]
    for row in report["by_setup_type"]:
        lines.append(f"- {row['key']}: count={row['count']}, win_rate={row['win_rate']}%, avg_pnl={row['avg_pnl_pct']}%")

    lines.extend(["", "## By regime"])
    for row in report["by_regime"]:
        lines.append(f"- {row['key']}: count={row['count']}, win_rate={row['win_rate']}%, avg_pnl={row['avg_pnl_pct']}%")

    lines.extend(["", "## By score band"])
    for row in report["by_score_band"]:
        lines.append(f"- {row['key']}: count={row['count']}, win_rate={row['win_rate']}%, avg_pnl={row['avg_pnl_pct']}%")

    lines.extend(["", "## By CoinGecko trend flag"])
    for row in report["by_in_cg"]:
        lines.append(f"- {row['key']}: count={row['count']}, win_rate={row['win_rate']}%, avg_pnl={row['avg_pnl_pct']}%")

    lines.append("")
    return "\n".join(lines)


def main() -> None:
    trades = load_trades()
    report = build_report(trades)
    JSON_REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    REPORT_PATH.write_text(render_markdown(report), encoding="utf-8")
    print(f"wrote {REPORT_PATH}")
    print(f"wrote {JSON_REPORT_PATH}")


if __name__ == "__main__":
    main()
