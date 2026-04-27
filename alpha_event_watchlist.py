#!/usr/bin/env python3
import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

ALPHA_WATCHLIST_PATH = DATA_DIR / "alpha_watchlist.json"
ALPHA_SEEN_PATH = DATA_DIR / "alpha_seen.json"

ANNOUNCEMENT_API = "https://www.binance.com/bapi/composite/v1/public/cms/article/list/query"
HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
}

TRIGGER_KEYWORDS = [
    "alpha",
    "airdrop",
    "tge",
    "token generation",
    "will list",
    "will launch",
    "exclusive",
    "binance wallet",
    "hodler",
]

EXCLUDE_KEYWORDS = [
    "delist",
    "delisting",
    "maintenance",
    "launchpool",
    "megadrop",
    "buyback",
    "futures will launch",
    "perpetual contract",
]


def api_get_json(url: str, params: dict[str, Any]) -> dict[str, Any]:
    response = requests.get(url, params=params, headers=HEADERS, timeout=12)
    response.raise_for_status()
    return response.json()


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def save_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def article_fingerprint(article: dict[str, Any]) -> str:
    stable = f"{article.get('code','')}|{article.get('title','')}|{article.get('releaseDate',0)}"
    return hashlib.sha1(stable.encode("utf-8")).hexdigest()


def extract_symbols(text: str) -> list[str]:
    raw = set(re.findall(r"\b[A-Z][A-Z0-9]{1,9}\b", text.upper()))
    stopwords = {"BINANCE", "USDT", "USD", "TGE", "API", "APR", "BTC", "ETH"}
    return sorted(symbol for symbol in raw if symbol not in stopwords)


def score_article(title: str, body: str) -> tuple[int, list[str]]:
    title_l = title.lower()
    body_l = body.lower()
    text = f"{title_l}\n{body_l}"

    reasons: list[str] = []
    score = 0

    for keyword in TRIGGER_KEYWORDS:
        if keyword in text:
            score += 12
            reasons.append(f"命中关键词: {keyword}")

    if "will list" in text or "will launch" in text:
        score += 18
    if "airdrop" in text or "hodler" in text:
        score += 10
    if "binance wallet" in text:
        score += 8

    return score, reasons[:4]


def should_exclude(title: str, body: str) -> bool:
    text = f"{title.lower()}\n{body.lower()}"
    return any(keyword in text for keyword in EXCLUDE_KEYWORDS)


def fetch_articles(page_size: int = 20) -> list[dict[str, Any]]:
    all_articles: list[dict[str, Any]] = []
    for catalog_id in [48, 161, 93]:
        payload = api_get_json(
            ANNOUNCEMENT_API,
            {
                "type": 1,
                "catalogId": catalog_id,
                "pageNo": 1,
                "pageSize": page_size,
            },
        )
        catalogs = payload.get("data", {}).get("catalogs", [])
        for catalog in catalogs:
            all_articles.extend(catalog.get("articles", []))
    return all_articles


def build_watchlist(hours_back: int = 72) -> dict[str, Any]:
    seen = load_json(ALPHA_SEEN_PATH, {})
    articles = fetch_articles()
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours_back)

    selected = []
    new_seen = dict(seen)

    for article in articles:
        title = article.get("title", "")
        body = article.get("body", "") or article.get("summary", "") or ""
        release_ms = int(article.get("releaseDate", 0) or 0)
        release_at = datetime.fromtimestamp(release_ms / 1000, tz=timezone.utc) if release_ms else datetime.now(timezone.utc)
        if release_at < cutoff:
            continue
        if should_exclude(title, body):
            continue

        score, reasons = score_article(title, body)
        if score < 18:
            continue

        fingerprint = article_fingerprint(article)
        symbols = extract_symbols(f"{title}\n{body}")
        selected.append(
            {
                "id": fingerprint,
                "title": title,
                "release_at": release_at.isoformat(),
                "score": score,
                "symbols": symbols[:8],
                "reasons": reasons,
                "url": article.get("webLink") or article.get("code") or "",
                "is_new": fingerprint not in seen,
            }
        )
        new_seen[fingerprint] = release_at.isoformat()

    selected.sort(key=lambda item: (item["score"], item["release_at"]), reverse=True)

    trimmed_seen = {
        key: value
        for key, value in new_seen.items()
        if datetime.fromisoformat(value) >= datetime.now(timezone.utc) - timedelta(days=14)
    }
    save_json(ALPHA_SEEN_PATH, trimmed_seen)

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "hours_back": hours_back,
        "count": len(selected),
        "items": selected[:20],
    }
    save_json(ALPHA_WATCHLIST_PATH, payload)
    return payload


def main() -> None:
    payload = build_watchlist()
    print(f"[alpha watchlist] count={payload['count']}")
    for item in payload["items"][:5]:
        symbol_text = ",".join(item["symbols"]) if item["symbols"] else "-"
        print(f"  score={item['score']} symbols={symbol_text} title={item['title']}")


if __name__ == "__main__":
    main()
