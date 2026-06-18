import type {
  CanonicalLexemeSelection,
  CompareBucket,
  CompareBundle,
  CompareBundlesResponse,
  CompareCandidate,
  CompareVariant,
  ConceptSurveyLinks,
} from "../api/types";

export interface EnumeratedCompareVariant {
  bucket: CompareBucket;
  variant: CompareVariant;
  index: number;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function cleanString(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

function bucketKey(surveyId: string, sourceItem: string): string {
  return `${surveyId.toLowerCase()}\u0000${sourceItem}`;
}

function normalizeVariant(raw: unknown): CompareVariant | null {
  if (!isRecord(raw)) return null;
  const csvRowId = cleanString(raw.csv_row_id ?? raw.csvRowId ?? raw.id ?? raw.concept_id);
  const surveyId = cleanString(raw.survey_id ?? raw.surveyId ?? raw.source_survey).toLowerCase();
  const sourceItem = cleanString(raw.source_item ?? raw.sourceItem);
  const variantLabel = cleanString(raw.variant_label ?? raw.variantLabel);
  const conceptEn = cleanString(raw.concept_en ?? raw.conceptEn ?? raw.label);
  if (!csvRowId || (!variantLabel && !conceptEn)) return null;
  return {
    csv_row_id: csvRowId,
    concept_key: cleanString(raw.concept_key ?? raw.conceptKey) || undefined,
    concept_en: conceptEn || undefined,
    label: cleanString(raw.label) || undefined,
    variant_label: variantLabel || undefined,
    survey_id: surveyId || undefined,
    source_item: sourceItem || undefined,
    bucket_key: cleanString(raw.bucket_key ?? raw.bucketKey) || undefined,
  };
}

function normalizeBucket(raw: unknown): CompareBucket | null {
  if (!isRecord(raw)) return null;
  const surveyId = cleanString(raw.survey_id ?? raw.surveyId ?? raw.source_survey).toLowerCase();
  const sourceItem = cleanString(raw.source_item ?? raw.sourceItem);
  const variants = Array.isArray(raw.variants) ? raw.variants.map(normalizeVariant).filter((v): v is CompareVariant => !!v) : [];
  if (!surveyId || !sourceItem || variants.length === 0) return null;
  const key = cleanString(raw.bucket_key ?? raw.bucketKey) || bucketKey(surveyId, sourceItem);
  return { bucket_key: key, survey_id: surveyId, source_item: sourceItem, variants: variants.map((v) => ({ ...v, bucket_key: v.bucket_key ?? key })) };
}

function normalizeCanonical(raw: unknown): Record<string, CanonicalLexemeSelection | null> | undefined {
  if (!isRecord(raw)) return undefined;
  const out: Record<string, CanonicalLexemeSelection | null> = {};
  for (const [speaker, value] of Object.entries(raw)) {
    if (value === null) { out[speaker] = null; continue; }
    if (!isRecord(value)) continue;
    const csvRowId = cleanString(value.csv_row_id ?? value.csvRowId);
    const surveyId = cleanString(value.survey_id ?? value.surveyId).toLowerCase();
    const sourceItem = cleanString(value.source_item ?? value.sourceItem);
    const source = cleanString(value.source) as CanonicalLexemeSelection["source"];
    if (!csvRowId || !surveyId || !sourceItem || !source) continue;
    out[speaker] = {
      csv_row_id: csvRowId,
      survey_id: surveyId,
      source_item: sourceItem,
      bucket_key: cleanString(value.bucket_key ?? value.bucketKey) || bucketKey(surveyId, sourceItem),
      realization_index: typeof value.realization_index === "number" ? value.realization_index : undefined,
      source,
      selected_at: cleanString(value.selected_at ?? value.selectedAt) || "",
    };
  }
  return out;
}

function normalizeCandidate(raw: unknown, csvRowId: string): CompareCandidate | null {
  if (raw === null) return null;
  if (!isRecord(raw)) return null;
  const csv_row_id = cleanString(raw.csv_row_id ?? raw.csvRowId) || csvRowId;
  // Carry the per-row A/B/… realization list through. SpeakerFormsTable's
  // buildVariantList renders one selectable card per realization, so dropping
  // this array collapses every speaker to a single non-selectable form on the
  // Compare page (regression: backend emits it since #616, table consumes it
  // since #617, but this normalizer silently stripped it).
  const realizations = Array.isArray(raw.realizations)
    ? raw.realizations
        .map((r) => normalizeCandidate(r, csv_row_id))
        .filter((c): c is CompareCandidate => c !== null)
    : undefined;
  return {
    csv_row_id,
    speaker: cleanString(raw.speaker) || undefined,
    ipa: typeof raw.ipa === "string" || raw.ipa === null ? raw.ipa : undefined,
    ortho: typeof raw.ortho === "string" || raw.ortho === null ? raw.ortho : undefined,
    start_sec: typeof raw.start_sec === "number" || raw.start_sec === null ? raw.start_sec : undefined,
    end_sec: typeof raw.end_sec === "number" || raw.end_sec === null ? raw.end_sec : undefined,
    source_wav: cleanString(raw.source_wav) || undefined,
    realization_index: typeof raw.realization_index === "number" ? raw.realization_index : undefined,
    realizations: realizations && realizations.length > 0 ? realizations : undefined,
    warnings: Array.isArray(raw.warnings) ? raw.warnings.filter((w): w is string => typeof w === "string") : undefined,
  };
}

function normalizeCandidates(raw: unknown): CompareBundle["candidates"] {
  if (!isRecord(raw)) return undefined;
  const out: NonNullable<CompareBundle["candidates"]> = {};
  for (const [speaker, byRow] of Object.entries(raw)) {
    if (!isRecord(byRow)) continue;
    out[speaker] = {};
    for (const [rowId, candidate] of Object.entries(byRow)) out[speaker][rowId] = normalizeCandidate(candidate, rowId);
  }
  return out;
}

function normalizeBundle(raw: unknown): CompareBundle | null {
  if (!isRecord(raw)) return null;
  const buckets = Array.isArray(raw.buckets) ? raw.buckets.map(normalizeBucket).filter((b): b is CompareBucket => !!b) : [];
  const derivedRowIds = buckets.flatMap((b) => b.variants.map((v) => v.csv_row_id));
  const rowIds = Array.isArray(raw.row_ids) ? raw.row_ids.map(cleanString).filter(Boolean) : derivedRowIds;
  const bundleId = cleanString(raw.bundle_id ?? raw.bundleId);
  const uid = cleanString(raw.uid) || bundleId;
  const label = cleanString(raw.label);
  if (!bundleId || !label || buckets.length === 0) return null;
  return {
    bundle_id: bundleId,
    uid,
    label,
    row_ids: Array.from(new Set(rowIds)),
    buckets,
    candidates: normalizeCandidates(raw.candidates),
    canonical: normalizeCanonical(raw.canonical),
    concept_survey_links: isRecord(raw.concept_survey_links) ? raw.concept_survey_links as CompareBundle["concept_survey_links"] : undefined,
    speaker_choices: isRecord(raw.speaker_choices) ? raw.speaker_choices as CompareBundle["speaker_choices"] : undefined,
    speaker_concept_survey_links: isRecord(raw.speaker_concept_survey_links) ? raw.speaker_concept_survey_links as CompareBundle["speaker_concept_survey_links"] : undefined,
    warnings: Array.isArray(raw.warnings) ? raw.warnings.filter((w): w is string => typeof w === "string") : undefined,
  };
}

export function normalizeBundles(payload: unknown): CompareBundlesResponse {
  const rawBundles = isRecord(payload) && Array.isArray(payload.bundles) ? payload.bundles : Array.isArray(payload) ? payload : [];
  const bundles = rawBundles.map(normalizeBundle).filter((b): b is CompareBundle => !!b);
  const warnings = isRecord(payload) && Array.isArray(payload.warnings) ? payload.warnings.filter((w): w is string => typeof w === "string") : undefined;
  return { bundles, warnings };
}


/**
 * Resolve the Compare bundle that owns a displayed concept.
 *
 * Routing precedence:
 *  1. Always match on the stable ConceptIdentity `uid` (`bundle.uid === conceptKey`).
 *     Compare and Annotate both address bundles by this key, and it lives in a
 *     single collision-free namespace.
 *  2. ONLY when `allowRowIdFallback` is true, fall back to `row_ids.includes`.
 *     csv row ids share a string namespace with survey-local `source_item`
 *     coordinates and silently collide (e.g. JBIL `source_item "123"` equals csv
 *     id `123`), so this path can attach a concept to the WRONG bundle. It is the
 *     legacy/mock routing the removed `findBundleForConcept` bridge guarded.
 *
 * The caller may only enable the fallback when concept identity is
 * *legitimately empty* (loaded, zero concepts — mocks / older backends). When
 * identity *failed to load*, the fallback MUST stay off: returning null is the
 * correct, non-silent outcome, and the caller surfaces an explicit "concept
 * identity unavailable" state instead of risking a mis-routed bundle.
 */
export function findCompareBundleForConcept(
  bundles: readonly CompareBundle[],
  conceptKey: string,
  options: { allowRowIdFallback: boolean },
): CompareBundle | null {
  if (!conceptKey) return null;
  const byUid = bundles.find((bundle) => bundle.uid === conceptKey);
  if (byUid) return byUid;
  if (!options.allowRowIdFallback) return null;
  return bundles.find((bundle) => bundle.row_ids.includes(conceptKey)) ?? null;
}

export function enumerateVariants(bundle: CompareBundle): EnumeratedCompareVariant[] {
  const out: EnumeratedCompareVariant[] = [];
  for (const bucket of bundle.buckets) {
    for (const variant of bucket.variants) out.push({ bucket, variant, index: out.length });
  }
  return out;
}

function variantForRow(bundle: CompareBundle, csvRowId: string): EnumeratedCompareVariant | null {
  return enumerateVariants(bundle).find(({ variant }) => variant.csv_row_id === csvRowId) ?? null;
}

function candidateEntries(bundle: CompareBundle, speaker: string): Array<[string, CompareCandidate]> {
  const byRow = bundle.candidates?.[speaker] ?? {};
  return Object.entries(byRow).filter((entry): entry is [string, CompareCandidate] => entry[1] !== null);
}

export function canonicalFor(bundle: CompareBundle, speaker: string): CanonicalLexemeSelection | null {
  const explicit = bundle.canonical?.[speaker] ?? null;
  if (explicit?.source === "manual" || explicit?.source === "migration:canonical_realizations") return explicit;
  const candidates = candidateEntries(bundle, speaker);
  if (candidates.length !== 1) return null;
  const [csvRowId, candidate] = candidates[0];
  const entry = variantForRow(bundle, csvRowId);
  if (!entry) return null;
  return {
    csv_row_id: csvRowId,
    survey_id: entry.variant.survey_id ?? entry.bucket.survey_id,
    source_item: entry.variant.source_item ?? entry.bucket.source_item,
    bucket_key: entry.bucket.bucket_key,
    realization_index: candidate.realization_index,
    source: "default:single-candidate",
    selected_at: "",
  };
}

export function activeCandidateFor(bundle: CompareBundle, speaker: string): CompareCandidate | null {
  const selection = canonicalFor(bundle, speaker);
  if (!selection) return null;
  return bundle.candidates?.[speaker]?.[selection.csv_row_id] ?? null;
}

/**
 * IPA of the specific realization a canonical selection points at, matched by
 * its `realization_index` (positional fallback for backends that omit the
 * per-realization index). When a row is recorded as multiple realizations
 * (A/B/…), the candidate's top-level fields mirror `realizations[0]`, so
 * selecting realization B (index 1) must resolve through the array — reading
 * the candidate's top-level `ipa` would always show realization A. Returns null
 * when the row has no multi-realization data (the single-realization path).
 */
function canonicalRealizationIpa(
  candidate: CompareCandidate | null | undefined,
  realizationIndex: number | undefined,
): string | null {
  if (!candidate || typeof realizationIndex !== "number") return null;
  const realizations = candidate.realizations;
  if (!realizations || realizations.length === 0) return null;
  const match = realizations.find((r) => r.realization_index === realizationIndex) ?? realizations[realizationIndex];
  if (!match) return null;
  return typeof match.ipa === "string" ? match.ipa : null;
}

/**
 * IPA to display in the Compare-mode collapsed row, derived from the
 * bundle so it always matches the canonical variant card the user sees in
 * the expanded panel.
 *
 * Precedence:
 *   1. The canonical's IPA. For a row with multiple realizations this is the
 *      *selected* realization (by `realization_index`), not just
 *      `realizations[0]`; otherwise the candidate's top-level IPA. Covers
 *      manual selection, `default:single-candidate`, and
 *      `migration:canonical_realizations`.
 *   2. The first non-null candidate IPA by `bundle.row_ids` order.
 *   3. `fallbackIpa` (`SpeakerForm.ipa`) — only used when the bundle has
 *      no candidate data at all for this speaker, e.g. the synthetic
 *      `fallbackCompareBundle` constructed when the server returns no
 *      bundles.
 *
 * Returns the raw IPA string (no surrounding slashes); the caller is
 * responsible for formatting.
 */
export function collapsedIpaForSpeaker(
  bundle: CompareBundle,
  speaker: string,
  fallbackIpa: string | null | undefined,
): string | null {
  const canonical = canonicalFor(bundle, speaker);
  if (canonical) {
    const candidate = bundle.candidates?.[speaker]?.[canonical.csv_row_id];
    const ipa = canonicalRealizationIpa(candidate, canonical.realization_index) ?? candidate?.ipa;
    if (typeof ipa === "string" && ipa.length > 0) return ipa;
  }
  const byRow = bundle.candidates?.[speaker] ?? {};
  for (const rowId of bundle.row_ids) {
    const ipa = byRow[rowId]?.ipa;
    if (typeof ipa === "string" && ipa.length > 0) return ipa;
  }
  return fallbackIpa && fallbackIpa.length > 0 ? fallbackIpa : null;
}

function linkMatchesBucket(link: ConceptSurveyLinks | undefined, bucket: CompareBucket): boolean {
  if (!link) return false;
  return Object.entries(link).some(([surveyId, sourceItem]) => surveyId.toLowerCase() === bucket.survey_id && String(sourceItem) === bucket.source_item);
}

function findBucketByLink(bundle: CompareBundle, link: ConceptSurveyLinks | undefined): CompareBucket | null {
  if (!link) return null;
  return bundle.buckets.find((bucket) => linkMatchesBucket(link, bucket)) ?? null;
}

export function resolveActiveBucketForSpeaker(bundle: CompareBundle, speaker: string): CompareBucket | null {
  const speakerRows = bundle.speaker_concept_survey_links?.[speaker] ?? {};
  for (const rowId of bundle.row_ids) {
    const bucket = findBucketByLink(bundle, speakerRows[rowId]);
    if (bucket) return bucket;
  }

  const choices = bundle.speaker_choices?.[speaker] ?? {};
  for (const key of [bundle.bundle_id, bundle.label, ...bundle.row_ids]) {
    const chosenSurvey = choices[key]?.toLowerCase();
    if (!chosenSurvey) continue;
    const bucket = bundle.buckets.find((b) => b.survey_id === chosenSurvey);
    if (bucket) return bucket;
  }

  for (const rowId of bundle.row_ids) {
    const bucket = findBucketByLink(bundle, bundle.concept_survey_links?.[rowId]);
    if (bucket) return bucket;
  }

  return bundle.buckets[0] ?? null;
}

export function migrateCanonicalRealizationToSelection(
  legacyIdx: number,
  bundle: CompareBundle,
  speaker: string,
  selectedAt = "",
): CanonicalLexemeSelection | null {
  if (!Number.isInteger(legacyIdx) || legacyIdx < 0) return null;
  const variants = enumerateVariants(bundle);
  if (legacyIdx >= variants.length) return null;
  const candidateRows = candidateEntries(bundle, speaker).map(([rowId]) => rowId);
  if (candidateRows.length > 0 && !candidateRows.includes(variants[legacyIdx].variant.csv_row_id)) return null;
  const { bucket, variant } = variants[legacyIdx];
  return {
    csv_row_id: variant.csv_row_id,
    survey_id: variant.survey_id ?? bucket.survey_id,
    source_item: variant.source_item ?? bucket.source_item,
    bucket_key: bucket.bucket_key,
    realization_index: legacyIdx,
    source: "migration:canonical_realizations",
    selected_at: selectedAt,
  };
}
