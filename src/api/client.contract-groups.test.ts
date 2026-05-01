// @vitest-environment jsdom
import { describe, expect, it } from "vitest";
import * as client from "./client";

const contractGroups = [
  {
    modulePath: "./contracts/annotation-data",
    exports: ["getAnnotation", "saveAnnotation", "getSttSegments"],
  },
  {
    modulePath: "./contracts/project-config-and-pipeline-state",
    exports: ["getConfig", "updateConfig", "getPipelineState"],
  },
  {
    modulePath: "./contracts/enrichments-tags-notes-imports",
    exports: [
      "getEnrichments",
      "saveEnrichments",
      "getTags",
      "mergeTags",
      "saveLexemeNote",
      "importConceptsCsv",
      "importTagCsv",
      "importCommentsCsv",
    ],
  },
  {
    modulePath: "./contracts/auth",
    exports: ["getAuthStatus", "startAuthFlow", "pollAuth", "saveApiKey", "logoutAuth"],
  },
  {
    modulePath: "./contracts/stt-normalize-onboard",
    exports: [
      "startSTT",
      "pollSTT",
      "startNormalize",
      "pollNormalize",
      "onboardSpeaker",
      "pollOnboardSpeaker",
    ],
  },
  {
    modulePath: "./contracts/offset-tools",
    exports: [
      "detectTimestampOffset",
      "detectTimestampOffsetFromPair",
      "detectTimestampOffsetFromPairs",
      "pollOffsetDetectJob",
      "applyTimestampOffset",
    ],
  },
  {
    modulePath: "./contracts/suggestions-lexeme-search",
    exports: ["requestSuggestions", "searchLexeme"],
  },
  {
    modulePath: "./contracts/chat-and-generic-compute",
    exports: ["startChatSession", "getChatSession", "runChat", "pollChat", "startCompute", "pollCompute", "cancelComputeJob"],
  },
  {
    modulePath: "./contracts/job-observability",
    exports: ["listActiveJobs", "getJobLogs"],
  },
  {
    modulePath: "./contracts/export-and-media",
    exports: ["getLingPyExport", "getNEXUSExport", "spectrogramUrl"],
  },
  {
    modulePath: "./contracts/clef-contact-lexeme",
    exports: [
      "getContactLexemeCoverage",
      "startContactLexemeFetch",
      "getClefConfig",
      "saveClefConfig",
      "clearClefData",
      "getClefCatalog",
      "getClefProviders",
      "getClefSourcesReport",
      "saveClefFormSelections",
    ],
  },
] as const;

describe("client.ts §6 contract-group barrel", () => {
  it("re-exports one module per §6 contract group while keeping the public client surface stable", async () => {
    for (const group of contractGroups) {
      const contractModule = await import(group.modulePath);
      for (const exportName of group.exports) {
        expect(contractModule).toHaveProperty(exportName);
        expect(contractModule[exportName as keyof typeof contractModule]).toBe(
          client[exportName as keyof typeof client],
        );
      }
    }
  });
});
