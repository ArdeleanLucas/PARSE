import { existsSync } from "node:fs";
import path from "node:path";

export function resolveFixtureAiConfigSource(repoRoot) {
  const directConfig = path.join(repoRoot, "config", "ai_config.json");
  if (existsSync(directConfig)) {
    return directConfig;
  }

  const exampleConfig = path.join(repoRoot, "config", "ai_config.example.json");
  if (existsSync(exampleConfig)) {
    return exampleConfig;
  }

  return null;
}
