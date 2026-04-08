import { useState } from "react";
import { Modal } from "../shared/Modal";
import { Button } from "../shared/Button";
import { useTagStore } from "../../stores/tagStore";
import { useConfigStore } from "../../stores/configStore";
import type { Tag } from "../../api/types";
import type { ProjectConfig } from "../../api/types";

interface TagManagerProps {
  isOpen: boolean;
  onClose: () => void;
}

interface ConceptEntry {
  id: string;
  label: string;
}

function getConceptList(config: ProjectConfig | null): ConceptEntry[] {
  if (!config) return [];
  const raw = (config as Record<string, unknown>)["concepts"];
  if (Array.isArray(raw)) {
    return raw.map((c, i) => {
      if (typeof c === "string") return { id: String(i), label: c };
      if (c && typeof c === "object") {
        const obj = c as Record<string, unknown>;
        return {
          id: String(obj["id"] ?? i),
          label: String(obj["label"] ?? obj["name"] ?? i),
        };
      }
      return { id: String(i), label: String(c) };
    });
  }
  return [];
}

export function TagManager({ isOpen, onClose }: TagManagerProps) {
  const tags = useTagStore((s) => s.tags);
  const addTag = useTagStore((s) => s.addTag);
  const removeTag = useTagStore((s) => s.removeTag);
  const updateTag = useTagStore((s) => s.updateTag);
  const tagConcept = useTagStore((s) => s.tagConcept);
  const untagConcept = useTagStore((s) => s.untagConcept);
  const getTagsForConcept = useTagStore((s) => s.getTagsForConcept);
  const config = useConfigStore((s: { config: ProjectConfig | null }) => s.config);

  const [selectedTagId, setSelectedTagId] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editLabel, setEditLabel] = useState("");
  const [editColor, setEditColor] = useState("#6b7280");
  const [newLabel, setNewLabel] = useState("");
  const [newColor, setNewColor] = useState("#6b7280");
  const [searchQuery, setSearchQuery] = useState("");

  const concepts = getConceptList(config);
  const selectedTag = tags.find((t) => t.id === selectedTagId) ?? null;

  const filteredConcepts = concepts.filter((c) =>
    c.label.toLowerCase().includes(searchQuery.toLowerCase())
  );

  function handleAdd() {
    if (!newLabel.trim()) return;
    addTag(newLabel.trim(), newColor);
    setNewLabel("");
    setNewColor("#6b7280");
  }

  function startEdit(tag: Tag) {
    setEditingId(tag.id);
    setEditLabel(tag.label);
    setEditColor(tag.color);
  }

  function saveEdit() {
    if (editingId && editLabel.trim()) {
      updateTag(editingId, { label: editLabel.trim(), color: editColor });
    }
    setEditingId(null);
  }

  function cancelEdit() {
    setEditingId(null);
  }

  function isConceptTagged(conceptId: string): boolean {
    if (!selectedTagId) return false;
    const conceptTags = getTagsForConcept(conceptId);
    return conceptTags.some((t) => t.id === selectedTagId);
  }

  function toggleConcept(conceptId: string) {
    if (!selectedTagId) return;
    if (isConceptTagged(conceptId)) {
      untagConcept(selectedTagId, conceptId);
    } else {
      tagConcept(selectedTagId, conceptId);
    }
  }

  function tagAllVisible() {
    if (!selectedTagId) return;
    for (const c of filteredConcepts) {
      if (!isConceptTagged(c.id)) {
        tagConcept(selectedTagId, c.id);
      }
    }
  }

  function untagAllVisible() {
    if (!selectedTagId) return;
    for (const c of filteredConcepts) {
      if (isConceptTagged(c.id)) {
        untagConcept(selectedTagId, c.id);
      }
    }
  }

  return (
    <Modal open={isOpen} onClose={onClose} title="Tag Manager">
      <div style={{ display: "flex", gap: "1rem", minHeight: "24rem" }}>
        {/* Left panel: tag list */}
        <div style={{ width: "35%", borderRight: "1px solid #e5e7eb", paddingRight: "1rem" }}>
          {tags.map((tag) => (
            <div
              key={tag.id}
              data-testid={`tag-row-${tag.id}`}
              onClick={() => setSelectedTagId(tag.id)}
              style={{
                display: "flex",
                alignItems: "center",
                gap: "0.5rem",
                padding: "0.375rem 0.25rem",
                cursor: "pointer",
                background: selectedTagId === tag.id ? "#f3f4f6" : "transparent",
                borderRadius: "0.25rem",
              }}
            >
              {editingId === tag.id ? (
                <div style={{ display: "flex", alignItems: "center", gap: "0.25rem", flex: 1 }}>
                  <input
                    type="color"
                    value={editColor}
                    onChange={(e) => setEditColor(e.target.value)}
                    style={{ width: "1.5rem", height: "1.5rem", border: "none", padding: 0 }}
                  />
                  <input
                    value={editLabel}
                    onChange={(e) => setEditLabel(e.target.value)}
                    style={{
                      flex: 1,
                      border: "1px solid #d1d5db",
                      borderRadius: "0.25rem",
                      padding: "0.125rem 0.375rem",
                      fontSize: "0.8rem",
                      fontFamily: "monospace",
                    }}
                  />
                  <Button size="sm" onClick={saveEdit}>Save</Button>
                  <Button size="sm" onClick={cancelEdit}>Cancel</Button>
                </div>
              ) : (
                <>
                  <span
                    style={{
                      width: "0.75rem",
                      height: "0.75rem",
                      borderRadius: "50%",
                      background: tag.color,
                      flexShrink: 0,
                    }}
                  />
                  <span style={{ flex: 1, fontSize: "0.85rem", fontFamily: "monospace" }}>
                    {tag.label}
                  </span>
                  <span
                    style={{
                      fontSize: "0.7rem",
                      background: "#e5e7eb",
                      borderRadius: "9999px",
                      padding: "0 0.375rem",
                      fontFamily: "monospace",
                    }}
                  >
                    {tag.concepts.length}
                  </span>
                  <Button size="sm" onClick={(e) => { e.stopPropagation(); startEdit(tag); }}>
                    Edit
                  </Button>
                  <Button
                    size="sm"
                    variant="danger"
                    onClick={(e) => { e.stopPropagation(); removeTag(tag.id); }}
                  >
                    Delete
                  </Button>
                </>
              )}
            </div>
          ))}

          {/* Add tag form */}
          <div
            data-testid="add-tag-form"
            style={{
              marginTop: "0.75rem",
              display: "flex",
              alignItems: "center",
              gap: "0.25rem",
            }}
          >
            <input
              type="color"
              value={newColor}
              onChange={(e) => setNewColor(e.target.value)}
              data-testid="new-tag-color"
              style={{ width: "1.5rem", height: "1.5rem", border: "none", padding: 0 }}
            />
            <input
              placeholder="Tag label"
              value={newLabel}
              onChange={(e) => setNewLabel(e.target.value)}
              data-testid="new-tag-label"
              style={{
                flex: 1,
                border: "1px solid #d1d5db",
                borderRadius: "0.25rem",
                padding: "0.25rem 0.5rem",
                fontSize: "0.8rem",
                fontFamily: "monospace",
              }}
            />
            <Button size="sm" variant="primary" onClick={handleAdd}>
              Add
            </Button>
          </div>
        </div>

        {/* Right panel: concept chips */}
        <div style={{ width: "65%", paddingLeft: "0.5rem" }}>
          {selectedTag ? (
            <>
              <div style={{ marginBottom: "0.5rem", fontFamily: "monospace", fontSize: "0.85rem" }}>
                Concepts for: <strong>{selectedTag.label}</strong>
              </div>
              <input
                placeholder="Search concepts..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                data-testid="concept-search"
                style={{
                  width: "100%",
                  border: "1px solid #d1d5db",
                  borderRadius: "0.25rem",
                  padding: "0.25rem 0.5rem",
                  fontSize: "0.8rem",
                  fontFamily: "monospace",
                  marginBottom: "0.5rem",
                  boxSizing: "border-box",
                }}
              />
              <div style={{ display: "flex", gap: "0.375rem", marginBottom: "0.5rem" }}>
                <Button size="sm" onClick={tagAllVisible}>Tag all visible</Button>
                <Button size="sm" onClick={untagAllVisible}>Untag all visible</Button>
              </div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: "0.375rem" }}>
                {filteredConcepts.map((c) => {
                  const tagged = isConceptTagged(c.id);
                  return (
                    <span
                      key={c.id}
                      data-testid={`concept-chip-${c.id}`}
                      onClick={() => toggleConcept(c.id)}
                      style={{
                        display: "inline-flex",
                        alignItems: "center",
                        gap: "0.25rem",
                        padding: "0.125rem 0.5rem",
                        borderRadius: "9999px",
                        fontSize: "0.75rem",
                        fontFamily: "monospace",
                        cursor: "pointer",
                        background: tagged ? selectedTag.color + "33" : "#f3f4f6",
                        border: tagged
                          ? `1px solid ${selectedTag.color}`
                          : "1px solid #d1d5db",
                      }}
                    >
                      {tagged && <span>&#10003;</span>}
                      {c.label}
                    </span>
                  );
                })}
              </div>
            </>
          ) : (
            <div style={{ color: "#9ca3af", fontFamily: "monospace", fontSize: "0.85rem" }}>
              Select a tag to manage concepts
            </div>
          )}
        </div>
      </div>
    </Modal>
  );
}
