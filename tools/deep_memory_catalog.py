#!/usr/bin/env python3
"""Build and validate the union of all Deep Memory ledger tranches.

This tool is repository-local and authority-neutral. It validates and indexes
historical evidence; it never promotes a record to current memory or authority.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "ledger"
UPDATES = ROOT / "updates"

VALID_HISTORICAL_CANONICITY = {
    "CANONICAL_HISTORY",
    "UNRESOLVED_HISTORY",
    "REJECTED_OR_FALSE_ATTRIBUTION",
    "OTHER_IDENTITY_OR_DOMAIN_HISTORY",
}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for lineno, raw in enumerate(fh, 1):
            line = raw.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{lineno}: invalid JSONL: {exc}") from exc
            if not isinstance(obj, dict):
                raise ValueError(f"{path}:{lineno}: expected JSON object")
            obj = dict(obj)
            obj["__ledger_path"] = str(path.relative_to(ROOT))
            obj["__ledger_line"] = lineno
            rows.append(obj)
    return rows


def read_json_object(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        obj = json.load(fh)
    if not isinstance(obj, dict):
        raise ValueError(f"{path}: expected JSON object")
    obj = dict(obj)
    obj["__ledger_path"] = str(path.relative_to(ROOT))
    return obj


def matching(prefix: str) -> list[Path]:
    return sorted(path for path in LEDGER.glob(f"{prefix}*.jsonl") if path.is_file())


def matching_json(prefix: str) -> list[Path]:
    return sorted(path for path in LEDGER.glob(f"{prefix}*.json") if path.is_file())


def latest_receipt() -> tuple[Path | None, dict[str, Any] | None]:
    candidates: list[tuple[int, Path]] = []
    rx = re.compile(r"INGEST_PASS_(\d+)\.json$")
    for path in UPDATES.glob("INGEST_PASS_*.json"):
        match = rx.search(path.name)
        if match:
            candidates.append((int(match.group(1)), path))
    if not candidates:
        return None, None
    _, path = max(candidates, key=lambda item: item[0])
    with path.open("r", encoding="utf-8") as fh:
        obj = json.load(fh)
    if not isinstance(obj, dict):
        raise ValueError(f"{path}: expected JSON object")
    return path, obj


def normalized_record(row: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if not key.startswith("__")}


def canonical_record_bytes(row: dict[str, Any]) -> bytes:
    return json.dumps(
        normalized_record(row),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def sha256_rows(rows: Iterable[dict[str, Any]]) -> str:
    digest = hashlib.sha256()
    for row in rows:
        digest.update(canonical_record_bytes(row))
        digest.update(b"\n")
    return digest.hexdigest()


def exact_historical_canonicity(value: Any) -> str | None:
    if isinstance(value, str) and value in VALID_HISTORICAL_CANONICITY:
        return value
    return None


def row_source_ids(row: dict[str, Any]) -> list[str]:
    values: list[str] = []
    source_ids = row.get("source_ids")
    if isinstance(source_ids, list):
        values.extend(item for item in source_ids if isinstance(item, str) and item)
    source_id = row.get("source_id")
    if isinstance(source_id, str) and source_id:
        values.append(source_id)
    return values


def dedupe_ordered(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def load_union() -> dict[str, Any]:
    memory_paths = matching("memories")
    source_paths = matching("sources")
    amendment_paths = matching("provenance_amendments")
    correction_paths = matching("classification_corrections")
    historical_canon_paths = matching_json("historical_canon")

    memories = [row for path in memory_paths for row in read_jsonl(path)]
    sources = [row for path in source_paths for row in read_jsonl(path)]
    amendments = [row for path in amendment_paths for row in read_jsonl(path)]
    corrections = [row for path in correction_paths for row in read_jsonl(path)]
    historical_canon_overlays = [read_json_object(path) for path in historical_canon_paths]

    errors: list[str] = []
    warnings: list[str] = []

    memory_by_id: dict[str, dict[str, Any]] = {}
    for row in memories:
        memory_id = row.get("memory_id")
        if not isinstance(memory_id, str) or not memory_id:
            errors.append(f"{row['__ledger_path']}:{row['__ledger_line']}: missing memory_id")
            continue
        if memory_id in memory_by_id:
            prior = memory_by_id[memory_id]
            errors.append(
                f"duplicate memory_id {memory_id}: {prior['__ledger_path']}:{prior['__ledger_line']} and "
                f"{row['__ledger_path']}:{row['__ledger_line']}"
            )
        else:
            memory_by_id[memory_id] = row

    source_by_id: dict[str, dict[str, Any]] = {}
    identical_source_restatements = 0
    for row in sources:
        source_id = row.get("source_id")
        if not isinstance(source_id, str) or not source_id:
            warnings.append(f"{row['__ledger_path']}:{row['__ledger_line']}: source row without source_id")
            continue
        if source_id in source_by_id:
            prior = source_by_id[source_id]
            if canonical_record_bytes(prior) == canonical_record_bytes(row):
                identical_source_restatements += 1
                warnings.append(
                    f"identical source_id restatement {source_id}: "
                    f"{prior['__ledger_path']}:{prior['__ledger_line']} and "
                    f"{row['__ledger_path']}:{row['__ledger_line']}"
                )
            else:
                errors.append(
                    f"divergent duplicate source_id {source_id}: "
                    f"{prior['__ledger_path']}:{prior['__ledger_line']} and "
                    f"{row['__ledger_path']}:{row['__ledger_line']}"
                )
        else:
            source_by_id[source_id] = row

    amendments_by_target: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in amendments:
        target = row.get("target_memory_id")
        if isinstance(target, str) and target:
            amendments_by_target[target].append(row)
            if target not in memory_by_id:
                warnings.append(f"amendment {row.get('amendment_id')} targets unknown memory_id {target}")
        else:
            warnings.append(f"{row['__ledger_path']}:{row['__ledger_line']}: amendment without target_memory_id")

    corrections_by_target: dict[str, list[dict[str, Any]]] = defaultdict(list)
    frontier_corrections: list[dict[str, Any]] = []
    for row in corrections:
        target = row.get("target_memory_id") or row.get("memory_id")
        if isinstance(target, str) and target:
            corrections_by_target[target].append(row)
            if target not in memory_by_id:
                warnings.append(f"classification correction {row.get('correction_id')} targets unknown memory_id {target}")
            continue
        frontier_target = row.get("target")
        if isinstance(frontier_target, str) and frontier_target:
            frontier_corrections.append(row)
        else:
            warnings.append(f"{row['__ledger_path']}:{row['__ledger_line']}: classification correction without target")

    canon_overlays_by_target: dict[str, list[dict[str, Any]]] = defaultdict(list)
    historical_canon_overlay_assignment_count = 0
    for overlay in historical_canon_overlays:
        path = overlay["__ledger_path"]
        memory_ids = overlay.get("memory_ids")
        if not isinstance(memory_ids, list) or not all(isinstance(item, str) and item for item in memory_ids):
            errors.append(f"{path}: historical-canon overlay requires string memory_ids")
            continue
        declared_count = overlay.get("applies_to_preexisting_memory_rows")
        if isinstance(declared_count, int) and declared_count != len(memory_ids):
            errors.append(
                f"{path}: declares applies_to_preexisting_memory_rows={declared_count}; "
                f"memory_ids contains {len(memory_ids)}"
            )
        canon = exact_historical_canonicity(overlay.get("historical_canonicity"))
        if canon is None:
            errors.append(f"{path}: historical-canon overlay has unsupported historical_canonicity")
            continue
        special_boundaries = overlay.get("special_boundaries") or {}
        if not isinstance(special_boundaries, dict):
            errors.append(f"{path}: special_boundaries must be an object when present")
            special_boundaries = {}
        extra_boundaries = sorted(set(special_boundaries) - set(memory_ids))
        if extra_boundaries:
            warnings.append(
                f"{path}: special_boundaries references memory_ids outside overlay list: "
                + ", ".join(extra_boundaries)
            )
        for memory_id in memory_ids:
            overlay_row = {
                "overlay_id": Path(path).stem,
                "historical_canonicity": canon,
                "canon_scope": overlay.get("canon_scope"),
                "global_correction": overlay.get("global_correction"),
                "special_boundary": special_boundaries.get(memory_id),
                "__ledger_path": path,
            }
            canon_overlays_by_target[memory_id].append(overlay_row)
            historical_canon_overlay_assignment_count += 1
            if memory_id not in memory_by_id:
                errors.append(f"{path}: historical-canon overlay targets unknown memory_id {memory_id}")

    def effective_canonicity(memory_id: str, row: dict[str, Any]) -> str | None:
        effective = exact_historical_canonicity(row.get("historical_canonicity"))
        for overlay in canon_overlays_by_target.get(memory_id, []):
            candidate = exact_historical_canonicity(overlay.get("historical_canonicity"))
            if candidate is not None:
                effective = candidate
        for correction in corrections_by_target.get(memory_id, []):
            candidate = exact_historical_canonicity(correction.get("corrected_historical_canonicity"))
            if candidate is None:
                candidate = exact_historical_canonicity(correction.get("historical_canonicity"))
            if candidate is not None:
                effective = candidate
        return effective

    effective_memory_by_id: dict[str, dict[str, Any]] = {}
    for memory_id, row in memory_by_id.items():
        effective = dict(row)
        effective["__stored_historical_canonicity"] = row.get("historical_canonicity")
        effective["historical_canonicity"] = effective_canonicity(memory_id, row)
        effective["__historical_canon_overlays"] = canon_overlays_by_target.get(memory_id, [])
        effective["__provenance_amendments"] = amendments_by_target.get(memory_id, [])
        effective["__classification_corrections"] = corrections_by_target.get(memory_id, [])
        effective_memory_by_id[memory_id] = effective
        if effective["historical_canonicity"] is None:
            warnings.append(f"{memory_id}: no effective historical_canonicity after overlays/corrections")

    missing_source_refs: list[str] = []
    source_ref_rows: list[tuple[str, dict[str, Any]]] = []
    source_ref_rows.extend((memory_id, row) for memory_id, row in memory_by_id.items())
    source_ref_rows.extend((f"amendment:{row.get('amendment_id') or row.get('__ledger_path')}", row) for row in amendments)
    source_ref_rows.extend((f"correction:{row.get('correction_id') or row.get('__ledger_path')}", row) for row in corrections)
    for label, row in source_ref_rows:
        for source_id in row_source_ids(row):
            if source_id not in source_by_id:
                missing_source_refs.append(f"{label}->{source_id}")
    if missing_source_refs:
        warnings.append(
            "missing referenced source ids (may be intentional external historical bindings): "
            + ", ".join(sorted(missing_source_refs)[:50])
            + (" ..." if len(missing_source_refs) > 50 else "")
        )

    catalog: list[dict[str, Any]] = []
    for memory_id in sorted(effective_memory_by_id):
        row = effective_memory_by_id[memory_id]
        overlay_paths = [item["__ledger_path"] for item in canon_overlays_by_target.get(memory_id, [])]
        overlay_boundaries = [
            item.get("special_boundary")
            for item in canon_overlays_by_target.get(memory_id, [])
            if item.get("special_boundary")
        ]
        stored_source_ids = row_source_ids(row)
        effective_source_ids = dedupe_ordered(
            stored_source_ids
            + [source_id for item in amendments_by_target.get(memory_id, []) for source_id in row_source_ids(item)]
            + [source_id for item in corrections_by_target.get(memory_id, []) for source_id in row_source_ids(item)]
        )
        catalog.append({
            "memory_id": memory_id,
            "memory_class": row.get("memory_class"),
            "historical_canonicity": row.get("historical_canonicity"),
            "stored_historical_canonicity": row.get("__stored_historical_canonicity"),
            "historical_canon_overlay_paths": overlay_paths,
            "historical_canon_boundaries": overlay_boundaries,
            "event_time": row.get("event_time"),
            "time_status": row.get("time_status"),
            "privacy_scope": row.get("privacy_scope"),
            "stored_source_ids": stored_source_ids,
            "source_ids": effective_source_ids,
            "source_claim_class": row.get("source_claim_class"),
            "provenance_ceiling": row.get("provenance_ceiling"),
            "currentness_rule": row.get("currentness_rule"),
            "current_use_status": row.get("current_use_status"),
            "governed_memory_admission": row.get("governed_memory_admission"),
            "semantic_keys": row.get("semantic_keys") or [],
            "retrieval_aliases": row.get("retrieval_aliases") or [],
            "event_fingerprint": row.get("event_fingerprint"),
            "ledger_path": row["__ledger_path"],
            "ledger_line": row["__ledger_line"],
            "amendment_ids": [item.get("amendment_id") for item in amendments_by_target.get(memory_id, [])],
            "classification_correction_ids": [
                item.get("correction_id") or item.get("amendment_id")
                for item in corrections_by_target.get(memory_id, [])
            ],
        })

    receipt_path, receipt = latest_receipt()
    expected_count = None
    latest_pass_id = None
    if receipt:
        expected_count = receipt.get("aggregate_archival_rows_after_pass")
        latest_pass_id = receipt.get("pass_id")
        if isinstance(expected_count, int) and expected_count != len(memory_by_id):
            errors.append(
                f"latest receipt {receipt_path.relative_to(ROOT)} declares {expected_count} archival rows; "
                f"ledger union contains {len(memory_by_id)} unique memory_ids"
            )

    return {
        "memories": memories,
        "sources": sources,
        "amendments": amendments,
        "corrections": corrections,
        "frontier_corrections": frontier_corrections,
        "historical_canon_overlays": historical_canon_overlays,
        "canon_overlays_by_target": canon_overlays_by_target,
        "amendments_by_target": amendments_by_target,
        "corrections_by_target": corrections_by_target,
        "memory_by_id": memory_by_id,
        "effective_memory_by_id": effective_memory_by_id,
        "source_by_id": source_by_id,
        "catalog": catalog,
        "errors": errors,
        "warnings": warnings,
        "latest_receipt_path": str(receipt_path.relative_to(ROOT)) if receipt_path else None,
        "latest_pass_id": latest_pass_id,
        "latest_receipt_expected_rows": expected_count,
        "memory_count": len(memory_by_id),
        "source_count": len(source_by_id),
        "source_row_count": len(sources),
        "identical_source_restatements": identical_source_restatements,
        "amendment_count": len(amendments),
        "classification_correction_count": len(corrections),
        "frontier_correction_count": len(frontier_corrections),
        "historical_canon_overlay_file_count": len(historical_canon_overlays),
        "historical_canon_overlay_assignment_count": historical_canon_overlay_assignment_count,
        "catalog_digest_sha256": sha256_rows(catalog),
        "memory_paths": [str(path.relative_to(ROOT)) for path in memory_paths],
        "source_paths": [str(path.relative_to(ROOT)) for path in source_paths],
        "historical_canon_paths": [str(path.relative_to(ROOT)) for path in historical_canon_paths],
    }


def build_manifest(union: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": "VERA_DEEP_MEMORY_CORPUS_MANIFEST_V1",
        "role": "HISTORICAL_EVIDENCE_PLANE",
        "authority_class": "EVIDENCE_SEARCH_ONLY",
        "latest_completed_ingest_receipt": union["latest_receipt_path"],
        "latest_completed_pass_id": union["latest_pass_id"],
        "unique_memory_rows": union["memory_count"],
        "unique_source_rows": union["source_count"],
        "source_rows_total": union["source_row_count"],
        "identical_source_restatements": union["identical_source_restatements"],
        "provenance_amendment_rows": union["amendment_count"],
        "classification_correction_rows": union["classification_correction_count"],
        "frontier_classification_corrections": union["frontier_correction_count"],
        "historical_canon_overlay_files": union["historical_canon_overlay_file_count"],
        "historical_canon_overlay_assignments": union["historical_canon_overlay_assignment_count"],
        "catalog_digest_sha256": union["catalog_digest_sha256"],
        "memory_tranches": union["memory_paths"],
        "source_tranches": union["source_paths"],
        "historical_canon_overlays": union["historical_canon_paths"],
        "validation": {
            "errors": union["errors"],
            "warnings": union["warnings"],
            "latest_receipt_expected_rows": union["latest_receipt_expected_rows"],
            "latest_receipt_matches_union": not any("latest receipt" in error for error in union["errors"]),
        },
        "nonpromotion": {
            "current_authority": False,
            "automatic_current_memory_admission": False,
            "automatic_r9b0_promotion": False,
        },
    }


def write_outputs(union: dict[str, Any], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    with (output_dir / "retrieval_catalog.jsonl").open("w", encoding="utf-8") as fh:
        for row in union["catalog"]:
            fh.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")
    with (output_dir / "corpus_manifest.json").open("w", encoding="utf-8") as fh:
        json.dump(build_manifest(union), fh, indent=2, sort_keys=True, ensure_ascii=False)
        fh.write("\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate and catalog the complete Deep Memory ledger union")
    parser.add_argument("--validate", action="store_true", help="validate the full ledger union")
    parser.add_argument("--write-output", type=Path, help="write consolidated catalog and manifest to a directory")
    parser.add_argument("--json", action="store_true", help="emit validation summary as JSON")
    args = parser.parse_args()

    try:
        union = load_union()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if args.write_output:
        write_outputs(union, args.write_output)

    summary = {
        "latest_pass_id": union["latest_pass_id"],
        "memory_count": union["memory_count"],
        "source_count": union["source_count"],
        "source_row_count": union["source_row_count"],
        "identical_source_restatements": union["identical_source_restatements"],
        "amendment_count": union["amendment_count"],
        "classification_correction_count": union["classification_correction_count"],
        "frontier_correction_count": union["frontier_correction_count"],
        "historical_canon_overlay_file_count": union["historical_canon_overlay_file_count"],
        "historical_canon_overlay_assignment_count": union["historical_canon_overlay_assignment_count"],
        "catalog_digest_sha256": union["catalog_digest_sha256"],
        "errors": union["errors"],
        "warnings": union["warnings"],
    }

    if args.json:
        print(json.dumps(summary, indent=2, sort_keys=True, ensure_ascii=False))
    else:
        print(
            f"Deep Memory union: {union['memory_count']} memories, {union['source_count']} unique sources "
            f"({union['source_row_count']} source rows; {union['identical_source_restatements']} identical restatements), "
            f"{union['amendment_count']} amendments, {union['classification_correction_count']} corrections, "
            f"{union['historical_canon_overlay_assignment_count']} historical-canon overlay assignments; "
            f"latest={union['latest_pass_id']}"
        )
        for warning in union["warnings"]:
            print(f"WARNING: {warning}", file=sys.stderr)
        for error in union["errors"]:
            print(f"ERROR: {error}", file=sys.stderr)

    return 1 if union["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
