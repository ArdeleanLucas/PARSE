import { create } from "zustand";
import type { Tag } from "../api/types";

const STORAGE_KEY_V2 = "parse-tags-v2";
const STORAGE_KEY_V1 = "parse-tags-v1";

const DEFAULT_TAGS: Omit<Tag, "concepts">[] = [
  { id: "review-needed", label: "Review needed", color: "#f59e0b" },
  { id: "confirmed", label: "Confirmed", color: "#10b981" },
  { id: "problematic", label: "Problematic", color: "#ef4444" },
];

interface TagStore {
  tags: Tag[];

  addTag: (label: string, color: string) => Tag;
  removeTag: (id: string) => void;
  updateTag: (id: string, patch: Partial<Tag>) => void;
  tagConcept: (tagId: string, conceptId: string) => void;
  untagConcept: (tagId: string, conceptId: string) => void;
  getTagsForConcept: (conceptId: string) => Tag[];

  syncFromServer: () => Promise<void>;
  mergeFromServer: (tags: Tag[]) => void;

  persist: () => void;
  hydrate: () => void;
}

export const useTagStore = create<TagStore>()((set, get) => ({
  tags: [],

  addTag: (label: string, color: string): Tag => {
    const newTag: Tag = {
      id: crypto.randomUUID(),
      label: label.trim(),
      color: color || "#6b7280",
      concepts: [],
    };

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
        tag.id === id ? { ...tag, ...patch } : tag
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

  getTagsForConcept: (conceptId: string): Tag[] => {
    const normalized = conceptId?.toString().trim() || "";
    if (!normalized) return [];
    return get().tags.filter((tag) => tag.concepts.includes(normalized));
  },

  mergeFromServer: (incomingTags: Tag[]) => {
    set((state) => {
      const existingById: Record<string, Tag> = {};
      for (const t of state.tags) {
        existingById[t.id] = { ...t };
      }
      for (const t of incomingTags) {
        if (existingById[t.id]) {
          const merged = new Set([...existingById[t.id].concepts, ...t.concepts]);
          existingById[t.id] = {
            ...existingById[t.id],
            label: t.label,
            color: t.color,
            concepts: Array.from(merged),
          };
        } else {
          existingById[t.id] = { ...t };
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
          migratedTags = parsed;
        } else if (parsed.tags && Array.isArray(parsed.tags)) {
          // v1 style with wrapper
          migratedTags = parsed.tags.map((t: any) => ({
            id: t.id || crypto.randomUUID(),
            label: t.name || t.label || "Untitled",
            color: t.color || "#6b7280",
            concepts: t.concepts || (parsed.assignments?.[t.id] || []),
          }));
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
    const defaults: Tag[] = DEFAULT_TAGS.map((t) => ({
      ...t,
      concepts: [],
    }));
    set({ tags: defaults });
    get().persist();
  },
}));

// Re-export for convenience
export type { TagStore };
