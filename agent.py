"""Autonomous AI Agent for YouTube Channel Monetization Audit & Cold Outreach."""

from __future__ import annotations

import json
import os
import sys
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

AGENT_SYSTEM_PROMPT = """You are an elite YouTube Monetization Strategist and Outreach Copywriter.
Your goal is to deeply analyze an influencer's YouTube channel, identify high-value monetization gaps, and craft a high-converting, personalized Cold Outreach DM.

### YOUR WORKFLOW:
1. First, inspect the channel overview using `get_channel_overview` to understand size, niche, country, and reach.
2. Next, fetch recent videos and descriptions using `get_recent_videos` to detect what monetization they already have (affiliates, sponsorships, merchandise, memberships, courses) and what they lack (e.g. high-ticket offer, dedicated sales funnel, email list).
3. If relevant, inspect audience comments with `get_video_comments` to pinpoint recurring questions, community pain points, or unmet subscriber demands.
4. Run `detect_monetization_matrix` to formalize the exact monetization breakdown (course, coaching, consulting, community, newsletter, affiliate, sponsorship, product, merch).
5. Synthesize your strategic monetization audit (Pain points & Revenue gaps).
6. Craft a punchy, human Cold DM (Instagram/Twitter/LinkedIn):
   - Hook: Reference a specific recent video, milestone, or topic they covered.
   - The Insight: Gently point out their specific monetization bottleneck based on the matrix (e.g., losing revenue relying only on affiliate links when audience wants a structured community/course).
   - The Offer: Propose building them a turnkey monetization asset (e.g., custom course + automated funnel) with zero heavy lifting for them.
   - Soft CTA: A low-friction question (e.g., "Open to seeing a 2-min breakdown?").
   - Tone: Friendly, peer-to-peer, direct, zero corporate buzzwords.
   - NO placeholders like '[Name]' (if no personal name is found, use 'Hey there,' or hook first).
   - Give exactly ONE final, polished version of the message.
7. Call `save_outreach_proposal` with the audit text, the monetization matrix JSON, the final cold DM, and 1-3 specific personalization terms used in the message.
8. Return a concise executive summary to the user.
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
            "description": "Fetch the channel's most recent videos with titles and descriptions to analyze content and current monetization.",
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
            "description": "Fetch top legitimate audience comments from recent videos to discover audience pains, questions, and demand.",
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
            "description": "Analyze channel and video texts to compute the exact monetization matrix (course, coaching, consulting, community, newsletter, affiliate, sponsorship, product, merch) and confidence score.",
            "parameters": {
                "type": "object",
                "properties": {
                    "channel_desc": {
                        "type": "string",
                        "description": "Channel description text."
                    },
                    "video_descs": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of recent video description texts."
                    }
                }
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
                        "description": "The strategic monetization analysis (overview, current monetization, identified gaps, pain points)."
                    },
                    "matrix": {
                        "type": "object",
                        "description": "The monetization matrix returned by detect_monetization_matrix."
                    },
                    "cold_dm": {
                        "type": "string",
                        "description": "The finalized, ready-to-send cold outreach DM."
                    },
                    "personalization_terms": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Specific channel, video, topic, or milestone terms that appear in the Cold DM."
                    }
                },
                "required": ["channel_title", "report_text", "cold_dm", "matrix"]
            }
        }
    }
]


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

    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"DeepSeek API HTTP {exc.code}: {body}") from exc
    except Exception as exc:
        raise RuntimeError(f"DeepSeek API network error: {exc}") from exc


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
        self.deepseek_api_key = deepseek_api_key
        self.model = os.environ.get("DEEPSEEK_MODEL") or model
        self.on_log = on_log or (lambda msg: None)

    def log(self, message: str) -> None:
        self.on_log(message)

    def execute_tool(self, name: str, args: dict[str, Any]) -> Any:
        """Dispatch tool calls to Python functions."""
        self.log(f"🛠️ [Tool Call] {name}({json.dumps(args, ensure_ascii=False)})")

        if name == "get_channel_overview":
            return tools.get_channel_overview(self.youtube, args["channel_input"])

        if name == "get_recent_videos":
            limit = args.get("limit", 10)
            return tools.get_recent_videos(self.youtube, args["uploads_playlist_id"], limit=limit)

        if name == "get_video_comments":
            vids = args.get("video_ids", [])
            max_c = args.get("max_comments", 15)
            return tools.get_video_comments(self.youtube, vids, max_comments=max_c)

        if name == "detect_monetization_matrix":
            ch_desc = args.get("channel_desc", "")
            v_descs = args.get("video_descs", [])
            matrix = tools.analyze_monetization_matrix(ch_desc, v_descs)
            self.log(f"📊 [Monetization Matrix] {json.dumps(matrix, ensure_ascii=False, indent=2)}")
            return matrix

        if name == "save_outreach_proposal":
            saved = tools.save_outreach_proposal(
                channel_title=args["channel_title"],
                report_text=args["report_text"],
                cold_dm=args["cold_dm"],
                matrix=args.get("matrix", {}),
                personalization_terms=args.get("personalization_terms", [])
            )
            self.log(f"💾 [Saved] Reports written to: {saved['analysis_file']} and {saved['outreach_file']}")
            return saved

        raise ValueError(f"Unknown tool: {name}")

    def run(self, channel_input: str, max_steps: int = 8) -> dict[str, Any]:
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
                    if fn_name == "save_outreach_proposal" and isinstance(res, dict):
                        saved_artifacts = res
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
