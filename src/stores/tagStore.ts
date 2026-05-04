// Unified PARSE tag vocabulary registry. Tag membership is stored per speaker
// on AnnotationRecord.concept_tags so one speaker's confirmation cannot leak to
// another speaker with the same concept id.
import { create } from "zustand";
import { putTags } from "../api/client";
import type { Tag } from "../api/types";

const STORAGE_KEY_V2 = "parse-tags-v2";
const STORAGE_KEY_V1 = "parse-tags-v1";

const DEFAULT_TAGS: Tag[] = [
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

interface TagStore {
  tags: Tag[];

  addTag: (label: string, color: string) => Tag;
  removeTag: (id: string) => void;
  updateTag: (id: string, patch: Partial<Tag>) => void;

  syncFromServer: () => Promise<void>;
  mergeFromServer: (tags: Tag[]) => void;

  persist: () => void;
  hydrate: () => void;
}

function normalizeTag(raw: Partial<Tag> & { name?: string }): Tag {
  return {
    id: raw.id || crypto.randomUUID(),
    label: raw.label || raw.name || "Untitled",
    color: raw.color || "#6b7280",
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

  mergeFromServer: (incomingTags: Tag[]) => {
    set((state) => {
      const existingById: Record<string, Tag> = {};
      for (const t of state.tags) {
        existingById[t.id] = normalizeTag(t);
      }
      for (const t of incomingTags) {
        const incoming = normalizeTag(t);
        existingById[incoming.id] = incoming;
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
      const data = get().tags.map(normalizeTag);
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
            })
          );
        } else {
          migratedTags = [];
        }

        set({ tags: migratedTags });
        if (source === "v1") {
          get().persist(); // migrate to v2 vocabulary-only shape
        }
        return;
      }
    } catch (error) {
      console.warn("[tagStore] hydrate failed, using defaults:", error);
    }

    set({ tags: DEFAULT_TAGS });
    get().persist();
  },
}));
