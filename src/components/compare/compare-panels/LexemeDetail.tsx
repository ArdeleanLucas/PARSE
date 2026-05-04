import { useEffect, useMemo, useRef, useState } from "react";
import { saveLexemeNote, spectrogramUrl } from "../../../api/client";
import type { LexemeNoteEntry } from "../../../api/types";
import { useAnnotationStore } from "../../../stores/annotationStore";
import { useTagStore } from "../../../stores/tagStore";
import { deriveAudioUrl, formatSeconds } from "./shared";
import { useEnrichmentsBinding } from "./useEnrichmentsBinding";
import { LexemeForm } from "./LexemeForm";
import type { LexemeDetailProps } from "./types";

export function LexemeDetail({ speaker, conceptId, conceptLabel, startSec, endSec }: LexemeDetailProps) {
  const records = useAnnotationStore((s) => s.records);
  const { enrichmentData, saveEnrichments } = useEnrichmentsBinding();
  const tags = useTagStore((s) => s.tags);
  const setConceptTag = useAnnotationStore((s) => s.setConceptTag);
  const clearConceptTag = useAnnotationStore((s) => s.clearConceptTag);
  const setConfirmedAnchor = useAnnotationStore((s) => s.setConfirmedAnchor);
  const addTag = useTagStore((s) => s.addTag);

  const lexemeNotesBlock = useMemo(() => {
    const block = enrichmentData?.lexeme_notes;
    if (!block || typeof block !== "object") return undefined;
    const speakerBlock = (block as Record<string, unknown>)[speaker];
    if (!speakerBlock || typeof speakerBlock !== "object") return undefined;
    const entry = (speakerBlock as Record<string, unknown>)[conceptId];
    return (entry && typeof entry === "object" ? entry : undefined) as LexemeNoteEntry | undefined;
  }, [conceptId, enrichmentData, speaker]);

  const [userNote, setUserNote] = useState(lexemeNotesBlock?.user_note ?? "");
  const [savingNote, setSavingNote] = useState(false);
  const [noteError, setNoteError] = useState<string | null>(null);
  const [showSpectrogram, setShowSpectrogram] = useState(false);
  const [tagSearch, setTagSearch] = useState("");

  useEffect(() => {
    setUserNote(lexemeNotesBlock?.user_note ?? "");
  }, [lexemeNotesBlock?.user_note]);

  const record = records[speaker] as { source_audio?: string; source_wav?: string; concept_tags?: Record<string, string[]> } | undefined;
  const lexemeTagIds = new Set(record?.concept_tags?.[conceptId] ?? []);
  const lexemeTags = tags.filter((tag) => lexemeTagIds.has(tag.id));
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const audioUrl = deriveAudioUrl(record);
  const canPlay = Boolean(audioUrl && startSec != null && endSec != null);
  const canShowSpectrogram = startSec != null && endSec != null;
  const spectrogramSrc = canShowSpectrogram && showSpectrogram
    ? spectrogramUrl({ speaker, startSec: startSec!, endSec: endSec!, audio: audioUrl ? audioUrl.replace(/^\//, "") : undefined })
    : null;

  const handlePlay = () => {
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
  };

  const handleSaveNote = async () => {
    setSavingNote(true);
    setNoteError(null);
    try {
      await saveLexemeNote({ speaker, concept_id: conceptId, user_note: userNote });
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
  };

  const filteredTagSuggestions = useMemo(() => {
    const q = tagSearch.trim().toLowerCase();
    const eligible = tags.filter((tag) => !lexemeTagIds.has(tag.id));
    if (!q) return eligible.slice(0, 8);
    return eligible.filter((tag) => tag.label.toLowerCase().includes(q)).slice(0, 8);
  }, [lexemeTagIds, tagSearch, tags]);

  const handleAddTag = (label: string) => {
    const trimmed = label.trim();
    if (!trimmed) return;
    const existing = tags.find((tag) => tag.label.toLowerCase() === trimmed.toLowerCase());
    const tag = existing ?? addTag(trimmed, "#6b7280");
    setConceptTag(speaker, conceptId, tag.id);
    setTagSearch("");
  };

  const importNoteText = lexemeNotesBlock?.import_note?.trim() || "";

  return (
    <div data-testid={`lexeme-detail-${speaker}-${conceptId}`} style={{ background: "#f9fafb", border: "1px solid #e5e7eb", borderRadius: "0.5rem", margin: "0.5rem 0" }}>
      {canShowSpectrogram && (
        <div style={{ padding: "0.5rem 0.75rem 0", display: "flex", alignItems: "center", gap: "0.75rem" }}>
          <button aria-label={`Play ${speaker} ${conceptLabel}`} onClick={handlePlay} disabled={!canPlay} style={{ width: 24, height: 24, borderRadius: "50%", border: "none", background: canPlay ? "#3b82f6" : "#d1d5db", color: "white", cursor: canPlay ? "pointer" : "not-allowed", fontSize: "0.625rem" }}>▶</button>
          <button data-testid={`toggle-spectrogram-${speaker}-${conceptId}`} onClick={() => setShowSpectrogram((value) => !value)} style={{ background: "none", border: "none", color: "#3b82f6", textDecoration: "underline", cursor: "pointer", fontSize: "0.8125rem", padding: 0 }}>
            {showSpectrogram ? "Hide Spectrogram" : "Toggle Spectrogram"}
          </button>
        </div>
      )}
      {spectrogramSrc && (
        <div style={{ padding: "0 0.75rem 0.75rem" }}>
          <img data-testid={`spectrogram-${speaker}-${conceptId}`} src={spectrogramSrc} alt={`Spectrogram of ${speaker} ${conceptLabel}`} style={{ width: "100%", maxHeight: 220, display: "block", borderRadius: "0.25rem", imageRendering: "pixelated", background: "#ffffff" }} />
          <div style={{ fontSize: "0.6875rem", color: "#6b7280", marginTop: "0.25rem" }}>{formatSeconds(startSec)} → {formatSeconds(endSec)} · shared with Annotate view</div>
        </div>
      )}
      <LexemeForm
        speaker={speaker}
        conceptId={conceptId}
        importNoteText={importNoteText}
        userNote={userNote}
        setUserNote={setUserNote}
        handleSaveNote={handleSaveNote}
        savingNote={savingNote}
        noteError={noteError}
        lexemeTags={lexemeTags}
        untagLexeme={(tagId, tagSpeaker, tagConceptId) => {
          clearConceptTag(tagSpeaker, tagConceptId, tagId);
          if (tagId === "confirmed") setConfirmedAnchor(tagSpeaker, tagConceptId, null);
        }}
        tagSearch={tagSearch}
        setTagSearch={setTagSearch}
        filteredTagSuggestions={filteredTagSuggestions}
        tagLexeme={(tagId, tagSpeaker, tagConceptId) => setConceptTag(tagSpeaker, tagConceptId, tagId)}
        handleAddTag={handleAddTag}
      />
    </div>
  );
}
