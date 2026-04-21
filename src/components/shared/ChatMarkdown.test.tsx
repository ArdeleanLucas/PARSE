// @vitest-environment jsdom
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ChatMarkdown, normalizeChatMarkdown } from "./ChatMarkdown";

describe("ChatMarkdown", () => {
  it("normalizes compact LLM markdown into heading and list boundaries", () => {
    const normalized = normalizeChatMarkdown(
      "**Cannot import speakers — read-only MVP constraints.** ### What I checked - `project_context_read`: 0 speakers. ### Recommended next steps 1. Add speaker audio files. 2. Create initial annotation files.",
    );

    expect(normalized).toContain("\n\n### What I checked");
    expect(normalized).toContain("\n- `project_context_read`");
    expect(normalized).toContain("\n\n1. Add speaker audio files.");
  });

  it("renders markdown semantics instead of raw punctuation", () => {
    render(
      <ChatMarkdown
        content={
          "**Cannot import speakers — read-only MVP constraints.**\n\n### What I checked\n- `project_context_read`: 0 speakers\n- `read_text_preview`: file not found"
        }
      />,
    );

    expect(screen.getByText(/Cannot import speakers/i).closest("strong")).not.toBeNull();
    expect(screen.getByRole("heading", { name: "What I checked" })).toBeTruthy();
    expect(screen.getByText("project_context_read").tagName).toBe("CODE");
    expect(screen.queryByText(/### What I checked/)).toBeNull();
  });
});
