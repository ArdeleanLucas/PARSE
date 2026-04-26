import { useCallback, useEffect, useState } from "react";

import {
  searchLexeme,
  type LexemeSearchCandidate,
  type LexemeSearchResponse,
} from "../../../api/client";
import { useAnnotationStore } from "../../../stores/annotationStore";

import { buildLexemeSearchStatus } from "./shared";

interface UseLexemeSearchJobArgs {
  activeConceptId: string | null;
  activeSpeaker: string | null;
  conceptLabel: string;
}

const emptyResponse = (
  activeSpeaker: string,
  activeConceptId: string | null,
  variants: string[],
): LexemeSearchResponse => ({
  speaker: activeSpeaker,
  concept_id: activeConceptId ? String(activeConceptId) : null,
  variants,
  language: "ku",
  candidates: [],
  signals_available: { phonemizer: false, cross_speaker_anchors: 0, contact_variants: [] },
});

export function useLexemeSearchJob({
  activeConceptId,
  activeSpeaker,
  conceptLabel,
}: UseLexemeSearchJobArgs) {
  const setConfirmedAnchor = useAnnotationStore((s) => s.setConfirmedAnchor);

  const [variantsRaw, setVariantsRaw] = useState("");
  const [response, setResponse] = useState<LexemeSearchResponse | null>(null);
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setResponse(null);
    setSelectedKey(null);
    setStatus("");
  }, [activeSpeaker, activeConceptId]);

  const seedHint = conceptLabel;

  const parseVariants = useCallback(
    (raw: string): string[] =>
      raw
        .split(/[\s,;/]+/)
        .map((v) => v.trim())
        .filter(Boolean),
    [],
  );

  const keyOf = useCallback(
    (c: LexemeSearchCandidate) => `${c.tier}|${c.start.toFixed(3)}|${c.end.toFixed(3)}`,
    [],
  );

  const candidates = response?.candidates ?? [];
  const signals = response?.signals_available ?? null;

  const runSearch = useCallback(async () => {
    const variants = parseVariants(variantsRaw);
    if (variants.length === 0) {
      setResponse(null);
      setStatus("Enter at least one variant.");
      return null;
    }
    if (!activeSpeaker) {
      setResponse(null);
      setStatus("No speaker selected.");
      return null;
    }
    setBusy(true);
    setStatus("Searching…");
    try {
      const resp = await searchLexeme(activeSpeaker, variants, {
        conceptId: activeConceptId ? String(activeConceptId) : undefined,
      });
      setResponse(resp);
      const first = resp.candidates[0];
      setSelectedKey(first ? keyOf(first) : null);
      setStatus(buildLexemeSearchStatus(resp));
      return first ?? null;
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setResponse(emptyResponse(activeSpeaker, activeConceptId, variants));
      setStatus(`Search failed: ${message}`);
      return null;
    } finally {
      setBusy(false);
    }
  }, [activeConceptId, activeSpeaker, keyOf, parseVariants, variantsRaw]);

  const useSeed = useCallback(() => {
    if (seedHint) setVariantsRaw(seedHint);
  }, [seedHint]);

  const confirmCandidate = useCallback(
    (candidate: LexemeSearchCandidate) => {
      if (!activeSpeaker || !activeConceptId) return;
      setConfirmedAnchor(activeSpeaker, String(activeConceptId), {
        start: candidate.start,
        end: candidate.end,
        source: `user+${candidate.tier}`,
        confirmed_at: new Date().toISOString(),
        matched_text: candidate.matched_text,
        matched_variant: candidate.matched_variant,
        variants_used: response?.variants ?? parseVariants(variantsRaw),
      });
      setStatus(
        `Anchor confirmed at ${candidate.start.toFixed(3)}–${candidate.end.toFixed(3)} (${candidate.matched_text}).`,
      );
    },
    [activeConceptId, activeSpeaker, parseVariants, response?.variants, setConfirmedAnchor, variantsRaw],
  );

  const clearAnchor = useCallback(() => {
    if (!activeSpeaker || !activeConceptId) return;
    setConfirmedAnchor(activeSpeaker, String(activeConceptId), null);
    setStatus("Anchor cleared.");
  }, [activeConceptId, activeSpeaker, setConfirmedAnchor]);

  const selectCandidate = useCallback((key: string) => setSelectedKey(key), []);

  return {
    busy,
    candidates,
    clearAnchor,
    confirmCandidate,
    keyOf,
    response,
    runSearch,
    seedHint,
    selectCandidate,
    selectedKey,
    setSelectedKey,
    setVariantsRaw,
    signals,
    status,
    useSeed,
    variantsRaw,
  };
}
