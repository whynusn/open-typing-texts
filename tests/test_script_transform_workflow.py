from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class ScriptTransformWorkflowTest(unittest.TestCase):
    def test_poem_transform_uses_fake_raw_without_network(self) -> None:
        from scripts.fetch_poem import transform

        result = transform(
            {"hitokoto": "春眠不觉晓", "from": "春晓", "from_who": "孟浩然"},
            "2026-07-13",
        )

        self.assertEqual(result["content"], "春眠不觉晓")
        self.assertEqual(result["title"], "春晓")

    def test_jisubei_transform_uses_fake_raw_without_network(self) -> None:
        from scripts.fetch_jisubei import transform

        result = transform(
            {"msg": {"0": "测试正文", "a_name": "测试赛文"}},
            "2026-07-13",
        )

        self.assertEqual(result["source_key"], "jisubei")
        self.assertEqual(result["content"], "测试正文")
        self.assertEqual(result["title"], "测试赛文")

    def test_poem_transform_rejects_non_object_raw_payload(self) -> None:
        from scripts.fetch_poem import transform

        self.assertEqual(transform([], "2026-07-13"), {})

    def test_cli_validate_script_reports_success_without_running_fetch(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "ott_adapter",
                "validate-script",
                str(ROOT / "scripts" / "fetch_poem.py"),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn("PASS", result.stdout)


if __name__ == "__main__":
    unittest.main()
