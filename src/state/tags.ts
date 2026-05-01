import { create } from 'zustand';
import { tagsApi } from '@/api/tags';

export interface Tag {
  id: string;
  name: string;
  color: string;
  createdAt: string;
}

interface TagsState {
  tags: Tag[];
  attachmentsByConcept: Record<string, string[]>;
  loaded: boolean;
  load: () => Promise<void>;
  createTag: (name: string, color: string) => Promise<Tag>;
  deleteTag: (id: string) => Promise<void>;
  attachTag: (conceptId: string, tagId: string) => Promise<void>;
  detachTag: (conceptId: string, tagId: string) => Promise<void>;
}

let warnedLoadFailure = false;

function withoutEmptyAttachmentKeys(attachments: Record<string, string[]>): Record<string, string[]> {
  return Object.fromEntries(Object.entries(attachments).filter(([, ids]) => ids.length > 0));
}

export const useTagsStore = create<TagsState>()((set, get) => ({
  tags: [],
  attachmentsByConcept: {},
  loaded: false,

  load: async () => {
    if (get().loaded) return;
    try {
      const data = await tagsApi.fetchAll();
      set({ tags: data.tags, attachmentsByConcept: data.attachments, loaded: true });
    } catch (error) {
      if (!warnedLoadFailure) {
        console.warn('[tags] load failed; backend may be pending', error);
        warnedLoadFailure = true;
      }
      set({ loaded: true });
    }
  },

  createTag: async (name, color) => {
    const tag = await tagsApi.create({ name, color });
    set((state) => ({ tags: [...state.tags, tag] }));
    return tag;
  },

  deleteTag: async (id) => {
    await tagsApi.delete(id);
    set((state) => {
      const next: Record<string, string[]> = {};
      for (const [conceptId, ids] of Object.entries(state.attachmentsByConcept)) {
        const filtered = ids.filter((tagId) => tagId !== id);
        if (filtered.length > 0) next[conceptId] = filtered;
      }
      return {
        tags: state.tags.filter((tag) => tag.id !== id),
        attachmentsByConcept: next,
      };
    });
  },

  attachTag: async (conceptId, tagId) => {
    const previous = get().attachmentsByConcept[conceptId] ?? [];
    set((state) => ({
      attachmentsByConcept: {
        ...state.attachmentsByConcept,
        [conceptId]: Array.from(new Set([...(state.attachmentsByConcept[conceptId] ?? []), tagId])),
      },
    }));
    try {
      await tagsApi.attach(conceptId, tagId);
    } catch (error) {
      set((state) => ({
        attachmentsByConcept: withoutEmptyAttachmentKeys({
          ...state.attachmentsByConcept,
          [conceptId]: previous,
        }),
      }));
      throw error;
    }
  },

  detachTag: async (conceptId, tagId) => {
    const previous = get().attachmentsByConcept[conceptId] ?? [];
    set((state) => ({
      attachmentsByConcept: withoutEmptyAttachmentKeys({
        ...state.attachmentsByConcept,
        [conceptId]: (state.attachmentsByConcept[conceptId] ?? []).filter((id) => id !== tagId),
      }),
    }));
    try {
      await tagsApi.detach(conceptId, tagId);
    } catch (error) {
      set((state) => ({
        attachmentsByConcept: withoutEmptyAttachmentKeys({
          ...state.attachmentsByConcept,
          [conceptId]: previous,
        }),
      }));
      throw error;
    }
  },
}));

export const useConceptTagIds = (conceptId: string): string[] =>
  useTagsStore((state) => state.attachmentsByConcept[conceptId] ?? []);

export const useTagUsageCounts = (): Record<string, number> =>
  useTagsStore((state) => {
    const counts: Record<string, number> = {};
    for (const ids of Object.values(state.attachmentsByConcept)) {
      for (const id of ids) counts[id] = (counts[id] ?? 0) + 1;
    }
    return counts;
  });

export type { TagsState };
