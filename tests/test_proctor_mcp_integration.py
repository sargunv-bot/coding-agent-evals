from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

from agent_evals.proctor import ProctorQueue


class ProctorMcpIntegrationTest(unittest.TestCase):
    def test_stdio_tool_round_trip(self) -> None:
        binary = Path("build/proctor-mcp")
        if not binary.is_file():
            self.skipTest("run `cae build-tools` to build proctor-mcp")
        with tempfile.TemporaryDirectory() as directory:
            queue = ProctorQueue(Path(directory))
            process = subprocess.Popen(
                [str(binary)],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=os.environ
                | {
                    "CAE_PROCTOR_QUEUE": directory,
                    "CAE_RUN_ID": "integration",
                    "CAE_TASK_ID": "ce-test",
                    "CAE_PROCTOR_TIMEOUT": "20s",
                },
            )
            self.assertIsNotNone(process.stdin)
            self.assertIsNotNone(process.stdout)
            assert process.stdin and process.stdout
            requests = [
                {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
                {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
                {
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/call",
                    "params": {
                        "name": "ask_user",
                        "arguments": {"question": "Should validation remain fail-fast?"},
                    },
                },
            ]
            for request in requests:
                process.stdin.write(json.dumps(request) + "\n")
            process.stdin.flush()
            initialize = json.loads(process.stdout.readline())
            tools = json.loads(process.stdout.readline())
            self.assertEqual(initialize["result"]["protocolVersion"], "2024-11-05")
            self.assertEqual(tools["result"]["tools"][0]["name"], "ask_user")

            deadline = time.monotonic() + 5
            pending = []
            while time.monotonic() < deadline and not pending:
                pending = queue.pending()
                time.sleep(0.05)
            self.assertEqual(len(pending), 1)
            queue.answer(
                pending[0].question_id,
                "Yes—keep caller argument validation fail-fast.",
                "Hermes Agent integration test",
            )
            response = json.loads(process.stdout.readline())
            self.assertIn("fail-fast", response["result"]["content"][0]["text"])
            process.stdin.close()
            process.wait(timeout=5)
            assert process.stdout and process.stderr
            process.stdout.close()
            process.stderr.close()
            self.assertEqual(process.returncode, 0)


if __name__ == "__main__":
    unittest.main()
