import { useEffect, useMemo, useState } from "react";
import { getClefConfig } from "../../../api/client";
import { Button } from "../../shared/Button";
import { Badge } from "../../shared/Badge";
import { BorrowingClassifier, SimilarityAccordion } from "./BorrowingClassifier";
import { lookupForm, normalizeDecision, resolveSpeakerDecision } from "./shared";
import { useCompareSelection } from "./useCompareSelection";
import { useEnrichmentsBinding } from "./useEnrichmentsBinding";
import type { ContactLanguage, SpeakerDecision } from "./types";

export function BorrowingPanel() {
  const { activeConcept, records, speakers } = useCompareSelection();
  const { enrichmentData, saveEnrichments } = useEnrichmentsBinding();
  const [localDecisions, setLocalDecisions] = useState<Record<string, SpeakerDecision>>({});
  const [openAccordions, setOpenAccordions] = useState<Record<string, boolean>>({});
  const [contactLanguages, setContactLanguages] = useState<ContactLanguage[]>([]);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let cancelled = false;
    getClefConfig()
      .then((data) => {
        if (cancelled || !Array.isArray(data?.languages)) return;
        const enrichmentConfig = (enrichmentData as Record<string, unknown>)?.config as { contact_languages?: string[] } | undefined;
        const allowed = Array.isArray(enrichmentConfig?.contact_languages)
          ? enrichmentConfig.contact_languages
          : Array.isArray(data?.primary_contact_languages)
            ? data.primary_contact_languages
            : undefined;
        const languages = data.languages.map((lang) => ({ code: lang.code, name: lang.name, family: lang.family ?? undefined }));
        setContactLanguages(allowed && allowed.length > 0 ? languages.filter((lang) => allowed.includes(lang.code)) : languages);
      })
      .catch(() => {
        if (!cancelled) setContactLanguages([]);
      });
    return () => {
      cancelled = true;
    };
  }, [enrichmentData]);

  const getSimilarity = (speaker: string, langCode: string): number | null => {
    if (!activeConcept) return null;
    const sim = (enrichmentData as Record<string, unknown>)?.similarity as Record<string, Record<string, Record<string, number>>> | undefined;
    if (!sim?.[activeConcept]) return null;
    const v1 = sim[activeConcept]?.[speaker]?.[langCode];
    if (typeof v1 === "number" && Number.isFinite(v1)) return v1;
    const v2 = sim[activeConcept]?.[langCode]?.[speaker];
    if (typeof v2 === "number" && Number.isFinite(v2)) return v2;
    return null;
  };

  const getAggregateSimilarity = (langCode: string): number | null => {
    const scores = speakers.map((speaker) => getSimilarity(speaker, langCode)).filter((value): value is number => value !== null);
    if (scores.length === 0) return null;
    return scores.reduce((a, b) => a + b, 0) / scores.length;
  };

  const autoPickLang = (speaker: string): string | null => {
    let best: { code: string; score: number } | null = null;
    for (const lang of contactLanguages) {
      const score = getSimilarity(speaker, lang.code);
      if (score !== null && (best === null || score > best.score)) best = { code: lang.code, score };
    }
    return best?.code ?? null;
  };

  const decisionCount = useMemo(() => {
    const ed = enrichmentData as Record<string, unknown>;
    const manualFlags = (ed?.manual_overrides as Record<string, unknown>)?.borrowing_flags as Record<string, Record<string, unknown>> | undefined;
    const baseFlags = ed?.borrowing_flags as Record<string, Record<string, unknown>> | undefined;
    const allConcepts = new Set<string>();
    if (manualFlags) Object.keys(manualFlags).forEach((key) => allConcepts.add(key));
    if (baseFlags) Object.keys(baseFlags).forEach((key) => allConcepts.add(key));
    let count = 0;
    for (const conceptId of allConcepts) {
      const merged = { ...baseFlags?.[conceptId], ...manualFlags?.[conceptId] };
      for (const value of Object.values(merged)) {
        const decision = typeof value === "object" && value !== null
          ? normalizeDecision((value as { decision?: unknown }).decision)
          : normalizeDecision(value);
        if (decision !== "skip") count += 1;
      }
    }
    return count;
  }, [enrichmentData]);

  const handleDecisionChange = (speaker: string, decision: SpeakerDecision["decision"]) => {
    setLocalDecisions((prev) => ({
      ...prev,
      [speaker]: {
        decision,
        sourceLang: decision === "borrowed" ? (prev[speaker]?.sourceLang ?? autoPickLang(speaker)) : null,
      },
    }));
  };

  const handleSourceLangChange = (speaker: string, langCode: string) => {
    setLocalDecisions((prev) => ({ ...prev, [speaker]: { decision: prev[speaker]?.decision ?? "borrowed", sourceLang: langCode || null } }));
  };

  const handleSave = async () => {
    if (!activeConcept) return;
    setSaving(true);
    try {
      const ed = enrichmentData as Record<string, unknown>;
      const existingOverrides = (ed?.manual_overrides ?? {}) as Record<string, unknown>;
      const existingFlags = (existingOverrides.borrowing_flags ?? {}) as Record<string, Record<string, SpeakerDecision>>;
      const updated = { ...existingFlags, [activeConcept]: { ...existingFlags[activeConcept], ...localDecisions } };
      await saveEnrichments({ manual_overrides: { ...existingOverrides, borrowing_flags: updated } });
    } finally {
      setSaving(false);
    }
  };

  useEffect(() => {
    setLocalDecisions({});
  }, [activeConcept]);

  if (!activeConcept) return <div style={{ fontFamily: "monospace", padding: "1rem", color: "#6b7280" }}>Select a concept</div>;

  return (
    <div style={{ fontFamily: "monospace", padding: "1rem", fontSize: "0.8125rem" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1rem" }}>
        <div style={{ fontWeight: 600, fontSize: "0.875rem" }}>Borrowing Adjudication</div>
        <Badge label={`${decisionCount} decisions`} />
      </div>
      <div style={{ color: "#6b7280", marginBottom: "1rem" }}>Concept #{activeConcept}: {activeConcept}</div>

      <div style={{ marginBottom: "1rem" }}>
        <div style={{ fontWeight: 600, marginBottom: "0.5rem", borderBottom: "1px solid #e5e7eb", paddingBottom: "0.25rem" }}>Current Forms</div>
        {speakers.map((speaker) => {
          const form = lookupForm(records, speaker, activeConcept);
          return <div key={speaker} style={{ padding: "0.25rem 0" }}><span style={{ fontWeight: 500 }}>{speaker}</span>{": "}{form ? <span>{form.ipa}{form.ortho && form.ipa ? " / " : ""}{form.ortho}</span> : <span style={{ color: "#9ca3af", fontStyle: "italic" }}>No form</span>}</div>;
        })}
      </div>

      {contactLanguages.length > 0 && (
        <div style={{ marginBottom: "1rem" }}>
          <div style={{ fontWeight: 600, marginBottom: "0.5rem", borderBottom: "1px solid #e5e7eb", paddingBottom: "0.25rem" }}>Contact Language Similarity</div>
          {contactLanguages.map((lang) => (
            <SimilarityAccordion
              key={lang.code}
              lang={lang}
              aggScore={getAggregateSimilarity(lang.code)}
              isOpen={openAccordions[lang.code] ?? false}
              toggleAccordion={(langCode) => setOpenAccordions((prev) => ({ ...prev, [langCode]: !prev[langCode] }))}
              speakers={speakers}
              getSimilarity={getSimilarity}
            />
          ))}
        </div>
      )}

      <div style={{ marginBottom: "1rem" }}>
        <div style={{ fontWeight: 600, marginBottom: "0.5rem", borderBottom: "1px solid #e5e7eb", paddingBottom: "0.25rem" }}>Adjudication</div>
        {speakers.map((speaker) => {
          const form = lookupForm(records, speaker, activeConcept);
          const resolved = resolveSpeakerDecision(localDecisions, activeConcept, enrichmentData, speaker);
          return (
            <BorrowingClassifier
              key={speaker}
              speaker={speaker}
              form={form}
              resolved={resolved}
              hasForm={form !== null}
              contactLanguages={contactLanguages}
              handleDecisionChange={handleDecisionChange}
              handleSourceLangChange={handleSourceLangChange}
            />
          );
        })}
      </div>

      <Button variant="primary" size="sm" loading={saving} onClick={handleSave} disabled={Object.keys(localDecisions).length === 0}>Save Decisions</Button>
    </div>
  );
}
