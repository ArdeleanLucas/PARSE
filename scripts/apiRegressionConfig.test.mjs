// @vitest-environment node

import { afterEach, describe, expect, it } from "vitest";
import { mkdtemp, mkdir, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";

import { resolveFixtureAiConfigSource } from "./apiRegressionConfig.mjs";

const tempRoots = [];

async function createRepoRoot() {
  const repoRoot = await mkdtemp(path.join(tmpdir(), "parse-api-config-"));
  tempRoots.push(repoRoot);
  await mkdir(path.join(repoRoot, "config"), { recursive: true });
  return repoRoot;
}

afterEach(async () => {
  await Promise.all(
    tempRoots.splice(0).map((root) => rm(root, { force: true, recursive: true }))
  );
});

describe("resolveFixtureAiConfigSource", () => {
  it("prefers config/ai_config.json when present", async () => {
    const repoRoot = await createRepoRoot();
    const directConfig = path.join(repoRoot, "config", "ai_config.json");
    const exampleConfig = path.join(repoRoot, "config", "ai_config.example.json");

    await writeFile(directConfig, '{"chat":{"provider":"openai"}}\n', "utf-8");
    await writeFile(exampleConfig, '{"chat":{"provider":"xai"}}\n', "utf-8");

    expect(resolveFixtureAiConfigSource(repoRoot)).toBe(directConfig);
  });

  it("falls back to config/ai_config.example.json when ai_config.json is missing", async () => {
    const repoRoot = await createRepoRoot();
    const exampleConfig = path.join(repoRoot, "config", "ai_config.example.json");

    await writeFile(exampleConfig, '{"chat":{"provider":"openai"}}\n', "utf-8");

    expect(resolveFixtureAiConfigSource(repoRoot)).toBe(exampleConfig);
  });

  it("returns null when neither config file exists", async () => {
    const repoRoot = await createRepoRoot();

    expect(resolveFixtureAiConfigSource(repoRoot)).toBeNull();
  });
});
