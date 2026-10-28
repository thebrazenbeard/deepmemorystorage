"""Regression checks for exact-scope Deep Memory overlay disclosure."""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from query_deep_memory import _visible_overlay_rows
import deep_memory_catalog as catalog


class OverlayPrivacyTests(unittest.TestCase):
    def visible(self, overlay, scopes=("PROJECT",)):
        return _visible_overlay_rows(
            [overlay],
            target_privacy_scope="PROJECT",
            audit_all_privacy=False,
            authorized_privacy=set(scopes),
        )

    def test_malformed_explicit_scope_does_not_inherit_target_access(self):
        for bad_scope in ([], {}, None, 0, False, "", "  "):
            with self.subTest(scope=bad_scope):
                self.assertEqual(
                    self.visible({"privacy_scope": bad_scope, "text": "restricted"}),
                    [],
                )

    def test_absent_scope_inherits_target_access(self):
        visible = self.visible({"text": "inherited"})
        self.assertEqual(len(visible), 1)
        self.assertEqual(visible[0]["effective_privacy_scope"], "PROJECT")

    def test_valid_explicit_scope_requires_exact_authorization(self):
        overlay = {"privacy_scope": "PRIVATE", "text": "private"}
        self.assertEqual(self.visible(overlay), [])
        self.assertEqual(
            self.visible(overlay, scopes=("PROJECT", "PRIVATE"))[0]["effective_privacy_scope"],
            "PRIVATE",
        )

    def test_missing_target_privacy_cannot_fabricate_access(self):
        self.assertEqual(
            _visible_overlay_rows(
                [{"text": "no target scope"}],
                target_privacy_scope=None,
                audit_all_privacy=False,
                authorized_privacy={"PROJECT"},
            ),
            [],
        )

    def test_historical_canon_catalog_preserves_explicit_privacy(self):
        # The catalog synthesizes per-memory overlay rows from JSON files.
        # That normalization must not erase an explicit PRIVATE or invalid
        # scope and silently reclassify it as inheriting the PROJECT target.
        for explicit_scope in ("PRIVATE", [], None, "  "):
            with self.subTest(explicit_scope=explicit_scope):
                with tempfile.TemporaryDirectory() as temp_name:
                    root = Path(temp_name)
                    ledger = root / "ledger"
                    ledger.mkdir()
                    (ledger / "memories.jsonl").write_text(json.dumps({
                        "memory_id": "SYNTH-001",
                        "privacy_scope": "PROJECT",
                        "historical_canonicity": "CANONICAL_HISTORY",
                    }) + "\n", encoding="utf-8")
                    (ledger / "historical_canon_restricted.json").write_text(json.dumps({
                        "memory_ids": ["SYNTH-001"],
                        "applies_to_preexisting_memory_rows": 1,
                        "historical_canonicity": "REJECTED_OR_FALSE_ATTRIBUTION",
                        "privacy_scope": explicit_scope,
                    }), encoding="utf-8")
                    with (patch.object(catalog, "ROOT", root),
                          patch.object(catalog, "LEDGER", ledger),
                          patch.object(catalog, "UPDATES", root / "updates")):
                        union = catalog.load_union()
                    self.assertEqual(union["errors"], [])
                    overlays = union["canon_overlays_by_target"]["SYNTH-001"]
                    project_only = _visible_overlay_rows(
                        overlays, target_privacy_scope="PROJECT",
                        audit_all_privacy=False, authorized_privacy={"PROJECT"},
                    )
                    self.assertEqual(project_only, [])
                    if explicit_scope == "PRIVATE":
                        permitted = _visible_overlay_rows(
                            overlays, target_privacy_scope="PROJECT",
                            audit_all_privacy=False,
                            authorized_privacy={"PROJECT", "PRIVATE"},
                        )
                        self.assertEqual(permitted[0]["effective_privacy_scope"],
                                         "PRIVATE")


if __name__ == "__main__":
    unittest.main()
