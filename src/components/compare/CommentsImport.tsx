import { useRef, useState } from "react";
import { Button } from "../shared/Button";
import { importCommentsCsv } from "../../api/client";
import { useConfigStore } from "../../stores/configStore";
import { useEnrichmentStore } from "../../stores/enrichmentStore";

interface CommentsImportProps {
  onImportComplete?: () => void;
}

type ImportStatus = "idle" | "uploading" | "done" | "error";

export function CommentsImport({ onImportComplete }: CommentsImportProps) {
  const config = useConfigStore((s) => s.config);
  const loadEnrichments = useEnrichmentStore((s) => s.load);
  const speakers = config?.speakers ?? [];

  const [speakerId, setSpeakerId] = useState<string>(speakers[0] ?? "");
  const [csvFile, setCsvFile] = useState<File | null>(null);
  const [status, setStatus] = useState<ImportStatus>("idle");
  const [result, setResult] = useState<{ imported: number; matched: number; total: number } | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const csvInputRef = useRef<HTMLInputElement>(null);

  async function handleImport() {
    if (!speakerId.trim() || !csvFile) return;
    setStatus("uploading");
    setErrorMsg(null);
    setResult(null);
    try {
      const resp = await importCommentsCsv(speakerId.trim(), csvFile);
      setResult({ imported: resp.imported, matched: resp.matched, total: resp.total_rows });
      setStatus("done");
      await loadEnrichments().catch(() => {});
      onImportComplete?.();
    } catch (err) {
      setStatus("error");
      setErrorMsg(err instanceof Error ? err.message : "Import failed");
    }
  }

  const canStart = status === "idle" && speakerId.trim().length > 0 && csvFile !== null;

  return (
    <div data-testid="comments-import" style={{ padding: "1rem", fontFamily: "monospace" }}>
      <div style={{ fontWeight: 600, fontSize: "1rem", marginBottom: "0.5rem" }}>
        Import Audition Comments
      </div>
      <div style={{ fontSize: "0.75rem", color: "#6b7280", marginBottom: "0.75rem" }}>
        Parses the Name column (e.g. <code>(2.3)- father (vocative) B short word, used by children</code>)
        and attaches any trailing comment as the lexeme's import note. Aligns to existing lexeme
        intervals by concept id, falling back to nearest start time (±500 ms).
      </div>

      <div style={{ marginBottom: "0.5rem" }}>
        <label style={{ display: "block", fontSize: "0.75rem", fontWeight: 500, marginBottom: "0.125rem" }}>
          Speaker
        </label>
        {speakers.length > 0 ? (
          <select
            value={speakerId}
            onChange={(e) => setSpeakerId(e.target.value)}
            disabled={status === "uploading"}
            style={{
              width: "100%",
              border: "1px solid #d1d5db",
              borderRadius: "0.25rem",
              padding: "0.375rem 0.625rem",
              fontSize: "0.875rem",
              fontFamily: "monospace",
            }}
          >
            {speakers.map((sp) => (
              <option key={sp} value={sp}>
                {sp}
              </option>
            ))}
          </select>
        ) : (
          <input
            value={speakerId}
            onChange={(e) => setSpeakerId(e.target.value)}
            disabled={status === "uploading"}
            placeholder="speaker id"
            style={{
              width: "100%",
              border: "1px solid #d1d5db",
              borderRadius: "0.25rem",
              padding: "0.375rem 0.625rem",
              fontSize: "0.875rem",
              fontFamily: "monospace",
            }}
          />
        )}
      </div>

      <div style={{ marginBottom: "0.75rem" }}>
        <label style={{ display: "block", fontSize: "0.75rem", fontWeight: 500, marginBottom: "0.125rem" }}>
          Comments CSV (tab-separated)
        </label>
        <input
          ref={csvInputRef}
          data-testid="comments-csv-input"
          type="file"
          accept=".csv,.tsv,.txt"
          disabled={status === "uploading"}
          onChange={(e) => setCsvFile(e.target.files?.[0] ?? null)}
          style={{ fontSize: "0.8rem" }}
        />
      </div>

      <Button
        variant="primary"
        disabled={!canStart}
        onClick={handleImport}
        data-testid="start-comments-import-btn"
      >
        {status === "uploading" ? "Importing…" : "Import Comments"}
      </Button>

      {status === "done" && result && (
        <div
          data-testid="comments-import-success"
          style={{ marginTop: "0.75rem", color: "#059669", fontSize: "0.85rem" }}
        >
          Imported {result.imported} of {result.total} rows ({result.matched} aligned to existing lexemes).
        </div>
      )}

      {status === "error" && errorMsg && (
        <div
          data-testid="comments-import-error"
          style={{ marginTop: "0.75rem", color: "#dc2626", fontSize: "0.85rem" }}
        >
          {errorMsg}
        </div>
      )}
    </div>
  );
}
