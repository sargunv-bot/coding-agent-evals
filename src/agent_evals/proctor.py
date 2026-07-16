from __future__ import annotations

import json
import os
import secrets
import time
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class Question:
    question_id: str
    run_id: str
    task_id: str
    text: str
    created_at: float


@dataclass(frozen=True)
class Answer:
    question_id: str
    text: str
    proctor: str
    created_at: float


class ProctorQueue:
    """Filesystem queue shared with the agent-side ask_user adapter.

    Every request and answer is immutable JSON. Atomic renames avoid partial reads.
    The queue is intentionally transport-only: the host SOTA proctor decides how
    to answer and records its identity/model separately in run metadata.
    """

    def __init__(self, root: Path):
        self.root = root.resolve()
        self.questions = self.root / "questions"
        self.answers = self.root / "answers"
        self.events = self.root / "events.jsonl"
        for path in (self.root, self.questions, self.answers):
            path.mkdir(parents=True, exist_ok=True, mode=0o777)
            path.chmod(0o777)

    def ask(self, run_id: str, task_id: str, text: str) -> Question:
        question = Question(
            question_id=f"q-{time.time_ns()}-{secrets.token_hex(4)}",
            run_id=run_id,
            task_id=task_id,
            text=text.strip(),
            created_at=time.time(),
        )
        if not question.text:
            raise ValueError("question must not be empty")
        self._atomic_json(self.questions / f"{question.question_id}.json", asdict(question))
        self._event("question", asdict(question))
        return question

    def pending(self) -> list[Question]:
        result: list[Question] = []
        for path in sorted(self.questions.glob("*.json")):
            data = json.loads(path.read_text())
            if not (self.answers / path.name).exists():
                result.append(Question(**data))
        return result

    def answer(self, question_id: str, text: str, proctor: str) -> Answer:
        question_path = self.questions / f"{question_id}.json"
        if not question_path.exists():
            raise KeyError(f"unknown question {question_id}")
        answer = Answer(question_id, text.strip(), proctor.strip(), time.time())
        if not answer.text or not answer.proctor:
            raise ValueError("answer and proctor must not be empty")
        path = self.answers / f"{question_id}.json"
        if path.exists():
            raise FileExistsError(f"question {question_id} was already answered")
        self._atomic_json(path, asdict(answer))
        self._event("answer", asdict(answer))
        return answer

    def wait(self, question_id: str, timeout: float, poll_interval: float = 0.2) -> Answer:
        path = self.answers / f"{question_id}.json"
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if path.exists():
                return Answer(**json.loads(path.read_text()))
            time.sleep(poll_interval)
        raise TimeoutError(f"proctor did not answer {question_id} within {timeout}s")

    def _event(self, kind: str, payload: dict[str, object]) -> None:
        fd = os.open(self.events, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(fd, "a") as stream:
            stream.write(json.dumps({"event": kind, **payload}, sort_keys=True) + "\n")

    @staticmethod
    def _atomic_json(path: Path, data: dict[str, object]) -> None:
        temp = path.with_suffix(f".tmp-{os.getpid()}")
        temp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
        os.replace(temp, path)
