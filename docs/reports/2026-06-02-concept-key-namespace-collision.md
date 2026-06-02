# Concept-key namespace collision — design note

**Status:** implemented in PR #634 (single PR — §7 records what shipped vs the original staged plan in §6).
**Spec gate:** [`src/lib/conceptKeyNamespace.test.ts`](../../src/lib/conceptKeyNamespace.test.ts)
**Related:** issue [#529](https://github.com/ArdeleanLucas/PARSE/issues/529) (concept identity pollution); [`2026-05-19-compare-display-bugs-fix-plan.md`](./2026-05-19-compare-display-bugs-fix-plan.md) (Bug 3 — same root cause, display-only fix).

---

## 1. Symptom

In Compare mode the per-speaker **flag** button works for some concepts (`leaf`, `green`, `hair`) and not others (`i`, `ice`). The same split affects per-speaker **cognate** letters and concept **tags**, because they share the same storage mechanism.

## 2. Root cause — two id namespaces share one keyspace

Decision state is persisted in dicts keyed by `Concept.key`:

| Store | Path | Key |
|---|---|---|
| per-speaker flag | `manual_overrides.speaker_flags[key][speaker]` | `Concept.key` |
| per-speaker cognate | `manual_overrides.cognate_sets[key][group]` | `Concept.key` |
| concept tags | tag store | `Concept.key` |
| borrowing flags | `borrowing_flags[key][speaker]` | `Concept.key` |
| canonical realization | `manual_overrides.canonical_realizations[key]` | `Concept.key` |

Save and read both use `Concept.key` symmetrically — the flag code is **not** the bug. The bug is how `Concept.key` is minted in [`conceptGrouping.ts`](../../src/lib/conceptGrouping.ts):

- **Singleton** concept → `key = entry.id` (the csv row id). *(`singletonConcept`)*
- **Grouped** concept (≥2 rows sharing `source_survey`+`source_item`) → `key = source_item`. *(`groupedConceptKey`)*

`source_item` and csv `id` are **different identifier namespaces stored as plain strings in the same dict**. When a grouped concept's `source_item` equals an unrelated concept's `id`, the two concepts collide on one storage slot.

### Why the user's split is exactly leaf/green/hair ✅ vs i/ice ❌

Verified against the live `concepts.csv` (598 rows, all ids unique integers):

| `source_survey` | `source_item` format | count | collides with id namespace? |
|---|---|---|---|
| JBIL | bare integer (`123`, `319`) | 338 | **yes** |
| KLQ | dotted decimal (`1.1`, `3.4`) | 195 | no |
| EXT | dotted decimal | 25 | no |

- `leaf` (id 322), `green` (id 385) are **singletons** → key = own id → immune.
- `hair` (KLQ) is **grouped** but keys on dotted `"1.1"` → never equals an integer id → immune.
- `ice` (JBIL, ice+snow group) keys on `"123"`; `I` (JBIL, I + 4 sentences) keys on `"319"` → both collide.

### The full collision set (9 grouped concepts)

| `Concept.key` | grouped concept | collides with csv id → concept |
|---|---|---|
| `21`  | twenty one / twenty-one | maternal uncle |
| `32`  | hair / hair (JBIL)      | son of sister |
| `100` | branch / tree branch    | to bathe (immerse the whole body) |
| `123` | **ice / snow**          | **to jump** |
| `319` | **I / i am teaching / …** | **wood (substance)** |
| `320` | you (sg.) / …           | branch |
| `321` | we / we are teaching    | stick |
| `322` | you (pl.) / …           | leaf |
| `323` | they / they are taching | root |

Note `322` → `you (pl.)` group collides with the very `leaf` singleton the user reports as *working*: flagging that pronoun group corrupts `leaf`'s flags, and vice versa. The bug is corpus-wide, not limited to the two reported concepts.

## 3. Why the obvious quick fixes are inadequate

- **"Always prefix grouped keys with `source:{survey}:{item}`."** Removes today's 9 collisions but: (a) collision-freedom relies on csv ids staying bare integers — a *format convention*, not an invariant; (b) re-keys all **25** grouped concepts when only 9 collide, needlessly orphaning 16 concepts' existing decisions; (c) leaves two namespaces in one dict, so a future code path that writes a bare key re-collides. It is the same local band-aid already applied to `findBundleForConcept`.
- **Read-time alias `"123" → ice`.** Impossible: `"123"` is genuinely ambiguous at rest. Historical data where a user flagged both `ice` and `to jump` already merged into one bit and cannot be split per concept.

## 4. The invariant

> Decision state MUST be keyed by a single, globally-unique, stable identifier in **one** namespace — the underlying concept id (`conceptKey` / csv `id`, the concepts table primary key) — **never** by a survey-local coordinate (`source_item`).

`source_item` is a *position in a survey wordlist*. It is not unique across the corpus and was never an identity. Keying persistence off it is wrong by construction and **will recur with any future survey** that uses integer source_items (JBIL already does, for 338 concepts).

## 5. Regression gate (this PR)

[`src/lib/conceptKeyNamespace.test.ts`](../../src/lib/conceptKeyNamespace.test.ts) asserts `Concept.key` uniqueness over a faithful slice of the corpus. The headline invariant test is marked `it.fails` — it passes today *because the invariant is violated*; when the fix lands it flips red, forcing conversion to a permanent `it(...)` guard. A positive-control test (singletons + dotted KLQ keys) stays green, and a third test pins the exact `ice↔to jump` / `I↔wood` collisions so the failure is legible in review.

A corpus-level counterpart (assert no grouped key ∈ `set(all csv ids)` over the actual `concepts.csv`) belongs in the backend test suite, since `concepts.csv` lives in the workspace, not the frontend bundle. Tracked in §6.

---

## 6. Implementation scope & migration (the actual fix — part b)

Aligns with #529: stop leaking the display-grouping key into persistence.

### 6.1 Code change

1. **Mint decision keys from concept identity, not the group key.** A grouped concept owns N underlying ids (its `variants[].conceptKey`). Per-speaker decisions resolve to the **underlying realization's** concept id (the variant the speaker actually has), not the synthetic group key. This forces — and answers — the latent question "flagging a speaker in the ice+snow group flags *which* concept?", which the current scheme silently loses.
   - Touch points (all currently pass `concept.key`): [`toggleSpeakerFlag`/`cycleSpeakerCognate`/`resetSpeakerCognate`](../../src/ParseUI.tsx), the read side in [`buildSpeakerForm`](../../src/lib/speakerForm.ts), the sidebar `flagged`/`unreviewed`/`borrowings` filters, and `findConceptByUnderlyingKey` consumers.
2. **Single key-mint function + a branded `ConceptKey` type** so a raw `source_item` string can never be passed where a concept key is expected (compile-time guard). One chokepoint to audit, not a dozen call sites.
3. **Backend corpus invariant test** over `concepts.csv`: every emitted key ∉ `set(all ids)`, all keys unique. Goes red in CI the moment a future survey reintroduces the pattern.

### 6.2 Migration (honest about ambiguity)

Existing on-disk decisions (`speaker_flags`, `cognate_sets`, tags, `borrowing_flags`, `canonical_realizations`) are keyed by the old `source_item`/`id` mix.

- **Unambiguous keys** — a key used by exactly one concept historically → deterministically remap to the new identity key.
- **Genuinely collided keys** (the 9 above, where two concepts shared a slot) → **do not silently guess.** Emit a migration report listing each collided key, the two concepts, and the affected speakers, and surface it in-app for manual triage. Default disposition: leave under the legacy key and prompt the user to re-confirm, rather than mis-attribute.
- Migration is **idempotent** and **dry-run-first** (writes a `*.migration-report.json`, no mutation, until confirmed).

### 6.3 Sequencing

> **Superseded by what shipped — see §7.** This was the original staged plan
> (separate spec-gate, read-compat shim, key-mint, migration PRs). It was
> collapsed into a **single PR** (#634) because the change is small and the
> spec gate, key mint, and migration are coherent together. Differences from
> the plan: the spec test asserts the invariant directly (it is not an
> `it.fails` placeholder); there is no read-compat shim (see the read-fallback
> discussion in §7); and there is no in-app report UI (the migration emits a
> JSON report instead). The plan is retained for context.

1. ~~Design note + `it.fails` spec gate.~~ → shipped as a passing invariant guard.
2. ~~Read-compat shim.~~ → not shipped; deploy couples code + migration (§7).
3. ~~Key mint + branded type + backend invariant test.~~ → key mint shipped; branded type + backend corpus test are follow-ups (§7).
4. ~~Migration tool + report UI.~~ → migration tool shipped (`python/migration/concept_key_namespace.py` + CLI); report UI not built.

### 6.4 Open questions for review

These two are genuine forks — the answers change the *shape* of the fix, not just a parameter. Decide both before code starts.

---

#### Q1 — At what granularity does a per-speaker decision attach: concept, or realization?

**The fork.** Today one flag button per speaker writes one bit under the concept key. With identity-correct keying (§6.1), the question becomes: does that bit belong to **(speaker, concept_id)** — the whole concept — or to **(speaker, concept_id, interval_index)** — the specific realization (one annotation interval / lexeme token)?

**Why it's unavoidable, not academic.** A speaker can have **N intervals on one concept_id** — that's exactly what #529 made the canonical representation of variants ("variant letters A/B/C are recomputed from interval order; they are NOT separate concept rows"). So "flag this speaker's form for `head`" is ambiguous the moment the speaker said `head` twice. The current single-bit-per-concept scheme silently flags *all* of them or *none*. The same ambiguity already exists for **cognate letters** and **canonical-realization selection** — all three keyed the same way — so whatever we pick must apply to all three consistently.

**Options.**

| | Key | Pros | Cons |
|---|---|---|---|
| **A. Concept-level** | `(speaker, concept_id)` | one button, matches today's UX; trivial migration of existing flags | can't flag one realization and not another; meaningless for the multi-interval case #529 created |
| **B. Realization-level** | `(speaker, concept_id, interval_index)` | linguistically precise — a flag marks an actual token; composes with #529's interval-order variant model | interval_index is positional → re-segmentation/re-save can shift it (needs a stable anchor: start-time or an interval id); existing concept-level flags can't be auto-assigned to an index |
| **C. Hybrid** | concept-level by default, realization-level override when a concept has ≥2 intervals for that speaker | best UX fit | most code; two read paths |

**Evidence needed / recommendation.** How often does a single (speaker, concept_id) actually have ≥2 intervals in the live workspace? If rare, **A** is fine now and **B** is a later refinement. If common (likely for elicitation re-takes), go **B** but key by a **stable interval anchor, not the positional index** (the positional `interval_index` is the same fragility that bit `pickIpaIntervalForConcept`). My lean: **A for v1** (keyed by canonical concept_id, unblocks the bug fix), with the storage schema shaped so a realization qualifier can be added later without another migration.

---

#### Q2 — #529 is **closed/landed** (2026-05-28). Does it make this moot, and what's the sequencing?

**Status confirmed.** #529 shipped its data migration. Its identity model: concept identity = the triple `(source_survey, source_item, base_label)`; same-triple rows merged to `canonical_id = min(ids)`; per-speaker variants reconstructed from interval order, **not** stored as separate concept rows.

**It does NOT make the fix moot — verified against current (post-#529) `concepts.csv`:** the 9 key collisions still exist. #529 deliberately left rows that share `(survey, source_item)` but differ in `base_label` ungrouped — and those are exactly the collisions.

**But it reframes the fix — and reveals the deeper drift.** The frontend's [`conceptGrouping.ts`](../../src/lib/conceptGrouping.ts) still groups by `(survey, source_item)` *only* (ignoring `base_label`) and synthesizes a group key from `source_item` plus a `variants[]` array. **That is the pre-#529 variant model.** Measured on the live post-#529 corpus, of the 25 groups it produces:

- **1** is a legitimate same-`base_label` group — `(JBIL, 32) ['hair','hair']` — and that one is a **#529 merge miss** (should have been merged to one id), not a grouping need.
- **24** are **spurious** — they lump genuinely different concepts that merely share a `source_item`:
  - distinct concepts: `ice`+`snow`, `I`+`i am teaching`+…, `to stand`+`to stop`, `how much`+`how many`, `baby`+`a 40 day old baby`;
  - data-entry near-dupes: `twenty one`/`twenty-one`, `branch`/`tree branch`, trailing-punctuation/quote variants.

So post-#529 the FE's `source_item` grouping is **almost entirely producing wrong groups**, and the key collision is just its most visible symptom. The frontend never migrated to #529's identity model.

**The correct fix, therefore:** align FE grouping with #529 — group by the triple (which, since #529 already merged same-triple rows, makes virtually every concept a **singleton keyed by its own unique csv id**). `ice`→`45`, `snow`→`144`, `I`→`517` — all distinct, real ids. **The `source_item` never becomes a storage key, so the collision class is eliminated by construction**, not by prefixing. The `variants[]` / source-item branch in [`buildSpeakerForm`](../../src/lib/speakerForm.ts) (lines 292–314) becomes vestigial and retires into #529's interval-order variant model.

**Sequencing & residual data tail.**
- #529 is landed, so we build on it **now** — no blocker. The active risk is the inverse: do **not** ship new code that perpetuates the `source_item`-as-key model.
- The exercise surfaces a data-cleanup tail independent of this fix: ~10 near-duplicate concept rows and the 1 `(JBIL,32)` #529 merge-miss should be cleaned by a #529-style re-merge. Splitting the 24 spurious groups will make these visible in the sidebar as separate entries (correct for `ice`/`snow`; mildly noisy for `twenty one`/`twenty-one` until deduped) — worth a heads-up so the UI change isn't mistaken for a regression.

**Net:** Q2's answer turns the proposed fix from "patch the key generator" into "retire the stale FE grouping and adopt #529's identity model." Narrower keying logic, far wider correctness — and it resolves a class of mis-groupings the user hasn't even reported yet.

---

## 7. Built fix + dry-run evidence (this branch)

**Chosen mechanism.** A grouped concept's `key` is now its **canonical csv id** —
`min(member_ids)`, the exact rule the landed backend #529 migration uses
(`canonical_id = min(ids)`). `source_item` never enters the key namespace.
Collision-free *by construction*: a group's key is one of its own members' ids,
which no other concept owns.

- Code: [`src/lib/conceptGrouping.ts`](../../src/lib/conceptGrouping.ts) — `canonicalConceptKey()` replaces `groupedConceptKey()`; the `source:`-prefix / `sourceItemsWithMultipleGroupedBuckets` machinery is deleted (no longer needed).
- Guard: [`src/lib/conceptKeyNamespace.test.ts`](../../src/lib/conceptKeyNamespace.test.ts) now asserts the invariant *holds* (`ice`→`45`, `I`→`517`, every key ∈ csv-id namespace, all unique).
- Migration: [`python/migration/concept_key_namespace.py`](../../python/migration/concept_key_namespace.py) (logic) + [`python/scripts/migrate_concept_key_namespace.py`](../../python/scripts/migrate_concept_key_namespace.py) (CLI), mirroring the #529 `concept_suffix_pollution` layout — dry-run-first, idempotent, optimistic-concurrency guarded, refuses to guess on ambiguous (collided) keys. Tests: [`python/migration/test_concept_key_namespace.py`](../../python/migration/test_concept_key_namespace.py).

**Verification:**

- Full frontend suite: **135 files, 1184 passed / 9 skipped.** (6 grouping-test assertions updated to the corrected canonical-id keys; merge test confirmed existing `concept_merges` must also be re-keyed.)
- Corpus-wide invariant over all concepts: **OLD scheme = 9 keys colliding with a real csv id; NEW scheme = 0 duplicate keys, 0 keys outside the id namespace.**
- Migration dry-run against the live workspace data (`parse-enrichments.json`, 564 concepts): 25 groups re-keyed (16 safe / 9 ambiguous). **0** decision keys needed auto-migration; **2** real entanglements surfaced and *left in place for triage*:
  - `cognate_sets["322"]` — `you (pl.)`/`you are teaching` group vs csv id 322 = **`leaf`** (the concept the user believed was fine);
  - `cognate_sets["323"]` — `they`/`they are taching` group vs csv id 323 = `root`.

These two are the irreducible historical-ambiguity cases from §3/§6.2: the slot was genuinely shared, so the tool reports them rather than guessing.

**Out of scope (tracked follow-ups, deliberately not bundled):** the FE still *groups* by `(survey, source_item)` (24/25 groups spurious post-#529) and ~10 near-duplicate concept rows + 1 `(JBIL,32)` #529 merge-miss remain. The keying fix is correct and collision-free regardless; grouping-model alignment and data dedup are separate PRs.

### 7.1 Follow-ups raised in review (PR #634)

Accepted but deliberately not bundled into this PR — each is its own concern:

- **MCP wrapper.** Expose the migration as a chat/MCP tool in `python/ai/tools/migration_tools.py`, mirroring `migrate_concept_suffix_pollution`. Deferred because adding an MCP tool bumps the surface-lock counts and needs parity-fixture updates; doing it here would widen the diff into the MCP surface tests. Tracked separately.
- **Read-compat fallback — DONE (safe-keys-only), per reviewer call.** A blanket "fall back to the legacy key" shim is unsafe for the 9 collided keys (falling back on `"123"` would read `to jump`'s slot into `ice`). The shipped shim is therefore **safe-keys-only**: `promote_safe_legacy_keys()` promotes decision data from the 16 non-colliding (dotted) legacy keys to their canonical keys at read time, and **never touches the 9 ambiguous keys** (they stay under the legacy key for the migration report + human triage). Wired defensively into the central loader `canonical_lexemes.load_enrichments` (cached `build_remap` by `concepts.csv` mtime; never raises), so the backend/MCP/AI/export tool surface stays correct even if the on-disk migration is skipped. A load-time scan logs a warning when ambiguous legacy keys remain. **FE stays deploy-gated** (the migration/report is the signal); the Python-side promotion covers the tool surface. The migration script remains the canonical "rewrite the file on disk + triage the 9" step.
- **Backend corpus invariant test.** `concepts.csv` lives in the workspace, not the repo, so a CI test can't read the live corpus. The shipped guard is the FE fixture test (`conceptKeyNamespace.test.ts`) over the real collision shapes plus the migration's `build_remap` tests. A live-corpus check belongs in a workspace-aware (non-CI) verification or the MCP tool's verify path.
- **Branded `ConceptKey` type.** Compile-time guard so a `source_item` string can never be passed where a concept key is expected. Pure type-system hardening; separate change.
