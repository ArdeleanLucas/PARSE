import type { Tag } from "../../../api/types";
import { Badge } from "../../shared/Badge";

export function LexemeForm({
  speaker,
  conceptId,
  importNoteText,
  userNote,
  setUserNote,
  handleSaveNote,
  savingNote,
  noteError,
  lexemeTags,
  untagLexeme,
  tagSearch,
  setTagSearch,
  filteredTagSuggestions,
  tagLexeme,
  handleAddTag,
}: {
  speaker: string;
  conceptId: string;
  importNoteText: string;
  userNote: string;
  setUserNote: (value: string) => void;
  handleSaveNote: () => Promise<void>;
  savingNote: boolean;
  noteError: string | null;
  lexemeTags: Tag[];
  untagLexeme: (tagId: string, speaker: string, conceptId: string) => void;
  tagSearch: string;
  setTagSearch: (value: string) => void;
  filteredTagSuggestions: Tag[];
  tagLexeme: (tagId: string, speaker: string, conceptId: string) => void;
  handleAddTag: (label: string) => void;
}) {
  const sectionStyle = {
    padding: "0.75rem",
    borderTop: "1px solid #e5e7eb",
    display: "grid",
    gridTemplateColumns: "1fr 1fr 1fr",
    gap: "1rem",
  } as const;
  const labelStyle = {
    fontSize: "0.6875rem",
    color: "#6b7280",
    textTransform: "uppercase",
    letterSpacing: "0.05em",
    marginBottom: "0.25rem",
  } as const;

  return (
    <div style={sectionStyle}>
      <div>
        <div style={labelStyle}>Import Notes (CSV)</div>
        {importNoteText ? (
          <div style={{ fontSize: "0.8125rem", color: "#374151", whiteSpace: "pre-wrap" }}>{importNoteText}</div>
        ) : (
          <div style={{ fontSize: "0.8125rem", color: "#9ca3af", fontStyle: "italic" }}>No notes attached.</div>
        )}
      </div>

      <div>
        <div style={labelStyle}>Speaker Notes</div>
        <textarea
          data-testid={`lexeme-user-note-${speaker}-${conceptId}`}
          value={userNote}
          onChange={(e) => setUserNote(e.target.value)}
          onBlur={() => void handleSaveNote()}
          placeholder="Add notes specific to this speaker/lexeme…"
          style={{ width: "100%", minHeight: 60, fontFamily: "inherit", fontSize: "0.8125rem", padding: "0.375rem", border: "1px solid #d1d5db", borderRadius: "0.25rem", resize: "vertical" }}
        />
        <div style={{ fontSize: "0.6875rem", color: savingNote ? "#6b7280" : noteError ? "#dc2626" : "transparent" }}>
          {savingNote ? "Saving…" : noteError ?? "saved"}
        </div>
      </div>

      <div>
        <div style={labelStyle}>Tags</div>
        {lexemeTags.length === 0 ? (
          <div style={{ fontSize: "0.8125rem", color: "#9ca3af", fontStyle: "italic", marginBottom: "0.375rem" }}>No tags yet.</div>
        ) : (
          <div style={{ display: "flex", gap: "0.25rem", flexWrap: "wrap", marginBottom: "0.375rem" }}>
            {lexemeTags.map((tag) => (
              <span key={tag.id} style={{ display: "inline-flex", alignItems: "center", gap: "0.25rem" }}>
                <Badge label={tag.label} color={tag.color} />
                <button
                  aria-label={`Remove tag ${tag.label}`}
                  onClick={() => untagLexeme(tag.id, speaker, conceptId)}
                  style={{ background: "transparent", border: "none", color: "#6b7280", cursor: "pointer", fontSize: "0.75rem", padding: 0, lineHeight: 1 }}
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
            style={{ width: "100%", fontSize: "0.8125rem", padding: "0.375rem", border: "1px solid #d1d5db", borderRadius: "0.25rem" }}
          />
          {tagSearch && filteredTagSuggestions.length > 0 && (
            <div style={{ position: "absolute", top: "100%", left: 0, right: 0, background: "white", border: "1px solid #d1d5db", borderRadius: "0.25rem", marginTop: "0.125rem", maxHeight: 160, overflowY: "auto", zIndex: 20 }}>
              {filteredTagSuggestions.map((tag) => (
                <button
                  key={tag.id}
                  onClick={() => {
                    tagLexeme(tag.id, speaker, conceptId);
                    setTagSearch("");
                  }}
                  style={{ display: "flex", alignItems: "center", gap: "0.375rem", width: "100%", textAlign: "left", padding: "0.25rem 0.5rem", border: "none", background: "transparent", cursor: "pointer", fontSize: "0.8125rem" }}
                >
                  <span style={{ width: 10, height: 10, borderRadius: "50%", background: tag.color }} />
                  {tag.label}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
