import { useCallback, useEffect, useMemo, useState } from "react";
import type { AnnotationRecord } from "../../../api/types";
import type { Mode } from "./types";
import { GROUP_LETTERS } from "./types";
import { sanitizeGroups, speakerHasForm } from "./shared";

export function useCognateDecisions({
  activeConcept,
  allSpeakers,
  enrichmentData,
  records,
  save,
  onGroupsChanged,
}: {
  activeConcept: string | null;
  allSpeakers: string[];
  enrichmentData: Record<string, unknown>;
  records: Record<string, AnnotationRecord>;
  save: (patch: Record<string, unknown>) => Promise<void>;
  onGroupsChanged?: (conceptId: string, groups: Record<string, string[]>) => void;
}) {
  const [mode, setMode] = useState<Mode>("view");
  const [groups, setGroups] = useState<Record<string, string[]>>({});
  const [splitTarget, setSplitTarget] = useState<typeof GROUP_LETTERS[number]>("A");

  const speakersWithForm = useMemo(
    () => (activeConcept ? allSpeakers.filter((speaker) => speakerHasForm(records, speaker, activeConcept)) : []),
    [activeConcept, allSpeakers, records],
  );

  useEffect(() => {
    if (!activeConcept) {
      setGroups({});
      setMode("view");
      return;
    }
    const overrides = enrichmentData?.manual_overrides as { cognate_sets?: Record<string, Record<string, string[]>> } | undefined;
    const base = enrichmentData?.cognate_sets as Record<string, Record<string, string[]>> | undefined;
    const raw = overrides?.cognate_sets?.[activeConcept] ?? base?.[activeConcept] ?? {};
    setGroups(sanitizeGroups(raw, speakersWithForm));
    setMode("view");
    setSplitTarget("A");
  }, [activeConcept, enrichmentData, speakersWithForm]);

  const saveGroups = useCallback(async (newGroups: Record<string, string[]>, previousGroups?: Record<string, string[]>) => {
    if (!activeConcept) return false;
    const existingOverrides = (enrichmentData?.manual_overrides as Record<string, unknown>) ?? {};
    const existingSets = (existingOverrides.cognate_sets as Record<string, unknown>) ?? {};
    try {
      await save({
        manual_overrides: {
          ...existingOverrides,
          cognate_sets: {
            ...existingSets,
            [activeConcept]: newGroups,
          },
        },
      });
    } catch {
      if (previousGroups) setGroups(previousGroups);
      return false;
    }
    onGroupsChanged?.(activeConcept, newGroups);
    return true;
  }, [activeConcept, enrichmentData, onGroupsChanged, save]);

  const findSpeakerGroup = useCallback((speaker: string): string | null => {
    for (const [letter, members] of Object.entries(groups)) {
      if (members.includes(speaker)) return letter;
    }
    return null;
  }, [groups]);

  const handleAccept = useCallback(async () => {
    const sanitized = sanitizeGroups(groups, speakersWithForm);
    const previousGroups = groups;
    setGroups(sanitized);
    const ok = await saveGroups(sanitized, previousGroups);
    if (ok) setMode("view");
  }, [groups, saveGroups, speakersWithForm]);

  const handleMerge = useCallback(async () => {
    const merged = sanitizeGroups({ A: speakersWithForm }, speakersWithForm);
    const previousGroups = groups;
    setGroups(merged);
    await saveGroups(merged, previousGroups);
    setMode("view");
  }, [groups, saveGroups, speakersWithForm]);

  const handleSplitToggle = useCallback(() => setMode((current) => current === "split" ? "view" : "split"), []);
  const handleCycleToggle = useCallback(() => setMode((current) => current === "cycle" ? "view" : "cycle"), []);

  const handleSplitMove = useCallback((speaker: string) => {
    const newGroups: Record<string, string[]> = {};
    for (const [letter, members] of Object.entries(groups)) {
      newGroups[letter] = members.filter((sp) => sp !== speaker);
    }
    newGroups[splitTarget] = [...(newGroups[splitTarget] ?? []), speaker];
    for (const key of Object.keys(newGroups)) {
      if (newGroups[key].length === 0) delete newGroups[key];
    }
    setGroups(newGroups);
  }, [groups, splitTarget]);

  const handleDoneSplit = useCallback(async () => {
    const sanitized = sanitizeGroups(groups, speakersWithForm);
    const previousGroups = groups;
    setGroups(sanitized);
    const ok = await saveGroups(sanitized, previousGroups);
    if (ok) setMode("view");
  }, [groups, saveGroups, speakersWithForm]);

  const handleCycleClick = useCallback(async (speaker: string) => {
    const current = findSpeakerGroup(speaker);
    const currentIdx = current ? GROUP_LETTERS.indexOf(current as typeof GROUP_LETTERS[number]) : -1;
    const nextLetter = GROUP_LETTERS[(currentIdx + 1) % GROUP_LETTERS.length];
    const newGroups: Record<string, string[]> = {};
    for (const [letter, members] of Object.entries(groups)) {
      newGroups[letter] = members.filter((sp) => sp !== speaker);
    }
    newGroups[nextLetter] = [...(newGroups[nextLetter] ?? []), speaker];
    for (const key of Object.keys(newGroups)) {
      if (newGroups[key].length === 0) delete newGroups[key];
    }
    const previousGroups = groups;
    setGroups(newGroups);
    await saveGroups(newGroups, previousGroups);
  }, [findSpeakerGroup, groups, saveGroups]);

  return {
    findSpeakerGroup,
    groups,
    handleAccept,
    handleCycleClick,
    handleCycleToggle,
    handleDoneSplit,
    handleMerge,
    handleSplitMove,
    handleSplitToggle,
    mode,
    setSplitTarget,
    speakersWithForm,
    splitTarget,
  };
}
