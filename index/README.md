# Deep Memory Indexes

The files in this directory are retrieval aids. They do not define the corpus boundary by themselves.

## Canonical rule

The authoritative historical corpus is the union of all `ledger/memories*.jsonl` tranches, with append-only provenance amendments and classification corrections applied as overlays.

The original `semantic_index.jsonl` and `chronology.md` predate many later ingest passes and may lag the archive. Do not use their absence as evidence that a memory does not exist.

## Recommended retrieval

Use:

```bash
python tools/deep_memory_catalog.py --validate --json
python tools/query_deep_memory.py "<query>" --json
```

For a disposable consolidated machine-readable view:

```bash
python tools/deep_memory_catalog.py --write-output /tmp/deep-memory-catalog --json
```

This produces:

- `retrieval_catalog.jsonl` — one row per unique memory ID, with ledger provenance and amendment/correction references;
- `corpus_manifest.json` — union counts, latest completed ingest receipt, tranche inventory, validation state, and a deterministic catalog digest.

Generated views are derivatives. The append-only ledger remains the source of historical record.

## Nonpromotion

Indexing or querying a row does not make it current, admitted, authoritative, consented, desired, portable, public, or training-eligible. Consumers must preserve each row's provenance/currentness/privacy/admission boundaries.
