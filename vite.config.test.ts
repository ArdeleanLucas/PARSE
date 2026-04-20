// @vitest-environment node
import { describe, expect, it } from "vitest";

import { resolveParseApiTarget } from "./vite.config";

describe("resolveParseApiTarget", () => {
  it("defaults to port 8766", () => {
    expect(resolveParseApiTarget({})).toBe("http://127.0.0.1:8766");
  });

  it("uses PARSE_API_PORT when provided", () => {
    expect(resolveParseApiTarget({ PARSE_API_PORT: "9000" })).toBe("http://127.0.0.1:9000");
  });

  it("falls back to legacy PARSE_PORT when PARSE_API_PORT is absent", () => {
    expect(resolveParseApiTarget({ PARSE_PORT: "9123" })).toBe("http://127.0.0.1:9123");
  });
});
