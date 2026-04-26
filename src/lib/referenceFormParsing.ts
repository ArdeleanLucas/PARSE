function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

interface ConceptLike {
  key: string;
  name: string;
}

// ---------------------------------------------------------------------------
// Reference-form parsing + classification (display-only; no transliteration)
// ---------------------------------------------------------------------------
// The Reference Forms panel renders every form the providers wrote for a
// (concept, language), letting the user pick which ones contribute to the
// similarity score. The functions below are pure *display* helpers: they
// never transliterate script to IPA. A bare string is routed to either the
// ``script`` slot or the ``ipa`` slot based on a conservative Unicode-range
// check, and the raw text is preserved verbatim. See ``classifyRawFormString``
// for the allowed non-Latin scripts. No character substitution happens
// anywhere in this pipeline.

// Unicode blocks we explicitly recognise as "not IPA" for display tagging
// when no per-language script hint is available. A bare string containing
// any char in these blocks is routed to the script slot; everything else
// (Latin + IPA extensions + diacritics) goes to the ipa slot. Greek is
// deliberately *not* in this set because IPA uses several Greek-block
// letters (β, χ, θ, ɣ, ɸ) and a string of phonetic ɣaβa would otherwise
// be misclassified -- Greek-script languages should rely on the
// per-language ISO 15924 script hint instead. This is a tag, not a
// transformation; the raw text is preserved as-is in whichever slot it
// lands.
const NON_LATIN_SCRIPT_RE = /[\u0400-\u04FF\u0500-\u052F\u0530-\u058F\u0590-\u05FF\u0600-\u06FF\u0700-\u074F\u0750-\u077F\u07C0-\u07FF\u0780-\u07BF\u0900-\u097F\u0980-\u09FF\u0A00-\u0A7F\u0A80-\u0AFF\u0B00-\u0B7F\u0B80-\u0BFF\u0C00-\u0C7F\u0C80-\u0CFF\u0D00-\u0D7F\u0D80-\u0DFF\u0E00-\u0E7F\u0E80-\u0EFF\u0F00-\u0FFF\u1000-\u109F\u10A0-\u10FF\u1100-\u11FF\u1200-\u137F\u1780-\u17FF\u4E00-\u9FFF\u3040-\u30FF\uAC00-\uD7AF\uFB50-\uFDFF\uFE70-\uFEFF]/;

// ISO 15924 codes that mean "Latin script" -- these should route to the
// IPA slot (since Latin-script languages submitting IPA forms is the
// happy path). The rest of the world's scripts route to the script slot
// when the hint is present.
const LATIN_SCRIPT_HINTS = new Set(['Latn', 'latn']);

/** Classify a bare reference-form string as script vs IPA for display.
 *  Display hint only -- the returned object always carries the *same*
 *  raw text in whichever slot it lands. No transliteration ever happens
 *  here.
 *
 *  When ``scriptHint`` is given (an ISO 15924 code from the SIL catalog
 *  or per-language config), the routing is deterministic: Latn -> IPA,
 *  anything else -> script. This is the preferred path because
 *  languages almost always commit to one script and the hint avoids
 *  edge cases the Unicode regex can't disambiguate (e.g. Greek IPA
 *  letters vs Greek-script forms).
 *
 *  Without a hint, falls back to the Unicode-block regex: any char in
 *  ``NON_LATIN_SCRIPT_RE`` -> script slot; otherwise IPA slot. */
function classifyRawFormString(raw: string, scriptHint?: string | null): { script: string; ipa: string } {
  const trimmed = raw.trim();
  if (!trimmed) return { script: '', ipa: '' };
  if (scriptHint) {
    if (LATIN_SCRIPT_HINTS.has(scriptHint)) {
      return { script: '', ipa: trimmed };
    }
    return { script: trimmed, ipa: '' };
  }
  if (NON_LATIN_SCRIPT_RE.test(trimmed)) {
    return { script: trimmed, ipa: '' };
  }
  return { script: '', ipa: trimmed };
}

export interface ReferenceFormEntry {
  /** Exact raw source string. Used as the stable selection key so
   *  ``_meta.form_selections`` persists verbatim across reloads. */
  raw: string;
  script: string;
  ipa: string;
  audioUrl: string | null;
  /** Provenance sources when available (``wikidata``, ``asjp``, ...).
   *  Empty for bare-string legacy entries and rolled-up non-provenance
   *  shapes that had no explicit source list. */
  sources: string[];
}

function _parseOneEntry(raw: unknown, scriptHint?: string | null): ReferenceFormEntry | null {
  if (typeof raw === 'string') {
    const trimmed = raw.trim();
    if (!trimmed) return null;
    const { script, ipa } = classifyRawFormString(trimmed, scriptHint);
    return { raw: trimmed, script, ipa, audioUrl: null, sources: [] };
  }

  if (!isRecord(raw)) return null;

  // Provenance shape: { form: <string>, sources: [<provider>, ...] }.
  // The ``form`` value is the verbatim provider output; we still tag it
  // by script hint / Unicode range so e.g. an LLM response that slipped
  // into Arabic script doesn't display in the IPA slot.
  if (typeof raw.form === 'string' && Array.isArray(raw.sources)) {
    const trimmed = (raw.form as string).trim();
    if (!trimmed) return null;
    const sources = (raw.sources as unknown[]).filter((s): s is string => typeof s === 'string');
    const { script, ipa } = classifyRawFormString(trimmed, scriptHint);
    const audioUrl = typeof raw.audioUrl === 'string' && raw.audioUrl.trim() ? raw.audioUrl : null;
    return { raw: trimmed, script, ipa, audioUrl, sources };
  }

  // Structured provider objects with explicit field labels. Trust the
  // label: if the provider wrote ``ipa: "foo"`` we display "foo" as IPA
  // even if it contains script-range chars -- that's their claim, and
  // it overrides the per-language script hint too.
  const scriptVal = [raw.script, raw.orthography, raw.text].find(
    (v) => typeof v === 'string' && (v as string).trim().length > 0,
  ) as string | undefined;
  const ipaVal = [raw.ipa, raw.phonetic, raw.transcription].find(
    (v) => typeof v === 'string' && (v as string).trim().length > 0,
  ) as string | undefined;
  const audioUrl = [raw.audioUrl, raw.audio, raw.url].find(
    (v) => typeof v === 'string' && (v as string).trim().length > 0,
  ) as string | undefined;

  // A bare ``form`` field with no sources array -- treat as a generic
  // string and classify (matches the bare-string path).
  if (!scriptVal && !ipaVal && typeof raw.form === 'string' && (raw.form as string).trim()) {
    const trimmed = (raw.form as string).trim();
    const { script, ipa } = classifyRawFormString(trimmed, scriptHint);
    return {
      raw: trimmed,
      script,
      ipa,
      audioUrl: audioUrl ?? null,
      sources: [],
    };
  }

  if (!scriptVal && !ipaVal) return null;

  // Selection keys against structured objects prefer the IPA text (it's
  // the canonical similarity-scoring string), falling back to script.
  const rawKey = (ipaVal ?? scriptVal ?? '').trim();
  if (!rawKey) return null;

  return {
    raw: rawKey,
    script: scriptVal ?? '',
    ipa: ipaVal ?? '',
    audioUrl: audioUrl ?? null,
    sources: [],
  };
}

/** Parse any provider-shaped reference data into an ordered list of
 *  display entries. Accepts the legacy string/array/object shapes the
 *  Reference Forms pipeline has seen. Duplicates (by raw text) collapse
 *  so a form fetched by multiple providers shows up once.
 *
 *  ``scriptHint`` is an ISO 15924 code (Arab, Latn, ...) attached to the
 *  language this concept belongs to. When present, bare strings route
 *  deterministically to the script vs IPA slot; explicit ``ipa``/``script``
 *  field labels still override (we trust the provider's claim). */
export function parseReferenceFormList(raw: unknown, scriptHint?: string | null): ReferenceFormEntry[] {
  const out: ReferenceFormEntry[] = [];
  const seen = new Set<string>();
  const push = (entry: ReferenceFormEntry | null) => {
    if (!entry || seen.has(entry.raw)) return;
    seen.add(entry.raw);
    out.push(entry);
  };
  if (Array.isArray(raw)) {
    for (const item of raw) push(_parseOneEntry(item, scriptHint));
  } else {
    push(_parseOneEntry(raw, scriptHint));
  }
  return out;
}

/** List-shaped resolver that preserves every
 *  provider-returned form instead of collapsing to the first one. Drives
 *  the Reference Forms panel's multi-form display + selection UI. Keyed
 *  by primary contact-language code; absent codes mean no populated
 *  forms were found (or the fallback SIL entry was empty too).
 *
 *  ``scriptByCode`` maps each language code to its ISO 15924 script
 *  hint (when known). The hint is propagated into ``parseReferenceFormList``
 *  so bare-string entries route deterministically to the script vs IPA
 *  slot per language, instead of relying on the Unicode-block heuristic. */
export function resolveReferenceFormLists(
  enrichments: Record<string, unknown>,
  silConcepts: Record<string, Record<string, unknown>>,
  concept: ConceptLike,
  codes: readonly string[],
  scriptByCode?: Readonly<Record<string, string | null | undefined>>,
): Record<string, ReferenceFormEntry[]> {
  const root = isRecord(enrichments.reference_forms) ? enrichments.reference_forms as Record<string, unknown> : null;
  const conceptEntry = root ? root[concept.key] ?? root[concept.name] : null;
  const conceptRecord = isRecord(conceptEntry) ? conceptEntry : {};

  const out: Record<string, ReferenceFormEntry[]> = {};
  for (const code of codes) {
    const hint = scriptByCode?.[code] ?? null;
    const primary = parseReferenceFormList(conceptRecord[code], hint);
    if (primary.length > 0) {
      out[code] = primary;
      continue;
    }
    const silForConcept = silConcepts[code]?.[concept.name];
    const fallback = parseReferenceFormList(silForConcept, hint);
    if (fallback.length > 0) out[code] = fallback;
  }
  return out;
}

/** Read the user's persisted form-selection allow-list for one
 *  (concept, lang) out of ``clefStatus.meta.form_selections``. Returns
 *  ``null`` when no explicit selection exists for that pair -- the
 *  caller should treat that as "every populated form is selected"
 *  (the default). Returns ``[]`` for explicit opt-out. */
export function resolveFormSelection(
  clefMeta: Record<string, unknown> | null | undefined,
  conceptEn: string,
  langCode: string,
): string[] | null {
  const selections = clefMeta && isRecord(clefMeta.form_selections)
    ? (clefMeta.form_selections as Record<string, unknown>)
    : null;
  if (!selections) return null;
  const perConcept = selections[conceptEn];
  if (!isRecord(perConcept)) return null;
  const entry = perConcept[langCode];
  if (!Array.isArray(entry)) return null;
  return entry.filter((v): v is string => typeof v === 'string');
}

/** Map a language code to a display tone + text direction for the
 *  Reference Forms cards. Known RTL scripts get `dir="rtl"`; the tone
 *  cycles over a short palette so two configured primaries always look
 *  distinct. Falls back to a neutral tone + LTR for anything we don't
 *  recognise -- good enough until the catalog ships script metadata. */
const RTL_CODES = new Set([
  'ar', 'arc', 'ara',
  'fa', 'pes', 'prs',
  'he', 'heb',
  'ur', 'urd',
  'ckb', 'sdh', 'sor',
  'ps', 'pus', 'pbt',
  'syr',
]);
const CARD_TONES = [
  'text-rose-500',
  'text-indigo-500',
  'text-emerald-500',
  'text-amber-600',
];

export function referenceCardStyle(code: string, idx: number): { tone: string; dir: 'ltr' | 'rtl' } {
  return {
    tone: CARD_TONES[idx % CARD_TONES.length],
    dir: RTL_CODES.has(code.toLowerCase()) ? 'rtl' : 'ltr',
  };
}
