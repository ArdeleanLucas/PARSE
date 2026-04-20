// @vitest-environment jsdom
import { renderHook, act } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { startChatSession, runChat, pollChat, syncFromServer } = vi.hoisted(() => ({
  startChatSession: vi.fn(),
  runChat: vi.fn(),
  pollChat: vi.fn(),
  syncFromServer: vi.fn(),
}));

vi.mock("../../api/client", () => ({
  startChatSession,
  runChat,
  pollChat,
}));

vi.mock("../../stores/tagStore", () => ({
  useTagStore: {
    getState: () => ({ syncFromServer }),
  },
}));

import { useChatSession } from "../useChatSession";

describe("useChatSession", () => {
  beforeEach(() => {
    sessionStorage.clear();
    vi.useFakeTimers();
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("hydrates a normalized session id returned by the API client", async () => {
    startChatSession.mockResolvedValue({ session_id: "chat_123" });

    const { result } = renderHook(() => useChatSession());

    await act(async () => {
      await Promise.resolve();
    });

    expect(result.current.sessionId).toBe("chat_123");
    expect(sessionStorage.getItem("parse-chat-session-id")).toBe("chat_123");
  });

  it("treats a complete poll status as a successful assistant reply", async () => {
    startChatSession.mockResolvedValue({ session_id: "chat_123" });
    runChat.mockResolvedValue({ job_id: "job_123" });
    pollChat
      .mockResolvedValueOnce({ status: "complete", result: "assistant reply" })
      .mockResolvedValueOnce({ status: "error", error: "should not poll twice" });

    const { result } = renderHook(() => useChatSession());

    await act(async () => {
      await Promise.resolve();
    });

    expect(result.current.sessionId).toBe("chat_123");

    await act(async () => {
      void result.current.send("hello");
    });

    expect(result.current.messages.map((message) => message.content)).toEqual(["hello"]);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(2100);
      await Promise.resolve();
    });

    expect(result.current.messages.map((message) => message.content)).toEqual([
      "hello",
      "assistant reply",
    ]);
    expect(result.current.error).toBeNull();
    expect(pollChat).toHaveBeenCalledTimes(1);
    expect(syncFromServer).toHaveBeenCalledTimes(1);
  });
});
