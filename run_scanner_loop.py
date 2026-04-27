#!/usr/bin/env python3
import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from perp_opportunity_agent import DATA_DIR, LATEST_RUN_PATH, run_scan

LOOP_HEARTBEAT_PATH = DATA_DIR / "loop_heartbeat.json"


def save_heartbeat(status: dict) -> None:
    LOOP_HEARTBEAT_PATH.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Loop scanner for the perpetual opportunity agent")
    parser.add_argument("--interval-seconds", type=int, default=900, help="Seconds between scans")
    parser.add_argument("--max-runs", type=int, default=0, help="Stop after N runs; 0 means run forever")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_index = 0
    while True:
        run_index += 1
        started_at = datetime.now(timezone.utc).isoformat()
        status = {"run_index": run_index, "started_at": started_at, "status": "running"}
        save_heartbeat(status)
        try:
            payload = run_scan()
            completed_at = datetime.now(timezone.utc).isoformat()
            status = {
                "run_index": run_index,
                "started_at": started_at,
                "completed_at": completed_at,
                "status": "ok",
                "regime": payload["meta"]["regime"],
                "live_signal_count": len(payload["live_trade_plans"]),
                "paper_summary": payload["paper_summary"],
                "latest_run_path": str(LATEST_RUN_PATH),
            }
            save_heartbeat(status)
            print(
                f"[{completed_at}] run={run_index} regime={status['regime']} "
                f"live={status['live_signal_count']} paper={status['paper_summary']}"
            )
        except KeyboardInterrupt:
            status["status"] = "stopped"
            save_heartbeat(status)
            raise
        except Exception as exc:
            completed_at = datetime.now(timezone.utc).isoformat()
            status = {
                "run_index": run_index,
                "started_at": started_at,
                "completed_at": completed_at,
                "status": "error",
                "error": str(exc),
            }
            save_heartbeat(status)
            print(f"[{completed_at}] run={run_index} error={exc}")

        if args.max_runs and run_index >= args.max_runs:
            break
        time.sleep(args.interval_seconds)


if __name__ == "__main__":
    main()
