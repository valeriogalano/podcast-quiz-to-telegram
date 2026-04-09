import json
import os
import sys
import time
import unittest
from unittest.mock import MagicMock, patch

# Env vars richiesti a import-time dal modulo
os.environ.setdefault("TELEGRAM_CHAT_ID", "@test_chat")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "123:test")

import quiz_bot


class TestExtractTranscript(unittest.TestCase):
    def test_content_field(self):
        episode = MagicMock()
        episode.content = [{"value": "testo trascrizione"}]
        self.assertEqual(quiz_bot.extract_transcript(episode), "testo trascrizione")

    def test_content_empty_falls_back_to_summary(self):
        episode = MagicMock()
        episode.content = []
        episode.get = lambda k, d=None: {"summary": "testo summary"}.get(k, d)
        self.assertEqual(quiz_bot.extract_transcript(episode), "testo summary")

    def test_summary_fallback(self):
        episode = {"summary": "testo summary", "itunes_transcript": "trascrizione itunes"}
        self.assertEqual(quiz_bot.extract_transcript(episode), "testo summary")

    def test_itunes_transcript_fallback(self):
        episode = {"itunes_transcript": "trascrizione itunes"}
        self.assertEqual(quiz_bot.extract_transcript(episode), "trascrizione itunes")

    def test_empty(self):
        episode = {}
        self.assertEqual(quiz_bot.extract_transcript(episode), "")


class TestFetchRandomEpisode(unittest.TestCase):
    @patch("quiz_bot.feedparser")
    def test_returns_random_episode(self, mock_feedparser):
        mock_feedparser.parse.return_value.entries = [{"title": "Ep 1"}, {"title": "Ep 2"}]
        episode = quiz_bot.fetch_random_episode()
        self.assertIn(episode["title"], ["Ep 1", "Ep 2"])

    @patch("quiz_bot.feedparser")
    def test_exits_on_empty_feed(self, mock_feedparser):
        mock_feedparser.parse.return_value.entries = []
        with self.assertRaises(RuntimeError):
            quiz_bot.fetch_random_episode()


class TestFetchGithubScript(unittest.TestCase):
    @patch("quiz_bot.requests.get")
    def test_returns_best_matching_script(self, mock_get):
        files_resp = MagicMock()
        files_resp.json.return_value = [
            {"name": "episodio-bluetooth.yml", "download_url": "http://example.com/bt.yml"},
            {"name": "altro-episodio.yml", "download_url": "http://example.com/altro.yml"},
        ]
        content_resp = MagicMock()
        content_resp.text = "contenuto script bluetooth"

        mock_get.side_effect = [files_resp, content_resp]

        with patch.object(quiz_bot, "SCRIPT_EXTENSIONS", (".yml",)):
            result = quiz_bot.fetch_github_script("Bluetooth: l'origine del nome")

        self.assertEqual(result, "contenuto script bluetooth")

    @patch("quiz_bot.requests.get")
    def test_returns_empty_on_no_match(self, mock_get):
        files_resp = MagicMock()
        files_resp.json.return_value = [
            {"name": "episodio-xyz.yml", "download_url": "http://example.com/xyz.yml"},
        ]
        mock_get.return_value = files_resp

        with patch.object(quiz_bot, "SCRIPT_EXTENSIONS", (".yml",)):
            result = quiz_bot.fetch_github_script("Bluetooth")

        self.assertEqual(result, "")

    @patch("quiz_bot.requests.get", side_effect=Exception("timeout"))
    def test_returns_empty_on_network_error(self, _):
        result = quiz_bot.fetch_github_script("qualsiasi titolo")
        self.assertEqual(result, "")


class TestCallClaude(unittest.TestCase):
    def _make_message(self, text):
        msg = MagicMock()
        msg.content = [MagicMock(text=text)]
        return msg

    @patch("quiz_bot.anthropic.Anthropic")
    def test_parses_valid_json(self, mock_anthropic):
        payload = {"question": "?", "options": ["a", "b"], "correct_option_ids": [0]}
        mock_anthropic.return_value.messages.create.return_value = self._make_message(
            json.dumps(payload)
        )
        result = quiz_bot.call_claude("system", "user")
        self.assertEqual(result["question"], "?")

    @patch("quiz_bot.anthropic.Anthropic")
    def test_strips_code_fences(self, mock_anthropic):
        payload = {"question": "?", "options": ["a", "b"], "correct_option_ids": [0]}
        wrapped = f"```json\n{json.dumps(payload)}\n```"
        mock_anthropic.return_value.messages.create.return_value = self._make_message(wrapped)
        result = quiz_bot.call_claude("system", "user")
        self.assertEqual(result["question"], "?")

    @patch("quiz_bot.anthropic.Anthropic")
    def test_exits_on_invalid_json(self, mock_anthropic):
        mock_anthropic.return_value.messages.create.return_value = self._make_message("non è json")
        with self.assertRaises(SystemExit):
            quiz_bot.call_claude("system", "user")


class TestSendPoll(unittest.TestCase):
    @patch("quiz_bot.requests.post")
    def test_sends_poll(self, mock_post):
        mock_post.return_value.json.return_value = {"result": {"message_id": 42}}
        quiz = {
            "question": "Domanda?",
            "options": ["A", "B", "C", "D"],
            "correct_option_ids": [1],
            "explanation": "Spiegazione",
        }
        result = quiz_bot.send_poll(quiz)
        self.assertEqual(result["result"]["message_id"], 42)
        payload = mock_post.call_args.kwargs["json"]
        self.assertEqual(payload["question"], "Domanda?")
        self.assertEqual(payload["correct_option_id"], 1)

    @patch("quiz_bot.requests.post")
    def test_appends_description_to_question(self, mock_post):
        mock_post.return_value.json.return_value = {"result": {"message_id": 1}}
        quiz = {
            "question": "Cosa stampa?",
            "description": "print(1+1)",
            "options": ["1", "2", "3", "4"],
            "correct_option_ids": [1],
        }
        quiz_bot.send_poll(quiz)
        payload = mock_post.call_args.kwargs["json"]
        self.assertIn("print(1+1)", payload["question"])


class TestHasRecentActivity(unittest.TestCase):
    def _make_update(self, chat_id, username, timestamp, update_id=1):
        return {
            "update_id": update_id,
            "message": {
                "chat": {"id": chat_id, "username": username},
                "date": timestamp,
            },
        }

    def _make_responses(self, *batches):
        """Costruisce una sequenza di risposte mock: ogni batch è una lista di update,
        seguita da una risposta vuota per terminare la paginazione."""
        responses = []
        for batch in batches:
            r = MagicMock()
            r.json.return_value = {"result": batch}
            responses.append(r)
        empty = MagicMock()
        empty.json.return_value = {"result": []}
        responses.append(empty)
        return responses

    @patch("quiz_bot.requests.get")
    def test_returns_true_on_recent_message(self, mock_get):
        mock_get.side_effect = self._make_responses(
            [self._make_update(-100123, "test_chat", int(time.time()) - 3600)]
        )
        with patch.object(quiz_bot, "TELEGRAM_ACTIVITY_CHAT_ID", "@test_chat"):
            self.assertTrue(quiz_bot.has_recent_activity())

    @patch("quiz_bot.requests.get")
    def test_returns_false_when_no_recent_message(self, mock_get):
        mock_get.side_effect = self._make_responses(
            [self._make_update(-100123, "test_chat", int(time.time()) - 7 * 3600)]
        )
        with patch.object(quiz_bot, "TELEGRAM_ACTIVITY_CHAT_ID", "@test_chat"):
            self.assertFalse(quiz_bot.has_recent_activity())

    @patch("quiz_bot.requests.get", side_effect=Exception("timeout"))
    def test_returns_true_on_network_error(self, _):
        self.assertTrue(quiz_bot.has_recent_activity())

    @patch("quiz_bot.requests.get")
    def test_ignores_messages_from_other_chats(self, mock_get):
        mock_get.side_effect = self._make_responses(
            [self._make_update(-999, "altro_chat", int(time.time()) - 1)]
        )
        with patch.object(quiz_bot, "TELEGRAM_ACTIVITY_CHAT_ID", "@test_chat"):
            self.assertFalse(quiz_bot.has_recent_activity())

    @patch("quiz_bot.requests.get")
    def test_finds_recent_message_in_second_page(self, mock_get):
        """Verifica che la paginazione funzioni: il messaggio recente è nel secondo batch."""
        old = self._make_update(-100123, "test_chat", int(time.time()) - 7 * 3600, update_id=1)
        recent = self._make_update(-100123, "test_chat", int(time.time()) - 60, update_id=2)
        mock_get.side_effect = self._make_responses([old], [recent])
        with patch.object(quiz_bot, "TELEGRAM_ACTIVITY_CHAT_ID", "@test_chat"):
            self.assertTrue(quiz_bot.has_recent_activity())


if __name__ == "__main__":
    unittest.main()
