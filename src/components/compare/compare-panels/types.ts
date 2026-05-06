import type { AnnotationRecord, Tag } from "../../../api/types";

export interface ConceptEntry {
  conceptId: string;
  ipa: string;
  ortho: string;
  sourceWav: string | null;
  startSec: number | null;
  endSec: number | null;
}

export interface CognateGroup {
  group: string;
  color: string;
}

export type BorrowingDecision = "native" | "borrowed" | "uncertain" | "skip";

export interface SpeakerDecision {
  decision: BorrowingDecision;
  sourceLang: string | null;
}

export interface ContactLanguage {
  code: string;
  name: string;
  family?: string;
}

export interface ConceptTableProps {
  onPlayEntry?: (
    speaker: string,
    conceptId: string,
    startSec: number,
    endSec: number,
    sourceWav: string,
  ) => void;
}

export interface LexemeDetailProps {
  speaker: string;
  conceptId: string;
  conceptLabel: string;
  ipa: string;
  ortho: string;
  startSec: number | null;
  endSec: number | null;
  cognateGroup?: string | null;
  cognateColor?: string | null;
}

export interface CognateControlsProps {
  onGroupsChanged?: (conceptId: string, groups: Record<string, string[]>) => void;
}

export type Mode = "view" | "split" | "cycle";
export type GroupLetter = "A" | "B" | "C" | "D" | "E";
export const GROUP_LETTERS: GroupLetter[] = ["A", "B", "C", "D", "E"];

export interface ConceptRowProps {
  concept: { id: string; label: string; key?: string };
  index: number;
  speakers: string[];
  activeConcept: string | null;
  records: Record<string, AnnotationRecord>;
  enrichmentData: Record<string, unknown>;
  expanded: Set<string>;
  toggleExpanded: (speaker: string, conceptId: string) => void;
  setActiveConcept: (conceptId: string) => void;
  getTagsForConcept: (conceptId: string) => Tag[];
  getTagsForLexeme: (speaker: string, conceptId: string) => Tag[];
  totalCols: number;
  onPlayEntry?: ConceptTableProps["onPlayEntry"];
}
