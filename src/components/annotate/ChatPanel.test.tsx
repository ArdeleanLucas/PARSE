// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest"
import { render, screen, fireEvent, cleanup, waitFor } from "@testing-library/react"
import { ChatPanel } from "./ChatPanel"

const mockSend = vi.fn()
const mockClear = vi.fn()

let mockMessages: { role: string; content: string; timestamp: string }[] = []
let mockSending = false

vi.mock("../../hooks/useChatSession", () => ({
  useChatSession: () => ({
    messages: mockMessages,
    sessionId: "test-session",
    sending: mockSending,
    error: null,
    send: mockSend,
    clear: mockClear,
  }),
}))

vi.mock("../../api/client", () => ({
  getAuthStatus: () => Promise.resolve({ authenticated: true, method: "api_key", provider: "xai" }),
  startAuthFlow: vi.fn(),
  pollAuth: vi.fn(),
  saveApiKey: vi.fn(),
  logoutAuth: vi.fn(),
}))

describe("ChatPanel", () => {
  beforeEach(() => {
    mockMessages = []
    mockSending = false
    mockSend.mockClear()
    mockClear.mockClear()
  })

  afterEach(() => {
    cleanup()
  })

  it("renders empty state", async () => {
    render(<ChatPanel speaker="SPK_01" conceptId="greeting" />)
    await waitFor(() => {
      expect(screen.getByText("No messages yet. Start a conversation.")).toBeTruthy()
    })
    expect(screen.getByText(/AI Assistant — SPK_01 \/ greeting/)).toBeTruthy()
  })

  it("Send button disabled when input empty", async () => {
    render(<ChatPanel speaker="SPK_01" conceptId={null} />)
    await waitFor(() => {
      expect(screen.getByText("Send")).toBeTruthy()
    })
    const sendBtn = screen.getByText("Send")
    expect((sendBtn as HTMLButtonElement).disabled).toBe(true)
  })

  it("send() called on submit", async () => {
    render(<ChatPanel speaker="SPK_01" conceptId={null} />)
    await waitFor(() => {
      expect(screen.getByPlaceholderText("Type a message...")).toBeTruthy()
    })
    const input = screen.getByPlaceholderText("Type a message...")
    fireEvent.change(input, { target: { value: "hello" } })
    fireEvent.submit(input.closest("form")!)
    expect(mockSend).toHaveBeenCalledWith("hello")
  })

  it("messages displayed in order", async () => {
    mockMessages = [
      { role: "user", content: "What is IPA?", timestamp: "2026-01-01T00:00:00Z" },
      { role: "assistant", content: "IPA stands for International Phonetic Alphabet.", timestamp: "2026-01-01T00:00:01Z" },
    ]
    render(<ChatPanel speaker={null} conceptId={null} />)
    await waitFor(() => {
      expect(screen.getByTestId("message-list")).toBeTruthy()
    })
    const messageList = screen.getByTestId("message-list")
    const texts = messageList.textContent ?? ""
    const userIdx = texts.indexOf("What is IPA?")
    const assistantIdx = texts.indexOf("IPA stands for International Phonetic Alphabet.")
    expect(userIdx).toBeLessThan(assistantIdx)
    expect(userIdx).toBeGreaterThanOrEqual(0)
  })
})
