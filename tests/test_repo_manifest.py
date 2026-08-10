"""OTT Repo v1 manifest validation tests.

Loads canonical fixtures from tests/fixtures/ott/repo-manifests/ and validates
against schemas/ott-repo.schema.json. Valid fixtures MUST pass; invalid
fixtures MUST fail. Extends the existing compatibility pack mechanism.
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

SCHEMA_PATH = ROOT / "schemas" / "ott-repo.schema.json"
FIXTURES = ROOT / "tests" / "fixtures" / "ott" / "repo-manifests"

VALID_FIXTURES = [
    "valid-minimal.json",
    "valid-directory.json",
    "valid-repository-mix.json",
    "valid-script.json",
]

INVALID_FIXTURES = [
    "invalid-missing-protocol.json",
    "invalid-protocol-value.json",
    "invalid-type-value.json",
    "invalid-missing-mirrors.json",
    "invalid-empty-mirrors.json",
    "invalid-mirror-missing-url.json",
    "invalid-source-unknown-type.json",
    "invalid-instance-missing-authority.json",
    "invalid-instance-empty-endpoints.json",
    "invalid-rule-missing-rule-id.json",
    "invalid-bridge-missing-endpoint.json",
    "invalid-directory-contains-non-ref.json",
    "invalid-script-missing-url.json",
    "invalid-script-non-https.json",
]


class RepoManifestSchemaTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))

    # ---- valid fixtures must validate ----

    def test_valid_fixtures_pass_schema(self) -> None:
        for name in VALID_FIXTURES:
            with self.subTest(fixture=name):
                data = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
                jsonschema.validate(data, self.schema)

    def test_valid_minimal_has_required_fields(self) -> None:
        data = json.loads((FIXTURES / "valid-minimal.json").read_text(encoding="utf-8"))
        for field in (
            "protocol",
            "version",
            "type",
            "repo_id",
            "name",
            "mirrors",
            "sources",
        ):
            self.assertIn(field, data)
        self.assertEqual(data["protocol"], "ott-repo")
        self.assertEqual(data["type"], "repository")
        self.assertEqual(len(data["mirrors"]), 1)
        self.assertEqual(
            data["mirrors"][0]["url"], "https://minimal.example.org/ott-repo.json"
        )

    def test_valid_directory_allows_only_repository_refs(self) -> None:
        data = json.loads(
            (FIXTURES / "valid-directory.json").read_text(encoding="utf-8")
        )
        self.assertEqual(data["type"], "directory")
        for src in data["sources"]:
            self.assertEqual(src["type"], "repository-ref")

    def test_valid_mix_has_all_source_types(self) -> None:
        data = json.loads(
            (FIXTURES / "valid-repository-mix.json").read_text(encoding="utf-8")
        )
        types = {s["type"] for s in data["sources"]}
        self.assertEqual(
            types, {"ott-instance", "ott-rule", "ott-bridge", "ott-script"}
        )

    # ---- invalid fixtures must fail schema ----

    def test_invalid_fixtures_fail_schema(self) -> None:
        for name in INVALID_FIXTURES:
            with self.subTest(fixture=name):
                data = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
                with self.assertRaises(jsonschema.ValidationError):
                    jsonschema.validate(data, self.schema)

    # ---- schema structural checks ----

    def test_schema_id_matches_spec(self) -> None:
        self.assertEqual(
            self.schema["$id"],
            "https://open-typing-texts.local/schemas/ott-repo.schema.json",
        )

    def test_schema_requires_protocol_const(self) -> None:
        self.assertEqual(self.schema["properties"]["protocol"], {"const": "ott-repo"})

    def test_schema_restricts_type_enum(self) -> None:
        self.assertEqual(
            self.schema["properties"]["type"], {"enum": ["repository", "directory"]}
        )

    def test_schema_mirrors_min_items(self) -> None:
        mirrors_schema = self.schema["properties"]["mirrors"]
        self.assertEqual(mirrors_schema["minItems"], 1)
        self.assertIn("url", mirrors_schema["items"]["required"])

    def test_schema_instance_requires_authority_and_endpoints(self) -> None:
        """Per-source-type refinement: ott-instance needs authority + endpoints."""
        for clause in self.schema["properties"]["sources"]["items"]["allOf"]:
            if (
                clause.get("if", {}).get("properties", {}).get("type", {}).get("const")
                == "ott-instance"
            ):
                self.assertIn("authority", clause["then"]["required"])
                self.assertIn("endpoints", clause["then"]["required"])
                self.assertEqual(
                    clause["then"]["properties"]["endpoints"]["minItems"], 1
                )
                break
        else:
            self.fail("Missing ott-instance allOf refinement in schema")

    def test_schema_directory_ref_only(self) -> None:
        """repository-ref requires url and forbids authority/endpoints."""
        for clause in self.schema["properties"]["sources"]["items"]["allOf"]:
            if (
                clause.get("if", {}).get("properties", {}).get("type", {}).get("const")
                == "repository-ref"
            ):
                self.assertIn("url", clause["then"]["required"])
                break
        else:
            self.fail("Missing repository-ref allOf refinement in schema")

    def test_schema_rule_requires_rule_id(self) -> None:
        for clause in self.schema["properties"]["sources"]["items"]["allOf"]:
            if (
                clause.get("if", {}).get("properties", {}).get("type", {}).get("const")
                == "ott-rule"
            ):
                self.assertIn("rule_id", clause["then"]["required"])
                self.assertIn("rule", clause["then"]["required"])
                break
        else:
            self.fail("Missing ott-rule allOf refinement in schema")

    def test_schema_bridge_requires_kind_and_endpoint(self) -> None:
        for clause in self.schema["properties"]["sources"]["items"]["allOf"]:
            if (
                clause.get("if", {}).get("properties", {}).get("type", {}).get("const")
                == "ott-bridge"
            ):
                self.assertIn("bridge_kind", clause["then"]["required"])
                self.assertIn("endpoint", clause["then"]["required"])
                break
        else:
            self.fail("Missing ott-bridge allOf refinement in schema")

    def test_schema_script_requires_https_url(self) -> None:
        """ott-script requires a public https url; executes only under L3 gate."""
        for clause in self.schema["properties"]["sources"]["items"]["allOf"]:
            if (
                clause.get("if", {}).get("properties", {}).get("type", {}).get("const")
                == "ott-script"
            ):
                self.assertIn("url", clause["then"]["required"])
                self.assertEqual(
                    clause["then"]["properties"]["url"]["pattern"], "^https?://"
                )
                break
        else:
            self.fail("Missing ott-script allOf refinement in schema")


if __name__ == "__main__":
    unittest.main()
