"""OTT Rule v2 (L1.5 DSL) schema validation tests.

Loads fixtures from tests/fixtures/rule-v2/ and validates against
schemas/ott-rule-v2.schema.json. Also verifies that an L1.5 `ott-rule`
source passes schemas/ott-repo.schema.json (the manifest contract), which
folds the DSL fields into the rule definition.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

import jsonschema

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

RULE_V2_SCHEMA = json.loads(
    (ROOT / "schemas" / "ott-rule-v2.schema.json").read_text(encoding="utf-8")
)
REPO_SCHEMA = json.loads(
    (ROOT / "schemas" / "ott-repo.schema.json").read_text(encoding="utf-8")
)
FIXTURES = ROOT / "tests" / "fixtures" / "rule-v2"

VALID_FIXTURES = ["valid-hitokoto-l1.json", "valid-jisubei-dsl.json"]

INVALID_FIXTURES = [
    "invalid-mix-transform-steps.json",
    "invalid-unknown-primitive.json",
    "invalid-steps-overflow.json",
    "invalid-min-api-level-zero.json",
]


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class RuleV2SchemaTest(unittest.TestCase):
    def test_valid_fixtures_pass_v2_schema(self) -> None:
        for name in VALID_FIXTURES:
            with self.subTest(name):
                jsonschema.validate(_load(name), RULE_V2_SCHEMA)  # no raise

    def test_invalid_fixtures_fail_v2_schema(self) -> None:
        for name in INVALID_FIXTURES:
            with self.subTest(name), self.assertRaises(jsonschema.ValidationError):
                jsonschema.validate(_load(name), RULE_V2_SCHEMA)

    def test_l15_rule_source_passes_repo_schema(self) -> None:
        """L1.5 规则（steps/permissions/rights）作为 ott-rule source 必须过 manifest 契约。"""
        manifest = {
            "protocol": "ott-repo",
            "version": "1.1",
            "type": "repository",
            "repo_id": "io.github.whynusn.test",
            "name": "Test",
            "mirrors": [
                {"url": "https://example.com/ott-repo.json", "priority": 1}
            ],
            "sources": [
                {
                    "type": "ott-rule",
                    "rule_id": "jisubei",
                    "label": "极速杯",
                    "rule": _load("valid-jisubei-dsl.json"),
                },
                {
                    "type": "ott-rule",
                    "rule_id": "hitokoto",
                    "label": "一言",
                    "rule": _load("valid-hitokoto-l1.json"),
                },
            ],
        }
        jsonschema.validate(manifest, REPO_SCHEMA)  # no raise

    def test_all_source_types_accept_default_enabled(self) -> None:
        """instance/rule/bridge/script 四种源类型都必须接受 default_enabled。"""
        base = {
            "protocol": "ott-repo",
            "version": "1.1",
            "type": "repository",
            "repo_id": "io.github.whynusn.test",
            "name": "Test",
            "mirrors": [{"url": "https://example.com/ott-repo.json", "priority": 1}],
        }
        sources = [
            {
                "type": "ott-instance",
                "authority": "demo",
                "label": "x",
                "endpoints": [{"url": "https://example.com/ott/", "profile": "static", "priority": 1}],
                "default_enabled": True,
            },
            {
                "type": "ott-rule",
                "rule_id": "r",
                "label": "x",
                "rule": {
                    "kind": "json-api",
                    "request": {"url": "https://example.com/api", "method": "GET"},
                    "extract": {"title": "$.t", "content": "$.c"},
                },
                "default_enabled": True,
            },
            {
                "type": "ott-bridge",
                "bridge_kind": "generic-http",
                "endpoint": "https://example.com/bridge",
                "label": "x",
                "default_enabled": True,
            },
            {
                "type": "ott-script",
                "url": "https://example.com/script.py",
                "label": "x",
                "default_enabled": True,
            },
        ]
        jsonschema.validate({**base, "sources": sources}, REPO_SCHEMA)  # no raise

    def test_l1_legacy_rule_still_passes_repo_schema(self) -> None:
        """v1.0 L1 规则（无 steps，有 transform）必须保持合法。"""
        manifest = {
            "protocol": "ott-repo",
            "version": "1.1",
            "type": "repository",
            "repo_id": "io.github.whynusn.test",
            "name": "Test",
            "mirrors": [
                {"url": "https://example.com/ott-repo.json", "priority": 1}
            ],
            "sources": [
                {
                    "type": "ott-rule",
                    "rule_id": "poem",
                    "label": "诗文",
                    "rule": {
                        "kind": "json-api",
                        "request": {"url": "https://example.com/api", "method": "GET"},
                        "extract": {"title": "$.title", "content": "$.content"},
                        "transform": ["trim"],
                    },
                }
            ],
        }
        jsonschema.validate(manifest, REPO_SCHEMA)  # no raise


if __name__ == "__main__":
    unittest.main()
