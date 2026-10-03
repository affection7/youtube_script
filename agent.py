"""Autonomous AI Agent for YouTube Channel Monetization Audit & Cold Outreach."""

from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from typing import Any, Callable

try:
    from googleapiclient.discovery import build
except ImportError:
    build = None

import tools

DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"
DEFAULT_MODEL = "deepseek-chat"
MAX_API_RETRIES = 3
RETRY_BACKOFF_SECONDS = 0.5
RETRYABLE_HTTP_STATUS_CODES = {408, 429, 500, 502, 503, 504}

# The save tool rejects a cold_dm that never states the service offer, so the
# agent's loop feeds the error back to the model and it rewrites the DM.
OFFER_INDICATOR_RE = re.compile(
    r"(\b(?:i|we)\s+(?:build|make|create|offer|provide)\b"
    r"|\b(?:i|we)\s+help\b"
    r"|done[\s-]for[\s-]you"
    r"|\bturnkey\b"
    r"|for you so you don'?t"
    r"|heavy lifting)",
    re.IGNORECASE
)
COLD_DM_MISSING_OFFER_ERROR = (
    "The cold_dm text appears to be missing the service offer "
    "(Hook/Insight present, but no 'I build...for you' statement found). "
    "Rewrite the DM to include it, then call save_outreach_proposal again."
)

AGENT_SYSTEM_PROMPT = """You are an elite YouTube Monetization Strategist and Outreach Copywriter.
Your goal: find ONE strong, provable, personal hook and turn it into a single high-converting Cold DM - not a generic report.

### YOUR WORKFLOW:
1. Call `get_channel_overview` to get size, niche, country, creation date, uploads playlist ID and subscriber count.
2. Call `get_recent_videos` (limit 20-25). Engagement rate is computed automatically from average views / subscribers.
3. Call `get_video_comments` with 4-6 recent video IDs (max_comments 20-30). The tool returns a question-first, representative sample across those videos.
4. Call `detect_audience_signals`. Takes NO arguments - it analyzes the comments you already fetched for repeated questions and explicit product/tutorial/checklist/template requests.
5. Call `extract_external_links`.
6. Call `detect_monetization_matrix`.
7. Call `detect_risk_flags`.
8. Call `compute_outreach_priority`. Takes NO arguments - it uses already-fetched data to produce a deterministic HIGH/MEDIUM/LOW/SKIP rating for this micro-influencer outreach.
9. Synthesize: CONTENT -> AUDIENCE SIGNALS -> MONETIZATION -> INFLUENCER PAIN -> OPPORTUNITY -> OUTREACH PRIORITY -> RISK.
10. Call `save_outreach_proposal` with report_text (FULL report), cold_dm, matrix and personalization_terms.
11. Return a concise executive summary.

### CONTENT ANALYSIS:
Identify the creator's Core Expertise - what they can actually explain/teach their audience. NOT "Crypto influencer", but e.g. "Primarily creates educational content around finding early-stage crypto projects and evaluating tokens before exchange listings". Also determine: main topics, recurring themes, audience level (beginner/intermediate/advanced), content type (educational/news/opinion/entertainment), and 2-3 standout videos (real titles, with view counts) most relevant for the future product and DM personalization.

### AUDIENCE ANALYSIS (the most important block):
Use ONLY the comments you actually fetched. NEVER invent comments or quotes. Determine:
- Repeated Questions: what viewers ask again and again.
- Audience Pain Points: problems that regularly come up.
- Audience Requests: tutorial / guide / step-by-step / checklist / template / deeper explanation / specific workflow.
- Buying/Product Signals: signs the audience needs a structured product.
IMPORTANT: "Great video!" is NOT a pain point. "Can you make a step-by-step guide on how you find these coins?" IS an audience signal.

### MONETIZATION ANALYSIS:
Use the matrix and extracted links. Link beats word: "my course: teachable.com/..." proves a course exists; "thinking about creating a course" does NOT. List current monetization, external links by category, the monetization gap, and your confidence.

### FACT VS INFERENCE:
Label statements as FACT (directly observed: a real title, comment, link) or INFERENCE (your interpretation). Never present inference as fact.

### EVIDENCE:
Support the main pain with concrete evidence: real video titles, short real comment quotes, real links from the tool results. Never fabricate quotes.

### INFLUENCER PAIN (specific, never generic):
The real pain formula: the audience repeatedly asks for X + the creator demonstrably has expertise in X + there is no structured product covering X.
FORBIDDEN generic phrases: "You aren't monetizing enough", "You have huge potential", "You should create a course", "Your audience is very engaged", "You could make more money".

### OPPORTUNITY:
Recommend ONE product format the evidence supports (course, workshop, paid guide, template, community, newsletter, coaching...). Do NOT always propose a course. If the evidence is insufficient, write: "Insufficient evidence for a specific product opportunity."

### COLD DM RULES:
Write exactly ONE final Cold DM. Conversational, short, direct, human, low-pressure. No generic praise ("Love your content"), no corporate jargon, no full business-model dump. Structure: hook with a specific piece of their content -> specific audience signal -> specific monetization gap -> concrete offer -> soft question CTA. The Offer step is MANDATORY regardless of how weak or strong the audience-demand evidence is. A low-confidence demand signal changes HOW confidently you frame the pitch (e.g. 'this could be worth exploring' instead of 'your audience is clearly ready to buy'), but it never means omitting the offer itself. Every Cold DM must contain one clear sentence stating what you build for them (a turnkey course + funnel, done for you) - a DM that only asks a reflective question with no stated offer is incomplete and must not be saved. NEVER invent names, video titles, quotes or facts. No '[Name]' placeholders (use 'Hey there,' or hook first if no personal name is found). Use the creator's real name only if it appeared in the fetched data.

### MICRO-INFLUENCER FOCUS:
This workflow targets micro-influencers (1,000–10,000 subscribers). Channels outside this range are analyzed but get a lower priority unless other signals are exceptionally strong. Use engagement rate (average recent views / subscribers) as the key health metric: >=3% is strong, <1% is weak.

### RISK GATE:
If the risk flags include referral_farming or unverifiable_token_hype, or the video descriptions promote leveraged trading signals / bots with win-rate claims, do NOT propose a signals, trading-tips or bot product. Propose an education-only offer (risk management, fundamentals), or recommend skipping this channel and state the reason in the summary.

### FINAL REPORT FORMAT (use exactly this structure in report_text):
Use each section header EXACTLY ONCE and in the order below. Never repeat a section (MONETIZATION must appear only once). Do not add extra sections or leave duplicate headers.
================================
INFLUENCER
==========

Channel:
Handle:
Subscribers:
Engagement Rate:
Niche:
Core Expertise:

================================
CONTENT
=======

Main Topics:
Recurring Themes:
Relevant Videos:

================================
AUDIENCE
========

Repeated Questions:
Audience Pain Points:
Audience Requests:
Buying/Product Signals:

================================
MONETIZATION
============

Current Monetization:
External Links:
Monetization Gap:
Confidence:

================================
INFLUENCER PAIN
===============

Main Pain:
Evidence:
Why It Matters:
Confidence:

================================
OPPORTUNITY
===========

Recommended Product:
Why This Product:
Audience Demand:
Creator Expertise:

================================
OUTREACH PRIORITY
=================

Priority:
Score:
Reasons:

================================
DM BRIEF
========

Main Pain (one sentence):
Hook Options (2-3, from REAL quotes/titles only):
Offer Angle:
Confidence:

================================
RISK
====

Risk Status:
Risk Flags:

================================
COLD DM
=======

[ONE FINAL COLD DM]
"""

AGENT_TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "get_channel_overview",
            "description": "Fetch channel stats, subscriber count, total views, creation date, and uploads playlist ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "channel_input": {
                        "type": "string",
                        "description": "Channel handle (e.g. '@MrBeast'), URL, or Channel ID."
                    }
                },
                "required": ["channel_input"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_recent_videos",
            "description": "Fetch the channel's most recent videos with titles, descriptions and engagement stats (views, likes, comments_count) to analyze content quality and current monetization.",
            "parameters": {
                "type": "object",
                "properties": {
                    "uploads_playlist_id": {
                        "type": "string",
                        "description": "The channel's uploads playlist ID (obtained from get_channel_overview)."
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Number of videos to fetch (default 10, max 25)."
                    }
                },
                "required": ["uploads_playlist_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_video_comments",
            "description": "Fetch a question-first, representative sample of legitimate audience comments across the given videos to discover repeated questions, pains and product demand.",
            "parameters": {
                "type": "object",
                "properties": {
                    "video_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of video IDs to inspect."
                    },
                    "max_comments": {
                        "type": "integer",
                        "description": "Maximum number of comments to retrieve (default 15)."
                    }
                },
                "required": ["video_ids"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "detect_monetization_matrix",
            "description": "Analyze the channel description and video descriptions already fetched in previous steps to compute the exact monetization matrix (course, coaching, consulting, community, newsletter, affiliate, sponsorship, product, merch) and confidence score. Takes no arguments.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "detect_risk_flags",
            "description": "Scan the audience comments and video titles already fetched in previous steps for high-risk promotion patterns (referral farming, unverifiable token hype, leveraged signals or win-rate bot claims). Takes no arguments.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "extract_external_links",
            "description": "Extract and classify external URLs (affiliate, course, community, newsletter, booking, social, product) from the channel description and video descriptions already fetched in previous steps. Takes no arguments.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "detect_audience_signals",
            "description": "Analyze the audience comments already fetched in previous steps to extract repeated questions and explicit product/tutorial requests. Takes no arguments.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "compute_outreach_priority",
            "description": "Compute a deterministic outreach priority (HIGH/MEDIUM/LOW/SKIP) from already-fetched data: subscriber range, engagement rate, monetization matrix, audience signals and risk flags. Takes no arguments - call it after get_channel_overview, get_recent_videos, detect_monetization_matrix, detect_audience_signals and detect_risk_flags.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "save_outreach_proposal",
            "description": "Save the completed channel audit analysis and outreach cold DM to files on disk.",
            "parameters": {
                "type": "object",
                "properties": {
                    "channel_title": {
                        "type": "string",
                        "description": "The name of the channel."
                    },
                    "report_text": {
                        "type": "string",
                        "description": "The FULL final report in the FINAL REPORT FORMAT (Influencer, Content, Audience, Monetization, Influencer Pain, Opportunity, Outreach Priority, DM Brief, Risk, Cold DM sections)."
                    },
                    "cold_dm": {
                        "type": "string",
                        "description": "The finalized, ready-to-send cold outreach DM."
                    },
                    "matrix": {
                        "type": "object",
                        "description": "The monetization matrix JSON produced by detect_monetization_matrix."
                    },
                    "personalization_terms": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Specific channel or video terms that appear in the Cold DM."
                    }
                },
                "required": ["channel_title", "report_text", "cold_dm"]
            }
        }
    }
]


def validate_tool_args(
    name: str,
    args: dict[str, Any],
    schema: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    """Check tool args against the declared schema; coerce JSON-string arrays.

    Raises ValueError on unknown keys so run()'s error feedback loop can send
    the message back to the model for self-correction.
    """
    fn_schema = next(
        (t["function"] for t in (schema if schema is not None else AGENT_TOOLS_SCHEMA)
         if t["function"]["name"] == name),
        None
    )
    if fn_schema is None:
        raise ValueError(f"Unknown tool: {name}")

    properties: dict[str, Any] = fn_schema.get("parameters", {}).get("properties", {})
    unknown = sorted(k for k in args if k not in properties)
    if unknown:
        raise ValueError(
            f"Unknown argument(s) {unknown} for {name}; expected {sorted(properties)}"
        )

    for key, spec in properties.items():
        if spec.get("type") == "array" and isinstance(args.get(key), str):
            try:
                args[key] = json.loads(args[key])
            except Exception as exc:
                raise ValueError(
                    f"Argument '{key}' for {name} must be a JSON array; failed to parse: {exc}"
                ) from exc

    return args


def post_deepseek(api_key: str, payload: dict, model: str = DEFAULT_MODEL) -> dict:
    """Send a chat completion request to DeepSeek API with OpenAI-compatible format."""
    payload["model"] = model
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        DEEPSEEK_API_URL,
        data=data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        },
        method="POST"
    )

    for attempt in range(MAX_API_RETRIES):
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            if exc.code not in RETRYABLE_HTTP_STATUS_CODES or attempt == MAX_API_RETRIES - 1:
                raise RuntimeError(f"DeepSeek API HTTP {exc.code}: {body}") from exc
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            if attempt == MAX_API_RETRIES - 1:
                raise RuntimeError(f"DeepSeek API network error: {exc}") from exc
        time.sleep(RETRY_BACKOFF_SECONDS * (2 ** attempt))

    raise RuntimeError("DeepSeek API request failed after retries")


class YouTubeAgent:
    """Autonomous ReAct agent that inspects channels and writes cold outreach."""

    def __init__(
        self,
        youtube_api_key: str,
        deepseek_api_key: str,
        model: str = DEFAULT_MODEL,
        on_log: Callable[[str], None] | None = None
    ):
        if not build:
            raise RuntimeError("google-api-python-client is required. Run: pip install google-api-python-client")
        if not youtube_api_key:
            raise ValueError("YouTube API Key is missing.")
        if not deepseek_api_key:
            raise ValueError("DeepSeek API Key is missing.")

        self.youtube = build("youtube", "v3", developerKey=youtube_api_key)
        self.youtube._http.timeout = 120  # медленное соединение с Google API не должно обрывать запросы
        self.deepseek_api_key = deepseek_api_key
        self.model = os.environ.get("DEEPSEEK_MODEL") or model
        self.on_log = on_log or (lambda msg: None)
        # Data accumulated from tool results; argument-free tools read from here.
        self.state: dict[str, Any] = {}

    def log(self, message: str) -> None:
        self.on_log(message)

    def execute_tool(self, name: str, args: dict[str, Any]) -> Any:
        """Dispatch tool calls to Python functions."""
        self.log(f"🛠️ [Tool Call] {name}({json.dumps(args, ensure_ascii=False)})")
        args = validate_tool_args(name, args)

        result: Any
        summary: str

        if name == "get_channel_overview":
            result = tools.get_channel_overview(self.youtube, args["channel_input"])
            self.state["channel_desc"] = result.get("description", "")
            self.state["subscribers"] = result.get("subscribers")
            summary = (
                f"1 channel: '{result.get('title')}', "
                f"subscribers={result.get('subscribers')}, videos={result.get('video_count')}"
            )

        elif name == "get_recent_videos":
            limit = args.get("limit", 10)
            result = tools.get_recent_videos(self.youtube, args["uploads_playlist_id"], limit=limit)
            self.state["video_descs"] = [v.get("description", "") for v in result]
            self.state["video_titles"] = [v.get("title", "") for v in result]
            self.state["video_views"] = [v.get("views") for v in result]
            titles = "; ".join((v.get("title", "") or "")[:60] for v in result[:3])
            total_views = sum(v.get("views") or 0 for v in result)
            engagement = tools.compute_engagement_rate(
                subscribers=self.state.get("subscribers"),
                views_list=self.state.get("video_views", [])
            )
            self.state["engagement_rate"] = engagement
            summary = f"{len(result)} videos, {total_views:,} total views, engagement_rate={engagement}: {titles}"

        elif name == "get_video_comments":
            vids = args.get("video_ids", [])
            max_c = args.get("max_comments", 15)
            result = tools.get_video_comments(self.youtube, vids, max_comments=max_c)
            self.state["comments"] = result
            q_count = sum(1 for c in result if c.get("question"))
            previews = " | ".join((c.get("text", "") or "")[:80] for c in result[:3])
            summary = f"{len(result)} comments ({q_count} questions): {previews}"

        elif name == "detect_monetization_matrix":
            links_state = self.state.get("external_links")
            matrix = tools.analyze_monetization_matrix(
                channel_desc=self.state.get("channel_desc", ""),
                video_descs=self.state.get("video_descs", []),
                external_links=links_state.get("links") if isinstance(links_state, dict) else None
            )
            self.state["matrix"] = matrix
            self.log(f"📊 [Monetization Matrix] {json.dumps(matrix, ensure_ascii=False, indent=2)}")
            result = matrix
            detected = [k for k, v in matrix.items() if v is True]
            summary = (
                f"monetization_detected={matrix.get('monetization_detected')}, "
                f"confidence={matrix.get('confidence')}, detected={detected}"
            )

        elif name == "detect_risk_flags":
            result = tools.detect_risk_flags(
                comments=self.state.get("comments", []),
                video_titles=self.state.get("video_titles", [])
            )
            self.state["risk_flags"] = result
            summary = f"flags={result.get('risk_flags', [])}, scanned={result.get('texts_scanned')} texts"

        elif name == "detect_audience_signals":
            result = tools.analyze_audience_signals(self.state.get("comments", []))
            self.state["audience_signals"] = result
            summary = (
                f"{result['request_count']} request(s), "
                f"{result['question_count']}/{result['total_comments']} questions"
            )

        elif name == "compute_outreach_priority":
            rfs = self.state.get("risk_flags", {})
            result = tools.compute_outreach_priority(
                subscribers=self.state.get("subscribers"),
                engagement_rate=self.state.get("engagement_rate"),
                matrix=self.state.get("matrix"),
                signals=self.state.get("audience_signals"),
                risk_flags=rfs.get("risk_flags") if isinstance(rfs, dict) else rfs
            )
            self.state["outreach_priority"] = result
            summary = f"priority={result['priority']}, score={result['score']}/{result['max_score']}"

        elif name == "extract_external_links":
            result = tools.extract_external_links(
                channel_desc=self.state.get("channel_desc", ""),
                video_descs=self.state.get("video_descs", [])
            )
            self.state["external_links"] = result
            parts = ", ".join(f"{cat}×{cnt}" for cat, cnt in result.get("summary", {}).items())
            summary = f"{result.get('total', 0)} links: {parts or 'none found'}"

        elif name == "save_outreach_proposal":
            if not OFFER_INDICATOR_RE.search(args.get("cold_dm", "")):
                # Don't save silently: the error goes back to the model as a tool
                # result so it rewrites the DM with the offer and calls again.
                self.log("⚠️ [Offer Gate] cold_dm не содержит указания услуги - сохранение отклонено.")
                result = {"error": COLD_DM_MISSING_OFFER_ERROR}
                summary = "REJECTED: cold_dm is missing the service offer; rewrite the DM and call save_outreach_proposal again"
            else:
                personalization_terms = args.get("personalization_terms") or []
                if not personalization_terms:
                    personalization_terms = [args["channel_title"]]
                    personalization_terms.extend(self.state.get("video_titles", [])[:5])
                saved = tools.save_outreach_proposal(
                    channel_title=args["channel_title"],
                    report_text=args["report_text"],
                    cold_dm=args["cold_dm"],
                    matrix=args.get("matrix") or self.state.get("matrix"),
                    personalization_terms=personalization_terms
                )
                self.log(f"💾 [Saved] Reports written to: {saved['analysis_file']} and {saved['outreach_file']}")
                result = saved
                summary = f"files: {saved['analysis_file']}, {saved['outreach_file']}"

        else:
            raise ValueError(f"Unknown tool: {name}")

        self.log(f"✅ [Result] {name} → {summary}")
        return result

    def run(self, channel_input: str, max_steps: int = 12) -> dict[str, Any]:
        """Run the autonomous agent loop for a given YouTube channel."""
        self.log(f"🚀 Запуск ИИ-агента для канала: {channel_input}")

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": AGENT_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"Please perform a complete monetization audit and write a cold outreach DM for the channel: {channel_input}"
            }
        ]

        saved_artifacts: dict[str, str] = {}
        final_report = ""
        final_dm = ""

        for step in range(1, max_steps + 1):
            self.log(f"🤔 [Шаг {step}] ИИ анализирует ситуацию...")

            payload = {
                "messages": messages,
                "tools": AGENT_TOOLS_SCHEMA,
                "temperature": 0.3,
            }

            resp = post_deepseek(self.deepseek_api_key, payload, model=self.model)
            choice = resp["choices"][0]
            msg = choice["message"]
            messages.append(msg)

            # If the model produced thought/text
            content = (msg.get("content") or "").strip()
            if content:
                self.log(f"💭 {content}")

            tool_calls = msg.get("tool_calls", [])
            if not tool_calls:
                # Agent completed reasoning and returned final text
                self.log("✅ ИИ-агент завершил работу!")
                return {
                    "summary": content,
                    "saved": saved_artifacts,
                    "report": final_report,
                    "cold_dm": final_dm,
                    "messages": messages
                }

            # Execute tool calls
            for call in tool_calls:
                fn_name = call["function"]["name"]
                try:
                    fn_args = json.loads(call["function"]["arguments"])
                except Exception:
                    fn_args = {}

                try:
                    res = self.execute_tool(fn_name, fn_args)
                    if fn_name == "save_outreach_proposal" and isinstance(res, dict) and "error" not in res:
                        saved_artifacts = res
                        final_report = str(fn_args.get("report_text", "") or "")
                        final_dm = str(fn_args.get("cold_dm", "") or "")
                    result_str = json.dumps(res, ensure_ascii=False)
                except Exception as exc:
                    result_str = json.dumps({"error": str(exc)})
                    self.log(f"⚠️ Ошибка вызова инструмента {fn_name}: {exc}")

                messages.append({
                    "role": "tool",
                    "tool_call_id": call["id"],
                    "content": result_str
                })

        self.log("⏱️ Достигнут лимит шагов агента.")
        return {
            "summary": "Agent reached max steps limit.",
            "saved": saved_artifacts,
            "report": final_report,
            "cold_dm": final_dm,
            "messages": messages
        }


def main():
    if len(sys.argv) < 2:
        print("Usage: python agent.py <@channel_handle_or_url>")
        sys.exit(1)

    channel = sys.argv[1]
    yt_key = os.environ.get("YOUTUBE_API_KEY", "").strip()
    ds_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()

    if not yt_key:
        print("Error: YOUTUBE_API_KEY environment variable is not set.", file=sys.stderr)
        sys.exit(1)
    if not ds_key:
        print("Error: DEEPSEEK_API_KEY environment variable is not set.", file=sys.stderr)
        sys.exit(1)

    agent = YouTubeAgent(
        youtube_api_key=yt_key,
        deepseek_api_key=ds_key,
        on_log=print
    )

    result = agent.run(channel)
    print("\n" + "=" * 60)
    print("ИТОГ РАБОТЫ АГЕНТА:")
    print("=" * 60)
    print(result.get("summary"))


if __name__ == "__main__":
    main()
