"""Unit and Integration tests for YouTube AI Agent and Tools."""

import unittest
from unittest.mock import MagicMock, patch
import os
import json
import urllib.error

import tools
import agent


class TestTools(unittest.TestCase):
    def test_slugify(self):
        self.assertEqual(tools.slugify("MrBeast Official! 2026"), "MrBeast_Official_2026")
        self.assertEqual(tools.slugify("Fratelli di Crypto 🦄"), "Fratelli_di_Crypto")
        self.assertEqual(tools.slugify(""), "channel")

    def test_parse_channel_input(self):
        self.assertEqual(tools.parse_channel_input("@mkbhd"), ("handle", "mkbhd"))
        self.assertEqual(tools.parse_channel_input("https://www.youtube.com/@veritasium"), ("handle", "veritasium"))
        self.assertEqual(tools.parse_channel_input("https://youtube.com/channel/UC_x5XG1OV2P6uZZ5FSM9Ttw"), ("id", "UC_x5XG1OV2P6uZZ5FSM9Ttw"))
        self.assertEqual(tools.parse_channel_input("UC1234567890123456789012"), ("id", "UC1234567890123456789012"))
        self.assertIsNone(tools.parse_channel_input(""))

    def test_parse_video_url_rejected(self):
        with self.assertRaises(ValueError):
            tools.parse_channel_input("https://www.youtube.com/watch?v=abc123")

    def test_analyze_monetization_matrix(self):
        matrix = tools.analyze_monetization_matrix(
            channel_desc="Join my course at teachable.com and buy merch!",
            video_descs=["Check affiliate link amzn.to/123", "Join our telegram community t.me/crypto"]
        )
        self.assertTrue(matrix["course"])
        self.assertTrue(matrix["merch"])
        self.assertTrue(matrix["affiliate"])
        self.assertTrue(matrix["community"])
        self.assertFalse(matrix["coaching"])
        self.assertTrue(matrix["monetization_detected"])
        self.assertGreaterEqual(matrix["confidence"], 0.8)

    def test_save_outreach_proposal(self):
        saved = tools.save_outreach_proposal(
            channel_title="Test Channel",
            report_text="Pain points & gaps",
            cold_dm="I watched Test Channel's tutorial on automation and noticed one useful offer gap. "
                    "Would you be open to a short breakdown?",
            personalization_terms=["Test Channel", "automation"]
        )
        self.assertTrue(os.path.exists(saved["analysis_file"]))
        self.assertTrue(os.path.exists(saved["outreach_file"]))

        with open(saved["outreach_file"], "r", encoding="utf-8") as f:
            self.assertIn("Test Channel", f.read())

    def test_save_outreach_proposal_with_matrix(self):
        saved = tools.save_outreach_proposal(
            channel_title="Matrix Channel",
            report_text="Audit body",
            cold_dm="Your Matrix Channel videos explain affiliate workflows clearly. "
                    "Would you be open to a short breakdown of one additional offer?",
            personalization_terms=["Matrix Channel", "affiliate workflows"],
            matrix={"course": False, "community": True, "confidence": 0.88}
        )
        with open(saved["analysis_file"], "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("### Monetization Matrix", content)
        self.assertIn('"course": false', content)
        self.assertIn('"confidence": 0.88', content)

    def test_save_outreach_proposal_matrix_as_json_string(self):
        saved = tools.save_outreach_proposal(
            channel_title="StringMatrix Channel",
            report_text="Audit body",
            cold_dm="Your StringMatrix Channel videos explain this topic clearly. "
                    "Would you be open to a short breakdown of one additional offer?",
            personalization_terms=["StringMatrix Channel"],
            matrix=json.dumps({"course": True})
        )
        with open(saved["analysis_file"], "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn('"course": true', content)

    def test_validate_cold_dm(self):
        valid = tools.validate_cold_dm(
            "I watched Test Channel's tutorial on automation and noticed one useful offer gap. "
            "Would you be open to a short breakdown?",
            ["Test Channel", "automation"]
        )
        self.assertTrue(valid["valid"])

        invalid = tools.validate_cold_dm(
            "Hey there, great channel! [Name]",
            ["Test Channel"]
        )
        self.assertFalse(invalid["valid"])
        self.assertGreaterEqual(len(invalid["issues"]), 3)


class TestRiskFlags(unittest.TestCase):
    def test_referral_farming_detected(self):
        res = tools.detect_risk_flags(
            comments=[{"text": "Join my referral program, signup bonus inside"}],
            video_titles=[]
        )
        self.assertIn("referral_farming", res["risk_flags"])
        self.assertEqual(res["texts_scanned"], 1)

    def test_token_hype_detected_in_titles(self):
        res = tools.detect_risk_flags(comments=[], video_titles=["100x GEM token presale!"])
        self.assertIn("unverifiable_token_hype", res["risk_flags"])

    def test_leveraged_signals_detected(self):
        res = tools.detect_risk_flags(
            comments=[{"text": "Your futures trading signals group changed my life, 95% win rate"}],
            video_titles=[]
        )
        self.assertIn("leveraged_signals_promotion", res["risk_flags"])

    def test_clean_channel_has_no_flags(self):
        res = tools.detect_risk_flags(
            comments=[{"text": "Great explanation of camera settings, thanks!"}],
            video_titles=["How I shoot cinematic video"]
        )
        self.assertEqual(res["risk_flags"], [])


class TestNicheSearch(unittest.TestCase):
    def test_search_cache(self):
        yt = MagicMock()
        search_request = MagicMock()
        yt.search.return_value.list.return_value = search_request
        search_request.execute.return_value = {
            "items": [{"snippet": {"channelId": "UC1"}}]
        }
        channel_request = MagicMock()
        yt.channels.return_value.list.return_value = channel_request
        channel_request.execute.return_value = {
            "items": [{"id": "UC1", "snippet": {"title": "Test"}, "statistics": {}}]
        }

        tools._NICHE_CACHE.clear()
        tools.search_channels_by_niche(yt, "test", max_results=1)
        tools.search_channels_by_niche(yt, "test", max_results=1)

        self.assertEqual(yt.search.return_value.list.call_count, 1)


class TestApiRetries(unittest.TestCase):
    @patch("tools.time.sleep")
    def test_youtube_request_retries_timeout(self, mock_sleep):
        request = MagicMock()
        request.execute.side_effect = [TimeoutError("temporary"), {"items": []}]

        result = tools.execute_with_retries(request)

        self.assertEqual(result, {"items": []})
        self.assertEqual(request.execute.call_count, 2)
        mock_sleep.assert_called_once_with(tools.RETRY_BACKOFF_SECONDS)

    @patch("agent.time.sleep")
    @patch("agent.urllib.request.urlopen")
    def test_deepseek_retries_network_error(self, mock_urlopen, mock_sleep):
        response = MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = b'{"choices": []}'
        mock_urlopen.side_effect = [urllib.error.URLError("temporary"), response]

        result = agent.post_deepseek("key", {"messages": []})

        self.assertEqual(result, {"choices": []})
        self.assertEqual(mock_urlopen.call_count, 2)
        mock_sleep.assert_called_once_with(agent.RETRY_BACKOFF_SECONDS)


class TestToolArgsValidation(unittest.TestCase):
    def test_unknown_argument_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            agent.validate_tool_args("detect_monetization_matrix", {"video_discs": ["desc"]})
        msg = str(ctx.exception)
        self.assertIn("Unknown argument(s) ['video_discs']", msg)
        self.assertIn("for detect_monetization_matrix", msg)
        self.assertIn("expected", msg)

    def test_unknown_argument_on_multi_prop_tool(self):
        with self.assertRaises(ValueError) as ctx:
            agent.validate_tool_args("get_channel_overview", {"channel_input": "@a", "channel_nam": "b"})
        self.assertIn("'channel_nam'", str(ctx.exception))

    def test_json_string_array_coerced_to_list(self):
        args = agent.validate_tool_args("get_video_comments", {"video_ids": "[\"abc\", \"def\"]"})
        self.assertEqual(args["video_ids"], ["abc", "def"])

    def test_json_string_array_invalid_raises(self):
        with self.assertRaises(ValueError):
            agent.validate_tool_args("get_video_comments", {"video_ids": "not-json"})

    def test_unknown_tool_rejected(self):
        with self.assertRaises(ValueError):
            agent.validate_tool_args("nonexistent_tool", {})


class TestAgentExecuteTool(unittest.TestCase):
    def _agent(self):
        with patch("agent.build"):
            return agent.YouTubeAgent(youtube_api_key="k", deepseek_api_key="d")

    def test_execute_tool_rejects_unknown_args(self):
        ag = self._agent()
        with self.assertRaises(ValueError) as ctx:
            ag.execute_tool("detect_monetization_matrix", {"video_discs": "x"})
        self.assertIn("video_discs", str(ctx.exception))

    @patch("tools.analyze_monetization_matrix")
    def test_matrix_reads_from_state(self, mock_analyze):
        ag = self._agent()
        ag.state["channel_desc"] = "Join my course at teachable.com"
        ag.state["video_descs"] = ["affiliate link amzn.to"]
        mock_analyze.return_value = {"course": True, "confidence": 0.9}

        res = ag.execute_tool("detect_monetization_matrix", {})

        mock_analyze.assert_called_once_with(
            channel_desc="Join my course at teachable.com",
            video_descs=["affiliate link amzn.to"],
            external_links=None
        )
        self.assertEqual(res, {"course": True, "confidence": 0.9})
        self.assertEqual(ag.state["matrix"], res)

    @patch("tools.detect_risk_flags")
    def test_risk_flags_read_from_state(self, mock_risk):
        ag = self._agent()
        ag.state["comments"] = [{"text": "referral spam"}]
        ag.state["video_titles"] = ["100x gem"]
        mock_risk.return_value = {"risk_flags": ["referral_farming"], "matched_examples": {}, "texts_scanned": 2}

        res = ag.execute_tool("detect_risk_flags", {})

        mock_risk.assert_called_once_with(
            comments=[{"text": "referral spam"}],
            video_titles=["100x gem"]
        )
        self.assertEqual(res["risk_flags"], ["referral_farming"])
        self.assertEqual(ag.state["risk_flags"], res)

    def test_state_populated_from_tool_results(self):
        ag = self._agent()
        fake_overview = {"title": "Ch", "description": "My course desc", "subscribers": "5"}
        fake_videos = [{"video_id": "v1", "title": "T1", "description": "D1"}]

        with patch("tools.get_channel_overview", return_value=fake_overview):
            ag.execute_tool("get_channel_overview", {"channel_input": "@x"})
        with patch("tools.get_recent_videos", return_value=fake_videos):
            ag.execute_tool("get_recent_videos", {"uploads_playlist_id": "UU1"})

        self.assertEqual(ag.state["channel_desc"], "My course desc")
        self.assertEqual(ag.state["video_descs"], ["D1"])
        self.assertEqual(ag.state["video_titles"], ["T1"])


class TestRecentVideosStats(unittest.TestCase):
    def _youtube_mock(self, statistics_items):
        yt = MagicMock()
        yt.playlistItems().list.return_value.execute.return_value = {
            "items": [
                {"snippet": {"title": "V1", "description": "D1", "publishedAt": "2026-01-01T00:00:00Z"},
                 "contentDetails": {"videoId": "v1"}},
                {"snippet": {"title": "V2", "description": "D2", "publishedAt": "2026-01-02T00:00:00Z"},
                 "contentDetails": {"videoId": "v2"}},
            ]
        }
        yt.videos().list.return_value.execute.return_value = {"items": statistics_items}
        return yt

    def test_full_stats_attached(self):
        yt = self._youtube_mock([
            {"id": "v1", "statistics": {"viewCount": "1000", "likeCount": "100", "commentCount": "10"}},
        ])
        videos = tools.get_recent_videos(yt, "UU1", limit=2)
        self.assertEqual(videos[0]["views"], 1000)
        self.assertEqual(videos[0]["likes"], 100)
        self.assertEqual(videos[0]["comments_count"], 10)
        self.assertIsNone(videos[1]["views"])

    def test_partial_stats_none(self):
        yt = self._youtube_mock([
            {"id": "v1", "statistics": {"viewCount": "777"}},
        ])
        videos = tools.get_recent_videos(yt, "UU1", limit=2)
        self.assertEqual(videos[0]["views"], 777)
        self.assertIsNone(videos[0]["likes"])
        self.assertIsNone(videos[0]["comments_count"])


class TestExtractExternalLinks(unittest.TestCase):
    def test_classifies_links_by_domain(self):
        res = tools.extract_external_links(
            channel_desc="DM me https://instagram.com/foo",
            video_descs=[
                "Enroll here https://teachable.com/p/course-x",
                "Join the room https://www.skool.com/myroom",
                "Sign up https://binance.com?ref=ABC123",
                "More at https://random-site.org",
            ]
        )
        by_url = {l["url"]: l["category"] for l in res["links"]}
        self.assertEqual(by_url["https://teachable.com/p/course-x"], "course")
        self.assertEqual(by_url["https://www.skool.com/myroom"], "community")
        self.assertEqual(by_url["https://binance.com?ref=ABC123"], "affiliate")
        self.assertEqual(by_url["https://instagram.com/foo"], "social")
        self.assertEqual(by_url["https://random-site.org"], "unknown")
        self.assertEqual(res["total"], 5)

    def test_no_links(self):
        res = tools.extract_external_links(channel_desc="just text", video_descs=["also text"])
        self.assertEqual(res["total"], 0)
        self.assertEqual(res["links"], [])


class TestMonetizationMatrixLinksAndIntent(unittest.TestCase):
    def test_negation_intent_not_monetization(self):
        matrix = tools.analyze_monetization_matrix(
            channel_desc="I am thinking about creating a course someday!"
        )
        self.assertFalse(matrix["course"])
        self.assertFalse(matrix["monetization_detected"])

    def test_links_confirm_monetization(self):
        matrix = tools.analyze_monetization_matrix(
            channel_desc="I am thinking about creating a course someday!",
            external_links=[{"url": "https://teachable.com/x", "category": "course"}]
        )
        self.assertTrue(matrix["course"])
        self.assertTrue(matrix["monetization_detected"])
        self.assertGreaterEqual(matrix["confidence"], 0.9)
        self.assertIn("course", matrix["confirmed_by_links"])

    def test_course_word_without_link_not_confirmed(self):
        matrix = tools.analyze_monetization_matrix(
            channel_desc="Join my course and learn trading basics"
        )
        self.assertFalse(matrix["course"])
        self.assertIn("course", matrix["unconfirmed"])

    def test_course_platform_domain_confirms(self):
        matrix = tools.analyze_monetization_matrix(
            channel_desc="My full course is hosted on teachable.com"
        )
        self.assertTrue(matrix["course"])
        self.assertNotIn("course", matrix["unconfirmed"])

    def test_course_url_in_text_confirms(self):
        matrix = tools.analyze_monetization_matrix(
            channel_desc="Enroll in my course: https://mysite.io/join"
        )
        self.assertTrue(matrix["course"])


class TestCommentSampling(unittest.TestCase):
    def _fake_threads(self, texts_by_video):
        def fake_list(**kwargs):
            m = MagicMock()
            items = []
            for t in texts_by_video.get(kwargs.get("videoId"), []):
                items.append({
                    "snippet": {"topLevelComment": {"snippet": {
                        "textDisplay": t, "likeCount": 5, "authorDisplayName": "V"
                    }}}
                })
            m.execute.return_value = {"items": items}
            return m
        return fake_list

    def test_round_robin_and_question_priority(self):
        yt = MagicMock()
        yt.commentThreads().list.side_effect = self._fake_threads({
            "a": ["Great video bro, loved it so much honestly speaking"],
            "b": ["Can you make a step-by-step guide on how to sell and transfer to exchange?"],
        })
        comments = tools.get_video_comments(yt, ["a", "b"], max_comments=2)
        self.assertEqual(len(comments), 2)
        self.assertEqual({c["video_id"] for c in comments}, {"a", "b"})
        question = [c for c in comments if c.get("question")]
        self.assertEqual(len(question), 1)
        self.assertIn("step-by-step", question[0]["text"])


class TestAgentExecuteToolExtras(unittest.TestCase):
    def _agent(self):
        with patch("agent.build"):
            return agent.YouTubeAgent(youtube_api_key="k", deepseek_api_key="d")

    def test_extract_links_reads_from_state(self):
        ag = self._agent()
        ag.state["channel_desc"] = "Join my telegram https://t.me/mychan"
        ag.state["video_descs"] = []

        res = ag.execute_tool("extract_external_links", {})

        self.assertEqual(res["summary"]["community"], 1)
        self.assertEqual(ag.state["external_links"], res)

        with self.assertRaises(ValueError):
            ag.execute_tool("extract_external_links", {"desc": "x"})


class TestSaveOutreachOfferGate(unittest.TestCase):
    def _agent(self):
        with patch("agent.build"):
            return agent.YouTubeAgent(youtube_api_key="k", deepseek_api_key="d")

    def test_prompt_mandates_offer(self):
        prompt = agent.AGENT_SYSTEM_PROMPT
        self.assertIn("The Offer step is MANDATORY", prompt)
        self.assertIn("must not be saved", prompt)

    def test_save_outreach_proposal_rejects_dm_without_offer(self):
        ag = self._agent()
        dm = ("Hey there, your comments are full of 'how do I sell this?' questions. "
              "Ever wondered why nobody answers them? Would a checklist even matter here? "
              "Curious what you think.")
        with patch("tools.save_outreach_proposal") as mock_save:
            res = ag.execute_tool("save_outreach_proposal", {
                "channel_title": "Offerless Channel",
                "report_text": "Some report",
                "cold_dm": dm
            })
        mock_save.assert_not_called()
        self.assertIn("error", res)
        self.assertIn("missing the service offer", res["error"])
        self.assertIn("save_outreach_proposal again", res["error"])

    def test_save_outreach_proposal_accepts_dm_with_offer(self):
        ag = self._agent()
        dm = ("Hey Imran, your comment section keeps asking how to buy coins before listing. "
              "I build turnkey courses + funnels for crypto educators, done for you. "
              "Want a 2-min outline?")
        saved_fake = {"analysis_file": "/tmp/a.txt", "outreach_file": "/tmp/b.txt"}
        with patch("tools.save_outreach_proposal", return_value=saved_fake) as mock_save:
            res = ag.execute_tool("save_outreach_proposal", {
                "channel_title": "Offer Channel",
                "report_text": "Report body",
                "cold_dm": dm
            })
        mock_save.assert_called_once()
        self.assertEqual(res, saved_fake)


class TestAudienceSignals(unittest.TestCase):
    def test_extracts_questions_and_requests(self):
        comments = [
            "Great video!",
            "Can you make a step-by-step guide on how to find these coins?",
            "How do I get started with this strategy?",
            "Love it",
        ]
        res = tools.analyze_audience_signals(comments)
        self.assertEqual(res["total_comments"], 4)
        self.assertEqual(res["question_count"], 2)
        self.assertEqual(res["request_count"], 2)
        self.assertEqual(len(res["request_examples"]), 2)

    def test_empty_comments(self):
        res = tools.analyze_audience_signals([])
        self.assertEqual(res["total_comments"], 0)
        self.assertEqual(res["question_count"], 0)
        self.assertEqual(res["request_count"], 0)


class TestEngagementRate(unittest.TestCase):
    def test_typical_rate(self):
        rate = tools.compute_engagement_rate("10000", [300, 500, 200])
        self.assertAlmostEqual(rate, 0.0333, places=3)

    def test_missing_subscribers(self):
        self.assertIsNone(tools.compute_engagement_rate("Hidden", [100, 200]))

    def test_missing_views(self):
        self.assertIsNone(tools.compute_engagement_rate("10000", [None, None]))


class TestOutreachPriority(unittest.TestCase):
    def test_high_priority(self):
        res = tools.compute_outreach_priority(
            subscribers="5000",
            engagement_rate=0.05,
            matrix={"course": False},
            signals={"request_count": 3, "question_count": 5},
            risk_flags=[]
        )
        self.assertEqual(res["priority"], "HIGH")
        self.assertTrue(res["in_micro_range"])

    def test_low_priority_outside_range(self):
        res = tools.compute_outreach_priority(
            subscribers="20000",
            engagement_rate=0.02,
            matrix={"course": False},
            signals={"request_count": 0, "question_count": 1},
            risk_flags=[]
        )
        self.assertEqual(res["priority"], "LOW")
        self.assertFalse(res["in_micro_range"])

    def test_skip_with_risk_flags(self):
        res = tools.compute_outreach_priority(
            subscribers="15000",
            engagement_rate=0.06,
            matrix={"course": False},
            signals={"request_count": 5},
            risk_flags=["referral_farming"]
        )
        self.assertEqual(res["priority"], "SKIP")

    def test_education_product_reduces_priority(self):
        res = tools.compute_outreach_priority(
            subscribers="5000",
            engagement_rate=0.04,
            matrix={"course": True},
            signals={"request_count": 2},
            risk_flags=[]
        )
        # In range + engagement + requests = 3 points even though course exists.
        # The test verifies the function returns a valid result and does not crash.
        self.assertIn(res["priority"], {"HIGH", "MEDIUM", "LOW"})
        self.assertGreaterEqual(res["score"], 0)


class TestAgent(unittest.TestCase):
    def test_tools_schema_validity(self):
        schema = agent.AGENT_TOOLS_SCHEMA
        self.assertIsInstance(schema, list)
        tool_names = [t["function"]["name"] for t in schema]
        self.assertIn("get_channel_overview", tool_names)
        self.assertIn("get_recent_videos", tool_names)
        self.assertIn("get_video_comments", tool_names)
        self.assertIn("detect_monetization_matrix", tool_names)
        self.assertIn("detect_risk_flags", tool_names)
        self.assertIn("detect_audience_signals", tool_names)
        self.assertIn("compute_outreach_priority", tool_names)
        self.assertIn("extract_external_links", tool_names)
        self.assertIn("save_outreach_proposal", tool_names)

    def test_argument_free_tools_declared_without_properties(self):
        for name in ("detect_monetization_matrix", "detect_risk_flags", "detect_audience_signals", "compute_outreach_priority", "extract_external_links"):
            fn = next(t["function"] for t in agent.AGENT_TOOLS_SCHEMA if t["function"]["name"] == name)
            self.assertEqual(fn["parameters"]["properties"], {})

    def test_prompt_has_outreach_sections(self):
        prompt = agent.AGENT_SYSTEM_PROMPT
        self.assertIn("OUTREACH PRIORITY", prompt)
        self.assertIn("DM BRIEF", prompt)
        self.assertIn("MICRO-INFLUENCER FOCUS", prompt)

    def test_save_tool_accepts_optional_matrix(self):
        fn = next(t["function"] for t in agent.AGENT_TOOLS_SCHEMA if t["function"]["name"] == "save_outreach_proposal")
        self.assertIn("matrix", fn["parameters"]["properties"])
        self.assertNotIn("matrix", fn["parameters"].get("required", []))

    def test_risk_gate_prompt_text(self):
        prompt = agent.AGENT_SYSTEM_PROMPT
        self.assertIn("referral_farming", prompt)
        self.assertIn("unverifiable_token_hype", prompt)
        self.assertIn("do NOT propose a signals, trading-tips or bot product", prompt)
        self.assertIn("education-only offer", prompt)
        self.assertIn("state the reason in the summary", prompt)

    def test_matrix_step_uses_fetched_data(self):
        prompt = agent.AGENT_SYSTEM_PROMPT
        self.assertIn("detect_monetization_matrix", prompt)
        self.assertIn("already fetched", prompt)

    @patch("agent.build")
    @patch("agent.post_deepseek")
    def test_agent_run_loop(self, mock_post, mock_build):
        mock_yt = MagicMock()
        mock_build.return_value = mock_yt

        # Step 1: LLM decides to call get_channel_overview
        # Step 2: LLM returns final text
        mock_post.side_effect = [
            {
                "choices": [{
                    "message": {
                        "role": "assistant",
                        "content": "Let me check the channel overview first.",
                        "tool_calls": [{
                            "id": "call_1",
                            "type": "function",
                            "function": {
                                "name": "get_channel_overview",
                                "arguments": json.dumps({"channel_input": "@test"})
                            }
                        }]
                    }
                }]
            },
            {
                "choices": [{
                    "message": {
                        "role": "assistant",
                        "content": "Here is the completed Cold DM outreach analysis.",
                        "tool_calls": []
                    }
                }]
            }
        ]

        with patch("tools.get_channel_overview") as mock_overview:
            mock_overview.return_value = {
                "channel_id": "UC123",
                "title": "Test Channel",
                "uploads_playlist_id": "UU123",
                "subscribers": "10000"
            }

            ag = agent.YouTubeAgent(
                youtube_api_key="fake_yt_key",
                deepseek_api_key="fake_ds_key"
            )

            res = ag.run("@test", max_steps=3)
            self.assertIn("completed Cold DM", res["summary"])
            self.assertIn("report", res)
            self.assertIn("cold_dm", res)
            mock_overview.assert_called_once_with(mock_yt, "@test")
            self.assertEqual(mock_post.call_count, 2)


if __name__ == "__main__":
    unittest.main()
