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

    def _make_response(self, updates):
        r = MagicMock()
        r.json.return_value = {"result": updates}
        return r

    @patch("quiz_bot.requests.get")
    def test_returns_true_on_recent_message(self, mock_get):
        mock_get.return_value = self._make_response(
            [self._make_update(-100123, "test_chat", int(time.time()) - 3600)]
        )
        with patch.object(quiz_bot, "TELEGRAM_ACTIVITY_CHAT_ID", "@test_chat"):
            self.assertTrue(quiz_bot.has_recent_activity())

    @patch("quiz_bot.requests.get")
    def test_uses_negative_offset(self, mock_get):
        """Regressione: offset=-100 serve a non consumare gli update dalla coda."""
        mock_get.return_value = self._make_response([])
        with patch.object(quiz_bot, "TELEGRAM_ACTIVITY_CHAT_ID", "@test_chat"):
            quiz_bot.has_recent_activity()
        self.assertEqual(mock_get.call_count, 1)
        params = mock_get.call_args.kwargs["params"]
        self.assertEqual(params["offset"], -100)

    @patch("quiz_bot.requests.get")
    def test_returns_false_when_no_recent_message(self, mock_get):
        mock_get.return_value = self._make_response(
            [self._make_update(-100123, "test_chat", int(time.time()) - 7 * 3600)]
        )
        with patch.object(quiz_bot, "TELEGRAM_ACTIVITY_CHAT_ID", "@test_chat"):
            self.assertFalse(quiz_bot.has_recent_activity())

    @patch("quiz_bot.requests.get", side_effect=Exception("timeout"))
    def test_returns_true_on_network_error(self, _):
        self.assertTrue(quiz_bot.has_recent_activity())

    @patch("quiz_bot.requests.get")
    def test_ignores_messages_from_other_chats(self, mock_get):
        mock_get.return_value = self._make_response(
            [self._make_update(-999, "altro_chat", int(time.time()) - 1)]
        )
        with patch.object(quiz_bot, "TELEGRAM_ACTIVITY_CHAT_ID", "@test_chat"):
            self.assertFalse(quiz_bot.has_recent_activity())

    @patch("quiz_bot.requests.get")
    def test_reads_window_from_env_short(self, mock_get):
        """Con finestra 30min un messaggio di 60min fa NON è recente."""
        mock_get.return_value = self._make_response(
            [self._make_update(-100123, "test_chat", int(time.time()) - 60 * 60)]
        )
        with patch.object(quiz_bot, "TELEGRAM_ACTIVITY_CHAT_ID", "@test_chat"), \
             patch.dict(os.environ, {"TELEGRAM_ACTIVITY_WINDOW_MINUTES": "30"}):
            self.assertFalse(quiz_bot.has_recent_activity())

    @patch("quiz_bot.requests.get")
    def test_reads_window_from_env_match(self, mock_get):
        """Con finestra 30min un messaggio di 10min fa è recente."""
        mock_get.return_value = self._make_response(
            [self._make_update(-100123, "test_chat", int(time.time()) - 10 * 60)]
        )
        with patch.object(quiz_bot, "TELEGRAM_ACTIVITY_CHAT_ID", "@test_chat"), \
             patch.dict(os.environ, {"TELEGRAM_ACTIVITY_WINDOW_MINUTES": "30"}):
            self.assertTrue(quiz_bot.has_recent_activity())

    @patch("quiz_bot.requests.get")
    def test_uses_latest_of_multiple_messages(self, mock_get):
        """Se la coda ha più messaggi, usa il più recente anche se preceduto da uno vecchio."""
        old = self._make_update(-100123, "test_chat", int(time.time()) - 7 * 3600, update_id=1)
        recent = self._make_update(-100123, "test_chat", int(time.time()) - 60, update_id=2)
        mock_get.return_value = self._make_response([old, recent])
        with patch.object(quiz_bot, "TELEGRAM_ACTIVITY_CHAT_ID", "@test_chat"):
            self.assertTrue(quiz_bot.has_recent_activity())


class TestValidateQuiz(unittest.TestCase):
    def test_valid_quiz_returns_no_errors(self):
        quiz = {
            "question": "Domanda breve?",
            "options": ["A", "B", "C"],
            "correct_option_ids": [0],
            "explanation": "Spiegazione breve.",
        }
        self.assertEqual(quiz_bot.validate_quiz(quiz), [])

    def test_flags_question_plus_description_over_limit(self):
        quiz = {
            "question": "Q" * 200,
            "description": "D" * 200,
            "options": ["A", "B"],
            "correct_option_ids": [0],
        }
        errors = quiz_bot.validate_quiz(quiz)
        self.assertEqual(len(errors), 1)
        self.assertIn("question+description", errors[0])

    def test_flags_option_over_limit(self):
        quiz = {
            "question": "Q",
            "options": ["ok", "X" * 150],
            "correct_option_ids": [0],
        }
        errors = quiz_bot.validate_quiz(quiz)
        self.assertTrue(any("opzione 1" in e for e in errors))

    def test_flags_explanation_over_limit(self):
        quiz = {
            "question": "Q",
            "options": ["A", "B"],
            "correct_option_ids": [0],
            "explanation": "E" * 300,
        }
        errors = quiz_bot.validate_quiz(quiz)
        self.assertTrue(any("explanation" in e for e in errors))

    def test_empty_quiz_returns_no_errors(self):
        """Nessun campo → nessun limite superato, lista vuota."""
        self.assertEqual(quiz_bot.validate_quiz({}), [])


class TestPrintQuiz(unittest.TestCase):
    """Smoke test: verifica che print_quiz non sollevi eccezioni sui rami principali."""

    def _quiz(self, **overrides):
        base = {
            "question": "Domanda?",
            "options": ["A", "B", "C"],
            "correct_option_ids": [1],
            "explanation": "Spiegazione",
        }
        base.update(overrides)
        return base

    @patch("builtins.print")
    def test_prints_generic_quiz(self, _):
        quiz_bot.print_quiz(self._quiz(), episode_ref=None)

    @patch("builtins.print")
    def test_prints_episode_quiz(self, _):
        quiz_bot.print_quiz(self._quiz(), episode_ref="Episodio 42")

    @patch("builtins.print")
    def test_prints_with_description(self, _):
        quiz_bot.print_quiz(self._quiz(description="print(1+1)"), episode_ref=None)

    @patch("builtins.print")
    def test_prints_with_index(self, _):
        quiz_bot.print_quiz(self._quiz(), episode_ref=None, index=3)


class TestGenerateQuizContent(unittest.TestCase):
    """Mockiamo `quiz_bot.call_claude` per evitare chiamate reali all'API Anthropic."""

    def _claude_response(self):
        return {
            "question": "Q?",
            "options": ["A", "B"],
            "correct_option_ids": [0],
            "explanation": "E",
        }

    @patch("quiz_bot.call_claude")
    @patch("quiz_bot.random")
    def test_generic_path_when_random_above_threshold(self, mock_random, mock_claude):
        mock_random.random.return_value = 0.9
        mock_random.choice.return_value = "tema test"
        mock_claude.return_value = self._claude_response()

        with patch.object(quiz_bot, "FEED_RSS_URL", "http://example.com/feed"):
            quiz, episode_ref = quiz_bot.generate_quiz_content()

        self.assertIsNone(episode_ref)
        self.assertEqual(quiz["question"], "Q?")
        mock_claude.assert_called_once()
        # Il system prompt usato deve essere quello generico.
        self.assertEqual(mock_claude.call_args.args[0], quiz_bot._GENERIC_SYSTEM)

    @patch("quiz_bot.call_claude")
    @patch("quiz_bot.fetch_github_script", return_value="")
    @patch("quiz_bot.fetch_random_episode")
    @patch("quiz_bot.random")
    def test_episode_path_with_transcript(
        self, mock_random, mock_fetch_ep, mock_fetch_script, mock_claude
    ):
        mock_random.random.return_value = 0.1
        mock_fetch_ep.return_value = {
            "title": "Titolo ep",
            "summary": "trascrizione dall'episodio",
        }
        mock_claude.return_value = self._claude_response()

        with patch.object(quiz_bot, "FEED_RSS_URL", "http://example.com/feed"):
            quiz, episode_ref = quiz_bot.generate_quiz_content()

        self.assertEqual(episode_ref, "Titolo ep")
        self.assertEqual(quiz["question"], "Q?")
        self.assertEqual(mock_claude.call_args.args[0], quiz_bot._EPISODE_SYSTEM)

    @patch("quiz_bot.call_claude")
    @patch("quiz_bot.fetch_random_episode", side_effect=RuntimeError("feed vuoto"))
    @patch("quiz_bot.random")
    def test_episode_feed_failure_falls_back_to_generic(
        self, mock_random, mock_fetch_ep, mock_claude
    ):
        mock_random.random.return_value = 0.1
        mock_random.choice.return_value = "tema test"
        mock_claude.return_value = self._claude_response()

        with patch.object(quiz_bot, "FEED_RSS_URL", "http://example.com/feed"):
            quiz, episode_ref = quiz_bot.generate_quiz_content()

        self.assertIsNone(episode_ref)
        self.assertEqual(mock_claude.call_args.args[0], quiz_bot._GENERIC_SYSTEM)

    @patch("quiz_bot.call_claude")
    @patch("quiz_bot.fetch_github_script", return_value="")
    @patch("quiz_bot.fetch_random_episode")
    @patch("quiz_bot.random")
    def test_episode_without_content_falls_back_to_generic(
        self, mock_random, mock_fetch_ep, mock_fetch_script, mock_claude
    ):
        mock_random.random.return_value = 0.1
        mock_random.choice.return_value = "tema test"
        # Episodio senza trascrizione né summary → fallback generico.
        mock_fetch_ep.return_value = {"title": "Titolo ep"}
        mock_claude.return_value = self._claude_response()

        with patch.object(quiz_bot, "FEED_RSS_URL", "http://example.com/feed"):
            quiz, episode_ref = quiz_bot.generate_quiz_content()

        self.assertIsNone(episode_ref)
        self.assertEqual(mock_claude.call_args.args[0], quiz_bot._GENERIC_SYSTEM)


class TestGenerateValidQuiz(unittest.TestCase):
    """Copre il loop di retry senza chiamare call_claude (stub diretto di generate_quiz_content)."""

    def _valid_quiz(self):
        return {
            "question": "Q?",
            "options": ["A", "B"],
            "correct_option_ids": [0],
            "explanation": "E",
        }

    @patch("quiz_bot.print_quiz")
    @patch("quiz_bot.generate_quiz_content")
    def test_returns_on_first_valid_attempt(self, mock_gen, _):
        mock_gen.return_value = (self._valid_quiz(), None)
        quiz, episode_ref = quiz_bot.generate_valid_quiz()
        self.assertEqual(quiz["question"], "Q?")
        self.assertIsNone(episode_ref)
        self.assertEqual(mock_gen.call_count, 1)

    @patch("quiz_bot.print_quiz")
    @patch("quiz_bot.generate_quiz_content")
    def test_retries_until_valid(self, mock_gen, _):
        invalid = {
            "question": "Q" * 400,  # oltre limite 300
            "options": ["A", "B"],
            "correct_option_ids": [0],
        }
        mock_gen.side_effect = [(invalid, None), (self._valid_quiz(), "Ep 1")]
        quiz, episode_ref = quiz_bot.generate_valid_quiz()
        self.assertEqual(quiz["question"], "Q?")
        self.assertEqual(episode_ref, "Ep 1")
        self.assertEqual(mock_gen.call_count, 2)

    @patch("quiz_bot.print_quiz")
    @patch("quiz_bot.generate_quiz_content")
    def test_exits_after_max_retries(self, mock_gen, _):
        invalid = {
            "question": "Q" * 400,
            "options": ["A", "B"],
            "correct_option_ids": [0],
        }
        mock_gen.return_value = (invalid, None)
        with self.assertRaises(SystemExit):
            quiz_bot.generate_valid_quiz()
        self.assertEqual(mock_gen.call_count, quiz_bot._MAX_QUIZ_RETRIES)


if __name__ == "__main__":
    unittest.main()
