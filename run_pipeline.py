#!/usr/bin/env python3
import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from env_utils import load_env_file
from perp_opportunity_agent import BASE_DIR, DATA_DIR

PIPELINE_HEARTBEAT_PATH = DATA_DIR / "pipeline_heartbeat.json"


def save_heartbeat(payload: dict[str, Any]) -> None:
    PIPELINE_HEARTBEAT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def run_step(step: str, command: list[str]) -> tuple[bool, str]:
    result = subprocess.run(command, cwd=BASE_DIR, text=True, capture_output=True)
    output = (result.stdout or "") + (result.stderr or "")
    if result.returncode == 0:
        return True, output.strip()
    return False, output.strip()


def one_round(args: argparse.Namespace, run_index: int) -> dict[str, Any]:
    started_at = datetime.now(timezone.utc).isoformat()
    status: dict[str, Any] = {
        "run_index": run_index,
        "started_at": started_at,
        "status": "running",
        "steps": [],
    }
    save_heartbeat(status)

    py = sys.executable
    steps: list[tuple[str, list[str]]] = [
        ("scan", [py, "perp_opportunity_agent.py", "--quiet"]),
        ("calibrate", [py, "calibrate_parameters.py"]),
    ]
    if not args.skip_alpha:
        steps.append(("alpha", [py, "alpha_event_watchlist.py"]))
    if not args.skip_analyze:
        steps.append(("analyze", [py, "analyze_paper_trades.py"]))
    if not args.skip_notify:
        notify_cmd = [py, "notify_telegram.py"]
        if args.dry_run:
            notify_cmd.append("--dry-run")
        steps.append(("notify", notify_cmd))

    all_ok = True
    for step_name, command in steps:
        ok, output = run_step(step_name, command)
        status["steps"].append(
            {
                "step": step_name,
                "ok": ok,
                "command": " ".join(command),
                "output_tail": "\n".join(output.splitlines()[-10:]),
            }
        )
        save_heartbeat(status)
        print(f"[pipeline] step={step_name} ok={ok}")
        if not ok:
            all_ok = False
            break

    status["status"] = "ok" if all_ok else "error"
    status["completed_at"] = datetime.now(timezone.utc).isoformat()
    save_heartbeat(status)
    return status


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Unified scheduler for perp opportunity agent")
    parser.add_argument("--interval-seconds", type=int, default=0, help="0 means run once; >0 means loop")
    parser.add_argument("--max-runs", type=int, default=0, help="0 means unlimited in loop mode")
    parser.add_argument("--dry-run", action="store_true", help="Pass dry-run to notifier")
    parser.add_argument("--skip-alpha", action="store_true", help="Skip alpha event watchlist step")
    parser.add_argument("--skip-analyze", action="store_true", help="Skip paper stats analyze step")
    parser.add_argument("--skip-notify", action="store_true", help="Skip Telegram notify step")
    parser.add_argument("--env-file", default=".env", help="Env file path")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    load_env_file(BASE_DIR / args.env_file)

    if args.interval_seconds <= 0:
        one_round(args, run_index=1)
        return

    run_index = 0
    while True:
        run_index += 1
        status = one_round(args, run_index=run_index)
        if status["status"] != "ok":
            break
        if args.max_runs and run_index >= args.max_runs:
            break
        time.sleep(args.interval_seconds)


if __name__ == "__main__":
    main()
