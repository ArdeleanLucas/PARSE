import { useEffect, useMemo, useRef, useState } from "react";
import { useAnnotationStore } from "../../stores/annotationStore";
import { useEnrichmentStore } from "../../stores/enrichmentStore";
import { useTagStore } from "../../stores/tagStore";
import { saveLexemeNote, spectrogramUrl } from "../../api/client";
import type { LexemeNoteEntry } from "../../api/types";
import { Badge } from "../shared/Badge";

interface LexemeDetailProps {
  speaker: string;
  conceptId: string;
  conceptLabel: string;
  ipa: string;
  ortho: string;
  startSec: number | null;
  endSec: number | null;
  arabicSim?: number | null;
  persianSim?: number | null;
  cognateGroup?: string | null;
  cognateColor?: string | null;
}

function deriveAudioUrl(record: { source_audio?: string; source_wav?: string } | null | undefined): string {
  const raw = (record?.source_audio ?? record?.source_wav ?? "").trim();
  if (!raw) return "";
  const cleaned = raw.replace(/\\/g, "/").replace(/^\/+/, "");
  return "/" + cleaned;
}

export function LexemeDetail({
  speaker,
  conceptId,
  conceptLabel,
  startSec,
  endSec,
}: LexemeDetailProps) {
  const records = useAnnotationStore((s) => s.records);
  const enrichmentData = useEnrichmentStore((s) => s.data);
  const saveEnrichments = useEnrichmentStore((s) => s.save);
  const tags = useTagStore((s) => s.tags);
  const getTagsForLexeme = useTagStore((s) => s.getTagsForLexeme);
  const tagLexeme = useTagStore((s) => s.tagLexeme);
  const untagLexeme = useTagStore((s) => s.untagLexeme);
  const addTag = useTagStore((s) => s.addTag);

  const lexemeNotesBlock = useMemo(() => {
    const block = (enrichmentData as Record<string, unknown>)?.lexeme_notes;
    if (!block || typeof block !== "object") return undefined;
    const speakerBlock = (block as Record<string, unknown>)[speaker];
    if (!speakerBlock || typeof speakerBlock !== "object") return undefined;
    const entry = (speakerBlock as Record<string, unknown>)[conceptId];
    return (entry && typeof entry === "object" ? entry : undefined) as LexemeNoteEntry | undefined;
  }, [enrichmentData, speaker, conceptId]);

  const [userNote, setUserNote] = useState<string>(lexemeNotesBlock?.user_note ?? "");
  const [savingNote, setSavingNote] = useState(false);
  const [noteError, setNoteError] = useState<string | null>(null);
  const [showSpectrogram, setShowSpectrogram] = useState(false);
  const [tagSearch, setTagSearch] = useState("");

  useEffect(() => {
    setUserNote(lexemeNotesBlock?.user_note ?? "");
  }, [lexemeNotesBlock?.user_note]);

  const lexemeTags = getTagsForLexeme(speaker, conceptId);
  const lexemeTagIds = new Set(lexemeTags.map((t) => t.id));

  const audioRef = useRef<HTMLAudioElement | null>(null);
  const record = records[speaker] as { source_audio?: string; source_wav?: string } | undefined;
  const audioUrl = deriveAudioUrl(record);

  const canPlay = audioUrl && startSec != null && endSec != null;
  const canShowSpectrogram = startSec != null && endSec != null;
  const spectrogramSrc =
    canShowSpectrogram && showSpectrogram
      ? spectrogramUrl({
          speaker,
          startSec: startSec!,
          endSec: endSec!,
          audio: audioUrl ? audioUrl.replace(/^\//, "") : undefined,
        })
      : null;

  function handlePlay() {
    if (!canPlay) return;
    let audio = audioRef.current;
    if (!audio) {
      audio = new Audio(audioUrl);
      audioRef.current = audio;
    } else if (audio.src !== window.location.origin + audioUrl && !audio.src.endsWith(audioUrl)) {
      audio.pause();
      audio.src = audioUrl;
    }
    const clipStart = startSec!;
    const clipEnd = endSec!;
    audio.currentTime = clipStart;
    const onTimeUpdate = () => {
      if (audio && audio.currentTime >= clipEnd) {
        audio.pause();
        audio.removeEventListener("timeupdate", onTimeUpdate);
      }
    };
    audio.addEventListener("timeupdate", onTimeUpdate);
    void audio.play().catch((err) => console.warn("[LexemeDetail] play failed", err));
  }

  async function handleSaveNote() {
    setSavingNote(true);
    setNoteError(null);
    try {
      await saveLexemeNote({ speaker, concept_id: conceptId, user_note: userNote });
      // Merge into local enrichment store so UI reflects immediately.
      await saveEnrichments({
        lexeme_notes: {
          [speaker]: {
            [conceptId]: {
              ...(lexemeNotesBlock ?? {}),
              user_note: userNote,
              updated_at: new Date().toISOString(),
            },
          },
        },
      });
    } catch (err) {
      setNoteError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setSavingNote(false);
    }
  }

  const filteredTagSuggestions = useMemo(() => {
    const q = tagSearch.trim().toLowerCase();
    const eligible = tags.filter((t) => !lexemeTagIds.has(t.id));
    if (!q) return eligible.slice(0, 8);
    return eligible.filter((t) => t.label.toLowerCase().includes(q)).slice(0, 8);
  }, [tags, lexemeTagIds, tagSearch]);

  function handleAddTag(label: string) {
    const trimmed = label.trim();
    if (!trimmed) return;
    const existing = tags.find((t) => t.label.toLowerCase() === trimmed.toLowerCase());
    const tag = existing ?? addTag(trimmed, "#6b7280");
    tagLexeme(tag.id, speaker, conceptId);
    setTagSearch("");
  }

  const sectionStyle: React.CSSProperties = {
    padding: "0.75rem",
    borderTop: "1px solid #e5e7eb",
    display: "grid",
    gridTemplateColumns: "1fr 1fr 1fr",
    gap: "1rem",
  };

  const labelStyle: React.CSSProperties = {
    fontSize: "0.6875rem",
    color: "#6b7280",
    textTransform: "uppercase",
    letterSpacing: "0.05em",
    marginBottom: "0.25rem",
  };

  const importNoteText =
    lexemeNotesBlock?.import_note?.trim() || "";

  return (
    <div
      data-testid={`lexeme-detail-${speaker}-${conceptId}`}
      style={{
        background: "#f9fafb",
        border: "1px solid #e5e7eb",
        borderRadius: "0.5rem",
        margin: "0.5rem 0",
      }}
    >
      {canShowSpectrogram && (
        <div style={{ padding: "0.5rem 0.75rem 0", display: "flex", alignItems: "center", gap: "0.75rem" }}>
          <button
            aria-label={`Play ${speaker} ${conceptLabel}`}
            onClick={handlePlay}
            disabled={!canPlay}
            style={{
              width: 24,
              height: 24,
              borderRadius: "50%",
              border: "none",
              background: canPlay ? "#3b82f6" : "#d1d5db",
              color: "white",
              cursor: canPlay ? "pointer" : "not-allowed",
              fontSize: "0.625rem",
            }}
          >
            ▶
          </button>
          <button
            data-testid={`toggle-spectrogram-${speaker}-${conceptId}`}
            onClick={() => setShowSpectrogram((v) => !v)}
            style={{
              background: "none",
              border: "none",
              color: "#3b82f6",
              textDecoration: "underline",
              cursor: "pointer",
              fontSize: "0.8125rem",
              padding: 0,
            }}
          >
            {showSpectrogram ? "Hide Spectrogram" : "Toggle Spectrogram"}
          </button>
        </div>
      )}

      {spectrogramSrc && (
        <div style={{ padding: "0 0.75rem 0.75rem" }}>
          <img
            data-testid={`spectrogram-${speaker}-${conceptId}`}
            src={spectrogramSrc}
            alt={`Spectrogram of ${speaker} ${conceptLabel}`}
            style={{
              width: "100%",
              maxHeight: 220,
              display: "block",
              borderRadius: "0.25rem",
              imageRendering: "pixelated",
              background: "#ffffff",
            }}
          />
          <div style={{ fontSize: "0.6875rem", color: "#6b7280", marginTop: "0.25rem" }}>
            {formatSeconds(startSec)} → {formatSeconds(endSec)} · shared with Annotate view
          </div>
        </div>
      )}

      <div style={sectionStyle}>
        <div>
          <div style={labelStyle}>Import Notes (CSV)</div>
          {importNoteText ? (
            <div style={{ fontSize: "0.8125rem", color: "#374151", whiteSpace: "pre-wrap" }}>
              {importNoteText}
            </div>
          ) : (
            <div style={{ fontSize: "0.8125rem", color: "#9ca3af", fontStyle: "italic" }}>
              No notes attached.
            </div>
          )}
        </div>

        <div>
          <div style={labelStyle}>Speaker Notes</div>
          <textarea
            data-testid={`lexeme-user-note-${speaker}-${conceptId}`}
            value={userNote}
            onChange={(e) => setUserNote(e.target.value)}
            onBlur={handleSaveNote}
            placeholder="Add notes specific to this speaker/lexeme…"
            style={{
              width: "100%",
              minHeight: 60,
              fontFamily: "inherit",
              fontSize: "0.8125rem",
              padding: "0.375rem",
              border: "1px solid #d1d5db",
              borderRadius: "0.25rem",
              resize: "vertical",
            }}
          />
          <div style={{ fontSize: "0.6875rem", color: savingNote ? "#6b7280" : noteError ? "#dc2626" : "transparent" }}>
            {savingNote ? "Saving…" : noteError ?? "saved"}
          </div>
        </div>

        <div>
          <div style={labelStyle}>Tags</div>
          {lexemeTags.length === 0 ? (
            <div style={{ fontSize: "0.8125rem", color: "#9ca3af", fontStyle: "italic", marginBottom: "0.375rem" }}>
              No tags yet.
            </div>
          ) : (
            <div style={{ display: "flex", gap: "0.25rem", flexWrap: "wrap", marginBottom: "0.375rem" }}>
              {lexemeTags.map((tag) => (
                <span
                  key={tag.id}
                  style={{
                    display: "inline-flex",
                    alignItems: "center",
                    gap: "0.25rem",
                  }}
                >
                  <Badge label={tag.label} color={tag.color} />
                  <button
                    aria-label={`Remove tag ${tag.label}`}
                    onClick={() => untagLexeme(tag.id, speaker, conceptId)}
                    style={{
                      background: "transparent",
                      border: "none",
                      color: "#6b7280",
                      cursor: "pointer",
                      fontSize: "0.75rem",
                      padding: 0,
                      lineHeight: 1,
                    }}
                  >
                    ×
                  </button>
                </span>
              ))}
            </div>
          )}
          <div style={{ position: "relative" }}>
            <input
              data-testid={`lexeme-tag-input-${speaker}-${conceptId}`}
              value={tagSearch}
              onChange={(e) => setTagSearch(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  handleAddTag(tagSearch);
                }
              }}
              placeholder="Type or select…"
              style={{
                width: "100%",
                fontSize: "0.8125rem",
                padding: "0.375rem",
                border: "1px solid #d1d5db",
                borderRadius: "0.25rem",
              }}
            />
            {tagSearch && filteredTagSuggestions.length > 0 && (
              <div
                style={{
                  position: "absolute",
                  top: "100%",
                  left: 0,
                  right: 0,
                  background: "white",
                  border: "1px solid #d1d5db",
                  borderRadius: "0.25rem",
                  marginTop: "0.125rem",
                  maxHeight: 160,
                  overflowY: "auto",
                  zIndex: 20,
                }}
              >
                {filteredTagSuggestions.map((tag) => (
                  <button
                    key={tag.id}
                    onClick={() => {
                      tagLexeme(tag.id, speaker, conceptId);
                      setTagSearch("");
                    }}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: "0.375rem",
                      width: "100%",
                      textAlign: "left",
                      padding: "0.25rem 0.5rem",
                      border: "none",
                      background: "transparent",
                      cursor: "pointer",
                      fontSize: "0.8125rem",
                    }}
                  >
                    <span
                      style={{
                        width: 10,
                        height: 10,
                        borderRadius: "50%",
                        background: tag.color,
                      }}
                    />
                    {tag.label}
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function formatSeconds(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "—";
  const minutes = Math.floor(value / 60);
  const seconds = value - minutes * 60;
  return `${minutes}:${seconds.toFixed(3).padStart(6, "0")}`;
}
