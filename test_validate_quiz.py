"""Unit tests for validate_quiz in quiz_bot.py."""
from quiz_bot import validate_quiz


class TestValidateQuiz:
    def _make_quiz(self, question="Q?", description="", options=None, correct_ids=None, explanation=""):
        return {
            "question": question,
            "description": description,
            "options": options or ["A", "B", "C", "D"],
            "correct_option_ids": correct_ids or [0],
            "explanation": explanation,
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

    def test_question_plus_description_too_long(self):
        # "Q?\n\n" = 4 chars, so 297 chars description → total 301 > 300
        long_desc = "x" * 297
        quiz = self._make_quiz(question="Q?", description=long_desc)
        errors = validate_quiz(quiz)
        assert any("question+description" in e for e in errors)

    def test_question_plus_description_at_exactly_300(self):
        # "Q?\n\n" (4 chars) + 296 chars = 300 → valid
        desc = "x" * 296
        quiz = self._make_quiz(question="Q?", description=desc)
        errors = validate_quiz(quiz)
        assert not any("question+description" in e for e in errors)

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
            question="Q?",
            description="x" * 295,
            options=["x" * 101, "B", "C", "D"],
            explanation="x" * 201,
        )
        errors = validate_quiz(quiz)
        assert len(errors) >= 2

    def test_no_description_uses_only_question_length(self):
        quiz = self._make_quiz(question="x" * 300, description="")
        errors = validate_quiz(quiz)
        assert not any("question+description" in e for e in errors)

    def test_no_description_over_limit(self):
        quiz = self._make_quiz(question="x" * 301, description="")
        errors = validate_quiz(quiz)
        assert any("question+description" in e for e in errors)
