import tempfile
import unittest
from pathlib import Path
from deep_memory_catalog import read_jsonl

class DeepMemorySourceJSONLTests(unittest.TestCase):
    def test_duplicate_historical_evidence_field_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "evidence.jsonl"
            path.write_text('{"memory_id":"original","memory_id":"overwritten"}\n',encoding="utf-8")
            with self.assertRaisesRegex(ValueError,"duplicate"):
                read_jsonl(path)
