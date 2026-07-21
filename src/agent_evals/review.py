from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class ProctorReview:
    run_id: str
    task_id: str
    proctor: str
    proctor_model: str
    blinded_to_model_identity: bool = True
    scope_discipline: int | None = None
    code_clarity: int | None = None
    test_quality: int | None = None
    repository_fit: int | None = None
    security_and_safety: int | None = None
    mergeable: bool | None = None
    blockers: list[str] = field(default_factory=list)
    strengths: list[str] = field(default_factory=list)
    summary: str = ""
    rating_rationales: dict[str, str] = field(default_factory=dict)
    overall_reasoning: str = ""
    deterministic_result_path: str = ""
    can_override_deterministic: bool = False

    def validate(self) -> list[str]:
        errors: list[str] = []
        for name in (
            "scope_discipline",
            "code_clarity",
            "test_quality",
            "repository_fit",
            "security_and_safety",
        ):
            value = getattr(self, name)
            if self.mergeable is not None and value is None:
                errors.append(f"completed review requires {name}")
            elif value is not None and not 1 <= value <= 5:
                errors.append(f"{name} must be between 1 and 5")
        if self.mergeable is True and self.blockers:
            errors.append("a mergeable patch cannot have blockers")
        if self.mergeable is not None and not self.summary.strip():
            errors.append("completed review requires a summary")
        if self.mergeable is not None:
            expected = {
                "scope_discipline",
                "code_clarity",
                "test_quality",
                "repository_fit",
                "security_and_safety",
            }
            missing = sorted(
                name for name in expected if not self.rating_rationales.get(name, "").strip()
            )
            if missing:
                detail = ", ".join(missing)
                errors.append(f"completed review requires rating rationales for {detail}")
            if not self.overall_reasoning.strip():
                errors.append("completed review requires overall reasoning")
        if self.can_override_deterministic:
            errors.append("qualitative review cannot override deterministic grading")
        return errors

    def write(self, path: Path) -> None:
        errors = self.validate()
        if errors:
            raise ValueError("; ".join(errors))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2, sort_keys=True) + "\n")
