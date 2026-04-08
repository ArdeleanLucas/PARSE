import { useState, useEffect, useCallback } from "react";
import { useUIStore } from "../../stores/uiStore";
import { useEnrichmentStore } from "../../stores/enrichmentStore";
import { useAnnotationStore } from "../../stores/annotationStore";
import { useConfigStore } from "../../stores/configStore";
import { Button } from "../shared/Button";

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

export interface CognateControlsProps {
  onGroupsChanged?: (
    conceptId: string,
    groups: Record<string, string[]>,
  ) => void;
}

type Mode = "view" | "split" | "cycle";
type GroupLetter = "A" | "B" | "C" | "D" | "E";

const GROUP_LETTERS: GroupLetter[] = ["A", "B", "C", "D", "E"];

const GROUP_COLORS: Record<string, string> = {
  A: "#dcfce7",
  B: "#dbeafe",
  C: "#fef9c3",
  D: "#fce7f3",
  E: "#f3e8ff",
};

const EPS = 0.01;

/* ------------------------------------------------------------------ */
/*  Helpers                                                            */
/* ------------------------------------------------------------------ */

function normalizeConcept(raw: string): string {
  let s = raw.trim();
  if (s.startsWith("#")) s = s.slice(1);
  const colonIdx = s.indexOf(":");
  if (colonIdx >= 0) s = s.slice(0, colonIdx);
  return s.trim();
}

function speakerHasForm(
  records: Record<string, unknown>,
  speaker: string,
  conceptId: string,
): boolean {
  const rec = records[speaker] as {
    tiers?: Record<
      string,
      { intervals?: { start: number; end: number; text: string }[] }
    >;
  } | undefined;
  if (!rec?.tiers?.concept?.intervals) return false;

  const conceptInterval = rec.tiers.concept.intervals.find(
    (iv) => normalizeConcept(iv.text) === conceptId,
  );
  if (!conceptInterval) return false;

  const ipaIntervals = rec.tiers?.ipa?.intervals;
  if (!ipaIntervals) return false;

  return ipaIntervals.some(
    (iv) =>
      Math.abs(iv.start - conceptInterval.start) < EPS &&
      Math.abs(iv.end - conceptInterval.end) < EPS &&
      iv.text.trim() !== "",
  );
}

function sanitizeGroups(
  groups: Record<string, string[]>,
  speakersWithForm: string[],
): Record<string, string[]> {
  const result: Record<string, string[]> = {};
  const assigned = new Set<string>();

  for (const letter of GROUP_LETTERS) {
    if (!groups[letter]) continue;
    const filtered = groups[letter].filter(
      (sp) => speakersWithForm.includes(sp) && !assigned.has(sp),
    );
    if (filtered.length > 0) {
      result[letter] = filtered;
      filtered.forEach((sp) => assigned.add(sp));
    }
  }

  const unassigned = speakersWithForm.filter((sp) => !assigned.has(sp));
  if (unassigned.length > 0) {
    result["A"] = [...(result["A"] ?? []), ...unassigned];
  }

  return result;
}

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

export function CognateControls({ onGroupsChanged }: CognateControlsProps) {
  const activeConcept = useUIStore((s) => s.activeConcept);
  const selectedSpeakers = useUIStore((s) => s.selectedSpeakers);
  const enrichmentData = useEnrichmentStore((s) => s.data);
  const records = useAnnotationStore((s) => s.records);
  const config = useConfigStore((s) => s.config);
  const save = useEnrichmentStore((s) => s.save);

  const [mode, setMode] = useState<Mode>("view");
  const [groups, setGroups] = useState<Record<string, string[]>>({});
  const [splitTarget, setSplitTarget] = useState<GroupLetter>("A");

  const allSpeakers =
    selectedSpeakers.length > 0
      ? selectedSpeakers
      : config?.speakers ?? [];

  const speakersWithForm = activeConcept
    ? allSpeakers.filter((sp) => speakerHasForm(records, sp, activeConcept))
    : [];

  // Load groups when activeConcept changes
  useEffect(() => {
    if (!activeConcept) {
      setGroups({});
      setMode("view");
      return;
    }

    const overrides = enrichmentData?.manual_overrides as
      | { cognate_sets?: Record<string, Record<string, string[]>> }
      | undefined;
    const base = enrichmentData?.cognate_sets as
      | Record<string, Record<string, string[]>>
      | undefined;

    const raw =
      overrides?.cognate_sets?.[activeConcept] ??
      base?.[activeConcept] ??
      {};

    setGroups(sanitizeGroups(raw, speakersWithForm));
    setMode("view");
    setSplitTarget("A");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeConcept]);

  const saveGroups = useCallback(
    async (newGroups: Record<string, string[]>) => {
      if (!activeConcept) return;

      const existingOverrides =
        (enrichmentData?.manual_overrides as Record<string, unknown>) ?? {};
      const existingSets =
        (existingOverrides?.cognate_sets as Record<string, unknown>) ?? {};

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
        // enrichmentStore.save not yet implemented — store locally
      }

      onGroupsChanged?.(activeConcept, newGroups);
    },
    [activeConcept, enrichmentData, save, onGroupsChanged],
  );

  const findSpeakerGroup = (speaker: string): string | null => {
    for (const [letter, members] of Object.entries(groups)) {
      if (members.includes(speaker)) return letter;
    }
    return null;
  };

  const handleAccept = () => {
    const sanitized = sanitizeGroups(groups, speakersWithForm);
    setGroups(sanitized);
    saveGroups(sanitized);
    setMode("view");
  };

  const handleMerge = () => {
    const merged = sanitizeGroups({ A: speakersWithForm }, speakersWithForm);
    setGroups(merged);
    saveGroups(merged);
    setMode("view");
  };

  const handleSplitToggle = () => {
    setMode((m) => (m === "split" ? "view" : "split"));
  };

  const handleCycleToggle = () => {
    setMode((m) => (m === "cycle" ? "view" : "cycle"));
  };

  const handleSplitMove = (speaker: string) => {
    const newGroups: Record<string, string[]> = {};
    for (const [letter, members] of Object.entries(groups)) {
      newGroups[letter] = members.filter((sp) => sp !== speaker);
    }
    newGroups[splitTarget] = [...(newGroups[splitTarget] ?? []), speaker];

    // Remove empty groups
    for (const key of Object.keys(newGroups)) {
      if (newGroups[key].length === 0) delete newGroups[key];
    }
    setGroups(newGroups);
  };

  const handleDoneSplit = () => {
    const sanitized = sanitizeGroups(groups, speakersWithForm);
    setGroups(sanitized);
    saveGroups(sanitized);
    setMode("view");
  };

  const handleCycleClick = (speaker: string) => {
    const current = findSpeakerGroup(speaker);
    const currentIdx = current
      ? GROUP_LETTERS.indexOf(current as GroupLetter)
      : -1;
    const nextLetter = GROUP_LETTERS[(currentIdx + 1) % GROUP_LETTERS.length];

    const newGroups: Record<string, string[]> = {};
    for (const [letter, members] of Object.entries(groups)) {
      newGroups[letter] = members.filter((sp) => sp !== speaker);
    }
    newGroups[nextLetter] = [...(newGroups[nextLetter] ?? []), speaker];

    for (const key of Object.keys(newGroups)) {
      if (newGroups[key].length === 0) delete newGroups[key];
    }

    setGroups(newGroups);
    saveGroups(newGroups);
  };

  if (!activeConcept) {
    return (
      <div style={{ fontFamily: "monospace", padding: "1rem", color: "#6b7280" }}>
        Select a concept in the table.
      </div>
    );
  }

  return (
    <div style={{ fontFamily: "monospace", padding: "1rem" }}>
      <div style={{ fontWeight: 600, marginBottom: "0.5rem" }}>
        Cognate Controls
      </div>
      <div style={{ marginBottom: "0.5rem", color: "#374151" }}>
        Concept: {activeConcept}
      </div>

      <div style={{ display: "flex", gap: "0.5rem", marginBottom: "0.75rem", flexWrap: "wrap" }}>
        <Button size="sm" onClick={handleAccept}>
          Accept
        </Button>
        <Button
          size="sm"
          variant={mode === "split" ? "primary" : "secondary"}
          onClick={handleSplitToggle}
        >
          Split
        </Button>
        <Button size="sm" onClick={handleMerge}>
          Merge
        </Button>
        <Button
          size="sm"
          variant={mode === "cycle" ? "primary" : "secondary"}
          onClick={handleCycleToggle}
        >
          Cycle
        </Button>
      </div>

      {mode === "split" && (
        <div style={{ marginBottom: "0.75rem" }}>
          <div style={{ fontSize: "0.75rem", color: "#6b7280", marginBottom: "0.25rem" }}>
            Target group:
          </div>
          <div style={{ display: "flex", gap: "0.25rem", marginBottom: "0.5rem" }}>
            {GROUP_LETTERS.map((letter) => (
              <button
                key={letter}
                onClick={() => setSplitTarget(letter)}
                style={{
                  padding: "0.125rem 0.5rem",
                  borderRadius: "0.25rem",
                  border:
                    splitTarget === letter
                      ? "2px solid #3b82f6"
                      : "1px solid #d1d5db",
                  background: GROUP_COLORS[letter],
                  cursor: "pointer",
                  fontFamily: "monospace",
                  fontSize: "0.75rem",
                  fontWeight: splitTarget === letter ? 700 : 400,
                }}
              >
                {letter}
              </button>
            ))}
          </div>
          <Button size="sm" onClick={handleDoneSplit}>
            Done Split
          </Button>
        </div>
      )}

      <div style={{ display: "flex", gap: "0.375rem", flexWrap: "wrap" }}>
        {allSpeakers.map((sp) => {
          const hasForm = speakersWithForm.includes(sp);
          const groupLetter = findSpeakerGroup(sp);

          const handleClick = () => {
            if (!hasForm) return;
            if (mode === "split") handleSplitMove(sp);
            else if (mode === "cycle") handleCycleClick(sp);
          };

          return (
            <button
              key={sp}
              data-testid={`speaker-btn-${sp}`}
              disabled={!hasForm}
              onClick={handleClick}
              style={{
                padding: "0.25rem 0.625rem",
                borderRadius: "0.25rem",
                border: "1px solid #d1d5db",
                background: groupLetter
                  ? GROUP_COLORS[groupLetter] ?? "#e5e7eb"
                  : "#f9fafb",
                cursor: hasForm ? "pointer" : "not-allowed",
                opacity: hasForm ? 1 : 0.5,
                fontFamily: "monospace",
                fontSize: "0.75rem",
              }}
            >
              {sp}: {groupLetter ?? "–"}
            </button>
          );
        })}
      </div>
    </div>
  );
}
