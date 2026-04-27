# Changelog

## v0.2.0 - 2026-04-27

- rewrote the core scanner into clean ASCII code and extracted `run_scan()`
- added rolling scan history at `data/scan_history.jsonl`
- added `run_scanner_loop.py` for repeated scanning
- added `analyze_paper_trades.py` to summarize paper-trade results
- added `SPEC.md` to capture product direction and trading constraints
- clarified that live plans are strong-signal only and paper mode opens all valid baseline setups

## v0.1.0 - 2026-04-27

- initial Binance USDT perpetual opportunity scanner
- added paper position tracking and latest run output
- added first-pass social, market, and derivatives scoring
