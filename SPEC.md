# Spec: Binance Perp Opportunity Agent v0.2

## Goal

Build a practical research-and-execution assistant for Binance USDT perpetual futures, optimized for a `100U` validation account.

This is not a "find 100x coin" machine. It is a:

- high-volatility opportunity radar
- risk filter
- execution suggestion agent
- paper-trade sample generator

## User constraints captured from discussion

- Venue: Binance perpetual futures, not spot
- Real capital: `100U`
- Real action: strong signals only
- Regular signals: observe only in live workflow
- Research workflow: every baseline-qualified signal should still open in paper mode
- Extra data inputs: Binance Square social heat and CoinGecko search heat
- Keep leverage contained: max `3x`

## Product decision

### Live layer

Only strong signals can produce a real trade plan.

Current live plan ceiling:

- leverage: `3x`
- margin: `15U`
- max notional: `45U`
- max risk: `2U`

If ATR-based stop distance makes the real-plan risk exceed `2U`, the signal is downgraded to `observe`.

### Paper layer

All setups above the baseline signal threshold are opened as paper positions, as long as they are valid:

- `score >= 55`
- `setup_type in {breakout_long, squeeze_long}`

Paper positions are used to estimate:

- win rate
- average pnl
- regime sensitivity
- setup-type edge
- score-band edge

## Strategy architecture

### 1. Regime engine

Inputs:

- BTC 24h change
- ETH 24h change
- top-50 perp breadth
- top-50 average change
- top-50 average funding

Outputs:

- `trend_up`
- `rotation`
- `trend_down`
- `chaos`

### 2. Discovery engine

Purpose:

- find contracts worth attention

Main inputs:

- 24h quote volume
- 24h trade count
- short-term momentum
- breakout structure
- Binance Square hashtag attention
- CoinGecko trending flag

### 3. Confirmation engine

Purpose:

- prevent social-only garbage signals from becoming trade candidates

Main inputs:

- open interest 1h / 6h expansion
- funding negativity
- ATR-based structure
- rejection wick
- blow-off candle risk

### 4. Execution engine

Outputs:

- `breakout_follow`
- `wait_pullback`
- `small_probe`
- `observe`

Current setup families:

- `breakout_long`
- `squeeze_long`
- `avoid`

## Versioned scope

### v0.1

- one-shot scanner
- social plus market plus derivatives scoring
- paper positions and closed-trade log

### v0.2

- loop scanner
- scan history snapshots
- paper trade stats report
- repo-ready docs and changelog

## Why these thresholds are treated as parameters, not truth

Discussion conclusion:

- momentum, liquidity, open interest, and volume confirmation are principle-level choices with real market-structure support
- exact cutoffs are engineering priors and should be calibrated over history

So this version keeps explicit thresholds, but treats them as tuneable parameters rather than universal truth.

## Future work

- add event sidecar based on `s1_binance_alpha_monitor.py`
- add Telegram or push delivery
- add threshold calibration over historical data
- add short-side mode after long-side validation is stable
- add real order execution only after paper sample is large enough
