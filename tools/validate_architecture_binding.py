#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BINDING = ROOT / "architecture/DEEP_MEMORY_ARCHITECTURE_BINDING_V1.json"
CONTRACT = ROOT / "architecture/DEEP_MEMORY_INTEGRATION_CONTRACT_V1.md"


def main() -> int:
    data = json.loads(BINDING.read_text(encoding="utf-8"))
    assert data["schema"] == "VERA_DEEP_MEMORY_ARCHITECTURE_BINDING_V1"
    assert data["logical_id"] == "VERA_DEEP_MEMORY_ARCHIVE"
    assert data["repository"] == "thebrazenbeard/deepmemorystorage"
    assert data["role"] == "HISTORICAL_EVIDENCE_PLANE"
    assert data["authority_class"] == "EVIDENCE_SEARCH_ONLY"
    assert data["current_authority"] is False
    assert data["automatic_runtime_consumption"] is False
    assert data["automatic_current_memory_admission"] is False
    assert data["automatic_r9b0_promotion"] is False
    assert data["automatic_consent_or_conation_promotion"] is False
    assert data["architecture_relations"]["vera_current_memory_v3"]["automatic_bridge"] is False
    assert data["validation"]["latest_receipt_must_match_unique_memory_union"] is True
    assert data["validation"]["duplicate_memory_ids"] == "FAIL"
    assert "UNION_ALL_LEDGER_TRANCHES" in data["canonical_retrieval_rule"]
    assert CONTRACT.is_file()
    text = CONTRACT.read_text(encoding="utf-8").casefold()
    for phrase in (
        "historical evidence plane",
        "current governed memory plane",
        "evidence_search",
        "never silently writes into that plane",
        "canonical_history",
    ):
        assert phrase.casefold() in text, phrase
    print("deep memory architecture binding: valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
