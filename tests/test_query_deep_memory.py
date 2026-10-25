"""Regression checks for exact-scope Deep Memory overlay disclosure."""

import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from query_deep_memory import _visible_overlay_rows


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


if __name__ == "__main__":
    unittest.main()
