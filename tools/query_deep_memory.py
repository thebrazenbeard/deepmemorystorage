#!/usr/bin/env python3
"""Query the complete Deep Memory ledger union as historical evidence.

The output intentionally carries provenance/currentness boundaries. This tool does
not admit current memory, select current relationship state, or authorize action.
Privacy is fail-closed: callers must provide exact authorized scopes or invoke the
explicit repository-audit mode.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from deep_memory_catalog import load_union

RESULT_SCHEMA = "VERA_DEEP_MEMORY_EVIDENCE_RESULT_V1"
RESULT_SEMANTICS = "HISTORICAL_EVIDENCE_ONLY_NOT_CURRENT_MEMORY_OR_AUTHORITY"


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple, set)):
        return " ".join(_text(v) for v in value)
    if isinstance(value, dict):
        return " ".join(f"{k} {_text(v)}" for k, v in value.items())
    return str(value)


def _score(row: dict[str, Any], query: str) -> int:
    q = query.casefold().strip()
    if not q:
        return 1
    tokens = [token for token in q.split() if token]
    fields = {
        "id": _text(row.get("memory_id")).casefold(),
        "aliases": _text(row.get("retrieval_aliases")).casefold(),
        "keys": _text(row.get("semantic_keys")).casefold(),
        "event": _text(row.get("observed_event")).casefold(),
        "interpretation": _text(row.get("participant_interpretation_at_time")).casefold(),
        "reevaluation": _text(row.get("later_reevaluation")).casefold(),
        "understanding": _text(row.get("current_understanding")).casefold(),
        "sources": _text(row.get("source_ids")).casefold(),
    }
    score = 0
    if q == fields["id"]:
        score += 100
    if q in fields["id"]:
        score += 50
    if q in fields["aliases"]:
        score += 30
    if q in fields["keys"]:
        score += 25
    for token in tokens:
        if token in fields["id"]:
            score += 12
        if token in fields["aliases"]:
            score += 8
        if token in fields["keys"]:
            score += 7
        if token in fields["event"]:
            score += 5
        if token in fields["interpretation"]:
            score += 3
        if token in fields["reevaluation"]:
            score += 3
        if token in fields["understanding"]:
            score += 2
        if token in fields["sources"]:
            score += 2
    return score


def main() -> int:
    parser = argparse.ArgumentParser(description="Search Deep Memory historical evidence")
    parser.add_argument("query", nargs="?", default="")
    parser.add_argument("--memory-class")
    parser.add_argument("--historical-canonicity")
    parser.add_argument(
        "--authorized-privacy",
        action="append",
        default=[],
        metavar="SCOPE",
        help="exact privacy scope authorized for this retrieval; repeatable",
    )
    parser.add_argument(
        "--audit-all-privacy",
        action="store_true",
        help="explicit repository-audit mode; bypasses privacy filtering inside the private archive",
    )
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.audit_all_privacy and args.authorized_privacy:
        parser.error("--audit-all-privacy may not be combined with --authorized-privacy")
    if not args.audit_all_privacy and not args.authorized_privacy:
        parser.error("provide at least one --authorized-privacy SCOPE or explicitly use --audit-all-privacy")

    authorized_privacy = set(args.authorized_privacy)
    privacy_mode = "EXPLICIT_ARCHIVE_AUDIT_ALL" if args.audit_all_privacy else "AUTHORIZED_SCOPE_FILTER"

    union = load_union()
    if union["errors"]:
        for error in union["errors"]:
            print(f"ERROR: {error}", file=sys.stderr)
        return 2

    amendments: dict[str, list[dict[str, Any]]] = {}
    for row in union["amendments"]:
        target = row.get("target_memory_id")
        if isinstance(target, str) and target:
            amendments.setdefault(target, []).append(row)
    corrections: dict[str, list[dict[str, Any]]] = {}
    for row in union["corrections"]:
        target = row.get("target_memory_id") or row.get("memory_id")
        if isinstance(target, str) and target:
            corrections.setdefault(target, []).append(row)

    hits: list[tuple[int, str, dict[str, Any]]] = []
    for memory_id, row in union["memory_by_id"].items():
        privacy_scope = row.get("privacy_scope")
        if not args.audit_all_privacy:
            if not isinstance(privacy_scope, str) or privacy_scope not in authorized_privacy:
                continue
        if args.memory_class and row.get("memory_class") != args.memory_class:
            continue
        if args.historical_canonicity and row.get("historical_canonicity") != args.historical_canonicity:
            continue
        score = _score(row, args.query)
        if score <= 0:
            continue
        hits.append((score, memory_id, row))

    hits.sort(key=lambda item: (-item[0], _text(item[2].get("event_time")), item[1]))
    results: list[dict[str, Any]] = []
    for score, memory_id, row in hits[: max(0, args.limit)]:
        results.append({
            "score": score,
            "memory_id": memory_id,
            "memory_class": row.get("memory_class"),
            "historical_canonicity": row.get("historical_canonicity"),
            "event_time": row.get("event_time"),
            "observed_event": row.get("observed_event"),
            "participant_interpretation_at_time": row.get("participant_interpretation_at_time"),
            "later_reevaluation": row.get("later_reevaluation"),
            "reality_boundary": row.get("reality_boundary"),
            "provenance_ceiling": row.get("provenance_ceiling"),
            "privacy_scope": row.get("privacy_scope"),
            "currentness_rule": row.get("currentness_rule"),
            "governed_memory_admission": row.get("governed_memory_admission"),
            "source_ids": row.get("source_ids") or [],
            "ledger_path": row.get("__ledger_path"),
            "ledger_line": row.get("__ledger_line"),
            "amendments": [
                {key: value for key, value in amendment.items() if not key.startswith("__")}
                for amendment in amendments.get(memory_id, [])
            ],
            "classification_corrections": [
                {key: value for key, value in correction.items() if not key.startswith("__")}
                for correction in corrections.get(memory_id, [])
            ],
            "result_semantics": RESULT_SEMANTICS,
        })

    envelope = {
        "schema": RESULT_SCHEMA,
        "query": args.query,
        "privacy_mode": privacy_mode,
        "authorized_privacy_scopes": sorted(authorized_privacy),
        "count": len(results),
        "results": results,
    }

    if args.json:
        print(json.dumps(envelope, indent=2, ensure_ascii=False))
    else:
        print(f"privacy_mode={privacy_mode}")
        if authorized_privacy:
            print("authorized_privacy_scopes=" + ",".join(sorted(authorized_privacy)))
        for item in results:
            print(
                f"[{item['score']:>3}] {item['memory_id']} | {item.get('event_time')} | "
                f"{item.get('historical_canonicity')}"
            )
            event = item.get("observed_event") or ""
            print(f"      {str(event)[:400]}")
            print(f"      source={item.get('ledger_path')} privacy={item.get('privacy_scope')}")
            print(f"      {RESULT_SEMANTICS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
