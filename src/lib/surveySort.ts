// Shared natural-sort helpers for survey_item values in the concept sidebar.
//
// This module is the single source of truth for how survey items compare —
// both ParseUI.tsx and the regression tests import from here. Any future
// branch that regresses the production sort will fail the tests in
// `src/__tests__/surveySort.test.ts` because those tests now exercise this
// exact code path.

/**
 * Tokenise a survey_item into alternating letter-runs and integer-runs so
 * that "KLQ_1.10.A" yields ["klq", 1, 10, "a"]. Dots and underscores act as
 * delimiters only — they are not part of any token. Consumed for ordering
 * only, not for display.
 */
export function surveyKey(raw: string): (string | number)[] {
  const tokens: (string | number)[] = [];
  for (const match of raw.matchAll(/([A-Za-z]+)|(\d+)/g)) {
    if (match[1]) tokens.push(match[1].toLowerCase());
    else if (match[2]) tokens.push(parseInt(match[2], 10));
  }
  return tokens;
}

/**
 * Element-wise comparator across surveyKey tokens. Numbers compare
 * numerically (so JBIL_10 sorts after JBIL_2 and KLQ_1.10 after KLQ_1.2),
 * letters compare lexicographically. Empty-tail key is the lesser one so
 * "JBIL_1" sorts before "JBIL_1.A".
 */
export function compareSurveyKeys(a: string, b: string): number {
  const ka = surveyKey(a);
  const kb = surveyKey(b);
  for (let i = 0; i < Math.max(ka.length, kb.length); i++) {
    const xa = ka[i];
    const xb = kb[i];
    if (xa === undefined) return -1;
    if (xb === undefined) return 1;
    if (typeof xa === "number" && typeof xb === "number") {
      if (xa !== xb) return xa - xb;
    } else {
      const sa = String(xa);
      const sb = String(xb);
      if (sa !== sb) return sa < sb ? -1 : 1;
    }
  }
  return 0;
}

/**
 * Badge prefix shown next to the concept name in the sidebar. Survey items
 * already carry their own source tag (JBIL / KLQ / …), so no extra letter
 * should be prepended. Numeric-id mode uses "#" (e.g. "#14"). Kept here so
 * the same constant applies wherever the sidebar badge is rendered.
 */
export function surveyBadgePrefix(sortMode: string): string {
  return sortMode === "survey" ? "" : "#";
}
