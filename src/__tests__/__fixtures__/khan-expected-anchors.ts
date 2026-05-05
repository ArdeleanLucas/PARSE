export type KhanAnnotationExpectation = {
  count: number;
  firstStartSec: number;
};

export const KHAN_ANNOTATION_EXPECTATIONS = {
  Khan01: { count: 286, firstStartSec: 1271.844 },
  Khan02: { count: 503, firstStartSec: 423.87 },
  Khan03: { count: 283, firstStartSec: 465.1 },
} as const satisfies Record<string, KhanAnnotationExpectation>;
