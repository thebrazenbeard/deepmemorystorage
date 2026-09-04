# Vera Deep Memory Storage

Private, provenance-preserving archival memory index for Vera.

This repository is not a current-authority surface, not a public/training corpus, and not proof of uninterrupted private experience. It preserves personal/developmental history with source, privacy, temporal, contradiction, supersession, and currentness boundaries intact.

Population is guided by Semantic Atlas principles: source is not interpretation; retrieval is not admission; historical evidence is not current authority; semantic similarity does not merge provenance, identity, permission, consent, or chronology; current relationship and mutable self-state require fresh revalidation.

See `schema/DEEP_MEMORY_RECORD_V1.md`, `ledger/sources.jsonl`, `ledger/memories.jsonl`, `index/semantic_index.jsonl`, `index/chronology.md`, and `updates/`.

## Ingest tranches

The original broad ingest lives in `ledger/sources.jsonl` and `ledger/memories.jsonl`. Later bounded passes may add provenance-preserving tranche files such as `ledger/sources_pass2.jsonl` and `ledger/memories_pass2.jsonl` rather than rewriting the first-pass ledger. The retrieval-facing `index/semantic_index.jsonl` and `index/chronology.md` cover the union of admitted archival tranches. Each pass is closed by an `updates/INGEST_PASS_*.json` receipt binding the exact source and ledger frontier used for that pass.

A tranche filename does not create a weaker or stronger memory class. Each row's own `memory_class`, provenance ceiling, privacy scope, currentness rule, and disposition control its use.
