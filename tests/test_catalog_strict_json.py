import importlib.util
import pathlib
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("deep_memory_catalog", ROOT / "tools" / "deep_memory_catalog.py")
catalog = importlib.util.module_from_spec(spec)
spec.loader.exec_module(catalog)


class StrictDeepMemoryJSONLTests(unittest.TestCase):
    def test_duplicate_record_fields_cannot_rewrite_archival_claim(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            source = root / "ledger" / "synthetic.jsonl"
            source.parent.mkdir()
            source.write_text(
                '{"memory_id":"original","memory_id":"forged","claim":"synthetic"}\n',
                encoding="utf-8",
            )
            with mock.patch.object(catalog, "ROOT", root):
                with self.assertRaisesRegex(ValueError, "duplicate"):
                    catalog.read_jsonl(source)
