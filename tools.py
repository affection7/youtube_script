"""YouTube Data API tools and helpers for the AI Agent."""

from __future__ import annotations

import os
import re
import unicodedata
from datetime import datetime
from typing import Any
from urllib.parse import parse_qs, urlparse

try:
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
except ImportError:
    build = None
    HttpError = Exception


REPORTS_DIR = os.path.join("reports", "channels")
_NICHE_CACHE: dict[tuple[str, int], list[dict[str, Any]]] = {}


def slugify(text: str) -> str:
    """Make text filesystem-safe across Windows/Linux/macOS."""
    text = unicodedata.normalize("NFKD", text or "channel")
    text = text.encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^\w\s-]", "", text).strip()
    return re.sub(r"[-\s]+", "_", text)[:60] or "channel"


def get_dated_dir() -> str:
    """Return reports path for current date."""
    date_str = datetime.now().strftime("%Y-%m-%d")
    target = os.path.join(REPORTS_DIR, date_str)
    os.makedirs(target, exist_ok=True)
    return target


def parse_channel_input(user_input: str) -> tuple[str, str] | None:
    """Parse user input into ('handle', 'name') or ('id', 'UC...')."""
    raw = (user_input or "").strip()
    if not raw:
        return None

    if raw.startswith("@"):
        return ("handle", raw[1:].strip())

    if raw.startswith("UC") and len(raw) >= 20 and " " not in raw:
        return ("id", raw)

    if "youtube.com" in raw or "youtu.be" in raw:
        parsed = urlparse(raw if "://" in raw else f"https://{raw}")
        path = parsed.path.strip("/")
        parts = path.split("/")
        if parts and parts[0].startswith("@"):
            return ("handle", parts[0][1:])
        if len(parts) >= 2 and parts[0] == "channel":
            return ("id", parts[1])
        if parts and parts[0] in ("watch", "shorts", "live", "embed"):
            video_id = parse_qs(parsed.query).get("v", [None])[0]
            if video_id:
                raise ValueError("Указана ссылка на видео, а не на канал")
            raise ValueError(f"Недостаточно данных для определения канала: '{user_input}'")
        if parts:
            if parts[0] in ("c", "user") and len(parts) >= 2:
                return ("handle", parts[1])
            return ("handle", parts[0])

    return ("handle", raw)


def resolve_channel(youtube, channel_input: str) -> dict[str, Any]:
    """Resolve channel metadata from handle, ID, or search query."""
    parsed = parse_channel_input(channel_input)
    if not parsed:
        raise ValueError(f"Invalid channel input: '{channel_input}'")

    kind, value = parsed

    if kind == "id":
        resp = youtube.channels().list(
            part="snippet,statistics,contentDetails,brandingSettings",
            id=value
        ).execute()
        items = resp.get("items", [])
        if items:
            return items[0]

    if kind == "handle":
        try:
            resp = youtube.channels().list(
                part="snippet,statistics,contentDetails,brandingSettings",
                forHandle=value
            ).execute()
            items = resp.get("items", [])
            if items:
                return items[0]
        except Exception:
            pass

        # Fallback to search if direct handle resolution fails
        search_resp = youtube.search().list(
            part="snippet",
            q=value,
            type="channel",
            maxResults=1
        ).execute()
        search_items = search_resp.get("items", [])
        if search_items:
            ch_id = search_items[0]["snippet"]["channelId"]
            return resolve_channel(youtube, ch_id)

    raise ValueError(f"Channel not found for '{channel_input}'")


def search_channels_by_niche(youtube, query: str, max_results: int = 25) -> list[dict[str, Any]]:
    """Search YouTube channels by niche or keyword with stats."""
    if not query.strip():
        return []

    cache_key = (query.strip().casefold(), min(max_results, 50))
    if cache_key in _NICHE_CACHE:
        return [dict(item) for item in _NICHE_CACHE[cache_key]]

    search_resp = youtube.search().list(
        part="snippet",
        q=query.strip(),
        type="channel",
        maxResults=min(max_results, 50)
    ).execute()

    items = search_resp.get("items", [])
    if not items:
        return []

    channel_ids = [it["snippet"]["channelId"] for it in items if "channelId" in it.get("snippet", {})]
    if not channel_ids:
        return []

    details_resp = youtube.channels().list(
        part="snippet,statistics",
        id=",".join(channel_ids)
    ).execute()

    results = []
    for it in details_resp.get("items", []):
        sn = it.get("snippet", {})
        stats = it.get("statistics", {})
        results.append({
            "channel_id": it.get("id"),
            "title": sn.get("title", "Unknown"),
            "custom_url": sn.get("customUrl", ""),
            "subscribers": stats.get("subscriberCount", "Hidden"),
            "video_count": stats.get("videoCount", "0"),
            "view_count": stats.get("viewCount", "0"),
            "description": sn.get("description", "")[:200],
            "country": sn.get("country", ""),
            "matrix": analyze_monetization_matrix(sn.get("description", ""))
        })

    _NICHE_CACHE[cache_key] = results
    return [dict(item) for item in results]


def get_channel_overview(youtube, channel_input: str) -> dict[str, Any]:
    """Get high-level stats and info about the channel."""
    item = resolve_channel(youtube, channel_input)
    snippet = item.get("snippet", {})
    stats = item.get("statistics", {})

    return {
        "channel_id": item.get("id"),
        "title": snippet.get("title", "Unknown"),
        "custom_url": snippet.get("customUrl", ""),
        "description": snippet.get("description", "")[:1000],
        "created_at": snippet.get("publishedAt", "")[:10],
        "country": snippet.get("country", "Unknown"),
        "subscribers": stats.get("subscriberCount", "Hidden"),
        "total_views": stats.get("viewCount", "0"),
        "video_count": stats.get("videoCount", "0"),
        "uploads_playlist_id": item.get("contentDetails", {}).get("relatedPlaylists", {}).get("uploads", "")
    }


def get_recent_videos(youtube, uploads_playlist_id: str, limit: int = 10) -> list[dict[str, Any]]:
    """Fetch the latest uploaded videos including titles, descriptions, and publish dates."""
    if not uploads_playlist_id:
        return []

    videos = []
    page_token = None
    remaining = max(0, min(limit, 50))
    while remaining:
        request = youtube.playlistItems().list(
            part="snippet,contentDetails",
            playlistId=uploads_playlist_id,
            maxResults=min(remaining, 50),
            **({"pageToken": page_token} if page_token else {})
        )
        resp = request.execute()
        for it in resp.get("items", []):
            sn = it.get("snippet", {})
            vid_id = it.get("contentDetails", {}).get("videoId")
            if not vid_id:
                continue
            videos.append({
                "video_id": vid_id,
                "title": sn.get("title", ""),
                "description": sn.get("description", "")[:1500],
                "published_at": sn.get("publishedAt", "")[:10],
            })
        remaining = limit - len(videos)
        page_token = resp.get("nextPageToken")
        if not page_token:
            break

    return videos


def get_video_comments(youtube, video_ids: list[str], max_comments: int = 15) -> list[dict[str, Any]]:
    """Fetch top audience comments from given video IDs, skipping bot/spam messages."""
    comments = []
    spam_patterns = re.compile(
        r"(t\.me/|whatsapp|telegram|viber|promo|invest|crypto pump|profit|whatsapp me|"
        r"presale|airdrop|binance.*bot|passive income|dm me on)",
        re.IGNORECASE
    )

    for vid in video_ids:
        if len(comments) >= max_comments:
            break
        page_token = None
        try:
            while len(comments) < max_comments:
                request = youtube.commentThreads().list(
                    part="snippet",
                    videoId=vid,
                    maxResults=min(20, max_comments - len(comments)),
                    textFormat="plainText",
                    order="relevance",
                    **({"pageToken": page_token} if page_token else {})
                )
                resp = request.execute()
                for item in resp.get("items", []):
                    sn = item.get("snippet", {}).get("topLevelComment", {}).get("snippet", {})
                    text = (sn.get("textDisplay") or "").strip()
                    likes = int(sn.get("likeCount", 0))

                    if not text or len(text) < 15 or len(text) > 400 or spam_patterns.search(text):
                        continue
                    comments.append({"video_id": vid, "author": sn.get("authorDisplayName", "Viewer"),
                                     "text": text, "likes": likes})
                    if len(comments) >= max_comments:
                        break
                page_token = resp.get("nextPageToken")
                if not page_token:
                    break
        except Exception:
            # Comments may be disabled on this video
            continue

    return comments


def analyze_monetization_matrix(channel_desc: str = "", video_descs: list[str] | None = None) -> dict[str, Any]:
    """Analyze channel & video descriptions to detect monetization methods and confidence."""
    text_corpus = f"{channel_desc} " + " ".join(video_descs or [])
    lower = text_corpus.lower()

    # Heuristic pattern definitions
    patterns = {
        "course": [
            r"course", r"masterclass", r"academy", r"workshop", r"teachable\.com",
            r"kajabi\.com", r"udemy\.com", r"skillshare\.com", r"обучение", r"курс", r"интенсив"
        ],
        "coaching": [
            r"coaching", r"1-on-1", r"1 on 1", r"mentorship", r"mentor", r"наставничеств", r"ментор"
        ],
        "consulting": [
            r"consulting", r"consultation", r"book a call", r"calendly\.com", r"cal\.com",
            r"strategy session", r"консультаци"
        ],
        "community": [
            r"patreon\.com", r"discord\.gg", r"discord\.com/invite", r"skool\.com",
            r"circle\.so", r"telegram", r"t\.me/", r"membership", r"сообщество", r"клуб", r"бусти", r"boosty\.to"
        ],
        "newsletter": [
            r"substack\.com", r"beehiiv\.com", r"convertkit\.com", r"newsletter",
            r"рассылк", r"subscribe to my email", r"mailerlite\.com"
        ],
        "affiliate": [
            r"amzn\.to", r"amazon\.com/shop", r"bit\.ly", r"affiliate", r"partner",
            r"discount code", r"promo code", r"партнерск", r"реферал", r"скидк.*промокод"
        ],
        "sponsorship": [
            r"sponsored by", r"thanks to .* for sponsoring", r"brought to you by",
            r"sponsorship", r"спонсор", r"реклама"
        ],
        "product": [
            r"gumroad\.com", r"notion\.site", r"etsy\.com", r"digital download",
            r"template", r"software", r"saas", r"шаблон"
        ],
        "merch": [
            r"merch", r"store\.", r"shop\.", r"teespring\.com", r"spring\.com",
            r"merchandise", r"мерч"
        ]
    }

    matrix: dict[str, Any] = {}
    detected_count = 0
    total_matches = 0

    for key, regex_list in patterns.items():
        matched = False
        for p in regex_list:
            if re.search(r"\b" + p if not p.startswith(r"t\.me") and "." not in p else p, lower):
                matched = True
                total_matches += 1
                break
        matrix[key] = matched
        if matched:
            detected_count += 1

    monetization_detected = detected_count > 0

    # Calculate confidence based on matches and text coverage
    if total_matches >= 4:
        confidence = 0.95
    elif total_matches == 3:
        confidence = 0.85
    elif total_matches == 2:
        confidence = 0.72
    elif total_matches == 1:
        confidence = 0.58
    elif len(lower.strip()) >= 300:
        confidence = 0.82
    elif len(lower.strip()) >= 50:
        confidence = 0.70
    else:
        confidence = 0.50

    matrix["monetization_detected"] = monetization_detected
    matrix["confidence"] = round(confidence, 2)
    return matrix


def save_outreach_proposal(channel_title: str, report_text: str, cold_dm: str,
                           matrix: dict[str, Any] | None = None) -> dict[str, str]:
    """Save the audit report and the finished cold outreach DM to disk."""
    slug = slugify(channel_title)
    folder = get_dated_dir()

    report_path = os.path.join(folder, f"analysis_{slug}.txt")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report_text.strip() + "\n")
        if matrix is not None:
            import json
            f.write("\n\nMONETIZATION MATRIX (JSON)\n")
            f.write(json.dumps(matrix, ensure_ascii=False, indent=2) + "\n")

    dm_path = os.path.join(folder, f"outreach_dm_{slug}.txt")
    with open(dm_path, "w", encoding="utf-8") as f:
        f.write(cold_dm.strip() + "\n")

    return {
        "analysis_file": os.path.abspath(report_path),
        "outreach_file": os.path.abspath(dm_path)
    }
