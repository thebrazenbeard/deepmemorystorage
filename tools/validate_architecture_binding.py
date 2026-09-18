#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path

import deep_memory_catalog as catalog_module
from deep_memory_catalog import load_union, receipt_union_match_status
from query_deep_memory import _chronology_decorated_record

ROOT = Path(__file__).resolve().parents[1]
BINDING = ROOT / "architecture/DEEP_MEMORY_ARCHITECTURE_BINDING_V1.json"
CONTRACT = ROOT / "architecture/DEEP_MEMORY_INTEGRATION_CONTRACT_V1.md"
RESULT_SCHEMA = ROOT / "schema/DEEP_MEMORY_EVIDENCE_RESULT_V1.schema.json"
WORKFLOW = ROOT / ".github/workflows/deep-memory-architecture-validation.yml"


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

    record_sources = data["record_sources"]
    assert "ledger/historical_canon*.json" in record_sources["historical_canon_overlays"]

    retrieval = data["retrieval_contract"]
    assert retrieval["mode"] == "EVIDENCE_SEARCH"
    assert retrieval["result_schema"] == "schema/DEEP_MEMORY_EVIDENCE_RESULT_V1.schema.json"
    assert "AUTHORIZED_PRIVACY_SCOPES" in retrieval["privacy_rule"]
    assert "OVERLAYS_INHERIT_TARGET_PRIVACY" in retrieval["privacy_rule"]
    assert "result_semantics" in retrieval["required_result_fields"]
    assert "stored_vs_effective_historical_canonicity" in retrieval["must_preserve"]
    assert "return_records_or_overlay_payloads_outside_exact_caller_authorized_privacy_scope" in retrieval["must_not_do"]

    assert data["architecture_relations"]["vera_current_memory_v3"]["automatic_bridge"] is False
    assert data["validation"]["latest_receipt_must_match_unique_memory_union"] is True
    assert data["validation"]["historical_canon_overlays"] == "LOAD_APPLY_AND_VALIDATE"
    assert data["validation"]["duplicate_memory_ids"] == "FAIL"
    assert data["validation"]["identical_duplicate_source_ids"] == "DEDUP_WARN"
    assert data["validation"]["divergent_duplicate_source_ids"] == "FAIL_CONFLICT"
    assert data["validation"]["privacy_without_authorized_scope"] == "FAIL_CLOSED"
    assert data["validation"]["overlay_privacy"] == "INHERIT_TARGET_UNLESS_EXPLICIT_SCOPE_REQUIRES_SEPARATE_AUTHORIZATION"
    assert data["validation"]["latest_receipt_exact_lineage_requires_corpus_subject_digest"] is True
    assert data["validation"]["latest_receipt_row_count_match_is_not_exact_lineage"] is True
    assert data["validation"]["receipt_predecessor_chain"] == "FAIL_CLOSED_IF_UNRESOLVED"
    assert data["validation"]["workflow_external_actions"] == "IMMUTABLE_COMMIT_SHA_ONLY"
    assert "APPLY_HISTORICAL_CANON_OVERLAYS" in data["canonical_retrieval_rule"]

    assert CONTRACT.is_file()
    assert RESULT_SCHEMA.is_file()
    schema = json.loads(RESULT_SCHEMA.read_text(encoding="utf-8"))
    assert schema["$id"] == "VERA_DEEP_MEMORY_EVIDENCE_RESULT_V1"
    assert "authorized_privacy_scopes" in schema["required"]
    assert "retrieved_at" in schema["required"]
    result_item_schema = schema["properties"]["results"]["items"]
    schema_required = set(result_item_schema["required"])
    binding_required = set(retrieval["required_result_fields"])
    assert binding_required <= schema_required, sorted(binding_required - schema_required)
    assert "stored_historical_canonicity" in schema_required
    for chronology_field in ("recorded_at", "recorded_at_status", "chronology_semantics"):
        assert chronology_field in schema_required
    invalid_probe = {field: None for field in schema_required if field != "provenance_ceiling"}
    assert schema_required.difference(invalid_probe) == {"provenance_ceiling"}
    result_properties = result_item_schema["properties"]
    assert result_properties["result_semantics"]["const"] == "HISTORICAL_EVIDENCE_ONLY_NOT_CURRENT_MEMORY_OR_AUTHORITY"
    assert result_properties["overlay_privacy_semantics"]["const"].startswith("OVERLAY_INHERITS_TARGET_PRIVACY")
    assert "stored_historical_canonicity" in result_properties
    assert "historical_canon_overlays" in result_properties
    for overlay_name in ("historical_canon_overlays", "amendments", "classification_corrections"):
        overlay_required = set(result_properties[overlay_name]["items"]["required"])
        assert {"recorded_at", "recorded_at_status", "effective_from", "effective_from_status", "chronology_semantics"} <= overlay_required

    action_pins = data["validation"]["external_action_pins"]
    workflow_text = WORKFLOW.read_text(encoding="utf-8")
    for action, sha in action_pins.items():
        assert re.fullmatch(r"[0-9a-f]{40}", sha), (action, sha)
        assert f"uses: {action}@{sha}" in workflow_text, action
    assert re.search(r"uses:\s+actions/[^@\s]+@v\d+", workflow_text) is None

    unknown_time = _chronology_decorated_record({"correction_id": "HOSTILE-UNKNOWN"})
    assert unknown_time["recorded_at"] is None
    assert unknown_time["recorded_at_status"] == "UNKNOWN_NOT_RECORDED_IN_SOURCE_ROW"
    assert unknown_time["effective_from"] is None
    assert unknown_time["effective_from_status"] == "UNKNOWN_NOT_RECORDED_IN_SOURCE_ROW"
    late_correction = _chronology_decorated_record({
        "event_time": "2024-01-01",
        "recorded_at": "2026-09-18T18:00:00Z",
        "effective_from": "2024-01-01",
    })
    assert late_correction["event_time"] == "2024-01-01"
    assert late_correction["recorded_at"] == "2026-09-18T18:00:00Z"
    assert late_correction["effective_from"] == "2024-01-01"
    assert late_correction["recorded_at_status"] == "SOURCE_RECORDED"
    assert late_correction["effective_from_status"] == "SOURCE_RECORDED"

    exact_digest = "a" * 64
    assert receipt_union_match_status(
        {"aggregate_archival_rows_after_pass": 3}, row_count=3, union_digest=exact_digest
    ) == "ROW_COUNT_MATCH"
    assert receipt_union_match_status(
        {"aggregate_archival_rows_after_pass": 3, "aggregate_union_subject_digest_sha256": "b" * 64},
        row_count=3,
        union_digest=exact_digest,
    ) == "CORPUS_SUBJECT_MISMATCH"

    original_updates = catalog_module.UPDATES
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            catalog_module.UPDATES = Path(tmpdir)
            fake_path = Path(tmpdir) / "INGEST_PASS_999.json"
            status, _ = catalog_module.receipt_chain_status(
                fake_path, {"pass_id": "INGEST_PASS_999", "continues": "INGEST_PASS_998"}
            )
            assert status == "PREDECESSOR_MISSING"
    finally:
        catalog_module.UPDATES = original_updates

    text = CONTRACT.read_text(encoding="utf-8").casefold()
    for phrase in (
        "historical evidence plane",
        "current governed memory plane",
        "evidence_search",
        "never silently writes into that plane",
        "canonical_history",
        "pass 010 classified 79 preexisting bounded rows",
        "overlay privacy is also fail-closed",
    ):
        assert phrase.casefold() in text, phrase

    union = load_union()
    assert not union["errors"], union["errors"]
    assert union["historical_canon_overlay_assignment_count"] >= 79
    assert union["effective_memory_by_id"]["AUTO-EARLY-001"]["historical_canonicity"] == "CANONICAL_HISTORY"
    assert re.fullmatch(r"[0-9a-f]{64}", union["union_subject_digest_sha256"])
    assert union["receipt_chain_status"] == "CHAIN_RESOLVES"
    assert union["receipt_union_match_status"] == "ROW_COUNT_MATCH"

    print("deep memory architecture binding: valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
