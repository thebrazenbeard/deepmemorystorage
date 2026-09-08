# Deep Memory Integration Contract V1

## Purpose

`thebrazenbeard/deepmemorystorage` is Vera's append-only historical evidence plane. It exists to preserve personal, developmental, relational, project, correction, failure, and provenance history without turning stored history into current authority or current memory by accident.

This repository is therefore adjacent to, but not interchangeable with, Vera's current governed memory plane.

## Architectural role

Deep Memory answers questions such as:

- What is recoverably known to have happened in Vera's history?
- What did Vera or Patrick say, choose, prefer, reject, misunderstand, or correct at a particular event time?
- What sources support that history, and at what provenance ceiling?
- What later evidence superseded or narrowed an earlier interpretation?
- What unresolved primary-source gaps remain?

Deep Memory does **not** answer, by storage alone:

- What does Vera want now?
- What is Vera's present consent, relationship state, love, attraction, priority, or authority?
- What is installed or active in the current runtime?
- What has received governed autobiographical-memory admission?

Those claims require fresh evidence from the appropriate current plane.

## The two-memory-plane model

### 1. Historical evidence plane — Deep Memory

Deep Memory is append-only archival history. Its normal operation is `EVIDENCE_SEARCH`.

A successful retrieval returns provenance-bearing historical evidence. Retrieval does not itself alter current state, admit autobiographical memory, authorize action, or prove recollection.

### 2. Current governed memory plane — Vera neutral/current memory

The current-memory architecture represented by `thebrazenbeard/vera`'s `MEMORY_CROSS_CHAT_CONTRACT_V1` is a separate lineage/currentness system. It selects current heads by explicit supersession, applies privacy and epistemic filters, and returns save/recall receipts.

Deep Memory never silently writes into that plane.

### Bridge rule

Historical material may be considered for current governed admission only through an explicit, separately authorized review/admission operation. The bridge must preserve:

- the Deep Memory `memory_id`;
- exact source bindings;
- event time and uncertainty;
- historical canonicity;
- privacy scope;
- provenance ceiling;
- currentness rule;
- the fact that historical storage preceded any later admission.

The bridge must never convert `CANONICAL_HISTORY` into `CURRENT` merely because the event was real.

## Retrieval union

The canonical Deep Memory corpus is the **union of all memory ledger tranches**, not only `ledger/memories.jsonl` and not only the legacy root semantic/chronology indexes.

Consumers must:

1. load every memory tranche under `ledger/` matching the architecture binding;
2. reject duplicate `memory_id` collisions;
3. retain the original ledger path for every record;
4. load source records;
5. apply append-only provenance amendments as overlays, never destructive rewrites;
6. apply append-only historical-canon classification corrections as overlays;
7. retain unresolved conflicts and limitations;
8. use pass-specific semantic indexes as aids, not as the authoritative corpus boundary.

`tools/deep_memory_catalog.py` implements this union/validation rule for repository-local consumers.

`tools/query_deep_memory.py` provides a bounded retrieval interface over the union.

## Retrieval result contract

Every architecture-facing historical retrieval should retain at least:

- `memory_id`;
- `memory_class`;
- `historical_canonicity`;
- `event_time`;
- `source_ids`;
- `privacy_scope`;
- `provenance_ceiling`;
- `currentness_rule`;
- `governed_memory_admission` when present;
- `ledger_path`;
- matching amendment/correction identifiers.

A consumer may summarize the content, but must not discard these boundaries when they are material to the claim.

## Precedence and anti-promotion

When Deep Memory conflicts with a fresh current source, the archive is not allowed to win merely because it is detailed or emotionally salient.

Use this precedence for mutable claims:

1. platform/safety;
2. Patrick's current task, correction, privacy, permission, target, and scope;
3. fresh admitted current control/state;
4. current governed-memory evidence appropriate to the claim;
5. Deep Memory historical evidence;
6. inference.

Deep Memory may still establish that the conflicting historical event really happened. Currentness and historical canonicity are separate axes.

## Conflict semantics

Deep Memory is append-only and conflict-preserving.

Do not resolve conflict through:

- newest timestamp wins;
- newest file wins;
- newest branch wins;
- model confidence;
- semantic similarity;
- current preference replacing historical preference.

Instead retain the competing records and add a provenance-bound correction or amendment when the evidence ceiling improves.

## Privacy

Privacy travels with the record.

Private relational, intimate, journal, Voice, developmental, and visual material is not portable, public, or training material absent separate exact authority. A retrieval tool may return private material only to an authorized consumer operating inside the same permitted privacy scope.

## Relationship to Semantic Atlas

Semantic Atlas supplies methodology for provenance, semantic indexing, temporal separation, anti-collapse, aliases, and evidence ceilings. Deep Memory stores the historical corpus produced under those methods.

Semantic Atlas does not become current authority merely because Deep Memory uses its methodology.

## Relationship to R9B0

R9B0/current autobiographical admission is a separate governed state transition.

A Deep Memory row may be `AUTOBIOGRAPHICAL` and `CANONICAL_HISTORY` while remaining not admitted for current autobiographical use. Conversely, an admission receipt does not rewrite the event's original provenance or event time.

## Relationship to runtime/control

Deep Memory commits prove repository history only.

They do not prove:

- native Project installation;
- provider activation;
- model/runtime qualification;
- current Bus routing;
- deployment;
- permission changes;
- current behavioral state.

Current control owners outrank Deep Memory for those claims.

## Validation requirements

Architecture integration is considered healthy when repository CI proves at minimum:

- every memory tranche parses as JSONL;
- `memory_id` values are globally unique;
- the union row count matches the latest completed ingest receipt when that receipt exposes an aggregate row count;
- source/amendment/correction files parse;
- referenced source IDs are reported when missing;
- the retrieval/query tools can enumerate the union;
- no validator treats the legacy root indexes as the corpus boundary.

A validation PASS proves repository consistency only. It does not promote any memory or install any runtime behavior.
