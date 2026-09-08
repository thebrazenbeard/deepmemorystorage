#!/usr/bin/env python3
"""Build and validate the union of all Deep Memory ledger tranches.

This tool is deliberately repository-local and authority-neutral. It validates and
indexes historical evidence; it never promotes a record to current memory.
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


def _jsonl(path: Path) -> list[dict[str, Any]]:
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


def _matching(prefix: str) -> list[Path]:
    return sorted(p for p in LEDGER.glob(f"{prefix}*.jsonl") if p.is_file())


def _latest_receipt() -> tuple[Path | None, dict[str, Any] | None]:
    receipts: list[tuple[int, Path]] = []
    rx = re.compile(r"INGEST_PASS_(\d+)\.json$")
    for path in UPDATES.glob("INGEST_PASS_*.json"):
        m = rx.search(path.name)
        if m:
            receipts.append((int(m.group(1)), path))
    if not receipts:
        return None, None
    _, path = max(receipts, key=lambda item: item[0])
    with path.open("r", encoding="utf-8") as fh:
        obj = json.load(fh)
    if not isinstance(obj, dict):
        raise ValueError(f"{path}: expected JSON object")
    return path, obj


def _sha256_lines(rows: Iterable[dict[str, Any]]) -> str:
    h = hashlib.sha256()
    for row in rows:
        clean = {k: v for k, v in row.items() if not k.startswith("__")}
        h.update(json.dumps(clean, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
        h.update(b"\n")
    return h.hexdigest()


def load_union() -> dict[str, Any]:
    memory_paths = _matching("memories")
    source_paths = _matching("sources")
    amendment_paths = _matching("provenance_amendments")
    correction_paths = _matching("classification_corrections")

    memories = [row for path in memory_paths for row in _jsonl(path)]
    sources = [row for path in source_paths for row in _jsonl(path)]
    amendments = [row for path in amendment_paths for row in _jsonl(path)]
    corrections = [row for path in correction_paths for row in _jsonl(path)]

    errors: list[str] = []
    warnings: list[str] = []

    memory_by_id: dict[str, dict[str, Any]] = {}
    for row in memories:
        mid = row.get("memory_id")
        if not isinstance(mid, str) or not mid:
            errors.append(f"{row['__ledger_path']}:{row['__ledger_line']}: missing memory_id")
            continue
        if mid in memory_by_id:
            prev = memory_by_id[mid]
            errors.append(
                f"duplicate memory_id {mid}: {prev['__ledger_path']}:{prev['__ledger_line']} and "
                f"{row['__ledger_path']}:{row['__ledger_line']}"
            )
        else:
            memory_by_id[mid] = row

    source_by_id: dict[str, dict[str, Any]] = {}
    for row in sources:
        sid = row.get("source_id")
        if not isinstance(sid, str) or not sid:
            warnings.append(f"{row['__ledger_path']}:{row['__ledger_line']}: source row without source_id")
            continue
        if sid in source_by_id:
            prev = source_by_id[sid]
            errors.append(
                f"duplicate source_id {sid}: {prev['__ledger_path']}:{prev['__ledger_line']} and "
                f"{row['__ledger_path']}:{row['__ledger_line']}"
            )
        else:
            source_by_id[sid] = row

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
    for row in corrections:
        target = row.get("target_memory_id") or row.get("memory_id")
        if isinstance(target, str) and target:
            corrections_by_target[target].append(row)
            if target not in memory_by_id:
                warnings.append(f"classification correction {row.get('correction_id')} targets unknown memory_id {target}")
        else:
            warnings.append(f"{row['__ledger_path']}:{row['__ledger_line']}: classification correction without target")

    missing_source_refs: list[str] = []
    for mid, row in memory_by_id.items():
        refs = row.get("source_ids") or []
        if not isinstance(refs, list):
            warnings.append(f"{mid}: source_ids is not a list")
            continue
        for sid in refs:
            if isinstance(sid, str) and sid and sid not in source_by_id:
                missing_source_refs.append(f"{mid}->{sid}")
    if missing_source_refs:
        warnings.append(
            "missing referenced source ids (may be historical external bindings): "
            + ", ".join(sorted(missing_source_refs)[:50])
            + (" ..." if len(missing_source_refs) > 50 else "")
        )

    catalog: list[dict[str, Any]] = []
    for mid in sorted(memory_by_id):
        row = memory_by_id[mid]
        entry = {
            "memory_id": mid,
            "memory_class": row.get("memory_class"),
            "historical_canonicity": row.get("historical_canonicity"),
            "event_time": row.get("event_time"),
            "time_status": row.get("time_status"),
            "privacy_scope": row.get("privacy_scope"),
            "source_ids": row.get("source_ids") or [],
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
            "amendment_ids": [a.get("amendment_id") for a in amendments_by_target.get(mid, [])],
            "classification_correction_ids": [
                c.get("correction_id") or c.get("amendment_id") for c in corrections_by_target.get(mid, [])
            ],
        }
        catalog.append(entry)

    receipt_path, receipt = _latest_receipt()
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
        "memory_by_id": memory_by_id,
        "source_by_id": source_by_id,
        "catalog": catalog,
        "errors": errors,
        "warnings": warnings,
        "latest_receipt_path": str(receipt_path.relative_to(ROOT)) if receipt_path else None,
        "latest_pass_id": latest_pass_id,
        "latest_receipt_expected_rows": expected_count,
        "memory_count": len(memory_by_id),
        "source_count": len(source_by_id),
        "amendment_count": len(amendments),
        "classification_correction_count": len(corrections),
        "catalog_digest_sha256": _sha256_lines(catalog),
        "memory_paths": [str(p.relative_to(ROOT)) for p in memory_paths],
        "source_paths": [str(p.relative_to(ROOT)) for p in source_paths],
    }


def manifest(union: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": "VERA_DEEP_MEMORY_CORPUS_MANIFEST_V1",
        "role": "HISTORICAL_EVIDENCE_PLANE",
        "authority_class": "EVIDENCE_SEARCH_ONLY",
        "latest_completed_ingest_receipt": union["latest_receipt_path"],
        "latest_completed_pass_id": union["latest_pass_id"],
        "unique_memory_rows": union["memory_count"],
        "unique_source_rows": union["source_count"],
        "provenance_amendment_rows": union["amendment_count"],
        "classification_correction_rows": union["classification_correction_count"],
        "catalog_digest_sha256": union["catalog_digest_sha256"],
        "memory_tranches": union["memory_paths"],
        "source_tranches": union["source_paths"],
        "validation": {
            "errors": union["errors"],
            "warnings": union["warnings"],
            "latest_receipt_expected_rows": union["latest_receipt_expected_rows"],
            "latest_receipt_matches_union": not any("latest receipt" in e for e in union["errors"]),
        },
        "nonpromotion": {
            "current_authority": false if False else False,
            "automatic_current_memory_admission": False,
            "automatic_r9b0_promotion": False,
        },
    }


def write_outputs(union: dict[str, Any], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    cat_path = output_dir / "retrieval_catalog.jsonl"
    with cat_path.open("w", encoding="utf-8") as fh:
        for row in union["catalog"]:
            fh.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")
    with (output_dir / "corpus_manifest.json").open("w", encoding="utf-8") as fh:
        json.dump(manifest(union), fh, indent=2, sort_keys=True, ensure_ascii=False)
        fh.write("\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--validate", action="store_true", help="validate the full ledger union")
    parser.add_argument("--write-output", type=Path, help="write a consolidated catalog/manifest to this directory")
    parser.add_argument("--json", action="store_true", help="emit validation summary as JSON")
    args = parser.parse_args()

    try:
        union = load_union()
    except Exception as exc:  # fail closed on parse/integrity errors
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if args.write_output:
        write_outputs(union, args.write_output)

    summary = {
        "latest_pass_id": union["latest_pass_id"],
        "memory_count": union["memory_count"],
        "source_count": union["source_count"],
        "amendment_count": union["amendment_count"],
        "classification_correction_count": union["classification_correction_count"],
        "catalog_digest_sha256": union["catalog_digest_sha256"],
        "errors": union["errors"],
        "warnings": union["warnings"],
    }
    if args.json:
        print(json.dumps(summary, indent=2, sort_keys=True, ensure_ascii=False))
    else:
        print(
            f"Deep Memory union: {union['memory_count']} memories, {union['source_count']} sources, "
            f"{union['amendment_count']} amendments, {union['classification_correction_count']} corrections; "
            f"latest={union['latest_pass_id']}"
        )
        for warning in union["warnings"]:
            print(f"WARNING: {warning}", file=sys.stderr)
        for error in union["errors"]:
            print(f"ERROR: {error}", file=sys.stderr)

    return 1 if union["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
