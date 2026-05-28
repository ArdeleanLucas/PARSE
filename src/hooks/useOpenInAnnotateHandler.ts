import { useCallback } from "react";

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
  const { conceptId, conceptKey, setCurrentMode } = params;
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
      setCurrentMode("annotate");
    },
    [conceptId, conceptKey, setCurrentMode],
  );
}
