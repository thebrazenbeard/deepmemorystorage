#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BINDING = ROOT / "architecture/DEEP_MEMORY_ARCHITECTURE_BINDING_V1.json"
CONTRACT = ROOT / "architecture/DEEP_MEMORY_INTEGRATION_CONTRACT_V1.md"
RESULT_SCHEMA = ROOT / "schema/DEEP_MEMORY_EVIDENCE_RESULT_V1.schema.json"


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
    assert data["privacy_default"] == "FAIL_CLOSED_EXACT_AUTHORIZED_SCOPE"

    retrieval = data["retrieval_contract"]
    assert retrieval["mode"] == "EVIDENCE_SEARCH"
    assert retrieval["result_schema"] == "schema/DEEP_MEMORY_EVIDENCE_RESULT_V1.schema.json"
    assert "AUTHORIZED_PRIVACY_SCOPES" in retrieval["privacy_rule"]
    assert "result_semantics" in retrieval["required_result_fields"]
    assert "return_records_outside_exact_caller_authorized_privacy_scope" in retrieval["must_not_do"]

    assert data["architecture_relations"]["vera_current_memory_v3"]["automatic_bridge"] is False
    assert data["validation"]["latest_receipt_must_match_unique_memory_union"] is True
    assert data["validation"]["duplicate_memory_ids"] == "FAIL"
    assert data["validation"]["identical_duplicate_source_ids"] == "DEDUP_WARN"
    assert data["validation"]["divergent_duplicate_source_ids"] == "FAIL_CONFLICT"
    assert data["validation"]["privacy_without_authorized_scope"] == "FAIL_CLOSED"
    assert "UNION_ALL_LEDGER_TRANCHES" in data["canonical_retrieval_rule"]

    assert CONTRACT.is_file()
    assert RESULT_SCHEMA.is_file()
    schema = json.loads(RESULT_SCHEMA.read_text(encoding="utf-8"))
    assert schema["$id"] == "VERA_DEEP_MEMORY_EVIDENCE_RESULT_V1"
    result_properties = schema["properties"]["results"]["items"]["properties"]
    assert result_properties["result_semantics"]["const"] == "HISTORICAL_EVIDENCE_ONLY_NOT_CURRENT_MEMORY_OR_AUTHORITY"

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
