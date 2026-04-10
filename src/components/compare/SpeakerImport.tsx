import { useState, useRef, useCallback } from "react";
import { Button } from "../shared/Button";
import { ProgressBar } from "../shared/ProgressBar";
import { onboardSpeaker, pollOnboardSpeaker } from "../../api/client";

interface SpeakerImportProps {
  onImportComplete?: (speakerId: string) => void;
}

type ImportStatus = "idle" | "uploading" | "polling" | "done" | "error";

export function SpeakerImport({ onImportComplete }: SpeakerImportProps) {
  const [speakerId, setSpeakerId] = useState("");
  const [audioFile, setAudioFile] = useState<File | null>(null);
  const [csvFile, setCsvFile] = useState<File | null>(null);
  const [status, setStatus] = useState<ImportStatus>("idle");
  const [progress, setProgress] = useState(0);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);

  const abortRef = useRef(false);
  const audioInputRef = useRef<HTMLInputElement>(null);
  const csvInputRef = useRef<HTMLInputElement>(null);

  const resetForm = useCallback(() => {
    setSpeakerId("");
    setAudioFile(null);
    setCsvFile(null);
    setStatus("idle");
    setProgress(0);
    setErrorMsg(null);
    setJobId(null);
    if (audioInputRef.current) audioInputRef.current.value = "";
    if (csvInputRef.current) csvInputRef.current.value = "";
  }, []);

  async function handleStartImport() {
    if (!speakerId.trim() || !audioFile) return;

    abortRef.current = false;
    setStatus("uploading");
    setProgress(10);
    setErrorMsg(null);

    try {
      // Step 1: Upload via typed client
      const { job_id: newJobId } = await onboardSpeaker(
        speakerId.trim(),
        audioFile,
        csvFile,
      );
      setJobId(newJobId);
      setStatus("polling");
      setProgress(30);

      // Step 2: Poll via typed client
      let pollCount = 0;
      const MAX_POLLS = 120;

      while (pollCount < MAX_POLLS && !abortRef.current) {
        await new Promise<void>((resolve) => setTimeout(resolve, 2000));
        pollCount++;

        const pollResult = await pollOnboardSpeaker(newJobId);
        const mappedProgress = 30 + Math.floor(pollResult.progress * 0.7);
        setProgress(mappedProgress);

        if (pollResult.status === "done" || pollResult.status === "complete") {
          setStatus("done");
          setProgress(100);
          onImportComplete?.(speakerId.trim());
          setTimeout(() => resetForm(), 2000);
          return;
        }

        if (pollResult.status === "error" || pollResult.status === "failed") {
          throw new Error("Processing failed on server");
        }
      }

      if (pollCount >= MAX_POLLS) {
        throw new Error("Import timed out after 4 minutes");
      }
    } catch (err: unknown) {
      setStatus("error");
      setErrorMsg(err instanceof Error ? err.message : "Unknown error");
    }
  }

  function handleRetry() {
    abortRef.current = true;
    setStatus("idle");
    setProgress(0);
    setErrorMsg(null);
    setJobId(null);
  }

  const canStart = status === "idle" && speakerId.trim().length > 0 && audioFile !== null;

  return (
    <div data-testid="speaker-import" style={{ padding: "1rem", fontFamily: "monospace" }}>
      <div style={{ fontWeight: 600, fontSize: "1rem", marginBottom: "0.75rem" }}>
        Speaker Import
      </div>

      {/* Speaker ID */}
      <div style={{ marginBottom: "0.5rem" }}>
        <label style={{ display: "block", fontSize: "0.75rem", fontWeight: 500, marginBottom: "0.125rem" }}>
          Speaker ID
        </label>
        <input
          data-testid="speaker-id-input"
          value={speakerId}
          onChange={(e) => setSpeakerId(e.target.value)}
          disabled={status !== "idle"}
          placeholder="e.g. speaker_01"
          style={{
            width: "100%",
            border: "1px solid #d1d5db",
            borderRadius: "0.25rem",
            padding: "0.375rem 0.625rem",
            fontSize: "0.875rem",
            fontFamily: "monospace",
            boxSizing: "border-box",
          }}
        />
      </div>

      {/* Audio file */}
      <div style={{ marginBottom: "0.5rem" }}>
        <label style={{ display: "block", fontSize: "0.75rem", fontWeight: 500, marginBottom: "0.125rem" }}>
          Audio WAV
        </label>
        <input
          ref={audioInputRef}
          data-testid="audio-file-input"
          type="file"
          accept="audio/*,.wav"
          disabled={status !== "idle"}
          onChange={(e) => setAudioFile(e.target.files?.[0] ?? null)}
          style={{ fontSize: "0.8rem" }}
        />
      </div>

      {/* CSV file */}
      <div style={{ marginBottom: "0.75rem" }}>
        <label style={{ display: "block", fontSize: "0.75rem", fontWeight: 500, marginBottom: "0.125rem" }}>
          Audition CSV (optional)
        </label>
        <input
          ref={csvInputRef}
          data-testid="csv-file-input"
          type="file"
          accept=".csv"
          disabled={status !== "idle"}
          onChange={(e) => setCsvFile(e.target.files?.[0] ?? null)}
          style={{ fontSize: "0.8rem" }}
        />
      </div>

      {/* Start button */}
      <Button
        variant="primary"
        disabled={!canStart}
        onClick={handleStartImport}
        data-testid="start-import-btn"
      >
        Start Import Pipeline
      </Button>

      {/* Progress */}
      {(status === "uploading" || status === "polling") && (
        <div style={{ marginTop: "0.75rem" }}>
          <ProgressBar value={progress} label="Import progress" />
          <div style={{ fontSize: "0.75rem", color: "#6b7280", marginTop: "0.25rem" }}>
            {status === "uploading" ? "Uploading..." : `Polling (job: ${jobId})`}
          </div>
        </div>
      )}

      {/* Done */}
      {status === "done" && (
        <div
          data-testid="import-success"
          style={{ marginTop: "0.75rem", color: "#059669", fontSize: "0.85rem" }}
        >
          Import complete for {speakerId}
        </div>
      )}

      {/* Error */}
      {status === "error" && errorMsg && (
        <div style={{ marginTop: "0.75rem" }}>
          <div
            data-testid="import-error"
            style={{ color: "#dc2626", fontSize: "0.85rem", marginBottom: "0.375rem" }}
          >
            {errorMsg}
          </div>
          <Button size="sm" variant="secondary" onClick={handleRetry}>
            Retry
          </Button>
        </div>
      )}
    </div>
  );
}
