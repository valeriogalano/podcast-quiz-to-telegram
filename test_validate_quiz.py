"""Unit tests for validate_quiz in quiz_bot.py."""
import os

os.environ.setdefault("TELEGRAM_CHAT_ID", "@test_chat")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "123:test")

from quiz_bot import validate_quiz


class TestValidateQuiz:
    def _make_quiz(self, question="Q?", description="", options=None, correct_ids=None, explanation="", model=""):
        return {
            "question": question,
            "description": description,
            "options": options or ["A", "B", "C", "D"],
            "correct_option_ids": correct_ids or [0],
            "explanation": explanation,
            "model": model,
        }

    def test_valid_quiz_returns_no_errors(self):
        quiz = self._make_quiz(
            question="What is Python?",
            description="A popular language.",
            options=["A language", "A snake", "A tool", "A library"],
            explanation="Python is a programming language.",
        )
        errors = validate_quiz(quiz)
        assert errors == []

    def test_question_at_exactly_300(self):
        """Bot API: la question accetta fino a 300 caratteri inclusi."""
        quiz = self._make_quiz(question="x" * 300)
        errors = validate_quiz(quiz)
        assert not any("question" in e for e in errors)

    def test_question_over_300(self):
        quiz = self._make_quiz(question="x" * 301)
        errors = validate_quiz(quiz)
        assert any("question" in e and "300" in e for e in errors)

    def test_description_independent_budget(self):
        """Bot API 9.0: question e description hanno limiti separati (300 e 200)."""
        quiz = self._make_quiz(question="x" * 300, description="d" * 100)
        errors = validate_quiz(quiz)
        # Né question né description dovrebbero essere segnalate.
        assert errors == []

    def test_description_at_exactly_200(self):
        quiz = self._make_quiz(description="d" * 200)
        errors = validate_quiz(quiz)
        assert not any("description" in e for e in errors)

    def test_description_over_200(self):
        quiz = self._make_quiz(description="d" * 201)
        errors = validate_quiz(quiz)
        assert any("description" in e and "200" in e for e in errors)

    def test_description_with_model_footer(self):
        """Il footer di trasparenza sul modello concorre al limite della description."""
        # 180 char + "\n\n— generato con claude-haiku-4-5" ≈ 222 > 200
        quiz = self._make_quiz(
            description="d" * 180,
            model="claude-haiku-4-5",
        )
        errors = validate_quiz(quiz)
        assert any("description" in e for e in errors)

    def test_option_too_long(self):
        long_opt = "x" * 101
        quiz = self._make_quiz(options=[long_opt, "B", "C", "D"])
        errors = validate_quiz(quiz)
        assert any("opzione 0" in e for e in errors)

    def test_option_at_exactly_100_chars(self):
        opt = "x" * 100
        quiz = self._make_quiz(options=[opt, "B", "C", "D"])
        errors = validate_quiz(quiz)
        assert not any("opzione 0" in e for e in errors)

    def test_explanation_too_long(self):
        quiz = self._make_quiz(explanation="x" * 201)
        errors = validate_quiz(quiz)
        assert any("explanation" in e for e in errors)

    def test_explanation_at_exactly_200_chars(self):
        quiz = self._make_quiz(explanation="x" * 200)
        errors = validate_quiz(quiz)
        assert not any("explanation" in e for e in errors)

    def test_multiple_errors_reported(self):
        quiz = self._make_quiz(
            question="x" * 301,
            options=["x" * 101, "B", "C", "D"],
            explanation="x" * 201,
        )
        errors = validate_quiz(quiz)
        assert len(errors) >= 3
