import { useEffect, useState } from "react";

import { useCompareReturnStore } from "../stores/compareReturnStore";

/**
 * Mode label shared with ParseUI. See note in `useOpenInAnnotateHandler.ts`
 * — kept inline to keep the import graph narrow.
 */
type AppMode = "annotate" | "compare" | "tags";

export interface UseCompareReturnRestoreParams {
  /**
   * ParseUI's current `currentMode` value. Local `useState` in ParseUI
   * (around `src/ParseUI.tsx:472`). The integration PR (MC-388-C) passes it
   * through.
   */
  currentMode: AppMode;
  /**
   * Optional. ParseUI's `setConceptId` setter (local `useState` around
   * `src/ParseUI.tsx:269`). When provided, the restore step calls it with
   * the snapshot's `conceptId` so `ConceptSidebar` re-selects the same
   * concept the user was viewing. Optional so the hook stays unit-testable
   * without wiring every consumer.
   */
  setConceptId?: (id: number) => void;
  /**
   * Optional. ParseUI's `setSelectedConceptKey` setter (local `useState`
   * around `src/ParseUI.tsx:270`). When provided, the restore step calls it
   * with the snapshot's `conceptKey`, which is the value ParseUI's
   * merge/variant resolution logic prefers when reconciling the active
   * concept.
   */
  setSelectedConceptKey?: (key: string) => void;
}

export interface UseCompareReturnRestoreResult {
  /**
   * The speaker whose row `SpeakerFormsTable` should expand on its first
   * mount after re-entering compare mode. `null` whenever there is no
   * pending snapshot (or while not in compare mode).
   *
   * Stable behavior: a snapshot is consumed exactly once per save. After
   * consumption, the value stays set as long as compare mode is active so
   * the table can read it on its mount. Leaving compare mode (transition to
   * `'annotate'` or `'tags'`) resets it to `null`, so a subsequent
   * compare-mount with no fresh snapshot does not re-expand the stale row.
   */
  initialExpandedSpeaker: string | null;
}

/**
 * Hook ParseUI mounts at top level alongside its other mode-aware state.
 *
 * Behavior:
 * - On every transition of `currentMode`:
 *   - If we just entered `'compare'`, consume any pending snapshot from
 *     `useCompareReturnStore`. When one exists, apply it: update the concept
 *     id + key via the passed-in setters and surface the expanded speaker.
 *   - If we left `'compare'`, reset `initialExpandedSpeaker` to `null` so the
 *     next compare-mount with no fresh snapshot does not re-expand a stale
 *     speaker row.
 *
 * The effect intentionally depends only on `currentMode`. The store
 * accessors are stable Zustand references, and the setter params come from
 * ParseUI's component-local state, where their identity is incidental to
 * the snapshot-restore contract. The effect runs once per mode transition.
 *
 * Wiring note for MC-388-C: pass `setConceptId` and `setSelectedConceptKey`
 * from ParseUI to make the restore visible in the UI. Without them the
 * hook still returns `initialExpandedSpeaker`, which is sufficient for the
 * Speaker Forms expansion alone.
 */
export function useCompareReturnRestore(
  params: UseCompareReturnRestoreParams,
): UseCompareReturnRestoreResult {
  const [initialExpandedSpeaker, setInitialExpandedSpeaker] = useState<
    string | null
  >(null);

  // We intentionally key the effect on currentMode only — see JSDoc above.
  // The setter params come from ParseUI's component-local state; their
  // identity is incidental to the snapshot-restore contract, and re-running
  // the consume() path when they change would risk double-consuming.
  useEffect(() => {
    if (params.currentMode !== "compare") {
      // Left compare mode (or never entered): clear any restored row so a
      // future compare-mount without a snapshot uses the default behavior.
      setInitialExpandedSpeaker((prev) => (prev === null ? prev : null));
      return;
    }
    // Entered compare mode (or re-rendered while in it). Consume at most
    // one snapshot per save — `consume()` is idempotent.
    const snapshot = useCompareReturnStore.getState().consume();
    if (snapshot != null) {
      params.setConceptId?.(snapshot.conceptId);
      params.setSelectedConceptKey?.(snapshot.conceptKey);
      setInitialExpandedSpeaker(snapshot.expandedSpeaker);
    }
  }, [params.currentMode]);

  return { initialExpandedSpeaker };
}
