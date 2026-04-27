# Perp Opportunity Agent

Minimal working scanner for Binance USDT perpetual futures.

## What it does

- Scans Binance USDT perpetual contracts only
- Uses market regime, Binance Square heat, CoinGecko trending, funding, open interest, and short-term structure
- Keeps `live` recommendations limited to strong signals only
- Opens `paper` positions for all baseline-qualified setups to build a sample set
- Does not place real orders yet
- Does not short yet

## Account assumptions

- Total equity: `100U`
- Max leverage: `3x`
- Max strong-signal margin: `15U`
- Max strong-signal notional: `45U`
- Max risk per real trade plan: `2U`

Important:

- `15U` is not a mandatory fixed size for every real trade, it is the current ceiling
- If ATR-implied stop distance would make `45U` notional risk exceed `2U`, the signal is downgraded to observation

## Files

- `perp_opportunity_agent.py`: one-shot scanner and paper-book updater
- `run_scanner_loop.py`: loop runner for repeated scans
- `analyze_paper_trades.py`: stats report generator for the paper log
- `data/latest_run.json`: latest full scan result
- `data/scan_history.jsonl`: rolling scan history snapshots
- `data/paper_positions.json`: current paper positions
- `data/paper_trades.jsonl`: closed paper trades
- `data/paper_stats_report.md`: generated paper stats summary

## Usage

```bash
python perp_opportunity_agent.py
python run_scanner_loop.py --interval-seconds 900
python run_scanner_loop.py --interval-seconds 900 --max-runs 4
python analyze_paper_trades.py
```

## Current scope choices

- `s3_accumulation_radar.py` logic is represented in the heat plus market discovery layer
- `s2_oi_funding_rate_scanner.py` logic is represented in the derivatives confirmation layer
- `s1_binance_alpha_monitor.py` stays outside the trigger path for now and is treated as a future event-watch sidecar
