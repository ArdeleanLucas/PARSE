import { useState, useEffect, useMemo, useCallback } from "react";
import { getClefConfig } from "../../api/client";
import { useConfigStore } from "../../stores/configStore";
import { useAnnotationStore } from "../../stores/annotationStore";
import { useUIStore } from "../../stores/uiStore";
import { useEnrichmentStore } from "../../stores/enrichmentStore";
import { Button } from "../shared/Button";
import { Select } from "../shared/Select";
import { Badge } from "../shared/Badge";

/* ------------------------------------------------------------------ */
/*  Local types                                                        */
/* ------------------------------------------------------------------ */

type BorrowingDecision = "native" | "borrowed" | "uncertain" | "skip";

interface SpeakerDecision {
  decision: BorrowingDecision;
  sourceLang: string | null;
}

interface ContactLanguage {
  code: string;
  name: string;
  family?: string;
}

/* ------------------------------------------------------------------ */
/*  Constants                                                          */
/* ------------------------------------------------------------------ */

const EPS = 0.01;
const DECISION_OPTIONS: BorrowingDecision[] = ["native", "borrowed", "uncertain", "skip"];

const BAND_COLORS: Record<string, { bg: string; label: string }> = {
  unlikely: { bg: "#dcfce7", label: "unlikely" },
  possible: { bg: "#fef3c7", label: "possible" },
  likely: { bg: "#fee2e2", label: "likely" },
};

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

function normalizeDecision(raw: unknown): BorrowingDecision {
  if (typeof raw === "string") {
    const v = raw.toLowerCase().trim();
    if (v === "yes" || v === "loan" || v === "loanword" || v === "borrowed") return "borrowed";
    if (v === "no" || v === "native" || v === "not_borrowing") return "native";
    if (v === "uncertain" || v === "unclear" || v === "possible") return "uncertain";
  }
  return "skip";
}

function scoreBand(score: number): string {
  if (score < 0.3) return "unlikely";
  if (score < 0.6) return "possible";
  return "likely";
}

function lookupForm(
  records: Record<string, unknown>,
  speaker: string,
  conceptId: string,
): { ipa: string; ortho: string } | null {
  const rec = records[speaker] as {
    tiers?: Record<string, { intervals?: { start: number; end: number; text: string }[] }>;
  } | undefined;
  if (!rec?.tiers?.concept?.intervals) return null;

  const conceptInterval = rec.tiers.concept.intervals.find(
    (iv) => normalizeConcept(iv.text) === conceptId,
  );
  if (!conceptInterval) return null;

  const { start, end } = conceptInterval;

  const findMatch = (tier: string): string => {
    const intervals = rec.tiers?.[tier]?.intervals;
    if (!intervals) return "";
    const match = intervals.find(
      (iv) => Math.abs(iv.start - start) < EPS && Math.abs(iv.end - end) < EPS,
    );
    return match?.text ?? "";
  };

  const ipa = findMatch("ipa");
  const ortho = findMatch("ortho");
  if (!ipa && !ortho) return null;
  return { ipa, ortho };
}

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

export function BorrowingPanel() {
  const activeConcept = useUIStore((s) => s.activeConcept);
  const selectedSpeakers = useUIStore((s) => s.selectedSpeakers);
  const config = useConfigStore((s) => s.config);
  const enrichmentData = useEnrichmentStore((s) => s.data);
  const saveEnrichments = useEnrichmentStore((s) => s.save);
  const records = useAnnotationStore((s) => s.records);

  const [localDecisions, setLocalDecisions] = useState<Record<string, SpeakerDecision>>({});
  const [openAccordions, setOpenAccordions] = useState<Record<string, boolean>>({});
  const [contactLanguages, setContactLanguages] = useState<ContactLanguage[]>([]);
  const [saving, setSaving] = useState(false);

  const speakers = useMemo(
    () => (selectedSpeakers.length > 0 ? selectedSpeakers : config?.speakers ?? []),
    [selectedSpeakers, config],
  );

  // Load contact languages through the typed CLEF client surface.
  useEffect(() => {
    let cancelled = false;
    getClefConfig()
      .then((data) => {
        if (cancelled || !Array.isArray(data?.languages)) return;
        const enrichmentConfig = (enrichmentData as Record<string, unknown>)?.config as
          | { contact_languages?: string[] }
          | undefined;
        const allowed = Array.isArray(enrichmentConfig?.contact_languages)
          ? enrichmentConfig.contact_languages
          : Array.isArray(data?.primary_contact_languages)
            ? data.primary_contact_languages
            : undefined;
        const languages = data.languages.map((lang) => ({
          code: lang.code,
          name: lang.name,
          family: lang.family ?? undefined,
        }));
        if (allowed && allowed.length > 0) {
          setContactLanguages(languages.filter((lang) => allowed.includes(lang.code)));
        } else {
          setContactLanguages(languages);
        }
      })
      .catch(() => {
        if (!cancelled) setContactLanguages([]);
      });
    return () => {
      cancelled = true;
    };
  }, [enrichmentData]);

  // Similarity data helpers
  const getSimilarity = useCallback(
    (speaker: string, langCode: string): number | null => {
      if (!activeConcept) return null;
      const sim = (enrichmentData as Record<string, unknown>)?.similarity as
        | Record<string, Record<string, Record<string, number>>>
        | undefined;
      if (!sim?.[activeConcept]) return null;
      // Try speaker→lang then lang→speaker
      const v1 = sim[activeConcept]?.[speaker]?.[langCode];
      if (typeof v1 === "number" && Number.isFinite(v1)) return v1;
      const v2 = sim[activeConcept]?.[langCode]?.[speaker];
      if (typeof v2 === "number" && Number.isFinite(v2)) return v2;
      return null;
    },
    [enrichmentData, activeConcept],
  );

  const getAggregateSimilarity = useCallback(
    (langCode: string): number | null => {
      const scores = speakers
        .map((sp) => getSimilarity(sp, langCode))
        .filter((v): v is number => v !== null);
      if (scores.length === 0) return null;
      return scores.reduce((a, b) => a + b, 0) / scores.length;
    },
    [speakers, getSimilarity],
  );

  const autoPickLang = useCallback(
    (speaker: string): string | null => {
      let best: { code: string; score: number } | null = null;
      for (const lang of contactLanguages) {
        const s = getSimilarity(speaker, lang.code);
        if (s !== null && (best === null || s > best.score)) {
          best = { code: lang.code, score: s };
        }
      }
      return best?.code ?? null;
    },
    [contactLanguages, getSimilarity],
  );

  // Decision resolution per speaker
  const resolveDecision = useCallback(
    (speaker: string): SpeakerDecision => {
      if (localDecisions[speaker]) return localDecisions[speaker];
      if (!activeConcept) return { decision: "skip", sourceLang: null };

      const ed = enrichmentData as Record<string, unknown>;
      const manualOverrides = ed?.manual_overrides as
        | { borrowing_flags?: Record<string, Record<string, unknown>> }
        | undefined;
      const baseFlags = ed?.borrowing_flags as
        | Record<string, Record<string, unknown>>
        | undefined;

      const manualEntry = manualOverrides?.borrowing_flags?.[activeConcept]?.[speaker];
      if (manualEntry) {
        if (typeof manualEntry === "object" && manualEntry !== null) {
          const e = manualEntry as { decision?: unknown; sourceLang?: string | null };
          return { decision: normalizeDecision(e.decision), sourceLang: e.sourceLang ?? null };
        }
        return { decision: normalizeDecision(manualEntry), sourceLang: null };
      }

      const baseEntry = baseFlags?.[activeConcept]?.[speaker];
      if (baseEntry) {
        if (typeof baseEntry === "object" && baseEntry !== null) {
          const e = baseEntry as { decision?: unknown; sourceLang?: string | null };
          return { decision: normalizeDecision(e.decision), sourceLang: e.sourceLang ?? null };
        }
        return { decision: normalizeDecision(baseEntry), sourceLang: null };
      }

      return { decision: "skip", sourceLang: null };
    },
    [localDecisions, activeConcept, enrichmentData],
  );

  // Global decision count
  const decisionCount = useMemo(() => {
    const ed = enrichmentData as Record<string, unknown>;
    const manualFlags = (ed?.manual_overrides as Record<string, unknown>)?.borrowing_flags as
      | Record<string, Record<string, unknown>>
      | undefined;
    const baseFlags = ed?.borrowing_flags as
      | Record<string, Record<string, unknown>>
      | undefined;

    const allConcepts = new Set<string>();
    if (manualFlags) Object.keys(manualFlags).forEach((k) => allConcepts.add(k));
    if (baseFlags) Object.keys(baseFlags).forEach((k) => allConcepts.add(k));

    let count = 0;
    for (const cid of allConcepts) {
      const merged = { ...baseFlags?.[cid], ...manualFlags?.[cid] };
      for (const val of Object.values(merged)) {
        let dec: BorrowingDecision;
        if (typeof val === "object" && val !== null) {
          dec = normalizeDecision((val as { decision?: unknown }).decision);
        } else {
          dec = normalizeDecision(val);
        }
        if (dec !== "skip") count++;
      }
    }
    return count;
  }, [enrichmentData]);

  // Radio change handler
  function handleDecisionChange(speaker: string, decision: BorrowingDecision) {
    setLocalDecisions((prev) => ({
      ...prev,
      [speaker]: {
        decision,
        sourceLang:
          decision === "borrowed"
            ? (prev[speaker]?.sourceLang ?? autoPickLang(speaker))
            : null,
      },
    }));
  }

  function handleSourceLangChange(speaker: string, langCode: string) {
    setLocalDecisions((prev) => ({
      ...prev,
      [speaker]: {
        decision: prev[speaker]?.decision ?? "borrowed",
        sourceLang: langCode || null,
      },
    }));
  }

  async function handleSave() {
    if (!activeConcept) return;
    setSaving(true);
    try {
      const ed = enrichmentData as Record<string, unknown>;
      const existingOverrides = (ed?.manual_overrides ?? {}) as Record<string, unknown>;
      const existingFlags = (existingOverrides.borrowing_flags ?? {}) as Record<
        string,
        Record<string, SpeakerDecision>
      >;
      const updated = { ...existingFlags };
      updated[activeConcept] = { ...existingFlags[activeConcept], ...localDecisions };
      await saveEnrichments({
        manual_overrides: { ...existingOverrides, borrowing_flags: updated },
      });
    } finally {
      setSaving(false);
    }
  }

  function toggleAccordion(langCode: string) {
    setOpenAccordions((prev) => ({ ...prev, [langCode]: !prev[langCode] }));
  }

  // Reset local decisions when concept changes
  useEffect(() => {
    setLocalDecisions({});
  }, [activeConcept]);

  /* ------------------------------------------------------------------ */
  /*  Render                                                             */
  /* ------------------------------------------------------------------ */

  if (!activeConcept) {
    return (
      <div style={{ fontFamily: "monospace", padding: "1rem", color: "#6b7280" }}>
        Select a concept
      </div>
    );
  }

  const conceptLabel = activeConcept;

  return (
    <div style={{ fontFamily: "monospace", padding: "1rem", fontSize: "0.8125rem" }}>
      {/* Header */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: "1rem",
        }}
      >
        <div style={{ fontWeight: 600, fontSize: "0.875rem" }}>Borrowing Adjudication</div>
        <Badge label={`${decisionCount} decisions`} />
      </div>
      <div style={{ color: "#6b7280", marginBottom: "1rem" }}>
        Concept #{activeConcept}: {conceptLabel}
      </div>

      {/* Current Forms */}
      <div style={{ marginBottom: "1rem" }}>
        <div style={{ fontWeight: 600, marginBottom: "0.5rem", borderBottom: "1px solid #e5e7eb", paddingBottom: "0.25rem" }}>
          Current Forms
        </div>
        {speakers.map((sp) => {
          const form = lookupForm(records, sp, activeConcept);
          return (
            <div key={sp} style={{ padding: "0.25rem 0" }}>
              <span style={{ fontWeight: 500 }}>{sp}</span>
              {": "}
              {form ? (
                <span>
                  {form.ipa}
                  {form.ortho && form.ipa ? " / " : ""}
                  {form.ortho}
                </span>
              ) : (
                <span style={{ color: "#9ca3af", fontStyle: "italic" }}>No form</span>
              )}
            </div>
          );
        })}
      </div>

      {/* Contact Language Similarity */}
      {contactLanguages.length > 0 && (
        <div style={{ marginBottom: "1rem" }}>
          <div style={{ fontWeight: 600, marginBottom: "0.5rem", borderBottom: "1px solid #e5e7eb", paddingBottom: "0.25rem" }}>
            Contact Language Similarity
          </div>
          {contactLanguages.map((lang) => {
            const aggScore = getAggregateSimilarity(lang.code);
            const band = aggScore !== null ? scoreBand(aggScore) : null;
            const isOpen = openAccordions[lang.code] ?? false;

            return (
              <div key={lang.code} style={{ marginBottom: "0.25rem" }}>
                <div
                  data-testid={`lang-row-${lang.code}`}
                  onClick={() => toggleAccordion(lang.code)}
                  style={{
                    cursor: "pointer",
                    padding: "0.375rem 0.5rem",
                    display: "flex",
                    alignItems: "center",
                    gap: "0.5rem",
                    background: "#f9fafb",
                    borderRadius: "0.25rem",
                  }}
                >
                  <span style={{ fontSize: "0.75rem" }}>{isOpen ? "v" : ">"}</span>
                  <span style={{ fontWeight: 500 }}>
                    {lang.name}
                    {lang.family ? ` (${lang.family})` : ""}
                  </span>
                  {aggScore !== null && band && (
                    <>
                      <SimBar score={aggScore} />
                      <span>{aggScore.toFixed(2)}</span>
                      <span
                        style={{
                          fontSize: "0.75rem",
                          padding: "0.125rem 0.375rem",
                          borderRadius: "0.25rem",
                          background: BAND_COLORS[band].bg,
                        }}
                      >
                        {BAND_COLORS[band].label}
                      </span>
                    </>
                  )}
                </div>
                {isOpen && (
                  <div style={{ paddingLeft: "1.5rem", padding: "0.25rem 0 0.25rem 1.5rem" }}>
                    {speakers.map((sp) => {
                      const spScore = getSimilarity(sp, lang.code);
                      return (
                        <div key={sp} style={{ display: "flex", alignItems: "center", gap: "0.5rem", padding: "0.125rem 0" }}>
                          <span style={{ minWidth: "4rem" }}>{sp}:</span>
                          {spScore !== null ? <SimBar score={spScore} /> : <span style={{ color: "#9ca3af" }}>--</span>}
                          {spScore !== null && <span>{spScore.toFixed(2)}</span>}
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* Adjudication */}
      <div style={{ marginBottom: "1rem" }}>
        <div style={{ fontWeight: 600, marginBottom: "0.5rem", borderBottom: "1px solid #e5e7eb", paddingBottom: "0.25rem" }}>
          Adjudication
        </div>
        {speakers.map((sp) => {
          const form = lookupForm(records, sp, activeConcept);
          const resolved = resolveDecision(sp);
          const hasForm = form !== null;

          return (
            <div
              key={sp}
              data-testid={`adjudication-${sp}`}
              style={{ padding: "0.5rem 0", borderBottom: "1px solid #f3f4f6" }}
            >
              <div style={{ fontWeight: 500, marginBottom: "0.25rem" }}>
                {sp}
                {form ? ` "${form.ipa || form.ortho}"` : ""}
                {!hasForm && (
                  <span style={{ color: "#9ca3af", fontStyle: "italic", marginLeft: "0.5rem" }}>
                    (no form)
                  </span>
                )}
              </div>
              <div style={{ display: "flex", gap: "0.75rem", alignItems: "center", flexWrap: "wrap" }}>
                {DECISION_OPTIONS.map((opt) => {
                  const isDisabled = !hasForm && opt !== "skip";
                  return (
                    <label
                      key={opt}
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: "0.25rem",
                        cursor: isDisabled ? "not-allowed" : "pointer",
                        opacity: isDisabled ? 0.4 : 1,
                      }}
                    >
                      <input
                        type="radio"
                        name={`decision-${sp}`}
                        value={opt}
                        checked={resolved.decision === opt}
                        disabled={isDisabled}
                        onChange={() => handleDecisionChange(sp, opt)}
                        data-testid={`radio-${sp}-${opt}`}
                      />
                      {opt}
                    </label>
                  );
                })}
              </div>
              {resolved.decision === "borrowed" && hasForm && (
                <div style={{ marginTop: "0.375rem" }}>
                  <Select
                    label="Source language"
                    data-testid={`source-lang-${sp}`}
                    value={resolved.sourceLang ?? ""}
                    onChange={(e) => handleSourceLangChange(sp, e.target.value)}
                    options={[
                      { value: "", label: "-- select --" },
                      ...contactLanguages.map((l) => ({
                        value: l.code,
                        label: `${l.name}${l.family ? ` (${l.family})` : ""}`,
                      })),
                    ]}
                  />
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Save */}
      <Button
        variant="primary"
        size="sm"
        loading={saving}
        onClick={handleSave}
        disabled={Object.keys(localDecisions).length === 0}
      >
        Save Decisions
      </Button>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  SimBar — inline similarity visualization                           */
/* ------------------------------------------------------------------ */

function SimBar({ score }: { score: number }) {
  const pct = Math.round(score * 100);
  const band = scoreBand(score);
  const barColor = band === "unlikely" ? "#86efac" : band === "possible" ? "#fcd34d" : "#fca5a5";
  return (
    <div
      style={{
        width: "4rem",
        height: "0.5rem",
        background: "#e5e7eb",
        borderRadius: "0.25rem",
        overflow: "hidden",
      }}
    >
      <div
        style={{
          width: `${pct}%`,
          height: "100%",
          background: barColor,
          borderRadius: "0.25rem",
        }}
      />
    </div>
  );
}
