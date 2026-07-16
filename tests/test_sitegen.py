from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from sitegen.__main__ import build_site, validate_site


class SiteGeneratorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.data = self.root / "data"
        self.output = self.root / "site"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def write_json(self, relative: str, value: object) -> Path:
        path = self.data / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
        return path

    def write_text(self, relative: str, value: str) -> Path:
        path = self.data / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value)
        return path

    def make_complete_experiment(self) -> tuple[str, str]:
        experiment = "example-v1"
        cell = "provider__model__task__default__ask_user__r01"
        report = f"reports/experiments/{experiment}"
        run = f"{report}/evidence/runs/{cell}"
        self.write_text(
            f"experiments/{experiment}.toml",
            """[experiment]
id = "example-v1"
description = "Example"
stage = "stage-b"
repeats = 1
proctor_model = "reviewer/judge"
[[models]]
provider = "provider"
model = "model"
[[cells]]
task = "task"
mode = "ask_user"
""",
        )
        self.write_json(
            f"{report}/results.json",
            {
                "experiment_id": experiment,
                "rows": [
                    {
                        "cell_id": cell,
                        "provider": "provider",
                        "model": "model",
                        "task_id": "task",
                        "scenario": "",
                        "mode": "ask_user",
                        "repeat": 1,
                        "state": "completed",
                        "run_id": "run-1",
                        "deterministic_pass": True,
                        "verification_outcome": "passed",
                        "input_tokens": 10,
                        "cached_input_tokens": 2,
                        "output_tokens": 4,
                        "reasoning_tokens": 1,
                        "duration_seconds": 3.5,
                    }
                ],
                "totals": {"cells": 1, "completed": 1},
            },
        )
        self.write_json(
            f"{report}/evidence/index.json",
            {"experiment_id": experiment, "runs": [{"cell_id": cell, "run_id": "run-1"}]},
        )
        self.write_json(
            f"{run}/matrix-record.json",
            {
                "experiment_id": experiment,
                "state": "completed",
                "cell": {
                    "cell_id": cell,
                    "provider": "provider",
                    "model": "model",
                    "task_id": "task",
                    "mode": "ask_user",
                    "repeat": 1,
                },
                "attempts": [
                    {
                        "result": {
                            "run_id": "run-1",
                            "duration_seconds": 3.5,
                            "usage": {"input_tokens": 10, "output_tokens": 4},
                            "verification": {"outcome": "passed", "exit_code": 0},
                        }
                    }
                ],
            },
        )
        self.write_json(
            f"{run}/proctor-review.json",
            {
                "proctor": "Blinded reviewer",
                "proctor_model": "reviewer/judge",
                "blinded_to_model_identity": True,
                "can_override_deterministic": False,
                "mergeable": True,
                "scope_discipline": 5,
                "code_clarity": 4,
                "test_quality": 5,
                "repository_fit": 4,
                "security_and_safety": 5,
                "rating_rationales": {
                    "scope_discipline": "Focused.",
                    "code_clarity": "Clear.",
                    "test_quality": "Covered.",
                    "repository_fit": "Fits.",
                    "security_and_safety": "Safe.",
                },
                "blockers": [],
                "strengths": ["Small patch"],
                "summary": "Good patch.",
                "overall_reasoning": "Ready to merge.",
            },
        )
        artifacts = {
            "model.patch": "diff --git a/a b/a\n",
            "transcript.jsonl": '{"type":"message","text":"done"}\n',
            "verifier/stdout.txt": "PASS\n",
        }
        manifest = []
        for name, content in artifacts.items():
            path = self.write_text(f"{run}/{name}", content)
            data = path.read_bytes()
            manifest.append(
                {"path": name, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
            )
        self.write_json(f"{run}/artifacts.json", manifest)
        self.write_text(f"{report}/subjective-summary.md", "# Subjective summary\n")
        return experiment, cell

    def test_complete_build_exposes_results_reviews_and_artifacts(self) -> None:
        experiment, cell = self.make_complete_experiment()
        site = build_site(self.data, self.output, "/coding-agent-evals")

        self.assertEqual(site["experiments"][0]["summary"]["completed_cells"], 1)
        detail_path = self.output / "data" / "experiments" / experiment / "cells" / f"{cell}.json"
        detail = json.loads(detail_path.read_text())
        self.assertTrue(detail["deterministic"]["authoritative"])
        self.assertTrue(detail["deterministic"]["pass"])
        self.assertFalse(detail["subjective"]["can_override_deterministic"])
        self.assertEqual(detail["subjective"]["scores"]["test_quality"], 5)
        self.assertTrue(detail["candidate_patch"]["hash_matches"])
        self.assertEqual(detail["transcript"]["path"], "transcript.jsonl")
        self.assertEqual(detail["verifier_output"][0]["path"], "verifier/stdout.txt")
        page = (self.output / "experiments" / experiment / "cells" / cell / "index.html").read_text()
        self.assertIn("provider / model", page)
        self.assertIn("<h1>provider / model</h1>", page)
        self.assertNotIn(f"<h1>{cell}</h1>", page)
        self.assertIn("Deterministic result", page)
        self.assertIn("Canonical transcript", page)
        self.assertIn("reviewer/judge", page)
        self.assertIn('aria-label="Cell evidence"', page)
        self.assertIn('<details open><summary>Inline preview</summary>', page)
        transcript = page.split('id="transcript"', 1)[1].split("</section>", 1)[0]
        self.assertIn("<details><summary>Inline preview</summary>", transcript)
        self.assertNotIn("<details open>", transcript)
        self.assertIn('title="Exact runtime: 3.5 seconds"', page)
        self.assertIn('title="Exact value: 10"', page)
        self.assertIn("Download raw", page)
        experiment_page = (self.output / "experiments" / experiment / "index.html").read_text()
        self.assertIn("1 completed of 1 planned", experiment_page)
        self.assertIn("Completed / planned", experiment_page)
        self.assertIn('data-label="Provider / model"', experiment_page)
        self.assertNotIn("1 of 1 cells", experiment_page)
        self.assertNotIn("data.js", (self.output / "index.html").read_text())
        self.assertIn("--linen:", (self.output / "assets" / "site.css").read_text())
        self.assertIn("index-metrics", (self.output / "index.html").read_text())
        self.assertIn("localStorage", (self.output / "assets" / "site.js").read_text())
        self.assertEqual(validate_site(self.output), [])

    def test_partial_and_malformed_metadata_builds_with_warnings(self) -> None:
        experiment = "running"
        cell = "provider__model__task__default__ask_user__r01"
        report = self.data / "reports" / "experiments" / experiment
        run = report / "evidence" / "runs" / cell
        run.mkdir(parents=True)
        (report / "results.json").write_text("{not json")
        self.write_json(
            f"reports/experiments/{experiment}/evidence/index.json",
            {"runs": [{"cell_id": cell}, "malformed"]},
        )
        (run / "proctor-review.json").write_text("[]")
        self.write_json(
            f"reports/experiments/{experiment}/evidence/runs/{cell}/artifacts.json",
            [{"path": "../escape", "sha256": "bad"}, {"broken": True}],
        )

        site = build_site(self.data, self.output, "/project")
        summary = site["experiments"][0]["summary"]
        self.assertEqual(summary["discovered_cells"], 1)
        self.assertEqual(summary["completed_cells"], 0)
        experiment_data = json.loads(
            (self.output / "data" / "experiments" / f"{experiment}.json").read_text()
        )
        self.assertTrue(experiment_data["warnings"])
        cell_data = experiment_data["cells"][0]
        self.assertEqual(cell_data["state"], "partial")
        self.assertTrue(any("unsafe" in warning for warning in cell_data["warnings"]))
        self.assertIsNone(cell_data["subjective"])
        self.assertEqual(validate_site(self.output), [])

    def test_progress_uses_completed_out_of_planned_not_discovered(self) -> None:
        experiment, _ = self.make_complete_experiment()
        config = self.data / "experiments" / f"{experiment}.toml"
        config.write_text(config.read_text().replace("repeats = 1", "repeats = 40"))

        build_site(self.data, self.output, "/repo")
        page = (self.output / "experiments" / experiment / "index.html").read_text()
        index = (self.output / "index.html").read_text()

        self.assertIn("1 completed of 40 planned", page)
        self.assertIn("1 completed of 40 planned", index)
        self.assertNotIn("1 completed of 1 planned", page)
        self.assertIn('<dd>1<span aria-hidden="true"> / </span>40</dd>', page)

    def test_empty_data_root_produces_valid_empty_site(self) -> None:
        build_site(self.data, self.output, "/repo")
        index = (self.output / "index.html").read_text()
        self.assertIn("No committed experiment reports", index)
        self.assertEqual(validate_site(self.output), [])

    def test_generation_is_byte_deterministic(self) -> None:
        self.make_complete_experiment()
        first = self.root / "first"
        second = self.root / "second"
        build_site(self.data, first, "/repo")
        build_site(self.data, second, "/repo")

        def digest_tree(root: Path) -> dict[str, str]:
            return {
                str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in sorted(root.rglob("*"))
                if path.is_file()
            }

        self.assertEqual(digest_tree(first), digest_tree(second))

    def test_validation_detects_broken_base_path_url(self) -> None:
        build_site(self.data, self.output, "/repo")
        index = self.output / "index.html"
        index.write_text(index.read_text().replace('/repo/assets/site.css', '/wrong/site.css'))
        errors = validate_site(self.output)
        self.assertTrue(any("outside base path" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
