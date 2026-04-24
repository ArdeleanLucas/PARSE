import type { AnnotationRecord } from "../api/types";

/**
 * Client-side lexeme candidate search.
 *
 * Scope (PR A): scans the tiers already loaded in the annotation record —
 * `ortho_words` > `ortho` > `stt` > `ipa` — and returns a ranked list of
 * time ranges whose text approximately matches any user-supplied variant.
 *
 * This is the scaffold half of the Lexical Anchor Alignment System. It is
 * intentionally simple:
 *   - orthographic similarity via normalized Levenshtein
 *   - tier-priority weighting (ortho_words is the most reliable source)
 *   - merges adjacent short intervals on the same tier so a word split
 *     across two segments ("ye" + "k" → "yek") still surfaces as one hit
 *
 * PR B will replace the scoring with the two-signal backend system
 * (phonetic Levenshtein on IPA + cross-speaker confirmed-anchor matching)
 * exposed via `GET /api/lexeme/search`. The candidate shape here is the
 * schema we plan to receive from that endpoint so the UI can stay stable
 * across the cut-over.
 */

export type SearchableTier = "ortho_words" | "ortho" | "stt" | "ipa";

export interface LexemeCandidate {
  start: number;
  end: number;
  /** Which tier the match came from. */
  tier: SearchableTier;
  /** The actual tier text that matched (or the merged text of adjacent
   * intervals when the match spans a split word). */
  matchedText: string;
  /** The variant that scored best against `matchedText`. */
  matchedVariant: string;
  /** Confidence in [0, 1]. Higher is better. */
  score: number;
  /** Human-readable source chip, e.g. `"ortho_words:0.92"`. */
  sourceLabel: string;
}

export interface SearchOptions {
  /** Maximum number of candidates to return. */
  limit?: number;
  /** Normalized Levenshtein distance threshold (0 = exact, 1 = totally different).
   * Candidates whose best match exceeds this are dropped. Default 0.55 —
   * loose enough to catch "yek" ↔ "jek" ↔ "yak". */
  maxNormalizedDistance?: number;
  /** Max seconds between adjacent intervals to consider merging. */
  adjacencyGapSec?: number;
  /** Max duration (seconds) of either interval for adjacency merge — keeps
   * the merge sane on word-level tiers without collapsing sentences. */
  maxAdjacentDurationSec?: number;
}

const DEFAULTS: Required<SearchOptions> = {
  limit: 10,
  maxNormalizedDistance: 0.55,
  adjacencyGapSec: 0.3,
  maxAdjacentDurationSec: 1.2,
};

/** Relative weight per tier. ortho_words ships with per-interval confidence
 * from forced alignment (PR #178) so it's the most trusted source. Plain
 * `ortho` is Whisper segments — trustworthy text, imprecise boundaries.
 * `stt` is the coarse reference. `ipa` is only useful for IPA-shaped queries
 * and is weighted lower for orthographic variants. */
const TIER_WEIGHT: Record<SearchableTier, number> = {
  ortho_words: 1.0,
  ortho: 0.85,
  stt: 0.7,
  ipa: 0.55,
};

const SEARCH_TIERS: SearchableTier[] = ["ortho_words", "ortho", "stt", "ipa"];

/** Normalize a string for fuzzy matching: lowercase, strip punctuation,
 * collapse internal whitespace. Keeps letters (including combining marks)
 * and digits, drops everything else. */
export function normalizeForMatch(s: string): string {
  return s
    .toLowerCase()
    .normalize("NFKD")
    .replace(/[^\p{L}\p{N}\s]/gu, "")
    .replace(/\s+/g, " ")
    .trim();
}

/** Standard iterative Levenshtein (two rolling rows). Not exported from a
 * library because the codebase had no existing edit-distance helper and the
 * implementation is small. */
export function levenshtein(a: string, b: string): number {
  if (a === b) return 0;
  if (a.length === 0) return b.length;
  if (b.length === 0) return a.length;

  let prev = new Array(b.length + 1);
  let curr = new Array(b.length + 1);
  for (let j = 0; j <= b.length; j++) prev[j] = j;

  for (let i = 1; i <= a.length; i++) {
    curr[0] = i;
    for (let j = 1; j <= b.length; j++) {
      const cost = a.charCodeAt(i - 1) === b.charCodeAt(j - 1) ? 0 : 1;
      curr[j] = Math.min(
        curr[j - 1] + 1,
        prev[j] + 1,
        prev[j - 1] + cost,
      );
    }
    [prev, curr] = [curr, prev];
  }
  return prev[b.length];
}

/** Levenshtein normalized by the longer string's length. Returns [0, 1];
 * 0 = identical, 1 = completely different. */
export function normalizedLevenshtein(a: string, b: string): number {
  const maxLen = Math.max(a.length, b.length);
  if (maxLen === 0) return 0;
  return levenshtein(a, b) / maxLen;
}

/** Best (lowest) normalized distance between `text` and any variant.
 * Tries whole-string match and per-token matches — so the variant "yek"
 * matches the interval text "yek dînarê" at the first token. */
function bestVariantDistance(text: string, variants: string[]): { distance: number; variant: string } {
  const normText = normalizeForMatch(text);
  const tokens = normText.split(" ").filter(Boolean);
  let best = { distance: 1, variant: variants[0] ?? "" };

  for (const variant of variants) {
    const normVariant = normalizeForMatch(variant);
    if (!normVariant) continue;

    const whole = normalizedLevenshtein(normText, normVariant);
    if (whole < best.distance) best = { distance: whole, variant };

    for (const token of tokens) {
      const tokenDist = normalizedLevenshtein(token, normVariant);
      if (tokenDist < best.distance) best = { distance: tokenDist, variant };
    }
  }
  return best;
}

interface MergedInterval {
  start: number;
  end: number;
  text: string;
}

/** Build a merged view of a tier's intervals: each original interval plus
 * merged pairs for adjacent short intervals (both ≤ `maxAdjacentDurationSec`,
 * separated by ≤ `adjacencyGapSec`). Both views are searched so we don't
 * miss either the split or the whole. */
function withAdjacencyMerges(
  intervals: Array<{ start: number; end: number; text: string }>,
  opts: Required<SearchOptions>,
): MergedInterval[] {
  const out: MergedInterval[] = [];
  for (const iv of intervals) {
    if (!iv.text || !iv.text.trim()) continue;
    out.push({ start: iv.start, end: iv.end, text: iv.text });
  }
  for (let i = 0; i < intervals.length - 1; i++) {
    const a = intervals[i];
    const b = intervals[i + 1];
    if (!a.text?.trim() || !b.text?.trim()) continue;
    if (b.start - a.end > opts.adjacencyGapSec) continue;
    if (a.end - a.start > opts.maxAdjacentDurationSec) continue;
    if (b.end - b.start > opts.maxAdjacentDurationSec) continue;
    out.push({
      start: a.start,
      end: b.end,
      text: `${a.text} ${b.text}`.trim(),
    });
  }
  return out;
}

export function searchLexeme(
  record: AnnotationRecord | null,
  rawVariants: string[],
  userOptions?: SearchOptions,
): LexemeCandidate[] {
  const opts: Required<SearchOptions> = { ...DEFAULTS, ...userOptions };
  const variants = rawVariants.map((v) => v.trim()).filter(Boolean);
  if (!record || variants.length === 0) return [];

  const candidates: LexemeCandidate[] = [];

  for (const tier of SEARCH_TIERS) {
    const tierData = record.tiers?.[tier];
    if (!tierData?.intervals?.length) continue;

    const merged = withAdjacencyMerges(tierData.intervals, opts);
    for (const iv of merged) {
      const { distance, variant } = bestVariantDistance(iv.text, variants);
      if (distance > opts.maxNormalizedDistance) continue;

      const phoneticScore = 1 - distance;
      const score = phoneticScore * TIER_WEIGHT[tier];
      candidates.push({
        start: iv.start,
        end: iv.end,
        tier,
        matchedText: iv.text,
        matchedVariant: variant,
        score,
        sourceLabel: `${tier}:${score.toFixed(2)}`,
      });
    }
  }

  // De-dupe: if two candidates cover the same time range within 10ms, keep
  // the higher-scoring one. Search across tiers often produces near-duplicate
  // hits (same word in ortho_words and ortho), no reason to show both.
  candidates.sort((a, b) => b.score - a.score);
  const deduped: LexemeCandidate[] = [];
  const tol = 0.01;
  for (const c of candidates) {
    const collision = deduped.find(
      (d) => Math.abs(d.start - c.start) < tol && Math.abs(d.end - c.end) < tol,
    );
    if (!collision) deduped.push(c);
  }

  return deduped.slice(0, opts.limit);
}
