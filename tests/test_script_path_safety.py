from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class ScriptPathSafetyTest(unittest.TestCase):
    def test_script_safety_flags_writes_outside_content_dir(self) -> None:
        from ott_adapter.script_safety import validate_script_file

        with tempfile.TemporaryDirectory(prefix="ott_script_safety_") as raw_dir:
            path = Path(raw_dir) / "fetch_bad.py"
            path.write_text(
                "from pathlib import Path\nPath('/tmp/ott-bad.json').write_text('x')\n",
                encoding="utf-8",
            )
            report = validate_script_file(path)

        self.assertFalse(report.valid)
        self.assertIn("unsafe_write_path", {issue.code for issue in report.issues})

    def test_script_safety_does_not_trust_output_path_name(self) -> None:
        from ott_adapter.script_safety import validate_script_file

        with tempfile.TemporaryDirectory(prefix="ott_script_safety_") as raw_dir:
            path = Path(raw_dir) / "fetch_bad.py"
            path.write_text(
                "from pathlib import Path\n"
                "OUTPUT_PATH = Path('/tmp/ott-bad.json')\n"
                "OUTPUT_PATH.write_text('x')\n",
                encoding="utf-8",
            )
            report = validate_script_file(path)

        self.assertFalse(report.valid)
        self.assertIn("unsafe_write_path", {issue.code for issue in report.issues})

    def test_script_safety_rejects_content_parent_escape(self) -> None:
        from ott_adapter.script_safety import validate_script_file

        with tempfile.TemporaryDirectory(prefix="ott_script_safety_") as raw_dir:
            path = Path(raw_dir) / "fetch_bad.py"
            path.write_text(
                "from pathlib import Path\n"
                "target = Path('content').parent / 'outside.json'\n"
                "target.write_text('x')\n",
                encoding="utf-8",
            )
            report = validate_script_file(path)

        self.assertFalse(report.valid)
        self.assertIn("unsafe_write_path", {issue.code for issue in report.issues})

    def test_script_safety_rejects_content_dotdot_escape(self) -> None:
        from ott_adapter.script_safety import validate_script_file

        with tempfile.TemporaryDirectory(prefix="ott_script_safety_") as raw_dir:
            path = Path(raw_dir) / "fetch_bad.py"
            path.write_text(
                "from pathlib import Path\n"
                "target = Path('content') / '..' / 'outside.json'\n"
                "target.write_text('x')\n",
                encoding="utf-8",
            )
            report = validate_script_file(path)

        self.assertFalse(report.valid)
        self.assertIn("unsafe_write_path", {issue.code for issue in report.issues})

    def test_script_safety_rejects_unmodeled_write_path_escapes(self) -> None:
        from ott_adapter.script_safety import validate_script_source

        cases = {
            "builtin_open_text_write": (
                "open('content/../outside.json', 'wt', encoding='utf-8').write('x')\n"
            ),
            "path_open_text_write": (
                "from pathlib import Path\n"
                "Path('content/../outside.json')"
                ".open('wt', encoding='utf-8')"
                ".write('x')\n"
            ),
            "os_replace": (
                "import os\n"
                "from pathlib import Path\n"
                "Path('content/tmp.json').write_text('x', encoding='utf-8')\n"
                "os.replace('content/tmp.json', 'content/../outside.json')\n"
            ),
            "os_replace_alias": (
                "import os as operating_system\n"
                "from pathlib import Path\n"
                "Path('content/tmp.json').write_text('x', encoding='utf-8')\n"
                "operating_system.replace("
                "'content/tmp.json', 'content/../outside.json'"
                ")\n"
            ),
            "from_os_replace": (
                "from os import replace\n"
                "from pathlib import Path\n"
                "Path('content/tmp.json').write_text('x', encoding='utf-8')\n"
                "replace('content/tmp.json', 'content/../outside.json')\n"
            ),
            "os_rename": (
                "import os\n"
                "from pathlib import Path\n"
                "Path('content/tmp.json').write_text('x', encoding='utf-8')\n"
                "os.rename('content/tmp.json', 'content/../outside.json')\n"
            ),
            "shutil_move": (
                "import shutil\n"
                "from pathlib import Path\n"
                "Path('content/tmp.json').write_text('x', encoding='utf-8')\n"
                "shutil.move('content/tmp.json', 'content/../outside.json')\n"
            ),
            "from_shutil_move": (
                "from shutil import move\n"
                "from pathlib import Path\n"
                "Path('content/tmp.json').write_text('x', encoding='utf-8')\n"
                "move('content/tmp.json', 'content/../outside.json')\n"
            ),
            "assigned_os_replace": (
                "import os\n"
                "from pathlib import Path\n"
                "replace_alias = os.replace\n"
                "Path('content/tmp.json').write_text('x', encoding='utf-8')\n"
                "replace_alias('content/tmp.json', 'content/../outside.json')\n"
            ),
            "assigned_shutil_move": (
                "import shutil\n"
                "from pathlib import Path\n"
                "move_alias = shutil.move\n"
                "Path('content/tmp.json').write_text('x', encoding='utf-8')\n"
                "move_alias('content/tmp.json', 'content/../outside.json')\n"
            ),
            "assigned_builtin_open": (
                "open_alias = open\n"
                "open_alias("
                "'content/../outside.json', 'wt', encoding='utf-8'"
                ").write('x')\n"
            ),
            "assigned_path_open": (
                "from pathlib import Path\n"
                "open_alias = Path('content/../outside.json').open\n"
                "open_alias('wt', encoding='utf-8').write('x')\n"
            ),
            "assigned_path_write_text": (
                "from pathlib import Path\n"
                "write_alias = Path('content/../outside.json').write_text\n"
                "write_alias('x', encoding='utf-8')\n"
            ),
            "getattr_os_replace": (
                "import os\n"
                "from pathlib import Path\n"
                "replace_alias = getattr(os, 'replace')\n"
                "Path('content/tmp.json').write_text('x', encoding='utf-8')\n"
                "replace_alias('content/tmp.json', 'content/../outside.json')\n"
            ),
            "getattr_alias_os_replace": (
                "import os\n"
                "from pathlib import Path\n"
                "get = getattr\n"
                "replace_alias = get(os, 'replace')\n"
                "Path('content/tmp.json').write_text('x', encoding='utf-8')\n"
                "replace_alias('content/tmp.json', 'content/../outside.json')\n"
            ),
            "getattr_path_write_text": (
                "from pathlib import Path\n"
                "write_alias = getattr("
                "Path('content/../outside.json'), 'write_text'"
                ")\n"
                "write_alias('x', encoding='utf-8')\n"
            ),
            "path_multi_arg_dotdot": (
                "from pathlib import Path\n"
                "Path('content', '..', 'outside.json').write_text('x')\n"
            ),
            "unknown_root_content_join": (
                "import os\n"
                "from pathlib import Path\n"
                "root = Path(os.environ['OTT_ROOT'])\n"
                "target = root / 'content' / 'outside.json'\n"
                "target.write_text('x', encoding='utf-8')\n"
            ),
        }

        for label, source in cases.items():
            with self.subTest(label=label):
                report = validate_script_source(source, f"{label}.py")

                self.assertFalse(report.valid, report.to_dict())
                self.assertIn(
                    "unsafe_write_path",
                    {issue.code for issue in report.issues},
                )


if __name__ == "__main__":
    unittest.main()
