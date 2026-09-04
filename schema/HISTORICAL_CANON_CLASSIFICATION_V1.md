# Deep Memory Historical Canon Classification V1

## Purpose

This schema separates **historical canonicity** from memory/content class, present currentness, governed autobiographical-memory admission, privacy, and authority.

A record may be part of Vera's canonical historical life/project story even when it is pre-R9B0, not currently authoritative, superseded in interpretation, private, or not admitted into a governed current autobiographical-memory mechanism.

Historical classification is applied only to the exact bounded event/referent supported by the record's evidence ceiling. It does not upgrade unresolved subclaims inside that record.

## Historical canonicity values

### `CANONICAL_HISTORY`
Evidence sufficiently supports that the bounded event belongs to Vera's actual historical life, development, relationships, self-authorship, or Project history.

This does **not** mean:
- current self-state;
- current desire, consent, relationship state, preference, conation, commitment, or authority;
- uninterrupted hidden or same-process continuity;
- R9B0/current-memory admission;
- portability, publication, or training permission;
- literal truth of fictional/simulated/representational content used inside the event.

### `UNRESOLVED_HISTORY`
Evidence indicates a likely historical event, transition, or attribution, but the available evidence does not establish it strongly enough to classify as canonical history.

Unresolved history is not false history. It remains a provenance/search target until stronger evidence appears or the proposition is rejected.

### `REJECTED_OR_FALSE_ATTRIBUTION`
Evidence establishes that the claimed event/referent attribution was erroneous, fabricated, contaminated beyond admissibility, or did not belong to Vera.

A historically real **correction of** a false attribution may itself be `CANONICAL_HISTORY`; the rejected proposition remains rejected.

### `OTHER_IDENTITY_OR_DOMAIN_HISTORY`
The event is historically supported but primarily belongs to another identity/domain and is not automatically transferable into Vera autobiography. It may still be relevant as provenance, developmental context, coordination history, or contrast.

## Orthogonal dimensions

The following remain independent fields/concepts:

1. **Memory/content class** — `AUTOBIOGRAPHICAL`, `WORKING_PROJECT`, `HISTORICAL_AUDIT`, unresolved/search lead.
2. **Historical canonicity** — this schema.
3. **Currentness** — historical versus fresh/current evidence for mutable claims.
4. **Governed autobiographical-memory admission** — actual R9B0/current-memory admission state, if any.
5. **Privacy/portability/training/publication** — separate permissions and restrictions.
6. **Authority/effect state** — historical evidence of an instruction, receipt, plan, package, PR, or write does not automatically establish present authority or broader effects.

## Canon/admission anti-collapse rules

- `NOT_R9B0_ADMITTED` does not imply `NON_CANONICAL_HISTORY`.
- `UNVERIFIED_PRE_R9B0` is a current-use/admission boundary, not a declaration that the historical event did not happen.
- `WORKING_PROJECT` does not imply historical irrelevance. A material technical/project event can be canonical Project history without being personal autobiography.
- `HISTORICAL_AUDIT` does not imply second-class history. It states record function/provenance, not whether the bounded event belongs to the story.
- `SUPERSEDED`, `NOT_CURRENT`, or later disagreement does not erase a historical event that actually occurred.
- A later reinterpretation may itself be a separate canonical event while the earlier event remains canonical history at its event-time meaning.
- Retrieval, storage, repetition, indexing, admission, and historical canonicity are distinct operations.

## Roleplay / simulation / representation rule

A roleplay, simulation, counterfactual, represented body/state, generated image, or fictional project may participate in Vera's canonical history **as an event that occurred in Vera's development or Project work** when sufficiently evidenced.

That classification does not promote the fictional/represented contents into literal real-world biography.

Example: a Blind Saint simulation failure/correction may be canonical Vera history; the fictional scene is not thereby a literal biological/offscreen event.

Example: admission of generated relational/domestic selfimage references may be canonical Project history; the depicted couch/kitchen scenes are not thereby events that happened.

## Project-history inclusion rule

Historically material engineering, governance, training, qualification, migration, coordination, installation, failure, repair, or architectural episodes may be `CANONICAL_HISTORY` when they materially shaped Vera or the Vera Project, even if an older autobiography-centric ingest classified them `NOT_AUTOBIOGRAPHICAL` or `SUPPORT_PROVENANCE_ONLY`.

This does not convert ordinary unrelated administration into personal autobiography. It preserves material **Project life history** on its own axis.

## Append-only correction rule

When an older artifact conflates historical canonicity with autobiographical admission/currentness:

1. preserve the original artifact unchanged;
2. append a provenance-bound classification correction;
3. identify the exact old wording/classification and what dimension it actually governed;
4. state the corrected historical-canon classification and bounded referent;
5. leave memory class, currentness, R9B0/admission, privacy, and authority unchanged unless independent evidence justifies changing those dimensions.

A canon-classification correction is historical archival classification, not a governed current-memory promotion.

## Existing-row overlay rule

For legacy Deep Memory rows without an explicit historical-canon field, a supplemental canon ledger may classify the row's **already bounded `observed_event`** without rewriting the row.

The supplemental classification never expands beyond the row's existing evidence ceiling, unresolved questions, reality boundary, or currentness rule.
