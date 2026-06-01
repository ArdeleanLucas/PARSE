import { useCallback } from "react";

import { buildRealizationKey } from "../lib/conceptGrouping";
import { usePlaybackStore } from "../stores/playbackStore";
import { useCompareReturnStore } from "../stores/compareReturnStore";

/**
 * Mode label shared with ParseUI. This type matches the local `AppMode` in
 * `src/ParseUI.tsx:100` and the exported one in
 * `src/components/parse/right-panel/types.ts`. We re-declare it inline rather
 * than importing from the right-panel barrel to keep this hook's import graph
 * narrow (and to keep the integration PR free to wire either source).
 */
type AppMode = "annotate" | "compare" | "tags";

/**
 * Minimal variant shape the handler needs. Whatever full `Variant` type
 * `SpeakerFormsTable` (MC-388-A) ends up defining is irrelevant to this
 * wire — only the start time and the row id are consumed here. `start_sec`
 * may be `null` for rows without a confirmed interval; in that case the
 * handler seeks to 0 (start of the speaker's audio).
 */
export interface OpenInAnnotateVariant {
  start_sec: number | null;
  csv_row_id: string;
  /** Which recorded realization (A/B/…) of csv_row_id this card represents.
   * When set, the handler selects exactly that interval in annotate so the
   * user lands on the form they clicked, ready to edit. Undefined for
   * single-realization rows (the row's only interval, index 0). */
  realizationIndex?: number;
}

export interface UseOpenInAnnotateHandlerParams {
  /**
   * The numeric id of the concept currently shown in compare mode. ParseUI
   * holds this in a local `useState` (see `src/ParseUI.tsx` around line 269).
   * The follow-up integration PR (MC-388-C) passes ParseUI's `conceptId`.
   */
  conceptId: number;
  /**
   * The semantic key of the same concept. ParseUI holds this in
   * `selectedRealizationKey` (with derived `selectedConceptKey`) in ParseUI. Stored so the
   * restore hook can resolve back to the same merged/variant-aware concept
   * even if the numeric id changes.
   */
  conceptKey: string;
  /**
   * ParseUI's local `setCurrentMode` setter. Because `currentMode` is local
   * `useState` in ParseUI (not a shared store), the integration PR must pass
   * the setter through — we cannot import it.
   */
  setCurrentMode: (mode: AppMode) => void;
  /**
   * Optional. ParseUI's `setSelectedRealizationKey` setter. When provided, the
   * handler selects the clicked variant's exact interval
   * (`<csv_row_id>:<realizationIndex>`) so annotate opens on that A/B/… form
   * rather than the row's first realization. Optional so the hook stays
   * unit-testable without wiring every consumer.
   */
  setSelectedRealizationKey?: (key: string | null) => void;
  /**
   * Optional. Seeds ParseUI's mode-switch concept resolver with the clicked
   * row's underlying key (= csv_row_id). Without this, the resolver runs on the
   * compare→annotate switch using the *previous* (compare) concept and both
   * navigates `conceptId` back to it AND resets the realization index to 0 —
   * so clicking a non-primary realization of a grouped concept would land on
   * the wrong form. Seeding the resolver makes it resolve to the clicked row's
   * concept and leave the chosen realization index intact. ParseUI wires this
   * to assign its `previousActiveRawKeyRef`.
   */
  seedActiveConceptKey?: (conceptKey: string) => void;
}

/**
 * Returns the click handler `SpeakerFormsTable` will mount on each variant's
 * "Open in annotate" button. When invoked it:
 *
 * 1. Saves a `CompareReturnSnapshot` (conceptId + conceptKey + the speaker
 *    whose row is currently expanded) so the restore hook can return to the
 *    same compare position later.
 * 2. Seeds the playback store: switches `activeSpeaker` to the variant's
 *    speaker and queues a seek to `variant.start_sec` (or 0 when null).
 *    Uses the public actions `setActiveSpeaker(speaker)` and
 *    `requestSeek(targetSec)` — note that `requestSeek` bumps a nonce so
 *    `AnnotateView` reliably re-seeks even if the target time matches the
 *    previous request.
 * 3. Flips ParseUI into annotate mode via the passed-in setter.
 *
 * Wiring note for MC-388-C: this hook depends on three values that live in
 * ParseUI's local component state (`conceptId`, derived `selectedConceptKey`,
 * `setCurrentMode`). The integration PR must pass them in via the params
 * object on every render.
 */
export function useOpenInAnnotateHandler(
  params: UseOpenInAnnotateHandlerParams,
) {
  const { conceptId, conceptKey, setCurrentMode, setSelectedRealizationKey, seedActiveConceptKey } = params;
  return useCallback(
    (speaker: string, variant: OpenInAnnotateVariant) => {
      useCompareReturnStore.getState().save({
        conceptId,
        conceptKey,
        expandedSpeaker: speaker,
      });
      const playback = usePlaybackStore.getState();
      playback.setActiveSpeaker(speaker);
      playback.requestSeek(variant.start_sec ?? 0);
      // Pre-seed the mode-switch resolver with the clicked row's key, BEFORE the
      // mode flip, so it resolves `conceptId` to that row's concept and keeps
      // the chosen realization index instead of restoring the prior concept and
      // resetting to index 0. (Grouped concepts otherwise land on the wrong
      // form.) The key is the underlying concept_id (= csv_row_id).
      seedActiveConceptKey?.(variant.csv_row_id);
      // Select the exact interval the user clicked so annotate opens on that
      // realization's IPA/ortho, not the row's first. The realization key is
      // keyed by the underlying concept_id (= csv_row_id) and the start-rank
      // index, matching annotate's own realization ordering.
      setSelectedRealizationKey?.(
        buildRealizationKey(variant.csv_row_id, variant.realizationIndex ?? 0),
      );
      setCurrentMode("annotate");
    },
    [conceptId, conceptKey, setCurrentMode, setSelectedRealizationKey, seedActiveConceptKey],
  );
}
