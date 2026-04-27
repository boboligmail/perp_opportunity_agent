#!/usr/bin/env python3
import argparse
import json
import math
import os
import statistics
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from env_utils import load_env_file

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
load_env_file(BASE_DIR / ".env")

LATEST_RUN_PATH = DATA_DIR / "latest_run.json"
PAPER_POSITIONS_PATH = DATA_DIR / "paper_positions.json"
PAPER_TRADES_PATH = DATA_DIR / "paper_trades.jsonl"
SCAN_HISTORY_PATH = DATA_DIR / "scan_history.jsonl"

FAPI = "https://fapi.binance.com"
BINANCE_MARKETING = "https://www.binance.com/bapi/composite/v1/public/marketing/symbol/list"
BINANCE_SQUARE_HASHTAG = "https://www.binance.com/bapi/composite/v4/friendly/pgc/content/queryByHashtag"
COINGECKO_TRENDING = "https://api.coingecko.com/api/v3/search/trending"

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Referer": "https://www.binance.com/en/square",
}

TOTAL_EQUITY = float(os.getenv("TOTAL_EQUITY", "100"))
LIVE_LEVERAGE = float(os.getenv("LIVE_LEVERAGE", "3"))
LIVE_MARGIN_MAX = float(os.getenv("LIVE_MARGIN_MAX", "15"))
LIVE_NOTIONAL_MAX = LIVE_MARGIN_MAX * LIVE_LEVERAGE
LIVE_RISK_USD = float(os.getenv("LIVE_RISK_USD", "2"))

MIN_QUOTE_VOL = float(os.getenv("MIN_QUOTE_VOL", "10000000"))
MIN_TRADE_COUNT = int(os.getenv("MIN_TRADE_COUNT", "20000"))
MIN_OI_USD = float(os.getenv("MIN_OI_USD", "5000000"))
SHORTLIST_VOL_TOP = int(os.getenv("SHORTLIST_VOL_TOP", "45"))
SHORTLIST_MOVE_TOP = int(os.getenv("SHORTLIST_MOVE_TOP", "25"))
SHORTLIST_ACTIVITY_TOP = int(os.getenv("SHORTLIST_ACTIVITY_TOP", "35"))
SHORTLIST_EARLY_TOP = int(os.getenv("SHORTLIST_EARLY_TOP", "35"))
SOCIAL_CHECK_TOP = int(os.getenv("SOCIAL_CHECK_TOP", "25"))
PAPER_SIGNAL_THRESHOLD = float(os.getenv("PAPER_SIGNAL_THRESHOLD", "55"))
LIVE_SIGNAL_THRESHOLD = float(os.getenv("LIVE_SIGNAL_THRESHOLD", "72"))
CHAOS_PROBE_THRESHOLD = float(os.getenv("CHAOS_PROBE_THRESHOLD", "62"))
MAX_HEAT_SCORE = float(os.getenv("MAX_HEAT_SCORE", "100"))


@dataclass
class Signal:
    symbol: str
    coin: str
    regime: str
    price: float
    px_chg_24h: float
    quote_volume: float
    trade_count: int
    funding_pct: float
    oi_usd: float
    oi_1h_pct: float
    oi_6h_pct: float
    heat_score: float
    market_score: float
    derivatives_score: float
    total_score: float
    setup_type: str
    action: str
    stop_pct: float
    atr_pct: float
    invalidation: str
    exit_idea: str
    why: list[str]
    risks: list[str]
    square_posts: int = 0
    square_views: int = 0
    in_cg: bool = False
    onboard_days: int = 0


def api_get(base: str, endpoint: str, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> Any:
    url = f"{base}{endpoint}"
    last_error = None
    for _ in range(3):
        try:
            response = requests.get(url, params=params, headers=headers, timeout=10)
            if response.status_code == 200:
                return response.json()
            last_error = f"{response.status_code}: {response.text[:120]}"
            if response.status_code in (418, 429):
                time.sleep(1.5)
            else:
                time.sleep(0.5)
        except Exception as exc:
            last_error = str(exc)
            time.sleep(1)
    raise RuntimeError(f"GET {url} failed: {last_error}")


def pct_rank(value: float, samples: list[float]) -> float:
    if not samples:
        return 50.0
    count = sum(1 for sample in samples if sample <= value)
    return 100.0 * count / len(samples)


def median(values: list[float], fallback: float = 0.0) -> float:
    clean = [value for value in values if value is not None and not math.isnan(value)]
    return statistics.median(clean) if clean else fallback


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def save_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def append_jsonl(path: Path, payload: Any) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def get_futures_universe() -> dict[str, dict[str, Any]]:
    info = api_get(FAPI, "/fapi/v1/exchangeInfo")
    now_ms = int(time.time() * 1000)
    universe: dict[str, dict[str, Any]] = {}
    for symbol_info in info["symbols"]:
        if symbol_info["contractType"] != "PERPETUAL":
            continue
        if symbol_info["quoteAsset"] != "USDT" or symbol_info["status"] != "TRADING":
            continue
        universe[symbol_info["symbol"]] = {
            "base": symbol_info["baseAsset"],
            "onboard_days": max(0, int((now_ms - symbol_info.get("onboardDate", now_ms)) / 86400000)),
        }
    return universe


def get_tickers() -> dict[str, dict[str, Any]]:
    data = api_get(FAPI, "/fapi/v1/ticker/24hr")
    out: dict[str, dict[str, Any]] = {}
    for ticker in data:
        symbol = ticker["symbol"]
        if not symbol.endswith("USDT"):
            continue
        out[symbol] = {
            "last_price": float(ticker["lastPrice"]),
            "px_chg_24h": float(ticker["priceChangePercent"]),
            "quote_volume": float(ticker["quoteVolume"]),
            "trade_count": int(ticker["count"]),
            "high_price": float(ticker["highPrice"]),
            "low_price": float(ticker["lowPrice"]),
        }
    return out


def get_funding_map() -> dict[str, float]:
    data = api_get(FAPI, "/fapi/v1/premiumIndex")
    return {item["symbol"]: float(item["lastFundingRate"]) * 100.0 for item in data if item["symbol"].endswith("USDT")}


def get_mcap_map() -> dict[str, float]:
    try:
        data = api_get("", BINANCE_MARKETING)
        return {
            item["name"]: float(item["marketCap"])
            for item in data.get("data", [])
            if item.get("name") and item.get("marketCap")
        }
    except Exception:
        return {}


def get_cg_trending() -> set[str]:
    try:
        data = api_get("", COINGECKO_TRENDING)
        return {item["item"]["symbol"].upper() for item in data.get("coins", [])}
    except Exception:
        return set()


def get_regime(tickers: dict[str, dict[str, Any]], funding_map: dict[str, float]) -> tuple[str, dict[str, float]]:
    btc = tickers.get("BTCUSDT", {})
    eth = tickers.get("ETHUSDT", {})
    top = sorted(tickers.items(), key=lambda item: item[1]["quote_volume"], reverse=True)[:50]
    breadth_up = sum(1 for _, data in top if data["px_chg_24h"] > 0)
    breadth = breadth_up / max(len(top), 1)
    avg_change = sum(data["px_chg_24h"] for _, data in top) / max(len(top), 1)
    avg_funding = sum(funding_map.get(symbol, 0.0) for symbol, _ in top) / max(len(top), 1)
    btc_change = btc.get("px_chg_24h", 0.0)
    eth_change = eth.get("px_chg_24h", 0.0)

    if breadth >= 0.66 and avg_change > 2 and btc_change > 1 and eth_change > 1:
        regime = "trend_up"
    elif breadth >= 0.52 and avg_change > 0.5:
        regime = "rotation"
    elif breadth <= 0.4 and avg_change < -1.0 and btc_change < 0 and eth_change < 0:
        regime = "trend_down"
    else:
        regime = "chaos"

    return regime, {
        "breadth": round(breadth, 3),
        "avg_top50_change": round(avg_change, 3),
        "avg_top50_funding_pct": round(avg_funding, 4),
        "btc_24h": round(btc_change, 3),
        "eth_24h": round(eth_change, 3),
    }


def shortlist_symbols(universe: dict[str, dict[str, Any]], tickers: dict[str, dict[str, Any]]) -> list[str]:
    filtered = [
        (symbol, data)
        for symbol, data in tickers.items()
        if symbol in universe and data["quote_volume"] >= MIN_QUOTE_VOL and data["trade_count"] >= MIN_TRADE_COUNT
    ]
    top_volume = sorted(filtered, key=lambda item: item[1]["quote_volume"], reverse=True)[:SHORTLIST_VOL_TOP]
    top_activity = sorted(filtered, key=lambda item: item[1]["trade_count"], reverse=True)[:SHORTLIST_ACTIVITY_TOP]
    early_band = [
        (symbol, data)
        for symbol, data in filtered
        if 1.5 <= data["px_chg_24h"] <= 22
    ]
    early_candidates = sorted(
        early_band,
        key=lambda item: (
            item[1]["quote_volume"],
            item[1]["trade_count"],
            -abs(item[1]["px_chg_24h"] - 8.0),
        ),
        reverse=True,
    )[:SHORTLIST_EARLY_TOP]
    top_moves = sorted(filtered, key=lambda item: item[1]["px_chg_24h"], reverse=True)[:SHORTLIST_MOVE_TOP]
    merged: list[str] = []
    seen = set()
    for symbol, _ in top_volume + top_activity + early_candidates + top_moves:
        if symbol not in seen:
            merged.append(symbol)
            seen.add(symbol)
    return merged


def fetch_oi_change(symbol: str, period: str, limit: int) -> tuple[float, float]:
    history = api_get(FAPI, "/futures/data/openInterestHist", {"symbol": symbol, "period": period, "limit": limit})
    if not isinstance(history, list) or len(history) < 2:
        return 0.0, 0.0
    old_value = float(history[0]["sumOpenInterestValue"])
    new_value = float(history[-1]["sumOpenInterestValue"])
    if old_value <= 0:
        return 0.0, new_value
    return (new_value - old_value) / old_value * 100.0, new_value


def fetch_klines(symbol: str, interval: str, limit: int) -> list[list[Any]]:
    return api_get(FAPI, "/fapi/v1/klines", {"symbol": symbol, "interval": interval, "limit": limit})


def calc_bar_metrics(symbol: str) -> dict[str, float]:
    klines = fetch_klines(symbol, "15m", 64)
    closes = [float(kline[4]) for kline in klines]
    highs = [float(kline[2]) for kline in klines]
    lows = [float(kline[3]) for kline in klines]
    quote_volumes = [float(kline[7]) for kline in klines]
    last_price = closes[-1]
    ret_1h = (last_price / closes[-5] - 1.0) * 100.0
    ret_4h = (last_price / closes[-17] - 1.0) * 100.0
    ret_12h = (last_price / closes[-49] - 1.0) * 100.0
    high_48h = max(highs)
    breakout = last_price > high_48h * 0.995 and closes[-1] > max(highs[-9:-1]) * 0.998

    tr_values = []
    for index in range(1, len(klines)):
        high = highs[index]
        low = lows[index]
        prev_close = closes[index - 1]
        tr_values.append(max(high - low, abs(high - prev_close), abs(low - prev_close)))
    atr = median(tr_values[-20:], fallback=last_price * 0.01)
    atr_pct = (atr / last_price) * 100.0 if last_price > 0 else 0.0

    vol_1h = sum(quote_volumes[-4:])
    vol_4h = sum(quote_volumes[-16:])
    median_1h = median([sum(quote_volumes[index - 4:index]) for index in range(4, len(quote_volumes) + 1)][:-1], fallback=vol_1h or 1.0)
    median_4h = median([sum(quote_volumes[index - 16:index]) for index in range(16, len(quote_volumes) + 1)][:-1], fallback=vol_4h or 1.0)

    recent = klines[-1]
    open_price = float(recent[1])
    high_price = float(recent[2])
    low_price = float(recent[3])
    close_price = float(recent[4])
    body_pct = abs(close_price - open_price) / open_price * 100 if open_price else 0.0
    upper_wick_ratio = ((high_price - max(open_price, close_price)) / (high_price - low_price)) if high_price > low_price else 0.0

    return {
        "ret_1h": ret_1h,
        "ret_4h": ret_4h,
        "ret_12h": ret_12h,
        "breakout": breakout,
        "atr_pct": atr_pct,
        "vol_1h_ratio": vol_1h / max(median_1h, 1.0),
        "vol_4h_ratio": vol_4h / max(median_4h, 1.0),
        "body_pct_15m": body_pct,
        "upper_wick_ratio": upper_wick_ratio,
        "high_48h": high_48h,
    }


def get_square_discussion(coin: str) -> tuple[int, int]:
    try:
        response = requests.get(
            BINANCE_SQUARE_HASHTAG,
            params={"hashtag": f"#{coin.lower()}", "pageIndex": 1, "pageSize": 1, "orderBy": "HOT"},
            headers=HEADERS,
            timeout=8,
        )
        if response.status_code == 200:
            hashtag = response.json().get("data", {}).get("hashtag", {})
            return int(hashtag.get("contentCount", 0)), int(hashtag.get("viewCount", 0))
    except Exception:
        pass
    return 0, 0


def build_signals() -> tuple[list[Signal], dict[str, Any]]:
    universe = get_futures_universe()
    tickers = get_tickers()
    funding = get_funding_map()
    _mcap = get_mcap_map()
    cg_trending = get_cg_trending()
    regime, regime_metrics = get_regime(tickers, funding)
    candidates = shortlist_symbols(universe, tickers)

    metric_cache: dict[str, dict[str, float]] = {}
    for symbol in candidates:
        metric_cache[symbol] = calc_bar_metrics(symbol)
        time.sleep(0.04)

    top_for_social = sorted(
        candidates,
        key=lambda symbol: (
            int(universe[symbol]["onboard_days"] >= 30),
            tickers[symbol]["quote_volume"],
            tickers[symbol]["px_chg_24h"],
        ),
        reverse=True,
    )[:SOCIAL_CHECK_TOP]

    square_heat: dict[str, dict[str, int]] = {}
    for symbol in top_for_social:
        coin = universe[symbol]["base"]
        posts, views = get_square_discussion(coin)
        square_heat[coin] = {"posts": posts, "views": views}
        time.sleep(0.08)

    all_ret_1h = [metric_cache[symbol]["ret_1h"] for symbol in candidates]
    all_ret_4h = [metric_cache[symbol]["ret_4h"] for symbol in candidates]
    all_ret_12h = [metric_cache[symbol]["ret_12h"] for symbol in candidates]

    signals: list[Signal] = []
    for symbol in candidates:
        coin = universe[symbol]["base"]
        ticker = tickers[symbol]
        metrics = metric_cache[symbol]
        oi_1h, oi_now = fetch_oi_change(symbol, "5m", 13)
        oi_6h, oi_now_2 = fetch_oi_change(symbol, "1h", 7)
        oi_usd = max(oi_now, oi_now_2)
        funding_pct = funding.get(symbol, 0.0)
        social = square_heat.get(coin, {"posts": 0, "views": 0})
        in_cg = coin in cg_trending

        heat_score = 0.0
        if in_cg:
            heat_score += 28.0
        if social["posts"] > 0:
            heat_score += clamp(10 + math.log10(max(social["posts"], 1)) * 12, 0, 28)
        if social["views"] > 0:
            heat_score += clamp(math.log10(max(social["views"], 1)) * 6, 0, 18)
        if metrics["vol_1h_ratio"] >= 2:
            heat_score += clamp((metrics["vol_1h_ratio"] - 2) * 10, 0, 18)
        heat_score = clamp(heat_score, 0, MAX_HEAT_SCORE)

        ret_1h_rank = pct_rank(metrics["ret_1h"], all_ret_1h)
        ret_4h_rank = pct_rank(metrics["ret_4h"], all_ret_4h)
        ret_12h_rank = pct_rank(metrics["ret_12h"], all_ret_12h)
        market_score = (
            0.30 * ret_1h_rank
            + 0.35 * ret_4h_rank
            + 0.20 * ret_12h_rank
            + 0.15 * min(metrics["vol_4h_ratio"] * 20, 100)
        )
        if metrics["breakout"]:
            market_score += 8
        market_score = clamp(market_score, 0, 100)

        derivatives_score = 0.0
        if oi_usd >= MIN_OI_USD:
            derivatives_score += 20
        derivatives_score += clamp(oi_1h * 3, 0, 25)
        derivatives_score += clamp(oi_6h * 2.5, 0, 30)
        if funding_pct < 0:
            derivatives_score += clamp(abs(funding_pct) * 250, 0, 15)
        derivatives_score = clamp(derivatives_score, 0, 100)

        risks: list[str] = []
        penalty = 0.0
        if ticker["quote_volume"] < 20_000_000:
            penalty += 8
            risks.append("Liquidity is only moderate")
        if ticker["trade_count"] < 40_000:
            penalty += 6
            risks.append("Trade count is still thin")
        if ticker["px_chg_24h"] > 28:
            penalty += 10
            risks.append("24h extension is already large")
        if metrics["body_pct_15m"] >= 4 and metrics["vol_1h_ratio"] >= 3.5:
            penalty += 12
            risks.append("Recent candle looks like a blow-off spike")
        if metrics["upper_wick_ratio"] >= 0.45 and metrics["ret_1h"] > 0:
            penalty += 10
            risks.append("Recent rejection wick is heavy")
        overheated = ret_1h_rank >= 95 and metrics["vol_1h_ratio"] >= 3
        if overheated:
            penalty += 10
            risks.append("Very hot short-term extension")
        if regime in {"trend_down", "chaos"}:
            penalty += 10
            risks.append("Regime is not friendly for chasing beta")
        if universe[symbol]["onboard_days"] < 30:
            penalty += 6
            risks.append("New listing volatility remains high")

        total_score = clamp(0.33 * heat_score + 0.37 * market_score + 0.30 * derivatives_score - penalty, 0, 100)

        why: list[str] = []
        if social["posts"] > 0:
            why.append("Binance Square is discussing it")
        if in_cg:
            why.append("CoinGecko trending confirms retail attention")
        if metrics["vol_1h_ratio"] >= 2:
            why.append(f"1h quote volume is {metrics['vol_1h_ratio']:.1f}x recent median")
        if oi_6h >= 5:
            why.append(f"Open interest expanded {oi_6h:.1f}% in 6h")
        if funding_pct < 0:
            why.append(f"Funding is negative at {funding_pct:.3f}%")
        if metrics["breakout"]:
            why.append("Price is near or above short-term breakout structure")

        setup_type = "avoid"
        action = "observe"
        if regime in {"trend_up", "rotation"} and metrics["breakout"] and oi_6h >= 5 and ticker["px_chg_24h"] > 0:
            setup_type = "breakout_long"
            action = "breakout_follow" if not overheated and total_score >= LIVE_SIGNAL_THRESHOLD else "wait_pullback"
        elif regime in {"trend_up", "rotation"} and funding_pct < 0 and oi_1h > 1 and oi_6h > 3 and ticker["px_chg_24h"] > 2:
            setup_type = "squeeze_long"
            action = "small_probe" if total_score >= PAPER_SIGNAL_THRESHOLD else "observe"
        elif (
            regime in {"chaos", "rotation"}
            and 0.5 <= ticker["px_chg_24h"] <= 32
            and metrics["vol_1h_ratio"] >= 1.0
            and oi_1h >= 0.0
            and oi_6h >= 1.5
            and funding_pct <= 0.2
        ):
            setup_type = "chaos_probe_long"
            if total_score >= CHAOS_PROBE_THRESHOLD:
                action = "wait_pullback" if overheated else "small_probe"
            else:
                action = "observe"

        stop_pct = clamp(metrics["atr_pct"] * 1.35, 1.2, 4.4)
        risk_if_live = LIVE_NOTIONAL_MAX * (stop_pct / 100.0)
        if risk_if_live > LIVE_RISK_USD:
            action = "observe"
            risks.append("ATR-based stop is too wide for a 100U account")

        signals.append(
            Signal(
                symbol=symbol,
                coin=coin,
                regime=regime,
                price=ticker["last_price"],
                px_chg_24h=ticker["px_chg_24h"],
                quote_volume=ticker["quote_volume"],
                trade_count=ticker["trade_count"],
                funding_pct=funding_pct,
                oi_usd=oi_usd,
                oi_1h_pct=oi_1h,
                oi_6h_pct=oi_6h,
                heat_score=round(heat_score, 2),
                market_score=round(market_score, 2),
                derivatives_score=round(derivatives_score, 2),
                total_score=round(total_score, 2),
                setup_type=setup_type,
                action=action,
                stop_pct=round(stop_pct, 2),
                atr_pct=round(metrics["atr_pct"], 2),
                invalidation=f"Break back below structure and retrace {round(stop_pct, 2)}%",
                exit_idea="Take partials around 2R, then trail only if volume keeps expanding",
                why=why[:4],
                risks=risks[:4],
                square_posts=social["posts"],
                square_views=social["views"],
                in_cg=in_cg,
                onboard_days=universe[symbol]["onboard_days"],
            )
        )
        time.sleep(0.05)

    signals.sort(key=lambda item: item.total_score, reverse=True)
    meta = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "regime": regime,
        "regime_metrics": regime_metrics,
        "candidate_count": len(candidates),
    }
    return signals, meta


def live_trade_plan(signal: Signal) -> dict[str, Any]:
    margin_usd = LIVE_MARGIN_MAX
    leverage = LIVE_LEVERAGE
    notional_usd = margin_usd * leverage
    stop_price = signal.price * (1 - signal.stop_pct / 100.0)
    take_profit_price = signal.price * (1 + 2 * signal.stop_pct / 100.0)
    return {
        "symbol": signal.symbol,
        "margin_usd": margin_usd,
        "leverage": leverage,
        "notional_usd": notional_usd,
        "risk_usd_max": LIVE_RISK_USD,
        "entry_price": signal.price,
        "stop_price": round(stop_price, 6),
        "take_profit_price": round(take_profit_price, 6),
        "action": signal.action,
    }


def update_paper_book(signals: list[Signal]) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    open_positions = load_json(PAPER_POSITIONS_PATH, [])
    open_by_symbol = {position["symbol"]: position for position in open_positions}
    live_prices = {signal.symbol: signal.price for signal in signals}
    next_open = []
    closed_count = 0

    for position in open_positions:
        symbol = position["symbol"]
        if symbol not in live_prices:
            next_open.append(position)
            continue

        price = live_prices[symbol]
        position["last_price"] = price
        position["max_price"] = max(position.get("max_price", position["entry_price"]), price)
        stop_price = position["stop_price"]
        target_price = position["take_profit_price"]
        age_hours = (now - datetime.fromisoformat(position["opened_at"])).total_seconds() / 3600.0
        close_reason = None

        if price <= stop_price:
            close_reason = "stop"
        elif price >= target_price:
            close_reason = "target"
        elif age_hours >= 24:
            close_reason = "timeout"
        elif position["max_price"] >= position["entry_price"] * (1 + position["stop_pct"] / 100.0):
            trail_trigger = position["max_price"] * (1 - (position["stop_pct"] / 100.0) * 0.8)
            if price <= trail_trigger:
                close_reason = "trail"

        if close_reason:
            pnl_pct = (price / position["entry_price"] - 1.0) * 100.0
            record = {
                **position,
                "closed_at": now.isoformat(),
                "close_price": price,
                "close_reason": close_reason,
                "pnl_pct": round(pnl_pct, 3),
            }
            append_jsonl(PAPER_TRADES_PATH, record)
            closed_count += 1
        else:
            next_open.append(position)

    for signal in signals:
        if signal.total_score < PAPER_SIGNAL_THRESHOLD:
            continue
        if signal.setup_type not in {"breakout_long", "squeeze_long", "chaos_probe_long"}:
            continue
        if signal.symbol in open_by_symbol:
            continue

        stop_price = signal.price * (1 - signal.stop_pct / 100.0)
        target_price = signal.price * (1 + 2 * signal.stop_pct / 100.0)
        next_open.append(
            {
                "symbol": signal.symbol,
                "setup_type": signal.setup_type,
                "regime": signal.regime,
                "score": signal.total_score,
                "entry_price": signal.price,
                "stop_pct": signal.stop_pct,
                "stop_price": round(stop_price, 6),
                "take_profit_price": round(target_price, 6),
                "opened_at": now.isoformat(),
                "last_price": signal.price,
                "max_price": signal.price,
                "heat_score": signal.heat_score,
                "market_score": signal.market_score,
                "derivatives_score": signal.derivatives_score,
                "funding_pct": signal.funding_pct,
                "oi_6h_pct": signal.oi_6h_pct,
                "square_posts": signal.square_posts,
                "in_cg": signal.in_cg,
            }
        )

    save_json(PAPER_POSITIONS_PATH, next_open)

    trades = []
    if PAPER_TRADES_PATH.exists():
        with PAPER_TRADES_PATH.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line:
                    trades.append(json.loads(line))

    wins = sum(1 for trade in trades if trade.get("pnl_pct", 0) > 0)
    summary = {
        "open_positions": len(next_open),
        "closed_count_total": len(trades),
        "closed_this_run": closed_count,
        "win_rate": round(wins / len(trades) * 100, 2) if trades else 0.0,
        "avg_pnl_pct": round(sum(trade.get("pnl_pct", 0) for trade in trades) / len(trades), 3) if trades else 0.0,
    }
    return summary


def build_history_record(meta: dict[str, Any], signals: list[Signal], paper_summary: dict[str, Any], live: list[Signal]) -> dict[str, Any]:
    top_signals = [
        {
            "symbol": signal.symbol,
            "score": signal.total_score,
            "setup_type": signal.setup_type,
            "action": signal.action,
            "heat_score": signal.heat_score,
            "market_score": signal.market_score,
            "derivatives_score": signal.derivatives_score,
        }
        for signal in signals[:10]
    ]
    return {
        "timestamp": meta["timestamp"],
        "regime": meta["regime"],
        "candidate_count": meta["candidate_count"],
        "live_signal_count": len(live),
        "paper_open_positions": paper_summary["open_positions"],
        "paper_closed_total": paper_summary["closed_count_total"],
        "paper_win_rate": paper_summary["win_rate"],
        "top_signals": top_signals,
    }


def run_scan() -> dict[str, Any]:
    signals, meta = build_signals()
    live = [
        signal
        for signal in signals
        if signal.total_score >= LIVE_SIGNAL_THRESHOLD and signal.action in {"breakout_follow", "small_probe", "wait_pullback"}
    ][:5]
    paper_summary = update_paper_book(signals)

    payload = {
        "meta": meta,
        "live_trade_plans": [live_trade_plan(signal) for signal in live],
        "signals": [asdict(signal) for signal in signals[:30]],
        "paper_summary": paper_summary,
    }
    save_json(LATEST_RUN_PATH, payload)
    append_jsonl(SCAN_HISTORY_PATH, build_history_record(meta, signals, paper_summary, live))
    return payload


def print_summary(payload: dict[str, Any]) -> None:
    meta = payload["meta"]
    live_plans = payload["live_trade_plans"]
    paper_summary = payload["paper_summary"]

    print(f"[regime] {meta['regime']} {meta['regime_metrics']}")
    print(f"[live strong signals] {len(live_plans)}")
    for plan in live_plans:
        print(
            f"  {plan['symbol']} action={plan['action']} "
            f"entry={plan['entry_price']:.6f} stop={plan['stop_price']:.6f} tp={plan['take_profit_price']:.6f} "
            f"notional={plan['notional_usd']:.1f}"
        )
    print(f"[paper] {paper_summary}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Binance perpetual opportunity scanner")
    parser.add_argument("--quiet", action="store_true", help="Only write files, skip console summary")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    payload = run_scan()
    if not args.quiet:
        print_summary(payload)


if __name__ == "__main__":
    main()
