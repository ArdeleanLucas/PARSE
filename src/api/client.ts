// PARSE API client — ALL fetch calls go through these typed functions.
// No component may call fetch() directly. Always use this module.
// Proxy: /api/* → http://localhost:8766 (configured in vite.config.ts)

const CONFIG_SCHEMA_VERSION = 1;

export { CONFIG_SCHEMA_VERSION };
export * from "./contracts/annotation-data";
export * from "./contracts/project-config-and-pipeline-state";
export * from "./contracts/enrichments-tags-notes-imports";
export * from "./contracts/auth";
export * from "./contracts/stt-normalize-onboard";
export * from "./contracts/offset-tools";
export * from "./contracts/suggestions-lexeme-search";
export * from "./contracts/chat-and-generic-compute";
export * from "./contracts/job-observability";
export * from "./contracts/export-and-media";
export * from "./contracts/clef-contact-lexeme";
export * from "./tags";
