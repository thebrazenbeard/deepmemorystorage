#!/usr/bin/env python3
"""Query the complete Deep Memory ledger union as historical evidence.

The output intentionally carries provenance/currentness boundaries. This tool does
not admit current memory, select current relationship state, or authorize action.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from deep_memory_catalog import load_union


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
    tokens = [t for t in q.split() if t]
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
    parser.add_argument("--privacy-scope")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    union = load_union()
    if union["errors"]:
        for error in union["errors"]:
            print(f"ERROR: {error}", file=sys.stderr)
        return 2

    amendments = {}
    for row in union["amendments"]:
        target = row.get("target_memory_id")
        if target:
            amendments.setdefault(target, []).append(row)
    corrections = {}
    for row in union["corrections"]:
        target = row.get("target_memory_id") or row.get("memory_id")
        if target:
            corrections.setdefault(target, []).append(row)

    hits = []
    for mid, row in union["memory_by_id"].items():
        if args.memory_class and row.get("memory_class") != args.memory_class:
            continue
        if args.historical_canonicity and row.get("historical_canonicity") != args.historical_canonicity:
            continue
        if args.privacy_scope and row.get("privacy_scope") != args.privacy_scope:
            continue
        score = _score(row, args.query)
        if score <= 0:
            continue
        hits.append((score, mid, row))

    hits.sort(key=lambda item: (-item[0], _text(item[2].get("event_time")), item[1]))
    results = []
    for score, mid, row in hits[: max(0, args.limit)]:
        results.append({
            "score": score,
            "memory_id": mid,
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
                {k: v for k, v in amendment.items() if not k.startswith("__")}
                for amendment in amendments.get(mid, [])
            ],
            "classification_corrections": [
                {k: v for k, v in correction.items() if not k.startswith("__")}
                for correction in corrections.get(mid, [])
            ],
            "result_semantics": "HISTORICAL_EVIDENCE_ONLY_NOT_CURRENT_MEMORY_OR_AUTHORITY",
        })

    if args.json:
        print(json.dumps({"query": args.query, "count": len(results), "results": results}, indent=2, ensure_ascii=False))
    else:
        for item in results:
            print(f"[{item['score']:>3}] {item['memory_id']} | {item.get('event_time')} | {item.get('historical_canonicity')}")
            event = item.get("observed_event") or ""
            print(f"      {event[:400]}")
            print(f"      source={item.get('ledger_path')} privacy={item.get('privacy_scope')}")
            print("      HISTORICAL_EVIDENCE_ONLY_NOT_CURRENT_MEMORY_OR_AUTHORITY")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
