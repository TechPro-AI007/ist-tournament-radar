import hashlib
import json
import os
import re
from datetime import datetime, timezone
from urllib.parse import quote_plus

import feedparser
import requests

WEBHOOK_URL = os.environ["DISCORD_WEBHOOK_URL"]
SEEN_FILE = "seen_tournaments.json"

# Replace these with your IST Gaming Society Role IDs (Right-click role -> Copy Role ID)
ROLE_IDS = {
    "BGMI": "1575190598938398983",       # Replace with @BGMI Role ID
    "Free Fire": "1575190644933132358",  # Replace with @Free Fire MAX Role ID
    "CODM": "1575190733818957865",       # Replace with @CODM Role ID
    "General": "1575190474401128570",    # Replace with @Verified Student Role ID
}

# Targeted Indian esports & college tournament search feeds
SEARCH_QUERIES = [
    "BGMI tournament India registration 2026",
    "BGMI college esports tournament India",
    "Free Fire MAX tournament India registration",
    "CODM Call of Duty Mobile tournament India registration",
    "esports tournament Delhi NCR Gurugram college fest",
]

GAME_RULES = [
    ("BGMI", ["bgmi", "battlegrounds mobile india", "krafton", "bgis", "bmps"], 0xF59E0B),
    ("Free Fire", ["free fire", "ff max", "garena"], 0xEF4444),
    ("CODM", ["codm", "call of duty mobile"], 0x10B981),
]


def load_seen() -> set:
    if not os.path.exists(SEEN_FILE):
        return set()
    with open(SEEN_FILE, "r", encoding="utf-8") as f:
        return set(json.load(f))


def save_seen(seen: set) -> None:
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted(list(seen))[-500:], f, indent=2)


def detect_game(text: str):
    lower = text.lower()
    for game, keywords, color in GAME_RULES:
        if any(kw in lower for kw in keywords):
            return game, color
    return "General", 0x5865F2


def clean_html(raw: str) -> str:
    text = re.sub(r"<[^>]+>", "", raw or "")
    return re.sub(r"\s+", " ", text).strip()[:280]


def fetch_candidates():
    candidates = []
    for query in SEARCH_QUERIES:
        rss_url = (
            f"https://news.google.com/rss/search?q={quote_plus(query)}"
            "&hl=en-IN&gl=IN&ceid=IN:en"
        )
        feed = feedparser.parse(rss_url)
        for entry in feed.entries[:6]:
            title = entry.get("title", "").strip()
            link = entry.get("link", "").strip()
            summary = clean_html(entry.get("summary", ""))
            published = entry.get("published", "Recently announced")
            uid = hashlib.sha256(title.lower().encode("utf-8")).hexdigest()[:16]
            candidates.append(
                {
                    "id": uid,
                    "title": title,
                    "link": link,
                    "summary": summary,
                    "published": published,
                }
            )
    return candidates


def post_to_discord(item: dict) -> None:
    game, color = detect_game(f"{item['title']} {item['summary']}")
    role_id = ROLE_IDS.get(game, ROLE_IDS["General"])
    ping_text = f"<@&{role_id}>" if role_id else ""

    payload = {
        "username": "IST Tournament Radar",
        "content": f"🚨 **New {game} Tournament / Event Alert!** {ping_text}",
        "embeds": [
            {
                "title": item["title"][:250],
                "url": item["link"],
                "description": item["summary"] or "Click the title link for registration & bracket details.",
                "color": color,
                "fields": [
                    {"name": "🎮 Category", "value": game, "inline": True},
                    {"name": "📅 Spotted", "value": item["published"][:40], "inline": True},
                ],
                "footer": {"text": "IST Gaming Society • Automated Radar"},
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        ],
    }

    resp = requests.post(WEBHOOK_URL, json=payload, timeout=15)
    resp.raise_for_status()


def main():
    seen = load_seen()
    candidates = fetch_candidates()
    new_posts = 0

    for item in candidates:
        if item["id"] in seen:
            continue
        # Filter out noise that isn't actually tournament/registration/qualifier related
        combined = f"{item['title']} {item['summary']}".lower()
        if not any(
            word in combined
            for word in ["tournament", "register", "registration", "qualifier", "championship", "cup", "scrim", "open", "esports"]
        ):
            continue

        post_to_discord(item)
        seen.add(item["id"])
        new_posts += 1
        if new_posts >= 5:  # Cap at 5 alerts per run to prevent channel spam
            break

    save_seen(seen)
    print(f"Posted {new_posts} new tournament alerts.")


if __name__ == "__main__":
    main()