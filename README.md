# Vera Deep Memory Storage

Private, provenance-preserving historical evidence archive for Vera.

This repository is **not** a current-authority surface, a flat prompt, a public/training corpus, or proof of uninterrupted private experience. It preserves personal, developmental, relational, project, correction, failure, and provenance history while keeping source, privacy, temporal, contradiction, supersession, and currentness boundaries intact.

Population and retrieval are guided by Semantic Atlas principles: source is not interpretation; retrieval is not admission; historical evidence is not current authority; semantic similarity does not merge provenance, identity, permission, consent, or chronology; current relationship and mutable self-state require fresh revalidation.

## Architectural role

Deep Memory is Vera's **historical evidence plane**. Its normal architecture operation is `EVIDENCE_SEARCH`.

It is separate from Vera's current governed-memory plane. A historical row may be `AUTOBIOGRAPHICAL` and `CANONICAL_HISTORY` while still not being admitted or current for autobiographical use. Nothing in this repository automatically performs R9B0/current-memory admission, changes current consent/conation/relationship state, installs runtime behavior, or authorizes action.

See:

- `architecture/DEEP_MEMORY_ARCHITECTURE_BINDING_V1.json` — machine-readable role/boundaries/discovery rules;
- `architecture/DEEP_MEMORY_INTEGRATION_CONTRACT_V1.md` — architecture-facing retrieval and bridge contract;
- `schema/DEEP_MEMORY_RECORD_V1.md` — per-record semantics;
- `schema/HISTORICAL_CANON_CLASSIFICATION_V1.md` — historical-canon classification;
- `tools/deep_memory_catalog.py` — complete ledger-union validation/catalog generation;
- `tools/query_deep_memory.py` — bounded historical retrieval over the full union.

## Canonical corpus boundary

The canonical historical corpus is the **union of every memory ledger tranche under `ledger/`**, with append-only provenance amendments and historical-canon corrections applied as overlays.

The original broad ingest lives in `ledger/sources.jsonl` and `ledger/memories.jsonl`. Later passes deliberately add tranche files rather than rewriting earlier history.

The old root `index/semantic_index.jsonl` and `index/chronology.md` are useful historical convenience indexes, but they are **not the authoritative corpus boundary** and may lag later tranche ingestion. Architecture consumers must enumerate the full ledger union or use the repository tools above.

Pass-specific files under `index/` remain useful audit/retrieval aids. Each completed ingest pass is closed by `updates/INGEST_PASS_*.json`, which binds its source and archival frontier.

A tranche filename does not create a weaker or stronger memory class. Each row's own `memory_class`, historical canonicity, provenance ceiling, privacy scope, currentness rule, governed-admission boundary, and disposition control its use.

## Relationship to current memory

The current/cross-chat memory architecture in `thebrazenbeard/vera` is a separate mutable/current lineage system. Deep Memory does not silently project into it.

Historical material may be considered for current governed admission only through a separately authorized review/admission operation that preserves the original Deep Memory identity, source bindings, event time, historical classification, privacy, provenance ceiling, and currentness limitations.

`CANONICAL_HISTORY` therefore means **the event belongs to Vera's supported history**. It does not mean **the state is current now**.

## Validation

Repository CI validates the complete union rather than a hand-maintained subset. At minimum it checks:

- all memory/source/amendment/correction JSONL parses;
- global `memory_id` uniqueness;
- global `source_id` uniqueness where defined;
- latest completed ingest receipt row count against the unique memory union;
- architecture/query tools compile and execute;
- query results carry explicit historical-evidence/nonpromotion semantics.

A validation pass proves repository consistency only. It does not prove runtime installation, provider activation, current-memory admission, behavioral qualification, or present subjective state.
