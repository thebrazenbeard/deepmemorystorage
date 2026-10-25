"""Fail-closed publication checks without loading private archival rows."""

from __future__ import annotations

import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import deep_memory_catalog as catalog


class InvalidCorpusPublicationTests(unittest.TestCase):
    @staticmethod
    def _invalid_union() -> dict[str, object]:
        return {
            "errors": ["synthetic digest mismatch"], "warnings": [],
            "latest_pass_id": "INGEST_PASS_001", "memory_count": 0,
            "source_count": 0, "source_row_count": 0,
            "identical_source_restatements": 0, "amendment_count": 0,
            "classification_correction_count": 0,
            "frontier_correction_count": 0,
            "historical_canon_overlay_file_count": 0,
            "historical_canon_overlay_assignment_count": 0,
            "catalog_digest_sha256": "a" * 64,
            "union_subject_digest_sha256": "b" * 64,
            "receipt_chain_status": "CHAIN_RESOLVES",
            "receipt_union_match_status": "CORPUS_SUBJECT_MISMATCH",
            "catalog": [],
        }

    def test_cli_rejects_materialization_of_invalid_union(self) -> None:
        fake_union = self._invalid_union()
        with tempfile.TemporaryDirectory() as tmpdir:
            destination = Path(tmpdir) / "catalog"
            with (
                patch.object(catalog, "load_union", return_value=fake_union),
                patch.object(catalog, "write_outputs") as writer,
                patch.object(sys, "argv", ["catalog", "--write-output", str(destination)]),
                patch("sys.stderr", new_callable=io.StringIO),
                patch("sys.stdout", new_callable=io.StringIO),
            ):
                code = catalog.main()
            self.assertEqual(code, 1)
            writer.assert_not_called()
            self.assertFalse(destination.exists())

    def test_valid_union_can_still_materialize_catalog_and_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            destination = Path(tmpdir) / "catalog"
            union = {"errors": [], "catalog": []}
            with patch.object(catalog, "build_manifest", return_value={"schema": "test"}):
                catalog.write_outputs(union, destination)
            self.assertEqual((destination / "retrieval_catalog.jsonl").read_text(), "")
            self.assertIn('"schema": "test"', (destination / "corpus_manifest.json").read_text())

    def test_direct_write_rejects_invalid_union_before_creating_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            destination = Path(tmpdir) / "catalog"
            with (
                self.assertRaisesRegex(ValueError, "invalid corpus"),
                patch.object(catalog, "build_manifest", return_value={}),
            ):
                catalog.write_outputs(self._invalid_union(), destination)
            self.assertFalse(destination.exists())

    def test_invalid_union_preserves_preexisting_catalog_and_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            destination = Path(tmpdir) / "catalog"
            destination.mkdir()
            catalog_file = destination / "retrieval_catalog.jsonl"
            manifest_file = destination / "corpus_manifest.json"
            catalog_file.write_text("previous-catalog\n")
            manifest_file.write_text("previous-manifest\n")
            with self.assertRaisesRegex(ValueError, "invalid corpus"):
                catalog.write_outputs(self._invalid_union(), destination)
            self.assertEqual(catalog_file.read_text(), "previous-catalog\n")
            self.assertEqual(manifest_file.read_text(), "previous-manifest\n")

    def test_serialization_failure_preserves_existing_pair(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            destination = Path(tmpdir) / "catalog"
            destination.mkdir()
            catalog_file = destination / "retrieval_catalog.jsonl"
            manifest_file = destination / "corpus_manifest.json"
            catalog_file.write_text("previous-catalog\n")
            manifest_file.write_text("previous-manifest\n")
            # A malformed manifest is rejected after the catalog stage is
            # serialized but before either published file is replaced.
            with patch.object(catalog, "build_manifest", return_value={"bad": object()}):
                with self.assertRaises(TypeError):
                    catalog.write_outputs({"errors": [], "catalog": []}, destination)
            self.assertEqual(catalog_file.read_text(), "previous-catalog\n")
            self.assertEqual(manifest_file.read_text(), "previous-manifest\n")


if __name__ == "__main__":
    unittest.main()
