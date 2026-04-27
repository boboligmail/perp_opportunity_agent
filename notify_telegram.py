#!/usr/bin/env python3
import argparse
import json
import os
from pathlib import Path
from typing import Any

import requests
from env_utils import load_env_file

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
load_env_file(BASE_DIR / ".env")

LATEST_RUN_PATH = DATA_DIR / "latest_run.json"
ALPHA_WATCHLIST_PATH = DATA_DIR / "alpha_watchlist.json"
STATE_PATH = DATA_DIR / "notify_state.json"

TG_API_TEMPLATE = "https://api.telegram.org/bot{token}/sendMessage"


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def save_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def normalize_live_plans(plans: list[dict[str, Any]]) -> list[str]:
    normalized = []
    for plan in plans:
        normalized.append(
            f"{plan.get('symbol','')}/{plan.get('action','')}/{plan.get('entry_price',0):.6f}/"
            f"{plan.get('stop_price',0):.6f}/{plan.get('take_profit_price',0):.6f}"
        )
    return sorted(normalized)


def send_telegram(text: str, dry_run: bool = False) -> bool:
    tg_bot_token = os.getenv("TG_BOT_TOKEN", "")
    tg_chat_id = os.getenv("TG_CHAT_ID", "")

    if dry_run:
        print("[dry-run] would send:\n")
        print(text)
        return True

    if not tg_bot_token or not tg_chat_id:
        print("[skip] TG_BOT_TOKEN or TG_CHAT_ID is not set")
        return False

    url = TG_API_TEMPLATE.format(token=tg_bot_token)
    chunks = [text[i:i + 3900] for i in range(0, len(text), 3900)]
    ok = True
    for chunk in chunks:
        response = requests.post(
            url,
            json={
                "chat_id": tg_chat_id,
                "text": chunk,
                "parse_mode": "Markdown",
            },
            timeout=10,
        )
        if response.status_code != 200:
            ok = False
    return ok


def build_message(changes: dict[str, Any], payload: dict[str, Any], alpha_payload: dict[str, Any]) -> str:
    meta = payload.get("meta", {})
    paper = payload.get("paper_summary", {})
    lines = []
    lines.append("*Perp Agent Update*")
    lines.append(f"Regime: `{meta.get('regime', 'unknown')}`")
    lines.append(
        f"Paper: open={paper.get('open_positions', 0)} closed={paper.get('closed_count_total', 0)} "
        f"win_rate={paper.get('win_rate', 0)}%"
    )

    if changes.get("regime_changed"):
        lines.append(f"- Regime changed: `{changes['old_regime']}` -> `{changes['new_regime']}`")

    if changes.get("closed_delta", 0) > 0:
        lines.append(f"- New paper closed trades: `{changes['closed_delta']}`")

    if changes.get("new_live"):
        lines.append("- New live strong signals:")
        for plan in payload.get("live_trade_plans", [])[:5]:
            lines.append(
                f"  `{plan.get('symbol')}` {plan.get('action')} "
                f"entry={plan.get('entry_price'):.6f} stop={plan.get('stop_price'):.6f}"
            )

    if changes.get("alpha_new_count", 0) > 0:
        lines.append(f"- New alpha watchlist items: `{changes['alpha_new_count']}`")
        for item in alpha_payload.get("items", [])[:3]:
            if item.get("is_new"):
                lines.append(f"  `{item.get('score', 0)}` {item.get('title', '')[:80]}")

    return "\n".join(lines)


def evaluate_changes(payload: dict[str, Any], alpha_payload: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    meta = payload.get("meta", {})
    paper = payload.get("paper_summary", {})
    live_plans = payload.get("live_trade_plans", [])

    current_regime = meta.get("regime", "unknown")
    previous_regime = state.get("last_regime", "")
    regime_changed = bool(previous_regime) and previous_regime != current_regime

    closed_total = int(paper.get("closed_count_total", 0) or 0)
    previous_closed_total = int(state.get("last_closed_total", 0) or 0)
    closed_delta = max(0, closed_total - previous_closed_total)

    live_fingerprint = normalize_live_plans(live_plans)
    previous_live_fingerprint = state.get("last_live_fingerprint", [])
    new_live = len(live_plans) > 0 and live_fingerprint != previous_live_fingerprint

    alpha_items = alpha_payload.get("items", [])
    alpha_new_count = sum(1 for item in alpha_items if item.get("is_new"))

    return {
        "regime_changed": regime_changed,
        "old_regime": previous_regime,
        "new_regime": current_regime,
        "closed_delta": closed_delta,
        "new_live": new_live,
        "alpha_new_count": alpha_new_count,
        "should_notify": regime_changed or closed_delta > 0 or new_live or alpha_new_count > 0,
        "live_fingerprint": live_fingerprint,
        "closed_total": closed_total,
        "regime": current_regime,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Telegram notifier for perp opportunity agent")
    parser.add_argument("--force", action="store_true", help="Send a notification even when no change detected")
    parser.add_argument("--dry-run", action="store_true", help="Print message instead of sending to Telegram")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    payload = load_json(LATEST_RUN_PATH, {})
    alpha_payload = load_json(ALPHA_WATCHLIST_PATH, {"items": []})
    state = load_json(STATE_PATH, {})

    if not payload:
        print("[skip] latest_run.json not found or empty")
        return

    changes = evaluate_changes(payload, alpha_payload, state)
    if not changes["should_notify"] and not args.force:
        print("[skip] no significant changes")
    else:
        message = build_message(changes, payload, alpha_payload)
        sent = send_telegram(message, dry_run=args.dry_run)
        print("[sent]" if sent else "[not-sent]")

    new_state = {
        "last_regime": changes["regime"],
        "last_closed_total": changes["closed_total"],
        "last_live_fingerprint": changes["live_fingerprint"],
        "last_meta_timestamp": payload.get("meta", {}).get("timestamp", ""),
    }
    save_json(STATE_PATH, new_state)


if __name__ == "__main__":
    main()
