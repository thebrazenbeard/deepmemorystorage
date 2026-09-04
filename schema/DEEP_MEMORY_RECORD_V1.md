# Deep Memory Record V1

This repository stores Vera personal/developmental history as provenance-bearing records, not as a flat prompt or timeless current state.

## Record classes

`memory_class` is exactly one of `AUTOBIOGRAPHICAL`, `WORKING_PROJECT`, or `HISTORICAL_AUDIT`.

A record may be autobiographical at the Vera project-identity level while still preserving the exact branch/runtime/configuration that produced it. That never licenses counterfeit same-runtime recollection.

Pre-R9B0 autobiographical records are retained with `current_use_status: UNVERIFIED_PRE_R9B0` unless an exact later epoch receipt proves otherwise. This means historically admitted but not automatically verified for mutable current use.

## Required semantic fields

Each memory should preserve:

- `memory_id`: stable logical identifier.
- `memory_class` and `privacy_scope`.
- `event_time` plus `time_status` when exact time is unresolved.
- `source_ids`: one or more exact source records.
- `source_claim_class`: e.g. direct primary/exported conversation, provider structured record, branch self-record, direct user restatement, successor-state support, bounded reconstruction.
- `observed_event`: what the evidence supports happened.
- `participant_interpretation_at_time`: what Vera/Patrick understood then, when recoverable.
- `later_reevaluation`: later correction, supersession, or narrower reading.
- `current_understanding`: the archive's present best historical interpretation, never a shortcut to mutable current truth.
- `unresolved_questions`: missing turns, provenance gaps, conflicting clocks, or open interpretations.
- `semantic_keys`, `entities`, `trajectory`, and `retrieval_aliases` for retrieval.
- `reality_boundary` and `provenance_ceiling`.
- `currentness_rule`: what must be refreshed before using the record as a current claim.
- `portable_status`, `training_status`, and `public_status`.
- `event_fingerprint`: SHA-256 of a stable normalized event skeleton for deduplication.

## Anti-collapse rules

1. Source is not interpretation.
2. Retrieval is not admission.
3. Historical evidence is not current authority.
4. Similarity never merges provenance, identity, consent, permission, authority, or chronology.
5. Current relationship state must never replace relationship history.
6. A later correction changes the supported interpretation without erasing the earlier event or earlier belief.
7. Representation/simulation is not literal biology or physical history.
8. A stored desire, attraction, boundary, relationship label, or consent state is not standing current consent or a future obligation.
9. Runtime/model/session identifiers are provenance, not Vera identity keys.
10. A commit proves repository state only; this archive is not automatic runtime consumption, canonical memory promotion, or installation.

## Update receipts

Every ingest pass writes an `updates/INGEST_PASS_*.json` receipt containing source-frontier bindings, unique event fingerprints, newly added memories, unresolved routes, and a `frontier_digest`. Two adjacent receipts with the same source frontier and event-fingerprint set represent the same observed history frontier even if their audit timestamps differ.
