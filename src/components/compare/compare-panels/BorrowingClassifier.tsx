import type React from "react";
import { Select } from "../../shared/Select";
import { BAND_COLORS, DECISION_OPTIONS, scoreBand } from "./shared";
import type { BorrowingDecision, ContactLanguage, SpeakerDecision } from "./types";

function SimBar({ score }: { score: number }) {
  const pct = Math.round(score * 100);
  const band = scoreBand(score);
  const barColor = band === "unlikely" ? "#86efac" : band === "possible" ? "#fcd34d" : "#fca5a5";
  return (
    <div style={{ width: "4rem", height: "0.5rem", background: "#e5e7eb", borderRadius: "0.25rem", overflow: "hidden" }}>
      <div style={{ width: `${pct}%`, height: "100%", background: barColor, borderRadius: "0.25rem" }} />
    </div>
  );
}

export function BorrowingClassifier({
  speaker,
  form,
  resolved,
  hasForm,
  contactLanguages,
  handleDecisionChange,
  handleSourceLangChange,
}: {
  speaker: string;
  form: { ipa: string; ortho: string } | null;
  resolved: SpeakerDecision;
  hasForm: boolean;
  contactLanguages: ContactLanguage[];
  handleDecisionChange: (speaker: string, decision: BorrowingDecision) => void;
  handleSourceLangChange: (speaker: string, langCode: string) => void;
}) {
  return (
    <div data-testid={`adjudication-${speaker}`} style={{ padding: "0.5rem 0", borderBottom: "1px solid #f3f4f6" }}>
      <div style={{ fontWeight: 500, marginBottom: "0.25rem" }}>
        {speaker}
        {form ? ` "${form.ipa || form.ortho}"` : ""}
        {!hasForm && <span style={{ color: "#9ca3af", fontStyle: "italic", marginLeft: "0.5rem" }}>(no form)</span>}
      </div>
      <div style={{ display: "flex", gap: "0.75rem", alignItems: "center", flexWrap: "wrap" }}>
        {DECISION_OPTIONS.map((opt) => {
          const isDisabled = !hasForm && opt !== "skip";
          return (
            <label key={opt} style={{ display: "flex", alignItems: "center", gap: "0.25rem", cursor: isDisabled ? "not-allowed" : "pointer", opacity: isDisabled ? 0.4 : 1 }}>
              <input
                type="radio"
                name={`decision-${speaker}`}
                value={opt}
                checked={resolved.decision === opt}
                disabled={isDisabled}
                onChange={() => handleDecisionChange(speaker, opt)}
                data-testid={`radio-${speaker}-${opt}`}
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
            data-testid={`source-lang-${speaker}`}
            value={resolved.sourceLang ?? ""}
            onChange={(e: React.ChangeEvent<HTMLSelectElement>) => handleSourceLangChange(speaker, e.target.value)}
            options={[
              { value: "", label: "-- select --" },
              ...contactLanguages.map((lang) => ({ value: lang.code, label: `${lang.name}${lang.family ? ` (${lang.family})` : ""}` })),
            ]}
          />
        </div>
      )}
    </div>
  );
}

export function SimilarityAccordion({
  lang,
  aggScore,
  isOpen,
  toggleAccordion,
  speakers,
  getSimilarity,
}: {
  lang: ContactLanguage;
  aggScore: number | null;
  isOpen: boolean;
  toggleAccordion: (langCode: string) => void;
  speakers: string[];
  getSimilarity: (speaker: string, langCode: string) => number | null;
}) {
  const band = aggScore !== null ? scoreBand(aggScore) : null;
  return (
    <div style={{ marginBottom: "0.25rem" }}>
      <div
        data-testid={`lang-row-${lang.code}`}
        onClick={() => toggleAccordion(lang.code)}
        style={{ cursor: "pointer", padding: "0.375rem 0.5rem", display: "flex", alignItems: "center", gap: "0.5rem", background: "#f9fafb", borderRadius: "0.25rem" }}
      >
        <span style={{ fontSize: "0.75rem" }}>{isOpen ? "v" : ">"}</span>
        <span style={{ fontWeight: 500 }}>{lang.name}{lang.family ? ` (${lang.family})` : ""}</span>
        {aggScore !== null && band && (
          <>
            <SimBar score={aggScore} />
            <span>{aggScore.toFixed(2)}</span>
            <span style={{ fontSize: "0.75rem", padding: "0.125rem 0.375rem", borderRadius: "0.25rem", background: BAND_COLORS[band].bg }}>{BAND_COLORS[band].label}</span>
          </>
        )}
      </div>
      {isOpen && (
        <div style={{ paddingLeft: "1.5rem", padding: "0.25rem 0 0.25rem 1.5rem" }}>
          {speakers.map((speaker) => {
            const spScore = getSimilarity(speaker, lang.code);
            return (
              <div key={speaker} style={{ display: "flex", alignItems: "center", gap: "0.5rem", padding: "0.125rem 0" }}>
                <span style={{ minWidth: "4rem" }}>{speaker}:</span>
                {spScore !== null ? <SimBar score={spScore} /> : <span style={{ color: "#9ca3af" }}>--</span>}
                {spScore !== null && <span>{spScore.toFixed(2)}</span>}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
