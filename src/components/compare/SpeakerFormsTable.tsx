import {
  AlertCircle,
  ArrowUpDown,
  CheckCircle2,
  ChevronRight,
  Flag,
  Pause,
  Play,
  SquareArrowOutUpRight,
} from 'lucide-react';
import {
  Fragment,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent,
  type MouseEvent,
} from 'react';
import { deleteCanonicalLexeme, putCanonicalLexeme } from '../../api/client';
import { saveEnrichments, saveLexemeNote } from '../../api/contracts/enrichments-tags-notes-imports';
import { mediaUrlFromSourceWav, spectrogramUrl } from '../../api/contracts/export-and-media';
import type {
  CanonicalLexemeSelection,
  CompareBundle,
  CompareCandidate,
} from '../../api/types';
import {
  canonicalFor,
  collapsedIpaForSpeaker,
  resolveActiveBucketForSpeaker,
} from '../../lib/compareBundles';
import type { SpeakerForm } from '../../lib/speakerForm';
import { useEnrichmentStore } from '../../stores/enrichmentStore';
import { VariantChip } from '../shared/VariantChip';
import { CognateCell, SimBar } from './CognateCell';

// Verbatim from CanonicalPicker.tsx:7-13 — keeps repair_hint extraction behaviour identical.
function errorMessage(error: unknown): string {
  if (error instanceof Error) {
    const match = error.message.match(/repair_hint["']?\s*[:=]\s*["']([^"']+)/i);
    return match?.[1] ?? error.message;
  }
  return 'Could not save canonical lexeme.';
}

export interface SpeakerFormsTableVariant {
  csv_row_id: string;
  label: string;          // variant_label ?? concept_en ?? label ?? csv_row_id
  letter: string;
  ipa: string | null;     // candidate.ipa
  ortho: string | null;   // candidate.ortho
  source_wav: string | null;
  start_sec: number | null;
  end_sec: number | null;
}

export interface SpeakerFormsTableProps {
  bundle: CompareBundle;
  speakers: string[];
  speakerForms?: SpeakerForm[];
  primaryContactCodes: string[];
  contactLanguageNames?: Record<string, string>;
  conceptKey: string;
  initialExpandedSpeaker?: string;
  onBundleUpdated?: (bundle: CompareBundle) => void;
  onCycleCognate?: (speaker: string, current: string) => void;
  onResetCognate?: (speaker: string) => void;
  onToggleSpeakerFlag?: (speaker: string, current: boolean) => void;
  onOpenInAnnotate?: (speaker: string, variant: SpeakerFormsTableVariant) => void;
}

type SortState = 'unsorted' | 'desc' | 'asc';
type SortMode = { state: SortState; code: string | null };

interface FilterState {
  flaggedOnly: boolean;
  noCanonical: boolean;
  multiVariantOnly: boolean;
}

const EMPTY_FILTERS: FilterState = {
  flaggedOnly: false,
  noCanonical: false,
  multiVariantOnly: false,
};

function buildVariantList(bundle: CompareBundle, speaker: string): SpeakerFormsTableVariant[] {
  const variants = resolveActiveBucketForSpeaker(bundle, speaker)?.variants ?? [];
  return variants
    .filter((variant) => bundle.candidates?.[speaker]?.[variant.csv_row_id])
    .map((variant) => {
      const candidate = bundle.candidates?.[speaker]?.[variant.csv_row_id] ?? null;
      const label = variant.variant_label ?? variant.concept_en ?? variant.label ?? variant.csv_row_id;
      const letterFromLabel = variant.label?.match(/\(([A-Z])\)/)?.[1] ?? '';
      const letter = letterFromLabel || (/^[A-Z]$/.test(variant.variant_label ?? '') ? variant.variant_label! : '');
      return {
        csv_row_id: variant.csv_row_id,
        label,
        letter,
        ipa: candidate?.ipa ?? null,
        ortho: candidate?.ortho ?? null,
        source_wav: candidate?.source_wav ?? null,
        start_sec: candidate?.start_sec ?? null,
        end_sec: candidate?.end_sec ?? null,
      } satisfies SpeakerFormsTableVariant;
    });
}

function readLexemeUserNote(
  data: Record<string, unknown> | null | undefined,
  speaker: string,
  conceptKey: string,
): string {
  const block = data?.lexeme_notes;
  if (!block || typeof block !== 'object') return '';
  const speakerBlock = (block as Record<string, unknown>)[speaker];
  if (!speakerBlock || typeof speakerBlock !== 'object') return '';
  const entry = (speakerBlock as Record<string, unknown>)[conceptKey];
  if (!entry || typeof entry !== 'object') return '';
  const note = (entry as Record<string, unknown>).user_note;
  return typeof note === 'string' ? note : '';
}

function readLexemeNoteBlock(
  data: Record<string, unknown> | null | undefined,
  speaker: string,
  conceptKey: string,
): Record<string, unknown> {
  const block = data?.lexeme_notes;
  if (!block || typeof block !== 'object') return {};
  const speakerBlock = (block as Record<string, unknown>)[speaker];
  if (!speakerBlock || typeof speakerBlock !== 'object') return {};
  const entry = (speakerBlock as Record<string, unknown>)[conceptKey];
  return entry && typeof entry === 'object' ? (entry as Record<string, unknown>) : {};
}

interface CompareNotesTextareaProps {
  speaker: string;
  conceptKey: string;
}

function CompareNotesTextarea({ speaker, conceptKey }: CompareNotesTextareaProps) {
  const dataFromStore = useEnrichmentStore((s) => s.data) as Record<string, unknown> | null;
  const initialNote = useMemo(
    () => readLexemeUserNote(dataFromStore, speaker, conceptKey),
    [dataFromStore, speaker, conceptKey],
  );
  const [userNote, setUserNote] = useState(initialNote);
  const [noteStatus, setNoteStatus] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle');
  const [noteError, setNoteError] = useState<string | null>(null);
  const focusedRef = useRef(false);
  const initialNoteRef = useRef(initialNote);
  const latestNoteRef = useRef(userNote);

  useEffect(() => {
    latestNoteRef.current = userNote;
  }, [userNote]);

  // Sync from store when external changes land — but only when the textarea
  // is not currently focused, to avoid yanking the value from under the user.
  useEffect(() => {
    if (focusedRef.current) return;
    setUserNote(initialNote);
    initialNoteRef.current = initialNote;
  }, [initialNote]);

  const handleSaveNote = useCallback(async () => {
    const noteToSave = latestNoteRef.current;
    setNoteStatus('saving');
    setNoteError(null);
    try {
      await saveLexemeNote({ speaker, concept_id: conceptKey, user_note: noteToSave });
      const existingBlock = readLexemeNoteBlock(
        useEnrichmentStore.getState().data as Record<string, unknown> | null,
        speaker,
        conceptKey,
      );
      await saveEnrichments({
        lexeme_notes: {
          [speaker]: {
            [conceptKey]: {
              ...existingBlock,
              user_note: noteToSave,
              updated_at: new Date().toISOString(),
            },
          },
        },
      });
      initialNoteRef.current = noteToSave;
      setNoteStatus('saved');
    } catch (err) {
      setNoteError(err instanceof Error ? err.message : 'Save failed');
      setNoteStatus('error');
    }
  }, [speaker, conceptKey]);

  // Save on unmount when there are unsaved edits. This catches the
  // type-then-Prev/Next case where the textarea unmounts before blur fires.
  useEffect(() => {
    return () => {
      if (latestNoteRef.current !== initialNoteRef.current) {
        void handleSaveNote();
      }
    };
  }, [handleSaveNote]);

  return (
    <div className="rounded-xl border border-slate-200 bg-white px-4 py-3">
      <label className="text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-500">
        Compare notes · {speaker}
      </label>
      <textarea
        data-testid={`lexeme-user-note-${speaker}-${conceptKey}`}
        value={userNote}
        onChange={(e) => {
          setUserNote(e.target.value);
          setNoteStatus('idle');
        }}
        onFocus={() => {
          focusedRef.current = true;
        }}
        onBlur={() => {
          focusedRef.current = false;
          void handleSaveNote();
        }}
        placeholder="Add notes specific to this speaker/lexeme — saved on blur."
        className="mt-2 min-h-[72px] w-full resize-y rounded-lg border border-slate-200 bg-slate-50/70 px-3 py-2 text-sm text-slate-800 placeholder:text-slate-300 focus:border-indigo-300 focus:bg-white focus:outline-none focus:ring-4 focus:ring-indigo-50"
      />
      <div className="mt-1 text-[10px]">
        {noteStatus === 'saving' && <span className="text-slate-500">Saving…</span>}
        {noteStatus === 'saved' && <span className="text-emerald-600">saved</span>}
        {noteStatus === 'error' && (
          <span className="text-rose-600">{noteError ?? 'save failed'}</span>
        )}
        {noteStatus === 'idle' && <span className="text-transparent">·</span>}
      </div>
    </div>
  );
}

interface VariantCardProps {
  speaker: string;
  bundle: CompareBundle;
  variant: SpeakerFormsTableVariant;
  candidate: CompareCandidate | null;
  isCanonical: boolean;
  isPlaying: boolean;
  playError?: string | null;
  onPlayToggle: (variant: SpeakerFormsTableVariant) => void;
  onCanonicalSelect: (variant: SpeakerFormsTableVariant) => void;
  onOpenInAnnotate: (variant: SpeakerFormsTableVariant) => void;
}

function VariantCard({
  speaker,
  bundle,
  variant,
  candidate,
  isCanonical,
  isPlaying,
  playError,
  onPlayToggle,
  onCanonicalSelect,
  onOpenInAnnotate,
}: VariantCardProps) {
  const [showSpec, setShowSpec] = useState(false);
  const [specErrored, setSpecErrored] = useState(false);
  const hasAudio = !!candidate?.source_wav
    && typeof candidate.start_sec === 'number'
    && typeof candidate.end_sec === 'number';
  const specUrl = hasAudio
    ? spectrogramUrl({
        speaker,
        startSec: candidate!.start_sec as number,
        endSec: candidate!.end_sec as number,
        audio: candidate!.source_wav ?? undefined,
      })
    : '';

  return (
    <div
      className="rounded-lg border border-slate-200 bg-white p-3"
      data-testid={`variant-card-${speaker}-${variant.csv_row_id}`}
    >
      <div className="flex items-start gap-3">
        <label
          className="mt-0.5 inline-flex cursor-pointer items-center"
          data-testid={`canonical-option-${speaker}-${variant.csv_row_id}`}
        >
          <input
            type="radio"
            name={`canonical-${bundle.bundle_id}-${speaker}`}
            checked={isCanonical}
            onChange={() => onCanonicalSelect(variant)}
            // Re-clicking an already-checked radio confirms a default
            // (auto-picked) selection by promoting it to manual. React
            // skips onChange when checked is unchanged, so wire onClick too.
            onClick={() => {
              if (isCanonical) onCanonicalSelect(variant);
            }}
            className="h-3.5 w-3.5 accent-indigo-600"
            aria-label={`Choose canonical lexeme ${variant.label} for ${speaker}`}
          />
        </label>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-baseline gap-2" data-testid={`variant-card-header-${speaker}-${variant.csv_row_id}`}>
            {variant.letter && <VariantChip letter={variant.letter} />}
            {variant.ipa && (
              <span className="font-mono text-[13px] text-indigo-700">/{variant.ipa}/</span>
            )}
            {variant.ipa && variant.ortho && <span className="text-slate-400" aria-hidden>·</span>}
            {variant.ortho && (
              <span className="font-serif text-[14px] text-slate-700">
                {variant.ortho}
              </span>
            )}
            {isCanonical && (
              <span
                className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2 py-0.5 text-[10px] font-semibold text-emerald-700 ring-1 ring-emerald-100"
                data-testid={`variant-canonical-badge-${speaker}-${variant.csv_row_id}`}
              >
                <CheckCircle2 className="h-2.5 w-2.5" /> canonical
              </span>
            )}
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-1.5">
          <button
            type="button"
            data-testid={`variant-play-${speaker}-${variant.csv_row_id}`}
            disabled={!hasAudio}
            onClick={(e) => {
              e.stopPropagation();
              onPlayToggle(variant);
            }}
            title={isPlaying ? 'Pause' : 'Play'}
            className="inline-flex h-6 w-6 items-center justify-center rounded-md bg-slate-900 text-white hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-30"
          >
            {isPlaying ? (
              <Pause className="h-3 w-3" />
            ) : (
              <Play className="h-3 w-3 translate-x-[1px]" />
            )}
          </button>
          <button
            type="button"
            data-testid={`variant-spec-${speaker}-${variant.csv_row_id}`}
            disabled={!hasAudio}
            onClick={(e) => {
              e.stopPropagation();
              setShowSpec((v) => !v);
              setSpecErrored(false);
            }}
            title={showSpec ? 'Hide spectrogram' : 'Show spectrogram'}
            className="inline-flex h-6 items-center gap-1 rounded-md border border-slate-200 bg-white px-2 text-[10px] font-semibold text-slate-600 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {showSpec ? 'Hide spec' : 'Spec'}
          </button>
          <button
            type="button"
            data-testid={`variant-open-annotate-${speaker}-${variant.csv_row_id}`}
            onClick={(e) => {
              e.stopPropagation();
              onOpenInAnnotate(variant);
            }}
            title="Open in annotate"
            className="inline-flex h-6 items-center gap-1 rounded-md border border-slate-200 bg-white px-2 text-[10px] font-semibold text-slate-600 hover:bg-slate-50"
          >
            <SquareArrowOutUpRight className="h-3 w-3" />
          </button>
        </div>
      </div>
      {playError && (
        <div
          className="mt-2 rounded border border-rose-200 bg-rose-50 px-2 py-1 text-[11px] text-rose-700"
          data-testid={`variant-play-error-${speaker}-${variant.csv_row_id}`}
        >
          Playback failed: {playError}
        </div>
      )}
      {showSpec && hasAudio && (
        <div className="mt-3" data-testid={`variant-spec-image-${speaker}-${variant.csv_row_id}`}>
          {specErrored ? (
            <div className="rounded border border-slate-200 bg-slate-50 px-3 py-4 text-center text-[11px] text-slate-500">
              spectrogram unavailable
            </div>
          ) : (
            <img
              src={specUrl}
              loading="lazy"
              alt={`spectrogram for ${speaker} ${(candidate!.start_sec as number).toFixed(2)}–${(candidate!.end_sec as number).toFixed(2)}`}
              onError={() => setSpecErrored(true)}
              className="block w-full rounded border border-slate-200 bg-white"
            />
          )}
          <div className="mt-1 break-all font-mono text-[10px] text-slate-400">{specUrl}</div>
        </div>
      )}
    </div>
  );
}

interface ExpandedPanelProps {
  speaker: string;
  bundle: CompareBundle;
  conceptKey: string;
  onBundleUpdated?: (bundle: CompareBundle) => void;
  onOpenInAnnotate: (speaker: string, variant: SpeakerFormsTableVariant) => void;
}

function ExpandedPanel({
  speaker,
  bundle,
  conceptKey,
  onBundleUpdated,
  onOpenInAnnotate,
}: ExpandedPanelProps) {
  const variants = useMemo(() => buildVariantList(bundle, speaker), [bundle, speaker]);
  const current = canonicalFor(bundle, speaker);
  const [error, setError] = useState<string | null>(null);
  const [playingVariantId, setPlayingVariantId] = useState<string | null>(null);
  const [playErrorByVariant, setPlayErrorByVariant] = useState<Record<string, string>>({});
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const rafRef = useRef<number | null>(null);
  const currentSrcRef = useRef<string>('');
  const playRequestIdRef = useRef(0);
  const pendingListenersCleanupRef = useRef<(() => void) | null>(null);

  const clearPendingListeners = useCallback(() => {
    pendingListenersCleanupRef.current?.();
    pendingListenersCleanupRef.current = null;
  }, []);

  const cancelRaf = useCallback(() => {
    if (rafRef.current !== null) {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    }
  }, []);

  // Cleanup audio + rAF on unmount.
  useEffect(() => {
    return () => {
      playRequestIdRef.current += 1;
      clearPendingListeners();
      cancelRaf();
      const audio = audioRef.current;
      if (audio) {
        try {
          audio.pause();
        } catch {
          /* noop */
        }
      }
    };
  }, [cancelRaf, clearPendingListeners]);

  const handlePlayToggle = useCallback(
    (variant: SpeakerFormsTableVariant) => {
      if (!variant.source_wav || typeof variant.start_sec !== 'number' || typeof variant.end_sec !== 'number') {
        return;
      }
      let audio = audioRef.current;
      if (!audio) {
        audio = new Audio();
        audio.preload = 'auto';
        audioRef.current = audio;
      }
      const requestId = ++playRequestIdRef.current;
      clearPendingListeners();
      // Toggle off when the same variant is already playing.
      if (playingVariantId === variant.csv_row_id) {
        cancelRaf();
        try {
          audio.pause();
        } catch {
          /* noop */
        }
        setPlayingVariantId(null);
        return;
      }
      const desiredSrc = mediaUrlFromSourceWav(variant.source_wav, { speaker });
      const endTime = variant.end_sec;
      const startTime = variant.start_sec;
      cancelRaf();
      try {
        audio.pause();
      } catch {
        /* noop */
      }
      // Clear prior error for this variant when retrying.
      setPlayErrorByVariant((prev) => {
        if (!(variant.csv_row_id in prev)) return prev;
        const next = { ...prev };
        delete next[variant.csv_row_id];
        return next;
      });

      // Bug 3 (Lucas, MC-388-A): the previous implementation set
      // `audio.currentTime = startTime` synchronously before metadata had
      // loaded, which throws InvalidStateError on a fresh src. The error
      // was swallowed and `audio.play()` then began at 0 (silent) — making
      // the button appear dead. Seek inside `loadedmetadata` and surface
      // `play()` rejections to the user via per-variant error state.
      const srcChanged = currentSrcRef.current !== desiredSrc;
      if (srcChanged) {
        audio.src = desiredSrc;
        currentSrcRef.current = desiredSrc;
      }
      const seekAndPlay = () => {
        const a = audioRef.current;
        if (!a) return;
        try {
          a.currentTime = startTime;
        } catch (err) {
          // Final fallback — should never trigger after loadedmetadata.
          console.warn('[SpeakerFormsTable] seek failed', err);
        }
        const playPromise = a.play();
        if (playPromise && typeof playPromise.then === 'function') {
          playPromise.catch((err: unknown) => {
            const msg = err instanceof Error ? err.message : String(err ?? 'play failed');
            console.error('[SpeakerFormsTable] audio.play() rejected', err);
            setPlayErrorByVariant((prev) => ({ ...prev, [variant.csv_row_id]: msg }));
            setPlayingVariantId((id) => (id === variant.csv_row_id ? null : id));
          });
        }
      };
      if (srcChanged && audio.readyState < 1 /* HAVE_METADATA */) {
        const cleanupListeners = () => {
          audio.removeEventListener('loadedmetadata', onLoaded);
          audio.removeEventListener('error', onError);
          if (pendingListenersCleanupRef.current === cleanupListeners) {
            pendingListenersCleanupRef.current = null;
          }
        };
        const onLoaded = () => {
          cleanupListeners();
          if (playRequestIdRef.current !== requestId) return;
          seekAndPlay();
        };
        const onError = () => {
          cleanupListeners();
          if (playRequestIdRef.current !== requestId) return;
          const err = audio?.error;
          const msg = err
            ? `audio load failed (code ${err.code})`
            : `audio load failed for ${desiredSrc}`;
          console.error('[SpeakerFormsTable] audio load error', err);
          setPlayErrorByVariant((prev) => ({ ...prev, [variant.csv_row_id]: msg }));
          setPlayingVariantId((id) => (id === variant.csv_row_id ? null : id));
        };
        audio.addEventListener('loadedmetadata', onLoaded);
        audio.addEventListener('error', onError);
        pendingListenersCleanupRef.current = cleanupListeners;
        try {
          audio.load();
        } catch (err) {
          console.warn('[SpeakerFormsTable] audio.load() threw', err);
        }
      } else {
        seekAndPlay();
      }
      setPlayingVariantId(variant.csv_row_id);
      const tick = () => {
        const a = audioRef.current;
        if (!a) {
          rafRef.current = null;
          return;
        }
        if (a.currentTime >= endTime) {
          try {
            a.pause();
          } catch {
            /* noop */
          }
          setPlayingVariantId((id) => (id === variant.csv_row_id ? null : id));
          rafRef.current = null;
          return;
        }
        rafRef.current = requestAnimationFrame(tick);
      };
      rafRef.current = requestAnimationFrame(tick);
    },
    [cancelRaf, clearPendingListeners, playingVariantId],
  );

  const handleCanonicalSelect = useCallback(
    async (variant: SpeakerFormsTableVariant) => {
      setError(null);
      const candidate = bundle.candidates?.[speaker]?.[variant.csv_row_id] ?? null;
      try {
        const response = await putCanonicalLexeme(bundle.bundle_id, speaker, {
          csv_row_id: variant.csv_row_id,
          realization_index: candidate?.realization_index,
        });
        const nextSelection: CanonicalLexemeSelection | null =
          response.bundle.canonical?.[speaker] ?? null;
        useEnrichmentStore.getState().patchCanonicalLexeme(bundle.bundle_id, speaker, nextSelection);
        onBundleUpdated?.(response.bundle);
      } catch (err) {
        setError(errorMessage(err));
      }
    },
    [bundle, speaker, onBundleUpdated],
  );

  const handleClearCanonical = useCallback(async () => {
    setError(null);
    try {
      const response = await deleteCanonicalLexeme(bundle.bundle_id, speaker);
      useEnrichmentStore.getState().patchCanonicalLexeme(bundle.bundle_id, speaker, null);
      onBundleUpdated?.(response.bundle);
    } catch (err) {
      setError(errorMessage(err));
    }
  }, [bundle, speaker, onBundleUpdated]);

  const activeBucket = resolveActiveBucketForSpeaker(bundle, speaker);
  const warnings = bundle.warnings ?? [];
  const timestampVariant = current
    ? variants.find((variant) => variant.csv_row_id === current.csv_row_id) ?? variants[0]
    : variants[0];
  const timestampText = typeof timestampVariant?.start_sec === 'number' && typeof timestampVariant?.end_sec === 'number'
    ? `${timestampVariant.start_sec.toFixed(2)}s – ${timestampVariant.end_sec.toFixed(2)}s`
    : '—';

  return (
    <div className="space-y-4 px-3 py-4">
      <div className="space-y-2" data-testid={`speaker-expanded-${speaker}`}>
        <div className="flex items-center justify-between gap-3">
          <h4 className="text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-500">
            Variants &amp; canonical
          </h4>
          {current && (
            <button
              type="button"
              data-testid={`canonical-clear-${speaker}`}
              onClick={(e) => {
                e.stopPropagation();
                void handleClearCanonical();
              }}
              className="text-[11px] font-semibold text-rose-600 hover:text-rose-700"
            >
              Clear canonical selection
            </button>
          )}
        </div>
        {current?.source === 'migration:canonical_realizations' && (
          <div
            className="rounded border border-amber-200 bg-amber-50 px-2 py-1 text-[11px] text-amber-800"
            data-testid={`canonical-migration-hint-${speaker}`}
          >
            Migrated legacy choice — confirm or change.
          </div>
        )}
        {current?.source === 'default:single-candidate' && (
          <div
            className="text-[11px] text-slate-500"
            data-testid={`canonical-auto-hint-${speaker}`}
          >
            Auto-picked single candidate. Confirm to lock manually.
          </div>
        )}
        {variants.length === 0 && (
          <div className="rounded border border-slate-100 bg-slate-50 px-2 py-3 text-[11px] text-slate-500">
            No recorded forms for this speaker on this bundle.
          </div>
        )}
        <div className="space-y-2">
          {variants.map((variant) => {
            const candidate = bundle.candidates?.[speaker]?.[variant.csv_row_id] ?? null;
            const isCanonical = current?.csv_row_id === variant.csv_row_id;
            return (
              <VariantCard
                key={variant.csv_row_id}
                speaker={speaker}
                bundle={bundle}
                variant={variant}
                candidate={candidate}
                isCanonical={isCanonical}
                isPlaying={playingVariantId === variant.csv_row_id}
                playError={playErrorByVariant[variant.csv_row_id] ?? null}
                onPlayToggle={handlePlayToggle}
                onCanonicalSelect={handleCanonicalSelect}
                onOpenInAnnotate={(v) => onOpenInAnnotate(speaker, v)}
              />
            );
          })}
        </div>
        {error && (
          <div
            className="rounded border border-rose-200 bg-rose-50 px-2 py-1 text-[11px] text-rose-700"
            data-testid={`canonical-error-${speaker}`}
          >
            {error}
          </div>
        )}
      </div>

      <CompareNotesTextarea speaker={speaker} conceptKey={conceptKey} />

      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
        <div
          className="rounded-xl border border-slate-200 bg-white px-4 py-3"
          data-testid={`speaker-metadata-${speaker}`}
        >
          <div className="text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-500">
            Metadata
          </div>
          <dl className="mt-2 space-y-1 text-[11px] text-slate-600">
            <div className="flex gap-2">
              <dt className="w-24 text-slate-400">Bundle</dt>
              <dd className="font-mono text-slate-700">{bundle.bundle_id}</dd>
            </div>
            <div className="flex gap-2">
              <dt className="w-24 text-slate-400">Active bucket</dt>
              <dd className="font-mono text-slate-700">
                {activeBucket
                  ? `${activeBucket.survey_id.toUpperCase()} · ${activeBucket.source_item}`
                  : '—'}
              </dd>
            </div>
            <div className="flex gap-2">
              <dt className="w-24 text-slate-400">Variants</dt>
              <dd className="font-mono text-slate-700">{variants.length}</dd>
            </div>
            <div className="flex gap-2">
              <dt className="w-24 text-slate-400">Timestamp</dt>
              <dd className="font-mono text-slate-700" data-testid={`metadata-timestamp-${speaker}`}>
                {timestampText}
              </dd>
            </div>
          </dl>
        </div>
        {warnings.length > 0 && (
          <div
            className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3"
            data-testid={`speaker-warnings-${speaker}`}
          >
            <div className="text-[10px] font-semibold uppercase tracking-[0.12em] text-amber-700">
              Warnings
            </div>
            <ul className="mt-2 list-disc space-y-1 pl-4 text-[11px] text-amber-800">
              {warnings.map((w) => (
                <li key={w}>{w}</li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  );
}

function speakerBadgeClass(surveyId: string | null | undefined): string {
  const id = (surveyId ?? '').toUpperCase();
  if (id === 'JBL') return 'bg-blue-100 text-blue-800';
  if (id === 'KLQ') return 'bg-amber-100 text-amber-800';
  return 'bg-slate-100 text-slate-600';
}

export function SpeakerFormsTable({
  bundle,
  speakers,
  speakerForms = [],
  primaryContactCodes,
  contactLanguageNames = {},
  conceptKey,
  initialExpandedSpeaker,
  onBundleUpdated,
  onCycleCognate,
  onResetCognate,
  onToggleSpeakerFlag,
  onOpenInAnnotate = () =>
    console.warn('[SpeakerFormsTable] onOpenInAnnotate not wired — see MC-388-I'),
}: SpeakerFormsTableProps) {
  const formsBySpeaker = useMemo(
    () => new Map(speakerForms.map((form) => [form.speaker, form])),
    [speakerForms],
  );

  const [expanded, setExpanded] = useState<string | null>(
    initialExpandedSpeaker ?? speakers[0] ?? null,
  );

  const [sortMode, setSortMode] = useState<SortMode>({ state: 'unsorted', code: null });
  const [filters, setFilters] = useState<FilterState>(EMPTY_FILTERS);
  const [filterMenuOpen, setFilterMenuOpen] = useState(false);

  // Reset sort + filter when the concept changes.
  useEffect(() => {
    setSortMode({ state: 'unsorted', code: null });
    setFilters(EMPTY_FILTERS);
    setFilterMenuOpen(false);
  }, [conceptKey]);

  // Reset expansion to the restored speaker, or the first speaker when the speaker list changes.
  useEffect(() => {
    setExpanded((current) => {
      if (initialExpandedSpeaker !== undefined) {
        if (speakers.includes(initialExpandedSpeaker)) return initialExpandedSpeaker;
        return current && speakers.includes(current) ? current : null;
      }
      if (current && speakers.includes(current)) return current;
      return speakers[0] ?? null;
    });
  }, [initialExpandedSpeaker, speakers]);

  const advanceSort = useCallback(() => {
    const codes = primaryContactCodes;
    // Cycle: unsorted → desc(codes[0]) → desc(codes[1]) → asc(codes[0]) → asc(codes[1]) → unsorted
    setSortMode((prev) => {
      if (codes.length === 0) return { state: 'unsorted', code: null };
      if (prev.state === 'unsorted') return { state: 'desc', code: codes[0] };
      if (prev.state === 'desc') {
        const idx = prev.code ? codes.indexOf(prev.code) : -1;
        if (idx === -1 || idx >= codes.length - 1) {
          return { state: 'asc', code: codes[0] };
        }
        return { state: 'desc', code: codes[idx + 1] };
      }
      if (prev.state === 'asc') {
        const idx = prev.code ? codes.indexOf(prev.code) : -1;
        if (idx === -1 || idx >= codes.length - 1) {
          return { state: 'unsorted', code: null };
        }
        return { state: 'asc', code: codes[idx + 1] };
      }
      return { state: 'unsorted', code: null };
    });
  }, [primaryContactCodes]);

  // Build the filtered + sorted speaker list.
  const orderedSpeakers = useMemo(() => {
    const variantCountFor = (speaker: string): number => {
      const variants = resolveActiveBucketForSpeaker(bundle, speaker)?.variants ?? [];
      return variants.filter((variant) => bundle.candidates?.[speaker]?.[variant.csv_row_id]).length;
    };
    const filtered = speakers.filter((speaker) => {
      const form = formsBySpeaker.get(speaker);
      if (filters.flaggedOnly && !form?.flagged) return false;
      if (filters.noCanonical && canonicalFor(bundle, speaker)) return false;
      if (filters.multiVariantOnly && variantCountFor(speaker) <= 1) return false;
      return true;
    });
    if (sortMode.state === 'unsorted' || !sortMode.code) return filtered;
    const code = sortMode.code;
    const direction = sortMode.state === 'desc' ? -1 : 1;
    return [...filtered].sort((a, b) => {
      const formA = formsBySpeaker.get(a);
      const formB = formsBySpeaker.get(b);
      const va = formA?.similarityByLang[code];
      const vb = formB?.similarityByLang[code];
      const aSentinel = typeof va === 'number' ? va : Number.NEGATIVE_INFINITY;
      const bSentinel = typeof vb === 'number' ? vb : Number.NEGATIVE_INFINITY;
      if (aSentinel === bSentinel) return 0;
      return aSentinel < bSentinel ? -1 * direction : 1 * direction;
    });
  }, [speakers, formsBySpeaker, filters, bundle, sortMode]);

  const activeFilterCount =
    Number(filters.flaggedOnly) + Number(filters.noCanonical) + Number(filters.multiVariantOnly);

  const sortLabel = useMemo(() => {
    if (sortMode.state === 'unsorted' || !sortMode.code) return 'unsorted';
    const langName = contactLanguageNames[sortMode.code] ?? sortMode.code.toUpperCase();
    return `${sortMode.state === 'desc' ? '↓' : '↑'} ${langName}`;
  }, [sortMode, contactLanguageNames]);

  const colCount = 4 + primaryContactCodes.length; // speaker + ipa + sims + cognate + flag

  const toggleRow = useCallback((speaker: string) => {
    setExpanded((current) => (current === speaker ? null : speaker));
  }, []);

  const handleRowClick = useCallback(
    (speaker: string, event: MouseEvent<HTMLTableRowElement>) => {
      // Bail when click came from an interactive child (button, input, label, textarea).
      const target = event.target as HTMLElement | null;
      if (target?.closest('button, input, textarea, label, a')) return;
      toggleRow(speaker);
    },
    [toggleRow],
  );

  const handleRowKeyDown = useCallback(
    (speaker: string, event: KeyboardEvent<HTMLTableRowElement>) => {
      if (event.key !== 'Enter' && event.key !== ' ') return;
      const target = event.target as HTMLElement | null;
      if (target && target !== event.currentTarget) return;
      event.preventDefault();
      toggleRow(speaker);
    },
    [toggleRow],
  );

  return (
    <div data-testid="speaker-forms-table">
      <div className="mb-3 flex items-center justify-end gap-2">
        <button
          type="button"
          data-testid="speaker-forms-sort"
          onClick={advanceSort}
          className={`inline-flex items-center gap-1 rounded-md px-2 py-1 text-[11px] font-semibold ring-1 ring-slate-200 ${
            sortMode.state === 'unsorted'
              ? 'bg-white text-slate-600 hover:bg-slate-50'
              : 'bg-indigo-50 text-indigo-700 ring-indigo-200'
          }`}
        >
          <ArrowUpDown className="h-3 w-3" /> Sort: {sortLabel}
        </button>
        <div className="relative">
          <button
            type="button"
            data-testid="speaker-forms-filter-toggle"
            onClick={() => setFilterMenuOpen((v) => !v)}
            className={`inline-flex items-center gap-1 rounded-md px-2 py-1 text-[11px] font-semibold ring-1 ring-slate-200 ${
              activeFilterCount > 0
                ? 'bg-indigo-50 text-indigo-700 ring-indigo-200'
                : 'bg-white text-slate-600 hover:bg-slate-50'
            }`}
          >
            Filter{activeFilterCount > 0 ? ` · ${activeFilterCount}` : ''}
          </button>
          {filterMenuOpen && (
            <div
              className="absolute right-0 top-full z-10 mt-1 w-56 rounded-md border border-slate-200 bg-white p-2 shadow-md"
              data-testid="speaker-forms-filter-menu"
            >
              <label className="flex items-center gap-2 rounded px-2 py-1 text-[11px] text-slate-700 hover:bg-slate-50">
                <input
                  type="checkbox"
                  data-testid="filter-flagged-only"
                  checked={filters.flaggedOnly}
                  onChange={(e) =>
                    setFilters((f) => ({ ...f, flaggedOnly: e.target.checked }))
                  }
                />
                Flagged only
              </label>
              <label className="flex items-center gap-2 rounded px-2 py-1 text-[11px] text-slate-700 hover:bg-slate-50">
                <input
                  type="checkbox"
                  data-testid="filter-no-canonical"
                  checked={filters.noCanonical}
                  onChange={(e) =>
                    setFilters((f) => ({ ...f, noCanonical: e.target.checked }))
                  }
                />
                No canonical chosen
              </label>
              <label className="flex items-center gap-2 rounded px-2 py-1 text-[11px] text-slate-700 hover:bg-slate-50">
                <input
                  type="checkbox"
                  data-testid="filter-multi-variant"
                  checked={filters.multiVariantOnly}
                  onChange={(e) =>
                    setFilters((f) => ({ ...f, multiVariantOnly: e.target.checked }))
                  }
                />
                Multi-variant only
              </label>
              {/* TODO: cognate-set filter (v2). Nontrivial to combine with the
                  cognate-cycle UI and per-speaker manual overrides — out of
                  scope for the initial Speaker Forms regression fix. */}
            </div>
          )}
        </div>
      </div>

      <div className="overflow-x-auto rounded-lg border border-slate-100">
        <table className="w-full min-w-[760px] text-xs">
          <thead>
            <tr className="bg-slate-50/80 text-[10px] uppercase tracking-[0.08em] text-slate-500">
              <th className="px-3 py-2 text-left font-semibold" style={{ width: 180 }}>
                Speaker
              </th>
              <th className="px-3 py-2 text-left font-semibold">IPA &amp; Utterances</th>
              {primaryContactCodes.map((code) => (
                <th
                  key={code}
                  className="px-3 py-2 text-left font-semibold"
                  data-testid={`sim-col-header-${code}`}
                >
                  {(contactLanguageNames[code] ?? code.toUpperCase()).toUpperCase()} SIM.
                </th>
              ))}
              <th className="px-3 py-2 text-left font-semibold" style={{ width: 80 }}>
                Cognate
              </th>
              <th
                className="px-3 py-2 text-right font-semibold"
                style={{ width: 70 }}
              >
                Flag
              </th>
            </tr>
          </thead>
          <tbody>
            {orderedSpeakers.map((speaker) => {
              const form = formsBySpeaker.get(speaker);
              const isExpanded = expanded === speaker;
              const activeBucket = resolveActiveBucketForSpeaker(bundle, speaker);
              const surveyId = activeBucket?.survey_id ?? null;
              const candidates = (activeBucket?.variants ?? []).filter(
                (variant) => bundle.candidates?.[speaker]?.[variant.csv_row_id],
              );
              const variantCount = candidates.length;
              const current = canonicalFor(bundle, speaker);
              const canonicalChosen = !!current;
              const collapsedIpa = collapsedIpaForSpeaker(bundle, speaker, form?.ipa);
              return (
                <Fragment key={speaker}>
                  <tr
                    data-testid={`speaker-row-${speaker}`}
                    tabIndex={0}
                    onClick={(e) => handleRowClick(speaker, e)}
                    onKeyDown={(e) => handleRowKeyDown(speaker, e)}
                    className={`cursor-pointer border-t border-slate-100 align-top hover:bg-slate-50/70 focus:outline-none focus:ring-2 focus:ring-indigo-200 ${
                      isExpanded ? 'border-l-2 border-l-indigo-500 bg-indigo-50/50' : 'bg-white'
                    }`}
                  >
                    <td className="px-3 py-2.5">
                      <div className="flex items-center gap-2">
                        <ChevronRight
                          className={`h-3 w-3 text-slate-400 transition-transform ${
                            isExpanded ? 'rotate-90' : ''
                          }`}
                          aria-hidden
                        />
                        <span className="font-mono text-[12px] font-semibold text-slate-800">
                          {speaker}
                        </span>
                        {surveyId && (
                          <span
                            className={`inline-flex items-center rounded-md px-1.5 py-0.5 text-[10px] font-semibold uppercase ${speakerBadgeClass(
                              surveyId,
                            )}`}
                            data-testid={`speaker-badge-${speaker}`}
                          >
                            {surveyId.toUpperCase()}
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="px-3 py-2.5" data-testid={`ipa-cell-${speaker}`}>
                      {/* Bug 1 (Lucas, MC-388-A): collapsed IPA cell is strictly
                          one-line `/ipa/` — no ortho subtitle, no concept-label,
                          no utterance text. Pills row below stays informational
                          only (no emerald canonical-chosen — that lives inside
                          the expanded VariantCard). See Bug 2. */}
                      <div className="font-mono text-[13px] text-slate-800">
                        {collapsedIpa ? `/${collapsedIpa}/` : '—'}
                      </div>
                      <div className="mt-1 flex flex-wrap items-center gap-1">
                        {variantCount > 1 && (
                          <span
                            className="inline-flex items-center gap-1 rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-medium text-slate-600 ring-1 ring-slate-200"
                            data-testid={`variant-count-${speaker}`}
                          >
                            +{variantCount - 1} variant{variantCount - 1 === 1 ? '' : 's'}
                          </span>
                        )}
                        {!canonicalChosen && variantCount > 1 && (
                          <span
                            className="inline-flex items-center gap-1 rounded-full bg-amber-50 px-2 py-0.5 text-[10px] font-semibold text-amber-700 ring-1 ring-amber-100"
                            data-testid={`canonical-missing-${speaker}`}
                          >
                            <AlertCircle className="h-2.5 w-2.5" /> choose canonical
                          </span>
                        )}
                      </div>
                    </td>
                    {primaryContactCodes.map((code) => (
                      <td
                        key={code}
                        className="px-3 py-2.5"
                        data-testid={`sim-cell-${speaker}-${code}`}
                      >
                        <SimBar value={form?.similarityByLang[code] ?? null} />
                      </td>
                    ))}
                    <td className="px-3 py-2.5">
                      <CognateCell
                        speaker={speaker}
                        group={form?.cognate ?? '—'}
                        onCycle={() => onCycleCognate?.(speaker, form?.cognate ?? '—')}
                        onReset={() => onResetCognate?.(speaker)}
                      />
                    </td>
                    <td className="px-3 py-2.5 text-right">
                      <button
                        type="button"
                        data-testid={`speaker-flag-${speaker}`}
                        title={`Toggle flag for ${speaker}`}
                        onClick={(e) => {
                          e.stopPropagation();
                          onToggleSpeakerFlag?.(speaker, Boolean(form?.flagged));
                        }}
                        className={`inline-grid h-6 w-6 place-items-center rounded-md ${
                          form?.flagged
                            ? 'bg-amber-100 text-amber-600 ring-1 ring-amber-200'
                            : 'text-slate-300 hover:bg-slate-100 hover:text-slate-500'
                        }`}
                      >
                        <Flag className="h-3 w-3" />
                      </button>
                    </td>
                  </tr>
                  {isExpanded && (
                    <tr
                      data-testid={`speaker-row-expanded-${speaker}`}
                      className="bg-indigo-50/30"
                    >
                      <td colSpan={colCount} className="p-0">
                        <ExpandedPanel
                          speaker={speaker}
                          bundle={bundle}
                          conceptKey={conceptKey}
                          onBundleUpdated={onBundleUpdated}
                          onOpenInAnnotate={(spk, variant) => onOpenInAnnotate(spk, variant)}
                        />
                      </td>
                    </tr>
                  )}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      </div>

      <div className="mt-2 rounded-lg bg-slate-50 px-3 py-2 text-[11px] text-slate-500">
        Tip · click any row to expand for audio, spectrogram, canonical picker, and per-speaker
        notes. Audio chrome is intentionally absent from the collapsed table.
      </div>
    </div>
  );
}
