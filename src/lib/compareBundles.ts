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
  if (!csvRowId || !surveyId || !sourceItem) return null;
  return {
    csv_row_id: csvRowId,
    concept_key: cleanString(raw.concept_key ?? raw.conceptKey) || undefined,
    label: cleanString(raw.label) || undefined,
    variant_label: cleanString(raw.variant_label ?? raw.variantLabel) || undefined,
    survey_id: surveyId,
    source_item: sourceItem,
    bucket_key: cleanString(raw.bucket_key ?? raw.bucketKey) || bucketKey(surveyId, sourceItem),
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
  return {
    csv_row_id: cleanString(raw.csv_row_id ?? raw.csvRowId) || csvRowId,
    speaker: cleanString(raw.speaker) || undefined,
    form: typeof raw.form === "string" ? raw.form : null,
    ipa: typeof raw.ipa === "string" || raw.ipa === null ? raw.ipa : undefined,
    ortho: typeof raw.ortho === "string" || raw.ortho === null ? raw.ortho : undefined,
    start: typeof raw.start === "number" || raw.start === null ? raw.start : undefined,
    end: typeof raw.end === "number" || raw.end === null ? raw.end : undefined,
    realization_index: typeof raw.realization_index === "number" ? raw.realization_index : undefined,
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
  const label = cleanString(raw.label);
  if (!bundleId || !label || buckets.length === 0) return null;
  return {
    bundle_id: bundleId,
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
  return Object.entries(byRow).filter((entry): entry is [string, CompareCandidate] => entry[1] !== null && entry[1].form !== null);
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
    survey_id: entry.variant.survey_id,
    source_item: entry.variant.source_item,
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
    survey_id: variant.survey_id,
    source_item: variant.source_item,
    bucket_key: bucket.bucket_key,
    realization_index: legacyIdx,
    source: "migration:canonical_realizations",
    selected_at: selectedAt,
  };
}
