# cross_speaker_match_preview

**Category:** Comparison
**Mutability:** read_only
**Supports Dry Run:** N/A (preview-only by design)
**Complexity:** Medium
**Estimated Tokens:** ~260 (short) / ~560 (full)

## One-Sentence Summary
Computes read-only cross-speaker match candidates from STT output (`sttJobId` or inline `sttSegments`) against existing annotations — surfaces which segments in one speaker's STT likely correspond to which concept rows across other speakers.

## When to Use
- After STT on a new speaker — find which existing concept rows this speaker's segments map to, before manually adjudicating in compare mode.
- For pre-flight to compare mode — run this to see candidate matches before bulk-tagging or moving rows around.
- To validate a `detect_timestamp_offset`-corrected speaker against the rest of the corpus.
- Inside `prepare_compare_mode` — the workflow tool calls this internally to build the cross-speaker section of the bundle.

## When NOT to Use
- To persist any matches. This is preview-only. Decisions get made elsewhere (compare-mode UI, `enrichments_write`).
- Without STT data. The tool requires either a completed `sttJobId` or inline `sttSegments`. No STT → no input.
- For unbounded full-record dumps. Inline `sttSegments` should be a bounded list (typically from a windowed STT run); don't paste an entire annotation file in here.
- For cognate similarity / borrowing comparison — that's `cognate_compute_preview`. This tool answers "which existing concept row is this segment?", not "are these forms cognate?".

## Parameters

| Parameter     | Type     | Required | Description                                                                                              | Default | Example                  |
|---------------|----------|----------|----------------------------------------------------------------------------------------------------------|---------|--------------------------|
| speaker       | string   | No*      | Speaker the STT data comes from. `minLength=1`, `maxLength=200`.                                         | —       | `"Khan04"`               |
| sttJobId      | string   | No*      | Identifier of a completed STT job (`stt_start` / `stt_word_level_start`). `minLength=1`, `maxLength=128`. | —       | `"stt-7f3a"`             |
| sttSegments   | object[] | No*      | Inline STT segments — each carries `start`/`end`/`text` (and optionally `ortho`/`ipa`).                  | —       | `[{"start": 12.34, "end": 12.78, "text": "water"}]` |
| topK          | integer  | No       | Number of top matches per segment. `minimum=1`, `maximum=20`.                                            | (server default) | `5`              |
| minConfidence | number   | No       | Minimum similarity score to include. `minimum=0.0`, `maximum=1.0`.                                       | (server default) | `0.35`           |
| maxConcepts   | integer  | No       | Cap on concepts considered. `minimum=1`, `maximum=500`.                                                  | (server default) | `25`             |

*Provide either `sttJobId` *or* `sttSegments` (and `speaker` for context).

## Expected Output
Returns `{ readOnly, matches: [{ segment, candidates: [{ speaker, conceptId, score, ortho, ipa }] }], speakersConsidered, conceptsConsidered, topK, minConfidence, ... }`. Each segment of input gets up to `topK` candidate (speaker, conceptId) matches from the existing annotation pool.

Does not mutate project state.

## Example Successful Call
Inline STT:
```json
{
  "speaker": "Khan04",
  "sttSegments": [
    {"start": 12.34, "end": 12.78, "text": "water", "ortho": "water", "ipa": "wɑtər"},
    {"startSec": 18.1, "endSec": 18.72, "text": "fire",  "ortho": "fire",  "ipa": "faɪr"}
  ],
  "topK": 5,
  "minConfidence": 0.35,
  "maxConcepts": 25
}
```

Via STT job:
```json
{
  "speaker": "Khan04",
  "sttJobId": "stt-7f3a",
  "topK": 5,
  "minConfidence": 0.35,
  "maxConcepts": 25
}
```

## Common Failure Modes & How to Recover

| Failure                                | Symptom                                                              | Recovery                                                                                                  |
|----------------------------------------|----------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------|
| Empty `matches`                        | No candidates returned for any segment                               | Lower `minConfidence`. Verify the speaker has overlap with existing concepts.                              |
| Generic / wrong matches                | Top candidate is irrelevant                                          | Increase `minConfidence`. Restrict scope by reducing `maxConcepts` or pre-filtering `sttSegments`.        |
| Too many candidates                    | `topK` results overwhelm the agent                                   | Lower `topK`. Default is usually `5`.                                                                      |
| Inline `sttSegments` shape mismatch    | Validation error                                                     | Segments accept `start`/`end` or `startSec`/`endSec`. Include `text` plus optional `ortho`/`ipa`.          |
| Speaker not provided                   | Matches lack source context                                          | Set `speaker` so each match has a clear "this is from speaker X" attribution.                              |

## Agent Reasoning Notes
This is the typical "where does this new speaker's data fit?" pre-flight before compare-mode review. Use a real `sttJobId` when one is available — it pulls the full segment set; only use inline `sttSegments` for spot-checks or when re-running against curated windows. Pair with `cognate_compute_preview` for the complementary "are these forms cognate?" question and `prepare_compare_mode` for the full bundle including both.

## Related Skills
- `prepare_compare_mode` — workflow that wraps this with cognate preview and annotation load.
- `cognate_compute_preview` — cognate/similarity comparison (different question, complementary signal).
- `stt_start`, `stt_word_level_start` — produce the `sttJobId` consumed here.
- `enrichments_write` (Project bucket) — persist decisions derived from this preview.
