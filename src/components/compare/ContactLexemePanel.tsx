import { useState, useEffect, useCallback, useRef } from "react";
import { getContactLexemeCoverage, startContactLexemeFetch, pollCompute } from "../../api/client";
import type { ContactLexemeCoverage } from "../../api/types";

const PROVIDERS = ["csv_override", "asjp", "cldf", "wikidata", "wiktionary", "grok_llm", "literature"];

export function ContactLexemePanel() {
  const [coverage, setCoverage] = useState<ContactLexemeCoverage | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedProviders, setSelectedProviders] = useState<string[]>([]);
  const [overwrite, setOverwrite] = useState(false);

  const [isRunning, setIsRunning] = useState(false);
  const [jobProgress, setJobProgress] = useState(0);
  const [jobMessage, setJobMessage] = useState("");
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const loadCoverage = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getContactLexemeCoverage();
      setCoverage(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load coverage");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadCoverage(); }, [loadCoverage]);

  useEffect(() => {
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, []);

  const handleFetch = async () => {
    setIsRunning(true);
    setJobProgress(0);
    setJobMessage("Starting...");
    setError(null);
    try {
      const job = await startContactLexemeFetch({
        providers: selectedProviders.length > 0 ? selectedProviders : undefined,
        overwrite,
      });
      const id = job.job_id || job.jobId || "";
      if (!id) throw new Error("Missing job id");

      const poll = async () => {
        try {
          const status = await pollCompute("contact-lexemes", id);
          setJobProgress(status.progress ?? 0);
          setJobMessage(status.message ?? "");
          if (status.status === "done" || status.status === "complete" || status.status === "error" || status.status === "failed") {
            setIsRunning(false);
            if (status.status === "error" || status.status === "failed") {
              setError(status.error ?? status.message ?? "Fetch failed");
            }
            loadCoverage();
          } else {
            timerRef.current = setTimeout(poll, 1500);
          }
        } catch (e) {
          setIsRunning(false);
          setError(e instanceof Error ? e.message : "Polling failed");
        }
      };
      timerRef.current = setTimeout(poll, 1000);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Fetch failed");
      setIsRunning(false);
    }
  };

  return (
    <div style={{ padding: "1rem", fontFamily: "monospace", fontSize: "0.85rem" }}>
      <div style={{ fontWeight: 700, marginBottom: "0.75rem", fontSize: "0.9rem" }}>
        Contact Language Lexemes
      </div>

      {loading && <div style={{ color: "#9ca3af" }}>Loading coverage...</div>}
      {error && <div style={{ color: "#ef4444" }}>{error}</div>}
      {coverage && (
        <div style={{ marginBottom: "1rem" }}>
          {Object.entries(coverage.languages).map(([code, lang]) => {
            const pct = lang.total > 0 ? Math.round((lang.filled / lang.total) * 100) : 0;
            return (
              <div key={code} style={{ marginBottom: "0.5rem" }}>
                <div style={{ display: "flex", justifyContent: "space-between", color: "#d1d5db" }}>
                  <span>{lang.name} ({code})</span>
                  <span>{lang.filled}/{lang.total} concepts</span>
                </div>
                <div style={{ background: "#374151", borderRadius: 2, height: 6, marginTop: 3 }}>
                  <div style={{
                    background: pct === 100 ? "#10b981" : "#3b82f6",
                    width: `${pct}%`, height: "100%", borderRadius: 2,
                    transition: "width 0.3s",
                  }} />
                </div>
              </div>
            );
          })}
        </div>
      )}

      <div style={{ marginBottom: "0.75rem" }}>
        <div style={{ color: "#9ca3af", marginBottom: "0.25rem" }}>Providers (empty = all):</div>
        <div style={{ display: "flex", flexWrap: "wrap", gap: "0.4rem" }}>
          {PROVIDERS.map((p) => {
            const active = selectedProviders.includes(p);
            return (
              <button
                key={p}
                onClick={() =>
                  setSelectedProviders((prev) =>
                    active ? prev.filter((x) => x !== p) : [...prev, p]
                  )
                }
                style={{
                  padding: "2px 8px",
                  background: active ? "#1d4ed8" : "#1f2937",
                  color: active ? "#fff" : "#9ca3af",
                  border: "1px solid #374151",
                  borderRadius: 3,
                  cursor: "pointer",
                  fontFamily: "monospace",
                  fontSize: "0.75rem",
                }}
              >
                {p}
              </button>
            );
          })}
        </div>
      </div>

      <label style={{ display: "flex", alignItems: "center", gap: "0.5rem", color: "#9ca3af", marginBottom: "0.75rem", cursor: "pointer" }}>
        <input type="checkbox" checked={overwrite} onChange={(e) => setOverwrite(e.target.checked)} />
        Overwrite existing forms
      </label>

      <button
        onClick={handleFetch}
        disabled={isRunning}
        style={{
          padding: "6px 16px",
          background: isRunning ? "#374151" : "#2563eb",
          color: isRunning ? "#9ca3af" : "#fff",
          border: "none",
          borderRadius: 3,
          cursor: isRunning ? "not-allowed" : "pointer",
          fontFamily: "monospace",
          fontSize: "0.85rem",
          marginBottom: "0.75rem",
        }}
      >
        {isRunning ? "Fetching..." : "Fetch Missing"}
      </button>

      {isRunning && (
        <div style={{ color: "#9ca3af", fontSize: "0.8rem" }}>
          <div style={{ background: "#374151", borderRadius: 2, height: 4, marginBottom: "0.25rem" }}>
            <div style={{ background: "#3b82f6", width: `${jobProgress}%`, height: "100%", borderRadius: 2, transition: "width 0.3s" }} />
          </div>
          {jobMessage}
        </div>
      )}
    </div>
  );
}
