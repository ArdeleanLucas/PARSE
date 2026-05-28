import { create } from "zustand";

/**
 * Snapshot of the user's position in compare mode at the moment they clicked
 * "Open in annotate" on a Speaker Forms variant row. The follow-up MC-388-C
 * integration PR uses this to restore the same concept + the same expanded
 * speaker row when the user returns to compare via the existing mode switcher.
 *
 * - `conceptId` drives `ConceptSidebar` selection (the numeric id ParseUI
 *   stores in its local `conceptId` state).
 * - `conceptKey` is the semantic identifier (`concept.key`); it is what
 *   ParseUI's derived `selectedConceptKey` holds and what survives merges /
 *   variant resolution.
 * - `expandedSpeaker` is the speaker row that was expanded in the Speaker
 *   Forms table at the moment of click.
 */
export interface CompareReturnSnapshot {
  conceptId: number;
  conceptKey: string;
  expandedSpeaker: string;
}

export interface CompareReturnState {
  snapshot: CompareReturnSnapshot | null;
  save: (snapshot: CompareReturnSnapshot) => void;
  /**
   * Returns the current snapshot and atomically clears it. Idempotent: a
   * second call without an intervening `save()` returns `null`. This lets the
   * restore hook safely read the snapshot exactly once per save without
   * leaking state into later mode transitions.
   */
  consume: () => CompareReturnSnapshot | null;
  clear: () => void;
}

/**
 * Zustand store that buffers a single compare-position snapshot across a
 * compare → annotate → compare round-trip.
 *
 * Contract:
 * - `save(snapshot)` is called by `useOpenInAnnotateHandler` when the user
 *   clicks "Open in annotate" on a variant inside `SpeakerFormsTable`.
 * - `consume()` is called by `useCompareReturnRestore` when ParseUI detects
 *   `currentMode === 'compare'` after a mode change. It returns the snapshot
 *   and clears it in a single transition.
 * - At most one snapshot is buffered at a time; a second `save()` simply
 *   overwrites the previous snapshot (the user can re-enter annotate without
 *   ever returning to compare).
 */
export const useCompareReturnStore = create<CompareReturnState>((set, get) => ({
  snapshot: null,
  save: (snapshot) => set({ snapshot }),
  consume: () => {
    const current = get().snapshot;
    if (current != null) {
      set({ snapshot: null });
    }
    return current;
  },
  clear: () => set({ snapshot: null }),
}));
