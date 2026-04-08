import { spawn } from "node:child_process";
import { mkdtemp, mkdir, writeFile, cp, rm } from "node:fs/promises";
import net from "node:net";
import { tmpdir } from "node:os";
import path from "node:path";
import process from "node:process";
import { setTimeout as delay } from "node:timers/promises";

const repoRoot = process.cwd();
const pythonBin = process.env.PARSE_PYTHON_BIN || "python";

function annotationFixture() {
  return {
    version: 1,
    project_id: "parse-api-regression-fixture",
    speaker: "Fail01",
    source_audio: "audio/test.wav",
    source_audio_duration_sec: 1.0,
    tiers: {
      ipa: {
        display_order: 1,
        intervals: [{ start: 0.0, end: 1.0, text: "a" }],
      },
      ortho: {
        display_order: 2,
        intervals: [{ start: 0.0, end: 1.0, text: "a" }],
      },
      concept: {
        display_order: 3,
        intervals: [{ start: 0.0, end: 1.0, text: "1: ash" }],
      },
      speaker: {
        display_order: 4,
        intervals: [{ start: 0.0, end: 1.0, text: "Fail01" }],
      },
    },
    metadata: {
      language_code: "sdh",
      created: "2026-01-01T00:00:00Z",
      modified: "2026-01-01T00:00:00Z",
    },
  };
}

function projectFixture() {
  return {
    project_name: "PARSE API Regression Fixture",
    language: { code: "sdh" },
    speakers: [{ id: "Fail01", name: "Fail01" }],
  };
}

function sourceIndexFixture() {
  return {
    speakers: {
      Fail01: {
        source_wavs: [
          {
            filename: "audio/test.wav",
            is_primary: true,
            duration_sec: 1.0,
          },
        ],
      },
    },
  };
}

function enrichmentsFixture() {
  return {
    computed_at: "2026-01-01T00:00:00Z",
    config: {
      contact_languages: [],
      speakers_included: ["Fail01"],
      concepts_included: [1],
      lexstat_threshold: 0.6,
    },
    cognate_sets: {
      "1": {
        cognate_sets: [
          {
            id: "1",
            members: ["Fail01"],
          },
        ],
      },
    },
    similarity: {},
    borrowing_flags: {
      "1": {
        Fail01: 0,
      },
    },
    manual_overrides: {},
  };
}

async function writeJsonFile(targetPath, payload) {
  await writeFile(targetPath, `${JSON.stringify(payload, null, 2)}\n`, "utf-8");
}

async function createFixtureProject(projectRoot) {
  await mkdir(path.join(projectRoot, "config"), { recursive: true });
  await mkdir(path.join(projectRoot, "annotations"), { recursive: true });

  await cp(
    path.join(repoRoot, "config", "ai_config.json"),
    path.join(projectRoot, "config", "ai_config.json")
  );

  try {
    await cp(
      path.join(repoRoot, "config", "sil_contact_languages.json"),
      path.join(projectRoot, "config", "sil_contact_languages.json")
    );
  } catch {
    // Optional fixture file. Compute tests still pass without it.
  }

  await writeJsonFile(path.join(projectRoot, "project.json"), projectFixture());
  await writeJsonFile(path.join(projectRoot, "source_index.json"), sourceIndexFixture());
  await writeJsonFile(path.join(projectRoot, "parse-enrichments.json"), enrichmentsFixture());
  await writeJsonFile(path.join(projectRoot, "annotations", "Fail01.json"), annotationFixture());
}

async function allocatePort() {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.unref();
    server.on("error", reject);
    server.listen(0, "127.0.0.1", () => {
      const address = server.address();
      const port = typeof address === "object" && address ? address.port : null;
      server.close((closeError) => {
        if (closeError) {
          reject(closeError);
          return;
        }
        if (!port) {
          reject(new Error("Failed to allocate an ephemeral port"));
          return;
        }
        resolve(port);
      });
    });
  });
}

function waitForExit(childProcess) {
  return new Promise((resolve) => {
    childProcess.once("exit", () => resolve());
  });
}

async function stopProcess(childProcess) {
  if (!childProcess || childProcess.exitCode !== null) {
    return;
  }

  childProcess.kill("SIGTERM");
  await Promise.race([waitForExit(childProcess), delay(2000)]);

  if (childProcess.exitCode === null) {
    childProcess.kill("SIGKILL");
    await Promise.race([waitForExit(childProcess), delay(2000)]);
  }
}

function spawnServer(projectRoot, port) {
  const pythonBootstrap = [
    "import os",
    "import sys",
    "repo_root = os.environ['PARSE_REPO_ROOT']",
    "project_root = os.environ['PARSE_TEST_PROJECT_ROOT']",
    "port = int(os.environ['PARSE_TEST_SERVER_PORT'])",
    "os.chdir(project_root)",
    "sys.path.insert(0, os.path.join(repo_root, 'python'))",
    "import server as s",
    "s.HOST = '127.0.0.1'",
    "s.PORT = port",
    "s.main()",
  ].join("\n");

  const childProcess = spawn(pythonBin, ["-c", pythonBootstrap], {
    cwd: repoRoot,
    env: {
      ...process.env,
      PARSE_REPO_ROOT: repoRoot,
      PARSE_TEST_PROJECT_ROOT: projectRoot,
      PARSE_TEST_SERVER_PORT: String(port),
    },
    stdio: ["ignore", "pipe", "pipe"],
  });

  childProcess.stdout.on("data", (chunk) => {
    process.stdout.write(`[api-server] ${chunk.toString()}`);
  });

  childProcess.stderr.on("data", (chunk) => {
    process.stderr.write(`[api-server] ${chunk.toString()}`);
  });

  return childProcess;
}

async function waitForServer(baseUrl, timeoutMs = 20000) {
  const deadline = Date.now() + timeoutMs;
  let lastError = null;

  while (Date.now() < deadline) {
    try {
      const response = await fetch(`${baseUrl}/api/config`, {
        signal: AbortSignal.timeout(1000),
      });

      if (response.ok) {
        return;
      }

      lastError = new Error(`GET /api/config returned ${response.status}`);
    } catch (error) {
      lastError = error;
    }

    await delay(250);
  }

  throw new Error(
    `Timed out waiting for API server at ${baseUrl}. Last error: ${String(lastError)}`
  );
}

async function runVitest(baseUrl) {
  const npxCommand = process.platform === "win32" ? "npx.cmd" : "npx";

  const vitestProcess = spawn(
    npxCommand,
    ["vitest", "run", "--config", "vitest.integration.ts"],
    {
      cwd: repoRoot,
      env: {
        ...process.env,
        PARSE_API_BASE_URL: baseUrl,
      },
      stdio: "inherit",
    }
  );

  return new Promise((resolve, reject) => {
    vitestProcess.on("error", reject);
    vitestProcess.on("exit", (code, signal) => {
      if (signal) {
        resolve(1);
        return;
      }
      resolve(code ?? 1);
    });
  });
}

async function main() {
  const projectRoot = await mkdtemp(path.join(tmpdir(), "parse-api-regression-"));
  let serverProcess = null;

  try {
    await createFixtureProject(projectRoot);
    const port = await allocatePort();
    const baseUrl = `http://127.0.0.1:${port}`;

    serverProcess = spawnServer(projectRoot, port);
    await waitForServer(baseUrl);

    const exitCode = await runVitest(baseUrl);
    process.exitCode = exitCode;
  } finally {
    await stopProcess(serverProcess);
    await rm(projectRoot, { recursive: true, force: true });
  }
}

main().catch((error) => {
  console.error(`[api-test-runner] ${String(error)}`);
  process.exitCode = 1;
});
