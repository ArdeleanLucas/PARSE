// Unified PARSE tag registry for concept-level and per-lexeme tags.
import { create } from "zustand";
import { putTags } from "../api/client";
import type { Tag } from "../api/types";

const STORAGE_KEY_V2 = "parse-tags-v2";
const STORAGE_KEY_V1 = "parse-tags-v1";

const DEFAULT_TAGS: Omit<Tag, "concepts" | "lexemeTargets">[] = [
  { id: "review-needed", label: "Review needed", color: "#f59e0b" },
  { id: "confirmed", label: "Confirmed", color: "#10b981" },
  { id: "problematic", label: "Problematic", color: "#ef4444" },
];

let writeTimer: ReturnType<typeof setTimeout> | null = null;

function scheduleServerWrite(get: () => TagStore): void {
  if (writeTimer) clearTimeout(writeTimer);
  writeTimer = setTimeout(() => {
    putTags(get().tags).catch((error) => {
      console.warn("[tagStore] server write failed; localStorage retains", error);
    });
  }, 500);
}

export function lexemeKey(speaker: string, conceptId: string): string {
  return `${speaker}::${conceptId}`;
}

interface TagStore {
  tags: Tag[];

  addTag: (label: string, color: string) => Tag;
  removeTag: (id: string) => void;
  updateTag: (id: string, patch: Partial<Tag>) => void;
  tagConcept: (tagId: string, conceptId: string) => void;
  untagConcept: (tagId: string, conceptId: string) => void;
  tagLexeme: (tagId: string, speaker: string, conceptId: string) => void;
  untagLexeme: (tagId: string, speaker: string, conceptId: string) => void;
  getTagsForConcept: (conceptId: string) => Tag[];
  getTagsForLexeme: (speaker: string, conceptId: string) => Tag[];

  syncFromServer: () => Promise<void>;
  mergeFromServer: (tags: Tag[]) => void;

  persist: () => void;
  hydrate: () => void;
}

function normalizeTag(raw: Partial<Tag>): Tag {
  return {
    id: raw.id || crypto.randomUUID(),
    label: raw.label || "Untitled",
    color: raw.color || "#6b7280",
    concepts: Array.isArray(raw.concepts) ? raw.concepts : [],
    lexemeTargets: Array.isArray(raw.lexemeTargets) ? raw.lexemeTargets : [],
  };
}

export const useTagStore = create<TagStore>()((set, get) => ({
  tags: [],

  addTag: (label: string, color: string): Tag => {
    const trimmed = label.trim();
    const normalizedLabel = trimmed.toLowerCase();
    if (get().tags.some((tag) => tag.label.trim().toLowerCase() === normalizedLabel)) {
      throw new Error("409: tag name already exists");
    }
    const newTag: Tag = normalizeTag({
      id: crypto.randomUUID(),
      label: trimmed,
      color: color || "#6b7280",
      concepts: [],
      lexemeTargets: [],
    });

    set((state) => ({
      tags: [...state.tags, newTag],
    }));

    get().persist();
    return newTag;
  },

  removeTag: (id: string) => {
    set((state) => ({
      tags: state.tags.filter((tag) => tag.id !== id),
    }));
    get().persist();
  },

  updateTag: (id: string, patch: Partial<Tag>) => {
    set((state) => ({
      tags: state.tags.map((tag) =>
        tag.id === id ? normalizeTag({ ...tag, ...patch }) : tag
      ),
    }));
    get().persist();
  },

  tagConcept: (tagId: string, conceptId: string) => {
    set((state) => ({
      tags: state.tags.map((tag) => {
        if (tag.id === tagId && !tag.concepts.includes(conceptId)) {
          return {
            ...tag,
            concepts: [...tag.concepts, conceptId],
          };
        }
        return tag;
      }),
    }));
    get().persist();
  },

  untagConcept: (tagId: string, conceptId: string) => {
    set((state) => ({
      tags: state.tags.map((tag) => {
        if (tag.id === tagId) {
          return {
            ...tag,
            concepts: tag.concepts.filter((cid) => cid !== conceptId),
          };
        }
        return tag;
      }),
    }));
    get().persist();
  },

  tagLexeme: (tagId: string, speaker: string, conceptId: string) => {
    const key = lexemeKey(speaker, conceptId);
    set((state) => ({
      tags: state.tags.map((tag) => {
        if (tag.id !== tagId) return tag;
        const current = tag.lexemeTargets ?? [];
        if (current.includes(key)) return tag;
        return { ...tag, lexemeTargets: [...current, key] };
      }),
    }));
    get().persist();
  },

  untagLexeme: (tagId: string, speaker: string, conceptId: string) => {
    const key = lexemeKey(speaker, conceptId);
    set((state) => ({
      tags: state.tags.map((tag) => {
        if (tag.id !== tagId) return tag;
        const current = tag.lexemeTargets ?? [];
        if (!current.includes(key)) return tag;
        return { ...tag, lexemeTargets: current.filter((k) => k !== key) };
      }),
    }));
    get().persist();
  },

  getTagsForConcept: (conceptId: string): Tag[] => {
    const normalized = conceptId?.toString().trim() || "";
    if (!normalized) return [];
    return get().tags.filter((tag) => tag.concepts.includes(normalized));
  },

  getTagsForLexeme: (speaker: string, conceptId: string): Tag[] => {
    const key = lexemeKey(speaker, conceptId);
    if (!speaker || !conceptId) return [];
    return get().tags.filter((tag) => (tag.lexemeTargets ?? []).includes(key));
  },

  mergeFromServer: (incomingTags: Tag[]) => {
    set((state) => {
      const existingById: Record<string, Tag> = {};
      for (const t of state.tags) {
        existingById[t.id] = normalizeTag(t);
      }
      for (const t of incomingTags) {
        const incoming = normalizeTag(t);
        if (existingById[incoming.id]) {
          const prev = existingById[incoming.id];
          const concepts = new Set([...prev.concepts, ...incoming.concepts]);
          const targets = new Set([
            ...(prev.lexemeTargets ?? []),
            ...(incoming.lexemeTargets ?? []),
          ]);
          existingById[incoming.id] = {
            ...prev,
            label: incoming.label,
            color: incoming.color,
            concepts: Array.from(concepts),
            lexemeTargets: Array.from(targets),
          };
        } else {
          existingById[incoming.id] = incoming;
        }
      }
      return { tags: Object.values(existingById) };
    });
    get().persist();
  },

  syncFromServer: async () => {
    try {
      const { getTags } = await import("../api/client");
      const resp = await getTags();
      if (resp.tags && resp.tags.length > 0) {
        get().mergeFromServer(resp.tags);
      }
    } catch {
      // non-fatal — localStorage tags remain
    }
  },

  persist: () => {
    try {
      const data = get().tags;
      localStorage.setItem(STORAGE_KEY_V2, JSON.stringify(data));
    } catch (error) {
      console.warn("[tagStore] persist failed:", error);
    }
    scheduleServerWrite(get);
  },

  hydrate: () => {
    try {
      let raw = localStorage.getItem(STORAGE_KEY_V2);
      let source = "v2";

      if (!raw) {
        raw = localStorage.getItem(STORAGE_KEY_V1);
        source = "v1";
      }

      if (raw) {
        const parsed = JSON.parse(raw);
        let migratedTags: Tag[] = [];

        if (Array.isArray(parsed)) {
          migratedTags = parsed.map((t) => normalizeTag(t));
        } else if (parsed.tags && Array.isArray(parsed.tags)) {
          migratedTags = parsed.tags.map((t: any) =>
            normalizeTag({
              id: t.id || crypto.randomUUID(),
              label: t.name || t.label || "Untitled",
              color: t.color || "#6b7280",
              concepts: t.concepts || (parsed.assignments?.[t.id] || []),
              lexemeTargets: t.lexemeTargets || [],
            })
          );
        } else {
          migratedTags = [];
        }

        set({ tags: migratedTags });
        if (source === "v1") {
          get().persist(); // migrate to v2
        }
        return;
      }
    } catch (error) {
      console.warn("[tagStore] hydrate failed, using defaults:", error);
    }

    // defaults
    const defaults: Tag[] = DEFAULT_TAGS.map((t) =>
      normalizeTag({ ...t, concepts: [], lexemeTargets: [] })
    );
    set({ tags: defaults });
    get().persist();
  },
}));

export type { TagStore };
