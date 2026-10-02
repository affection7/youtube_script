"""YouTube Data API tools and helpers for the AI Agent."""

from __future__ import annotations

import json
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

COLD_DM_MIN_LENGTH = 40
COLD_DM_MAX_LENGTH = 800
_COLD_DM_PLACEHOLDER_RE = re.compile(
    r"\[[^\]\r\n]{1,80}\]|\{\{?[^}\r\n]{1,80}\}?\}|<[^>\r\n]{1,80}>"
)
_COLD_DM_TEMPLATE_PATTERNS = (
    "great channel",
    "love your content",
    "came across your channel",
    "hope you're well",
    "just wanted to reach out",
    "take your channel to the next level",
)

NEGATION_INTENT_RE = re.compile(
    r"(thinking about|thinking of|planning|plan to|considering|coming soon|in the works|"
    r"планирую|планируем|в планах|думаю (?:о|про|об)|собираюсь)",
    re.IGNORECASE
)
QUESTION_HINTS_RE = re.compile(
    r"(\?|\bhow\b|\bwhat\b|\bwhy\b|\bwhen\b|\bcan (?:you|u)\b|\bcould (?:you|u)\b|\bplease\b|"
    r"\bguide\b|\btutorial\b|\bstep[- ]by[- ]step\b|\bexplain\b|\bmake a video\b|"
    r"\bкак\b|\bчто\b|\bпочему\b|\bможно ли\b|\bподскажи|\bобъясни|\bгайд|\bтуториал|\bпошагов)",
    re.IGNORECASE
)


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
            if video_id or parts[0] in ("shorts", "live", "embed"):
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


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def get_recent_videos(youtube, uploads_playlist_id: str, limit: int = 10) -> list[dict[str, Any]]:
    """Fetch latest uploads with titles, descriptions, dates and engagement stats."""
    if not uploads_playlist_id:
        return []

    resp = youtube.playlistItems().list(
        part="snippet,contentDetails",
        playlistId=uploads_playlist_id,
        maxResults=min(limit, 50)
    ).execute()

    videos = []
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

    # Engagement stats (views / likes / comments) come from a separate videos().list call.
    video_ids = [v["video_id"] for v in videos]
    stats_by_id: dict[str, dict[str, Any]] = {}
    for i in range(0, len(video_ids), 50):
        try:
            stats_resp = youtube.videos().list(
                part="statistics",
                id=",".join(video_ids[i:i + 50])
            ).execute()
            for item in stats_resp.get("items", []):
                st = item.get("statistics", {})
                stats_by_id[item.get("id")] = {
                    "views": _int_or_none(st.get("viewCount")),
                    "likes": _int_or_none(st.get("likeCount")),
                    "comments_count": _int_or_none(st.get("commentCount")),
                }
        except Exception:
            continue

    for v in videos:
        st = stats_by_id.get(v["video_id"], {})
        v["views"] = st.get("views")
        v["likes"] = st.get("likes")
        v["comments_count"] = st.get("comments_count")

    return videos


def get_video_comments(youtube, video_ids: list[str], max_comments: int = 15) -> list[dict[str, Any]]:
    """Fetch a representative sample of audience comments across videos.

    Spam/bot messages are filtered out; within each video candidates are
    scored (questions, substance, likes) and then picked round-robin so the
    final sample covers all videos instead of only the first ones.
    """
    spam_patterns = re.compile(
        r"(t\.me/|whatsapp|telegram|viber|promo|invest|crypto pump|profit|whatsapp me|"
        r"presale|airdrop|binance.*bot|passive income|dm me on)",
        re.IGNORECASE
    )

    def _comment_score(text: str, likes: int) -> int:
        score = 1
        if QUESTION_HINTS_RE.search(text):
            score += 3
        if len(text) >= 30:
            score += 2
        if likes >= 50:
            score += 2
        elif likes >= 10:
            score += 1
        return score

    candidates_by_video: dict[str, list[dict[str, Any]]] = {}
    for vid in video_ids:
        candidates: list[dict[str, Any]] = []
        try:
            resp = youtube.commentThreads().list(
                part="snippet",
                videoId=vid,
                maxResults=50,
                textFormat="plainText",
                order="relevance"
            ).execute()

            for item in resp.get("items", []):
                sn = item.get("snippet", {}).get("topLevelComment", {}).get("snippet", {})
                text = (sn.get("textDisplay") or "").strip()
                likes = int(sn.get("likeCount", 0) or 0)

                if not text or len(text) < 15 or len(text) > 400:
                    continue
                if spam_patterns.search(text):
                    continue

                candidates.append({
                    "video_id": vid,
                    "author": sn.get("authorDisplayName", "Viewer"),
                    "text": text,
                    "likes": likes,
                    "question": bool(QUESTION_HINTS_RE.search(text)),
                })
        except Exception:
            # Comments may be disabled on this video
            continue

        candidates.sort(key=lambda c: _comment_score(c["text"], c["likes"]), reverse=True)
        candidates_by_video[vid] = candidates

    comments: list[dict[str, Any]] = []
    while len(comments) < max_comments:
        picked_any = False
        for vid in video_ids:
            bucket = candidates_by_video.get(vid) or []
            if bucket:
                comments.append(bucket.pop(0))
                picked_any = True
                if len(comments) >= max_comments:
                    break
        if not picked_any:
            break

    return comments


def analyze_monetization_matrix(
    channel_desc: str = "",
    video_descs: list[str] | None = None,
    external_links: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    """Analyze descriptions and extracted links to detect monetization methods and confidence."""
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
            regex = r"\b" + p if not p.startswith(r"t\.me") and "." not in p else p
            for m in re.finditer(regex, lower):
                # "thinking about creating a course" is intent, not monetization
                window = lower[max(0, m.start() - 60):m.end() + 60]
                if NEGATION_INTENT_RE.search(window):
                    continue
                matched = True
                total_matches += 1
                break
            if matched:
                break
        matrix[key] = matched
        if matched:
            detected_count += 1

    # Structured links are stronger evidence than words in descriptions.
    confirmed_by_links: list[str] = []
    link_category_to_key = {
        "course": "course",
        "community": "community",
        "newsletter": "newsletter",
        "booking": "consulting",
        "product": "product",
        "affiliate": "affiliate",
    }
    for link in external_links or []:
        cat = link.get("category") if isinstance(link, dict) else None
        key = link_category_to_key.get(str(cat))
        if key:
            if not matrix.get(key):
                matrix[key] = True
                detected_count += 1
            if key not in confirmed_by_links:
                confirmed_by_links.append(key)

    monetization_detected = detected_count > 0

    # Calculate confidence based on matches and text coverage
    if total_matches >= 3:
        confidence = 0.95
    elif total_matches >= 1:
        confidence = 0.88
    elif len(lower.strip()) >= 300:
        confidence = 0.82
    elif len(lower.strip()) >= 50:
        confidence = 0.70
    else:
        confidence = 0.50
    if confirmed_by_links:
        confidence = max(confidence, 0.9)

    matrix["monetization_detected"] = monetization_detected
    matrix["confidence"] = round(confidence, 2)
    matrix["confirmed_by_links"] = confirmed_by_links
    return matrix


URL_RE = re.compile(r"https?://[^\s)\]>\"'<>]+", re.IGNORECASE)

# Ordered rules: first match wins. The URL is classified together with ~30
# chars of text right before it, so "Course: https://skool.com/x" keeps its
# label context without leaking into the previous unrelated line.
LINK_CATEGORY_RULES: list[tuple[str, list[str]]] = [
    ("course", [
        r"teachable\.com", r"kajabi\.com", r"udemy\.com", r"skillshare\.com",
        r"thinkific\.com", r"masterclass", r"academy", r"\bcourse\b",
    ]),
    ("community", [
        r"discord\.gg", r"discord\.com", r"t\.me/", r"telegram\.", r"patreon\.com",
        r"skool\.com", r"circle\.so", r"boosty\.to", r"whop\.com",
    ]),
    ("newsletter", [
        r"substack\.com", r"beehiiv\.com", r"convertkit\.com", r"mailerlite\.com",
        r"newsletter",
    ]),
    ("booking", [
        r"calendly\.com", r"cal\.com/", r"bookings?", r"консультаци",
    ]),
    ("product", [
        r"gumroad\.com", r"etsy\.com", r"notion\.", r"\bshop\b", r"\bstore\b", r"template",
    ]),
    ("affiliate", [
        r"amzn\.to", r"amazon\.", r"bit\.ly", r"[?&](?:ref|aff|af)=", r"affiliate",
        r"partner", r"промокод", r"промо", r"бонус",
        r"(?:bybit|binance|okx|mexc|kucoin|bingx|huobi|htx|wazirx|coindcx)\.com",
    ]),
    ("social", [
        r"instagram\.com", r"twitter\.com", r"\bx\.com", r"tiktok\.com",
        r"facebook\.com", r"linkedin\.com", r"youtube\.com", r"youtu\.be",
    ]),
]


def extract_external_links(
    channel_desc: str = "",
    video_descs: list[str] | None = None
) -> dict[str, Any]:
    """Extract URLs from descriptions and classify them by domain/label.

    No network requests: classification uses the URL itself plus the text
    immediately before it ("Course: https://..." -> course).
    """
    links: list[dict[str, Any]] = []
    seen: set[str] = set()

    sources: list[tuple[str, str]] = [("channel", channel_desc or "")]
    for i, desc in enumerate(video_descs or [], start=1):
        sources.append((f"video{i}", desc or ""))

    for source_name, text in sources:
        for m in URL_RE.finditer(text):
            url = m.group(0).rstrip(".,;")
            if url in seen:
                for link in links:
                    if link["url"] == url and source_name not in link["sources"]:
                        link["sources"].append(source_name)
                continue
            seen.add(url)
            context = text[max(0, m.start() - 30):m.start()]
            haystack = f"{context} {url}".lower()
            category = "unknown"
            for cat, rules in LINK_CATEGORY_RULES:
                if any(re.search(rule, haystack) for rule in rules):
                    category = cat
                    break
            links.append({
                "url": url,
                "category": category,
                "sources": [source_name],
            })

    summary: dict[str, int] = {}
    for link in links:
        summary[link["category"]] = summary.get(link["category"], 0) + 1

    return {"links": links, "summary": summary, "total": len(links)}


RISK_FLAG_PATTERNS: dict[str, list[str]] = {
    "referral_farming": [
        r"referral", r"refer a friend", r"invite (?:code|friends?)", r"sign ?-?up bonus",
        r"deposit bonus", r"promo ?code.*bonus", r"реферал", r"пригласи друга",
        r"бонус за регистраци",
    ],
    "unverifiable_token_hype": [
        r"\b(?:50|100|1000)x\b", r"\d+x gem", r"next .*gem", r"moonshot", r"to the moon",
        r"guaranteed (?:\d+x|profit|return)", r"token presale", r"presale.*token",
        r"guaranteed pump", r"икс[аоы]", r"гарантирую", r"пресейл",
    ],
    "leveraged_signals_promotion": [
        r"trading signals?", r"(?:vip|premium|free) signals?", r"signals? (?:group|channel|vip)",
        r"futures? signals?", r"leverage(?:d)? (?:trading|signals?)", r"\d+x leverage",
        r"win ?-?rate (?:of )?\d+", r"\d+\s?% win ?-?rate", r"\d+\s?% (?:success|accuracy)",
        r"trading bot", r"сигнал[ыа]", r"винре[йи]т", r"фьючерс",
    ],
}


def detect_risk_flags(
    comments: list[dict[str, Any]] | list[str] | None = None,
    video_titles: list[str] | None = None
) -> dict[str, Any]:
    """Scan fetched audience comments and video titles for high-risk promotion patterns."""
    texts: list[str] = []
    for c in comments or []:
        texts.append(str(c.get("text", "")) if isinstance(c, dict) else str(c))
    for t in video_titles or []:
        texts.append(str(t))

    corpus = "\n".join(texts).lower()

    risk_flags: list[str] = []
    matched_examples: dict[str, list[str]] = {}
    for flag, patterns in RISK_FLAG_PATTERNS.items():
        hits: list[str] = []
        for p in patterns:
            m = re.search(p, corpus)
            if m:
                hits.append(m.group(0))
        if hits:
            risk_flags.append(flag)
            matched_examples[flag] = hits[:3]

    return {
        "risk_flags": risk_flags,
        "matched_examples": matched_examples,
        "texts_scanned": len(texts),
    }


def validate_cold_dm(
    cold_dm: str,
    personalization_terms: list[str] | None = None
) -> dict[str, Any]:
    """Validate a Cold DM with deterministic quality rules."""
    text = (cold_dm or "").strip()
    normalized = text.casefold()
    issues: list[str] = []

    if len(text) < COLD_DM_MIN_LENGTH or len(text) > COLD_DM_MAX_LENGTH:
        issues.append(
            f"length must be between {COLD_DM_MIN_LENGTH} and {COLD_DM_MAX_LENGTH} characters"
        )
    if _COLD_DM_PLACEHOLDER_RE.search(text):
        issues.append("contains an unfilled placeholder")
    if any(pattern in normalized for pattern in _COLD_DM_TEMPLATE_PATTERNS):
        issues.append("contains a generic template phrase")

    terms = [term.strip().casefold() for term in (personalization_terms or []) if term.strip()]
    personalized = not terms or any(term in normalized for term in terms)
    if terms and not personalized:
        issues.append("does not contain a supplied personalization term")

    return {
        "valid": not issues,
        "issues": issues,
        "length": len(text),
        "personalized": personalized,
    }


def save_outreach_proposal(
    channel_title: str,
    report_text: str,
    cold_dm: str,
    matrix: dict[str, Any] | str | None = None,
    personalization_terms: list[str] | None = None
) -> dict[str, Any]:
    """Save the audit report, the monetization matrix and the cold outreach DM to disk."""
    validation = validate_cold_dm(cold_dm, personalization_terms)
    if not validation["valid"]:
        raise ValueError("Invalid Cold DM: " + "; ".join(validation["issues"]))

    slug = slugify(channel_title)
    folder = get_dated_dir()

    analysis_content = report_text.strip() + "\n"
    if matrix is not None:
        if isinstance(matrix, str):
            try:
                matrix = json.loads(matrix)
            except Exception:
                pass  # keep the raw string
        analysis_content += "\n### Monetization Matrix\n"
        analysis_content += (
            matrix.strip() + "\n" if isinstance(matrix, str)
            else json.dumps(matrix, ensure_ascii=False, indent=2) + "\n"
        )

    report_path = os.path.join(folder, f"analysis_{slug}.txt")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(analysis_content)

    dm_path = os.path.join(folder, f"outreach_dm_{slug}.txt")
    with open(dm_path, "w", encoding="utf-8") as f:
        f.write(cold_dm.strip() + "\n")

    return {
        "analysis_file": os.path.abspath(report_path),
        "outreach_file": os.path.abspath(dm_path),
        "validation": validation,
    }
