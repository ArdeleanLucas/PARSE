import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import type { ConceptNoteEntry } from '../../api/types';
import { useEnrichmentStore } from '../../stores/enrichmentStore';

// Legacy browser-only store key. Concept notes are now server-backed in
// parse-enrichments.json (`concept_notes`), but we keep reading/writing this
// localStorage cache so notes typed before the migration are not lost and the
// box still works offline.
const COMPARE_NOTES_STORAGE_KEY = 'parseui-compare-notes-v1';

/** Pure read of the server-backed note for a concept from the enrichments payload. */
export function conceptNoteFromEnrichments(
  data: Record<string, unknown> | null | undefined,
  conceptKey: string,
): string {
  const block = (data as Record<string, unknown> | null | undefined)?.concept_notes;
  if (!block || typeof block !== 'object') return '';
  const entry = (block as Record<string, unknown>)[conceptKey] as ConceptNoteEntry | undefined;
  if (!entry || typeof entry !== 'object') return '';
  return typeof entry.note === 'string' ? entry.note : '';
}

function readLocalCache(conceptKey: string): string {
  try {
    const raw = window.localStorage.getItem(COMPARE_NOTES_STORAGE_KEY);
    const stored = raw ? (JSON.parse(raw) as Record<string, string>) : {};
    const value = stored[conceptKey];
    return typeof value === 'string' ? value : '';
  } catch {
    return '';
  }
}

function writeLocalCache(conceptKey: string, value: string): void {
  try {
    const raw = window.localStorage.getItem(COMPARE_NOTES_STORAGE_KEY);
    const stored = raw ? (JSON.parse(raw) as Record<string, string>) : {};
    stored[conceptKey] = value;
    window.localStorage.setItem(COMPARE_NOTES_STORAGE_KEY, JSON.stringify(stored));
  } catch {
    // non-fatal localStorage failure
  }
}

interface ConceptNotesBoxProps {
  conceptId: number | string;
}

/**
 * General per-concept notes box (Compare). Persists to the shared, workspace-
 * resident `parse-enrichments.json` via the enrichment store's merge-safe
 * `save()` (deep-merges full state then POSTs), so notes are shareable like the
 * speaker files and survive a browser clear. localStorage is kept only as a
 * legacy read fallback + write-through cache.
 */
export function ConceptNotesBox({ conceptId }: ConceptNotesBoxProps) {
  const conceptKey = conceptId.toString();
  const data = useEnrichmentStore((s) => s.data) as Record<string, unknown> | null;

  const serverNote = useMemo(() => conceptNoteFromEnrichments(data, conceptKey), [data, conceptKey]);
  const resolved = useMemo(() => serverNote || readLocalCache(conceptKey), [serverNote, conceptKey]);

  const [note, setNote] = useState(resolved);
  const [status, setStatus] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle');
  const [error, setError] = useState<string | null>(null);
  const focusedRef = useRef(false);
  const initialRef = useRef(resolved);
  const latestRef = useRef(note);
  const inFlightRef = useRef(false);

  useEffect(() => {
    latestRef.current = note;
  }, [note]);

  // Reset the transient save indicator when switching concepts so a "Saved" /
  // error pill from the previous concept doesn't linger on the next one.
  useEffect(() => {
    setStatus('idle');
    setError(null);
  }, [conceptKey]);

  // Resync from the store (or legacy cache) when the concept or the server
  // value changes — but never while the user is mid-edit, while a save is in
  // flight, or while there is an unsaved/errored local edit (the enrichment
  // store updates ``data`` optimistically before the POST resolves, so without
  // this guard a failed save would be silently marked clean).
  useEffect(() => {
    if (focusedRef.current || inFlightRef.current) return;
    if (latestRef.current !== initialRef.current) return;
    setNote(resolved);
    initialRef.current = resolved;
  }, [resolved]);

  const save = useCallback(async () => {
    const value = latestRef.current;
    if (value === initialRef.current) return;
    // Guard against a concurrent in-flight save (e.g. blur then immediate
    // unmount) double-POSTing the same edit.
    if (inFlightRef.current) return;
    inFlightRef.current = true;
    // Write-through cache first so the note survives offline / unsaved navigation
    // regardless of whether the server round-trip succeeds.
    writeLocalCache(conceptKey, value);
    setStatus('saving');
    setError(null);
    try {
      await useEnrichmentStore.getState().save({
        concept_notes: { [conceptKey]: { note: value, updated_at: new Date().toISOString() } },
      });
      // Only mark the edit clean once the server round-trip succeeds, so a
      // failed save stays dirty and is retried on the next blur/unmount.
      initialRef.current = value;
      setStatus('saved');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Save failed');
      setStatus('error');
    } finally {
      inFlightRef.current = false;
    }
  }, [conceptKey]);

  // Save on unmount when there are unsaved edits (e.g. Prev/Next before blur).
  useEffect(() => {
    return () => {
      if (latestRef.current !== initialRef.current) void save();
    };
  }, [save]);

  return (
    <div>
      <textarea
        data-testid={`concept-note-${conceptKey}`}
        value={note}
        onChange={(e) => {
          const next = e.target.value;
          setNote(next);
          setStatus('idle');
          // Immediate write-through cache: persists per-concept without a blur
          // and keeps notes available offline (server save still runs on blur).
          writeLocalCache(conceptKey, next);
        }}
        onFocus={() => {
          focusedRef.current = true;
        }}
        onBlur={() => {
          focusedRef.current = false;
          void save();
        }}
        placeholder="Add observations, etymological notes, or questions for review…"
        className="min-h-[220px] w-full resize-y rounded-lg border border-slate-200 bg-slate-50/40 p-3 text-xs leading-relaxed text-slate-700 placeholder:text-slate-400 focus:border-indigo-300 focus:bg-white focus:outline-none focus:ring-2 focus:ring-indigo-100"
      />
      {status === 'saving' && <p className="mt-1 text-[10px] text-slate-400">Saving…</p>}
      {status === 'saved' && <p className="mt-1 text-[10px] text-emerald-500">Saved</p>}
      {status === 'error' && <p className="mt-1 text-[10px] text-rose-500">{error}</p>}
    </div>
  );
}
