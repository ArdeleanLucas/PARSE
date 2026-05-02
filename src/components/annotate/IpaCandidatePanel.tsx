import { useCallback, useEffect, useMemo, useState } from "react";

import { putIpaReview } from "../../api/client";
import type { IpaCandidate, IpaReviewState, IpaReviewUpdate } from "../../api/types";
import { useAnnotationStore } from "../../stores/annotationStore";
import { Button } from "../shared/Button";
import { Input } from "../shared/Input";

interface IpaCandidatePanelProps {
  speaker: string;
  intervalKey: string;
}

const EMPTY_HINT = "No IPA candidate for this interval. Run IPA in the run modal to generate one.";

function statusLabel(status: IpaReviewState["status"] | undefined): string {
  if (!status || status === "needs_review") return "needs review";
  if (status === "auto_accepted") return "auto accepted";
  return status;
}

function reviewWithDefaults(state: IpaReviewUpdate): IpaReviewState {
  return {
    status: state.status ?? "needs_review",
    suggested_ipa: state.suggested_ipa ?? "",
    resolution_type: state.resolution_type ?? "",
    evidence_sources: state.evidence_sources ?? [],
    notes: state.notes ?? "",
  };
}

export function IpaCandidatePanel({ speaker, intervalKey }: IpaCandidatePanelProps) {
  const record = useAnnotationStore((state) => state.records[speaker] ?? null);
  const setIpaReview = useAnnotationStore((state) => state.setIpaReview);
  const candidates = record?.ipa_candidates?.[intervalKey] ?? [];
  const currentReview = record?.ipa_review?.[intervalKey] ?? null;
  const selected = useMemo<IpaCandidate | null>(() => candidates.length ? candidates[candidates.length - 1] : null, [candidates]);
  const [expanded, setExpanded] = useState(true);
  const [editing, setEditing] = useState(false);
  const [editedIpa, setEditedIpa] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    setEditing(false);
    setEditedIpa("");
    setError("");
  }, [intervalKey]);

  const hasCandidates = candidates.length > 0;

  const saveReview = useCallback(async (partialState: IpaReviewUpdate) => {
    if (!selected && partialState.status !== "needs_review") return;
    const nextReview = reviewWithDefaults(partialState);
    const previous = currentReview;
    setError("");
    setSaving(true);
    setIpaReview(speaker, intervalKey, nextReview);
    try {
      const saved = await putIpaReview(speaker, intervalKey, partialState);
      setIpaReview(speaker, intervalKey, reviewWithDefaults(saved));
      setEditing(false);
    } catch {
      setIpaReview(speaker, intervalKey, previous);
      setError("Could not save IPA review. Restored previous state.");
    } finally {
      setSaving(false);
    }
  }, [currentReview, intervalKey, selected, setIpaReview, speaker]);

  const handleAccept = () => {
    if (!selected) return;
    void saveReview({
      status: "accepted",
      suggested_ipa: selected.raw_ipa,
      resolution_type: "human_review",
      evidence_sources: ["user"],
    });
  };

  const handleEditStart = () => {
    setEditedIpa(selected?.raw_ipa ?? "");
    setEditing(true);
    setError("");
  };

  const handleEditSubmit = () => {
    void saveReview({
      status: "accepted",
      suggested_ipa: editedIpa,
      resolution_type: "human_review_edited",
      evidence_sources: ["user_edit"],
    });
  };

  const handleEditCancel = () => {
    setEditing(false);
    setEditedIpa("");
    setError("");
  };

  const handleReject = () => {
    void saveReview({
      status: "rejected",
      resolution_type: "human_rejected",
      evidence_sources: ["user"],
    });
  };

  const handleDefer = () => {
    void saveReview({ status: "needs_review" });
  };

  return (
    <section
      aria-label="IPA candidates"
      style={{
        borderTop: "1px solid #d6e0ea",
        paddingTop: "0.5rem",
        display: "flex",
        flexDirection: "column",
        gap: "0.5rem",
      }}
    >
      <button
        type="button"
        aria-expanded={expanded}
        onClick={() => setExpanded((value) => !value)}
        style={{
          alignItems: "center",
          background: "transparent",
          border: 0,
          color: "#111827",
          cursor: "pointer",
          display: "flex",
          fontFamily: "inherit",
          fontWeight: 600,
          justifyContent: "space-between",
          padding: 0,
          textAlign: "left",
        }}
      >
        <span>IPA candidates</span>
        <span aria-hidden="true">{expanded ? "−" : "+"}</span>
      </button>

      {expanded && (
        <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
          {hasCandidates ? (
            candidates.map((candidate) => (
              <div
                key={candidate.candidate_id}
                style={{
                  background: "#ffffff",
                  border: "1px solid #d6e0ea",
                  borderRadius: "0.25rem",
                  display: "grid",
                  gap: "0.25rem",
                  padding: "0.5rem",
                }}
              >
                <div style={{ fontWeight: 600 }}>{candidate.model}</div>
                <div>raw: {candidate.raw_ipa}</div>
                <div>timing: {candidate.timing_basis}</div>
                <div>decoded: {candidate.decoded_at}</div>
              </div>
            ))
          ) : (
            <div style={{ color: "#6b7280" }}>{EMPTY_HINT}</div>
          )}

          <div>Status: {statusLabel(currentReview?.status)}</div>

          <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem" }}>
            <Button size="sm" variant="primary" disabled={!hasCandidates || saving} onClick={handleAccept}>
              Accept
            </Button>
            <Button size="sm" variant="secondary" disabled={!hasCandidates || saving} onClick={handleEditStart}>
              Edit & Accept
            </Button>
            <Button size="sm" variant="danger" disabled={!hasCandidates || saving} onClick={handleReject}>
              Reject
            </Button>
            <Button size="sm" variant="secondary" disabled={!hasCandidates || saving} onClick={handleDefer}>
              Needs human review
            </Button>
          </div>

          {editing && (
            <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
              <Input label="Edited IPA" value={editedIpa} onChange={(event) => setEditedIpa(event.target.value)} />
              <div style={{ display: "flex", gap: "0.5rem" }}>
                <Button size="sm" variant="primary" disabled={saving} onClick={handleEditSubmit}>
                  Save edited IPA
                </Button>
                <Button size="sm" variant="secondary" disabled={saving} onClick={handleEditCancel}>
                  Cancel
                </Button>
              </div>
            </div>
          )}

          {error && <div style={{ color: "#b91c1c", fontSize: "0.75rem" }}>{error}</div>}
        </div>
      )}
    </section>
  );
}
