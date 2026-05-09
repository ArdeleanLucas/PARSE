export interface SidebarVariantVisibilityOptions {
  scopedToSpeaker: boolean;
  activeSpeakerForSidebar: string | null;
  elicitedConceptKeys: Set<string>;
  selectedTagIds: Set<string>;
  getTagsForConcept: (key: string, scope: any) => any[];
  activeTagScope: any;
}

/**
 * Return whether a grouped/source-item variant should be visible in the concept sidebar.
 *
 * Extracted from PR #316's inline `ParseUI.tsx` callback so sidebar visibility remains
 * reusable across future components that need to render the same survey-aware grouped
 * variants. The parent grouped concept is accepted for API symmetry with
 * `ConceptSidebar`, but visibility is intentionally decided from the raw variant
 * `conceptKey`: survey/source grouping can put multiple raw concepts under one display
 * row, so each child must be checked independently.
 *
 * Visibility rules, in order:
 * 1. Speaker scoping + elicited concepts: when sidebar speaker scope is enabled, an
 *    active sidebar speaker exists, and that speaker has elicited concept ids, hide any
 *    variant whose raw `conceptKey` is absent from `elicitedConceptKeys`.
 * 2. Tag filtering: when one or more sidebar tag filters are selected, the same raw
 *    variant key must have every selected tag in the active tag scope.
 * 3. Default visible: if neither rule rejects the variant, keep it visible.
 */
export function isConceptVariantVisibleInSidebar(
  _concept: unknown,
  variant: { conceptKey: string },
  options: SidebarVariantVisibilityOptions,
): boolean {
  const conceptKey = variant.conceptKey;
  if (
    options.scopedToSpeaker
    && options.activeSpeakerForSidebar
    && options.elicitedConceptKeys.size > 0
    && !options.elicitedConceptKeys.has(conceptKey)
  ) {
    return false;
  }
  if (options.selectedTagIds.size > 0) {
    const conceptTagIds = new Set(options.getTagsForConcept(conceptKey, options.activeTagScope).map((tag) => tag.id));
    for (const tagId of options.selectedTagIds) {
      if (!conceptTagIds.has(tagId)) return false;
    }
  }
  return true;
}
