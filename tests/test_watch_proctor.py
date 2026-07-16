from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.watch_proctor import pending


class ProctorWatcherTest(unittest.TestCase):
    def test_only_returns_unanswered_questions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runs = Path(directory)
            queue = runs / "run-1" / "proctor"
            questions = queue / "questions"
            answers = queue / "answers"
            questions.mkdir(parents=True)
            answers.mkdir()
            question = {
                "question_id": "q1",
                "task_id": "task",
                "question": "Which policy?",
                "asked_at": "now",
            }
            (questions / "q1.json").write_text(json.dumps(question))
            rows = pending(runs)
            self.assertEqual(1, len(rows))
            self.assertEqual("Which policy?", rows[0]["question"])
            self.assertEqual(str(queue), rows[0]["queue"])
            (answers / "q1.json").write_text("{}")
            self.assertEqual([], pending(runs))


if __name__ == "__main__":
    unittest.main()
