"""Unit and Integration tests for YouTube AI Agent and Tools."""

import unittest
from unittest.mock import MagicMock, patch
import os
import json

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
            cold_dm="I noticed Test Channel's recent videos focus on practical tutorials. "
                    "I have one idea to turn that audience interest into a simple offer.",
            personalization_terms=["Test Channel", "practical tutorials"]
        )
        self.assertTrue(os.path.exists(saved["analysis_file"]))
        self.assertTrue(os.path.exists(saved["outreach_file"]))

        with open(saved["outreach_file"], "r", encoding="utf-8") as f:
            self.assertIn("Test Channel", f.read())

        saved = tools.save_outreach_proposal(
            channel_title="Matrix Channel",
            report_text="Audit",
            cold_dm="Your Matrix Channel videos explain affiliate workflows clearly. "
                    "Would you be open to a short breakdown of one additional offer?",
            matrix={"course": False, "affiliate": True},
            personalization_terms=["Matrix Channel", "affiliate workflows"]
        )
        with open(saved["analysis_file"], "r", encoding="utf-8") as f:
            self.assertIn('"affiliate": true', f.read())

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

    def test_niche_search_cache(self):
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


class TestAgent(unittest.TestCase):
    def test_tools_schema_validity(self):
        schema = agent.AGENT_TOOLS_SCHEMA
        self.assertIsInstance(schema, list)
        tool_names = [t["function"]["name"] for t in schema]
        self.assertIn("get_channel_overview", tool_names)
        self.assertIn("get_recent_videos", tool_names)
        self.assertIn("get_video_comments", tool_names)
        self.assertIn("save_outreach_proposal", tool_names)

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
            mock_overview.assert_called_once_with(mock_yt, "@test")
            self.assertEqual(mock_post.call_count, 2)


if __name__ == "__main__":
    unittest.main()
