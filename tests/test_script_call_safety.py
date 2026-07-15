from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class ScriptCallSafetyTest(unittest.TestCase):
    def test_script_safety_allows_current_scripts(self) -> None:
        from ott_adapter.script_safety import validate_script_file

        for path in sorted((ROOT / "scripts").glob("fetch_*.py")):
            report = validate_script_file(path)
            self.assertTrue(report.valid, report.to_dict())

    def test_script_safety_flags_high_risk_calls(self) -> None:
        from ott_adapter.script_safety import validate_script_file

        with tempfile.TemporaryDirectory(prefix="ott_script_safety_") as raw_dir:
            path = Path(raw_dir) / "fetch_bad.py"
            path.write_text("eval('1 + 1')\n", encoding="utf-8")
            report = validate_script_file(path)

        self.assertFalse(report.valid)
        self.assertIn("banned_call", {issue.code for issue in report.issues})

    def test_script_safety_flags_from_os_system_import(self) -> None:
        from ott_adapter.script_safety import validate_script_file

        with tempfile.TemporaryDirectory(prefix="ott_script_safety_") as raw_dir:
            path = Path(raw_dir) / "fetch_bad.py"
            path.write_text("from os import system\nsystem('date')\n", encoding="utf-8")
            report = validate_script_file(path)

        self.assertFalse(report.valid)
        self.assertIn("banned_import", {issue.code for issue in report.issues})

    def test_script_safety_flags_dynamic_banned_import(self) -> None:
        from ott_adapter.script_safety import validate_script_source

        cases = {
            "direct_importlib": (
                "import importlib\nimportlib.import_module('subprocess')\n",
                "banned_dynamic_import",
            ),
            "importlib_alias": (
                "import importlib as importer\nimporter.import_module('subprocess')\n",
                "banned_dynamic_import",
            ),
            "from_import_module_alias": (
                "from importlib import import_module as import_module_alias\n"
                "import_module_alias('subprocess')\n",
                "banned_dynamic_import",
            ),
            "assigned_import_module": (
                "import importlib\n"
                "import_module_alias = importlib.import_module\n"
                "import_module_alias('subprocess')\n",
                "banned_dynamic_import",
            ),
            "dunder_import": ("__import__('subprocess')\n", "banned_dynamic_import"),
            "assigned_dunder_import": (
                "import_alias = __import__\nimport_alias('subprocess')\n",
                "banned_dynamic_import",
            ),
            "getattr_import_module": (
                "import importlib\n"
                "import_module_alias = getattr(importlib, 'import_module')\n"
                "import_module_alias('subprocess')\n",
                "banned_dynamic_import",
            ),
            "dynamic_module_name": (
                "module_name = 'subprocess'\n__import__(module_name)\n",
                "banned_dynamic_import",
            ),
            "dunder_import_system_chain": (
                "__import__('os').system('date')\n",
                "banned_call",
            ),
            "import_module_system_chain": (
                "import importlib\nimportlib.import_module('os').system('date')\n",
                "banned_call",
            ),
            "getattr_import_system_chain": (
                "getattr(__import__('os'), 'system')('date')\n",
                "banned_call",
            ),
            "assigned_import_system_chain": (
                "module = __import__('os')\nmodule.system('date')\n",
                "banned_call",
            ),
        }

        for label, (source, expected_code) in cases.items():
            with self.subTest(label=label):
                report = validate_script_source(source, f"{label}.py")

                self.assertFalse(report.valid)
                self.assertIn(
                    expected_code,
                    {issue.code for issue in report.issues},
                )


if __name__ == "__main__":
    unittest.main()
