import type { AnnotationInterval, AnnotationRecord, Tag as StoreTag } from '../api/types';

export type ConceptTag = 'untagged' | 'review' | 'confirmed' | 'problematic';

const REVIEW_TAG_IDS = new Set(['review', 'review-needed']);
const REGEX_SPECIAL_CHARS = new Set(["\\", ".", "*", "+", "?", "^", "$", "{", "}", "(", ")", "|", "[", "]"]);

/** Render a number of seconds as ``MM:SS.cs`` — the same format the
 *  Annotate playback bar shows under the waveform. Lifted to module
 *  scope so the offset-capture toast + manual-anchor chips can mirror
 *  it exactly (so users can verify what was captured against the
 *  readout they were just looking at). */
export function isInteractiveHotkeyTarget(target: EventTarget | null): boolean {
  if (!(target instanceof Element)) return false;
  const tag = target.tagName.toLowerCase();
  if (tag === 'input' || tag === 'textarea' || tag === 'select' || tag === 'button') return true;
  return Boolean((target as HTMLElement).isContentEditable);
}

export function overlaps(a: AnnotationInterval, b: AnnotationInterval): boolean {
  return a.start <= b.end && b.start <= a.end;
}

export interface AssetUrlOptions {
  dev?: boolean;
  apiTarget?: string;
}

const DEFAULT_PARSE_API_TARGET = typeof __PARSE_API_TARGET__ === 'string'
  ? __PARSE_API_TARGET__.replace(/\/$/, '')
  : '';

export function resolveAssetUrl(path: string, options: AssetUrlOptions = {}): string {
  if (!path) return '';
  const normalizedPath = path.startsWith('/') ? path : `/${path.replace(/^\/+/, '')}`;
  const dev = options.dev ?? import.meta.env.DEV;
  const apiTarget = (options.apiTarget ?? DEFAULT_PARSE_API_TARGET).replace(/\/$/, '');
  if (!dev || !apiTarget || /^https?:\/\//i.test(normalizedPath)) {
    return normalizedPath;
  }
  return `${apiTarget}${normalizedPath}`;
}

// Build a workspace-relative audio URL from an annotation record. Server serves
// static files from the project root, so "audio/working/X/foo.wav" → "/audio/working/X/foo.wav".
export function deriveAudioUrl(
  record: AnnotationRecord | null | undefined,
  options: AssetUrlOptions = {},
): string {
  const raw = (record?.source_audio ?? record?.source_wav ?? '').trim();
  if (!raw) return '';
  const cleaned = raw.replace(/\\/g, '/').replace(/^\/+/, '');
  return resolveAssetUrl('/' + cleaned, options);
}

export function conceptMatchesIntervalText(
  concept: { id?: number | string; name: string; key: string },
  text: string,
  intervalConceptId?: string | number | null,
): boolean {
  if (intervalConceptId != null && intervalConceptId !== '' && concept.id != null) {
    return String(intervalConceptId) === String(concept.id);
  }

  const normalizedText = text.trim().toLowerCase();
  const normalizedName = concept.name.trim().toLowerCase();
  const normalizedKey = concept.key.trim().toLowerCase();

  if (normalizedText === normalizedName) return true;
  if (normalizedText === normalizedKey) return true;
  if (!normalizedName) return false;

  const escapedName = Array.from(normalizedName, (char) => REGEX_SPECIAL_CHARS.has(char) ? `\\${char}` : char).join('');
  return new RegExp(`\\b${escapedName}\\b`).test(normalizedText);
}

export function getConceptStatus(tags: StoreTag[]): ConceptTag {
  if (tags.some((tag) => tag.id === 'problematic')) return 'problematic';
  if (tags.some((tag) => tag.id === 'confirmed')) return 'confirmed';
  if (tags.some((tag) => REVIEW_TAG_IDS.has(tag.id))) return 'review';
  return 'untagged';
}

// Prefer word-level ortho_words (from Tier-2 forced alignment) over the
// coarse ortho tier. When the coarse tier is one monolithic segment — as
// razhan often produces on long elicited word-list recordings — picking
// the whole-paragraph interval by overlap dumps the entire narrative into
// a single lexeme field. The word-level tier yields a single clean word.
export function pickOrthoIntervalForConcept(
  record: AnnotationRecord,
  conceptInterval: AnnotationInterval,
): AnnotationInterval | null {
  const words = record.tiers.ortho_words?.intervals ?? [];
  if (words.length) {
    const contained = words.find(
      (iv) => iv.start >= conceptInterval.start && iv.end <= conceptInterval.end,
    );
    if (contained) return contained;

    let bestOverlap = 0;
    let bestWord: AnnotationInterval | null = null;
    for (const iv of words) {
      if (iv.end <= conceptInterval.start || iv.start >= conceptInterval.end) continue;
      const ov = Math.min(iv.end, conceptInterval.end) - Math.max(iv.start, conceptInterval.start);
      if (ov > bestOverlap) {
        bestOverlap = ov;
        bestWord = iv;
      }
    }
    if (bestWord) return bestWord;
  }
  return (record.tiers.ortho?.intervals ?? []).find((iv) => overlaps(iv, conceptInterval)) ?? null;
}

export function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

export function readTextBlob(blob: Blob): Promise<string> {
  return new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result ?? ''));
    reader.onerror = () => reject(reader.error);
    reader.readAsText(blob);
  });
}
