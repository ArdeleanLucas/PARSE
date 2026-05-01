// Global concept-tag registry + per-concept attachments. Hydrated from /api/tags. NOT per-speaker annotation tags — see src/stores/tagStore.ts.
import { create } from 'zustand';
import { useShallow } from 'zustand/react/shallow';
import { tagsApi } from '@/api/tags';

export interface ConceptTag {
  id: string;
  name: string;
  color: string;
  createdAt: string;
}

interface ConceptTagsState {
  tags: ConceptTag[];
  attachmentsByConcept: Record<string, string[]>;
  loaded: boolean;
  warnedLoadFailure: boolean;
  load: () => Promise<void>;
  createTag: (name: string, color: string) => Promise<ConceptTag>;
  deleteTag: (id: string) => Promise<void>;
  attachTag: (conceptId: string, tagId: string) => Promise<void>;
  detachTag: (conceptId: string, tagId: string) => Promise<void>;
}

const EMPTY_ATTACHMENT_LIST: readonly string[] = Object.freeze([]);

function withoutEmptyAttachmentKeys(attachments: Record<string, string[]>): Record<string, string[]> {
  return Object.fromEntries(Object.entries(attachments).filter(([, ids]) => ids.length > 0));
}

export const useConceptTagsStore = create<ConceptTagsState>()((set, get) => ({
  tags: [],
  attachmentsByConcept: {},
  loaded: false,
  warnedLoadFailure: false,

  load: async () => {
    if (get().loaded) return;
    try {
      const data = await tagsApi.fetchAll();
      set({ tags: data.tags, attachmentsByConcept: data.attachments, loaded: true });
    } catch (error) {
      if (!get().warnedLoadFailure) {
        console.warn('[conceptTags] load failed; backend may be pending', error);
      }
      set({ loaded: true, warnedLoadFailure: true });
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
    set((state) => ({
      attachmentsByConcept: {
        ...state.attachmentsByConcept,
        [conceptId]: Array.from(new Set([...(state.attachmentsByConcept[conceptId] ?? []), tagId])),
      },
    }));
    try {
      await tagsApi.attach(conceptId, tagId);
    } catch (error) {
      set((state) => {
        const next = (state.attachmentsByConcept[conceptId] ?? []).filter((id) => id !== tagId);
        return {
          attachmentsByConcept: withoutEmptyAttachmentKeys({
            ...state.attachmentsByConcept,
            [conceptId]: next,
          }),
        };
      });
      throw error;
    }
  },

  detachTag: async (conceptId, tagId) => {
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
        attachmentsByConcept: {
          ...state.attachmentsByConcept,
          [conceptId]: Array.from(new Set([...(state.attachmentsByConcept[conceptId] ?? []), tagId])),
        },
      }));
      throw error;
    }
  },
}));

export const useConceptTagsForConcept = (conceptId: string): readonly string[] =>
  useConceptTagsStore((state) => state.attachmentsByConcept[conceptId] ?? EMPTY_ATTACHMENT_LIST);

export const useConceptTagUsageCounts = (): Record<string, number> =>
  useConceptTagsStore(
    useShallow((state) => {
      const counts: Record<string, number> = {};
      for (const ids of Object.values(state.attachmentsByConcept)) {
        for (const id of ids) counts[id] = (counts[id] ?? 0) + 1;
      }
      return counts;
    }),
  );

export type { ConceptTagsState };
