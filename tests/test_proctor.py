from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from agent_evals.proctor import ProctorQueue


class ProctorQueueTest(unittest.TestCase):
    def test_question_answer_round_trip_and_immutability(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            queue = ProctorQueue(Path(directory))
            question = queue.ask("run-1", "ce-07", "Should validation stay fail-fast?")
            self.assertEqual([question], queue.pending())
            answer = queue.answer(
                question.question_id, "Yes; caller misuse stays fail-fast.", "Hermes"
            )
            self.assertEqual(answer, queue.wait(question.question_id, 0.2))
            self.assertEqual([], queue.pending())
            with self.assertRaises(FileExistsError):
                queue.answer(question.question_id, "different", "Hermes")
            events = [json.loads(line) for line in queue.events.read_text().splitlines()]
            self.assertEqual(["question", "answer"], [event["event"] for event in events])

    def test_rejects_empty_question(self) -> None:
        with tempfile.TemporaryDirectory() as directory, self.assertRaises(ValueError):
            ProctorQueue(Path(directory)).ask("run", "task", "  ")


if __name__ == "__main__":
    unittest.main()
