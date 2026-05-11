# phonetic_rules_apply

**Category:** Annotation
**Mutability:** read_only
**Supports Dry Run:** N/A (read-only computation)
**Complexity:** Low
**Estimated Tokens:** ~230 (short) / ~510 (full)

## One-Sentence Summary
Applies the project's phonetic rules to IPA forms in one of three modes — `normalize` (strip delimiters / lowercase / whitespace), `apply` (return all rule-generated variants), or `equivalence` (compare two forms, returning `isEquivalent` + similarity score).

## When to Use
- **`normalize` mode** — before comparing or storing IPA forms; ensures consistent delimiter / case / whitespace handling.
- **`apply` mode** — to expand a base IPA form into its rule-permitted variants (free variation, allophones, etc.) for cognate matching or display.
- **`equivalence` mode** — to decide whether two surface IPA forms are the same lexeme up to allowable variation, for cognate / borrowing decisions.

## When NOT to Use
- For orthographic forms — this tool operates on IPA. Use a different transformation if the input is graphemes.
- For tier-wide batch transformations on an annotation file. The tool is per-form (or per-form-pair); apply it programmatically over the cells you care about.
- To author or modify the project's rule file. The tool reads `phonetic_rules.json` (or accepts inline `rules`); it does not write back.

## Parameters

| Parameter | Type     | Required | Description                                                                                  | Default       | Example                |
|-----------|----------|----------|----------------------------------------------------------------------------------------------|---------------|------------------------|
| form      | string   | Yes      | Primary IPA form to operate on. `minLength=1`, `maxLength=256`.                              | —             | `"[xosˈtin]"`          |
| mode      | string   | No       | Operation: `normalize`, `apply`, or `equivalence`.                                           | `"normalize"` | `"equivalence"`        |
| form2     | string   | No*      | Second form (required for `equivalence` mode). `minLength=1`, `maxLength=256`.               | —             | `"xostin"`             |
| rules     | object[] | No       | Optional inline rule list (same schema as `phonetic_rules.json` entries). Omit to use the project file. | — | `[{"from": "x", "to": "h"}]` |

*Required when `mode: "equivalence"`.

## Expected Output
Shape depends on `mode`:

- **`normalize`**: `{ normalized: "<form>" }` — the input with delimiters stripped, lowercased, whitespace normalized.
- **`apply`**: `{ variants: ["...", "..."] }` — all rule-generated variants of the input.
- **`equivalence`**: `{ isEquivalent: bool, score: 0.0..1.0, normalizedForm, normalizedForm2 }` — the comparison verdict and similarity score.

Does not mutate project state.

## Example Successful Call
Normalize:
```json
{
  "form": "[xosˈtin]",
  "mode": "normalize"
}
```

Apply rules (variants):
```json
{
  "form": "xostin",
  "mode": "apply"
}
```

Equivalence:
```json
{
  "form": "[xosˈtin]",
  "form2": "xostin",
  "mode": "equivalence"
}
```

## Common Failure Modes & How to Recover

| Failure                                 | Symptom                                                              | Recovery                                                                                              |
|-----------------------------------------|----------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------|
| Missing `form2` in equivalence mode     | Validation error                                                     | Provide both forms when `mode: "equivalence"`.                                                        |
| Inline `rules` schema mismatch          | Validation error or unexpected behavior                              | Match `phonetic_rules.json` schema; or omit `rules` to use the project file.                          |
| Surprising equivalence verdict          | `isEquivalent: false` when you expected true (or vice versa)         | Inspect `normalizedForm` / `normalizedForm2` in the response — the rules may not capture the variation. Edit `phonetic_rules.json`.|
| Variant explosion in `apply` mode       | Hundreds of variants for a long form                                 | The rule set may have too many rewrites. Consider scoping the inline `rules` to just what's needed.   |

## Agent Reasoning Notes
Normalize first, equivalence-test second. In compare-mode cognate review (Comparison bucket), this tool is the canonical check for "are these two forms the same?". The similarity score is useful for borderline cases — pair with a threshold (e.g. > 0.85) for automated grouping, but always show the matched normalized forms to a human reviewer before persisting a decision. Project-wide rules live in `phonetic_rules.json`; modify that file via direct edit (not via this tool) if rules need to change.

## Related Skills
- `cognate_compute_preview`, `cross_speaker_match_preview` — comparison-bucket tools that consume normalized IPA.
- `annotation_read` — get the raw IPA cells to feed this tool.
