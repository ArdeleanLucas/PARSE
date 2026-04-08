// tagStore.ts — Oda (Track B) implements the body.
// ParseBuilder defines the interface only.
import { create } from "zustand";
import type { Tag } from "../api/types";

interface TagStore {
  tags: Tag[];
  addTag: (label: string, color: string) => Tag;
  removeTag: (id: string) => void;
  updateTag: (id: string, patch: Partial<Tag>) => void;
  tagConcept: (tagId: string, conceptId: string) => void;
  untagConcept: (tagId: string, conceptId: string) => void;
  getTagsForConcept: (conceptId: string) => Tag[];
  persist: () => void;
  hydrate: () => void;
}

export const useTagStore = create<TagStore>()(() => ({
  tags: [],

  // TODO Track B (Oda): implement all methods
  addTag: (_label: string, _color: string): Tag => {
    throw new Error("Not implemented — Track B");
  },
  removeTag: (_id: string) => {
    throw new Error("Not implemented — Track B");
  },
  updateTag: (_id: string, _patch: Partial<Tag>) => {
    throw new Error("Not implemented — Track B");
  },
  tagConcept: (_tagId: string, _conceptId: string) => {
    throw new Error("Not implemented — Track B");
  },
  untagConcept: (_tagId: string, _conceptId: string) => {
    throw new Error("Not implemented — Track B");
  },
  getTagsForConcept: (_conceptId: string): Tag[] => {
    throw new Error("Not implemented — Track B");
  },
  persist: () => {
    throw new Error("Not implemented — Track B");
  },
  hydrate: () => {
    throw new Error("Not implemented — Track B");
  },
}));
