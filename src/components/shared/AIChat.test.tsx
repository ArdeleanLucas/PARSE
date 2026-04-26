// @vitest-environment jsdom
import { render, screen, fireEvent, act, cleanup } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import type { UseChatSessionResult } from "../../hooks/useChatSession";

const mockSaveApiKey = vi.fn();
const mockGetAuthStatus = vi.fn();
const mockPollAuth = vi.fn();
const mockStartAuthFlow = vi.fn();

vi.mock("../../api/client", () => ({
  saveApiKey: (...args: unknown[]) => mockSaveApiKey(...args),
  getAuthStatus: (...args: unknown[]) => mockGetAuthStatus(...args),
  pollAuth: (...args: unknown[]) => mockPollAuth(...args),
  startAuthFlow: (...args: unknown[]) => mockStartAuthFlow(...args),
}));

import { AIChat } from "./AIChat";

function makeChatSession(overrides: Partial<UseChatSessionResult> = {}): UseChatSessionResult {
  return {
    messages: [],
    sessionId: "session-1",
    sending: false,
    statusMessage: null,
    error: null,
    tokensUsed: null,
    tokensLimit: null,
    send: vi.fn().mockResolvedValue(undefined),
    clear: vi.fn(),
    ...overrides,
  };
}

describe("AIChat", () => {
  beforeEach(() => {
    mockSaveApiKey.mockReset();
    mockGetAuthStatus.mockReset();
    mockPollAuth.mockReset();
    mockStartAuthFlow.mockReset();
    mockGetAuthStatus.mockResolvedValue({ authenticated: false, flow_active: false });
  });

  afterEach(() => {
    cleanup();
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("shows the provider chooser when auth is absent", async () => {
    render(
      <AIChat
        height={320}
        minimized={false}
        onResizeStart={vi.fn()}
        onMinimize={vi.fn()}
        conceptName="water"
        conceptId={1}
        speakerCount={3}
        chatSession={makeChatSession()}
      />,
    );

    expect(await screen.findByRole("heading", { name: "Connect PARSE AI" })).toBeTruthy();
    expect(screen.getByText("xAI / Grok")).toBeTruthy();
    expect(screen.getByText("OpenAI API")).toBeTruthy();
  });

  it("restores the xAI badge and renders assistant markdown after reload", async () => {
    mockGetAuthStatus.mockResolvedValue({ authenticated: true, provider: "xai", flow_active: false });

    render(
      <AIChat
        height={320}
        minimized={false}
        onResizeStart={vi.fn()}
        onMinimize={vi.fn()}
        conceptName="water"
        conceptId={1}
        speakerCount={3}
        chatSession={makeChatSession({
          messages: [
            {
              role: "assistant",
              content: "### What I checked\n- `project_context_read`: 3 speakers",
              timestamp: "2026-04-26T10:00:00.000Z",
            },
          ],
        })}
      />,
    );

    expect(await screen.findByText("Connected to xAI")).toBeTruthy();
    expect(screen.getByText(/grok-4\.2 reasoning/i)).toBeTruthy();
    expect(screen.getByRole("heading", { name: "What I checked" })).toBeTruthy();
    expect(screen.getByText("project_context_read").tagName).toBe("CODE");
  });

  it("submits the collapsed command bar after expanding", async () => {
    const onMinimize = vi.fn();
    const chatSession = makeChatSession();

    render(
      <AIChat
        height={320}
        minimized
        onResizeStart={vi.fn()}
        onMinimize={onMinimize}
        conceptName="water"
        conceptId={1}
        speakerCount={3}
        chatSession={chatSession}
      />,
    );

    fireEvent.change(screen.getByPlaceholderText(/Ask PARSE AI about water \(#1\)/i), {
      target: { value: "Analyze cognates" },
    });
    fireEvent.click(screen.getByTitle("Send"));

    expect(onMinimize).toHaveBeenCalledTimes(1);
    expect(chatSession.send).not.toHaveBeenCalled();

    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 300));
    });

    expect(chatSession.send).toHaveBeenCalledWith("Analyze cognates");
  });

  it("switches from xAI to OpenAI and saves the new provider key", async () => {
    mockGetAuthStatus.mockResolvedValue({ authenticated: true, provider: 'xai', flow_active: false });
    mockSaveApiKey.mockResolvedValue({ authenticated: true });

    render(
      <AIChat
        height={320}
        minimized={false}
        onResizeStart={vi.fn()}
        onMinimize={vi.fn()}
        conceptName="water"
        conceptId={1}
        speakerCount={3}
        chatSession={makeChatSession()}
      />,
    );

    expect(await screen.findByText('Connected to xAI')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: /switch provider/i }));
    fireEvent.click(await screen.findByRole('button', { name: /openai api/i }));
    fireEvent.change(screen.getByPlaceholderText('sk-...'), { target: { value: 'sk-live-openai' } });
    fireEvent.click(screen.getByRole('button', { name: /save key/i }));

    expect(await screen.findByText('Connected to OpenAI')).toBeTruthy();
    expect(screen.getByText(/gpt-5\.4/i)).toBeTruthy();
    expect(mockSaveApiKey).toHaveBeenCalledWith('sk-live-openai', 'openai');
  });

  it("fires onMinimize and renders the collapsed bar without the resize handle when minimized", async () => {
    mockGetAuthStatus.mockResolvedValue({ authenticated: true, provider: 'xai', flow_active: false });
    const onMinimize = vi.fn();

    const { rerender, container } = render(
      <AIChat
        height={320}
        minimized={false}
        onResizeStart={vi.fn()}
        onMinimize={onMinimize}
        conceptName="water"
        conceptId={1}
        speakerCount={3}
        chatSession={makeChatSession()}
      />,
    );

    expect(await screen.findByText('Connected to xAI')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: /minimize/i }));
    expect(onMinimize).toHaveBeenCalledTimes(1);
    expect(container.querySelector('.cursor-ns-resize')).not.toBeNull();

    rerender(
      <AIChat
        height={320}
        minimized
        onResizeStart={vi.fn()}
        onMinimize={onMinimize}
        conceptName="water"
        conceptId={1}
        speakerCount={3}
        chatSession={makeChatSession()}
      />,
    );

    expect(screen.getByPlaceholderText(/Ask PARSE AI about water \(#1\)/i)).toBeTruthy();
    expect(screen.queryByRole('button', { name: /minimize/i })).toBeNull();
    expect(container.querySelector('.cursor-ns-resize')).toBeNull();
  });

  it("shows concept-specific header copy with the concept name and speaker count", async () => {
    mockGetAuthStatus.mockResolvedValue({ authenticated: true, provider: 'openai', flow_active: false });

    render(
      <AIChat
        height={320}
        minimized={false}
        onResizeStart={vi.fn()}
        onMinimize={vi.fn()}
        conceptName="Foo"
        conceptId={99}
        speakerCount={3}
        chatSession={makeChatSession()}
      />,
    );

    expect(await screen.findByText('Connected to OpenAI')).toBeTruthy();
    expect(screen.getByText(/asking about/i).textContent).toContain('Foo');
    expect(screen.getByText(/asking about/i).textContent).toContain('3 speakers');
    expect(screen.getByText(/hi, i'm parse ai/i).textContent).toContain('concept "Foo" across 3 speakers');
  });

  it("submits on Enter and preserves a newline on Shift+Enter", async () => {
    mockGetAuthStatus.mockResolvedValue({ authenticated: true, provider: 'openai', flow_active: false });
    const chatSession = makeChatSession();

    render(
      <AIChat
        height={320}
        minimized={false}
        onResizeStart={vi.fn()}
        onMinimize={vi.fn()}
        conceptName="water"
        conceptId={1}
        speakerCount={3}
        chatSession={chatSession}
      />,
    );

    expect(await screen.findByText('Connected to OpenAI')).toBeTruthy();
    const composer = screen.getByPlaceholderText(/Ask PARSE AI about water/i);

    fireEvent.change(composer, { target: { value: 'line one' } });
    fireEvent.keyDown(composer, { key: 'Enter', code: 'Enter' });
    expect(chatSession.send).toHaveBeenCalledWith('line one');

    fireEvent.change(composer, { target: { value: 'line one' } });
    fireEvent.keyDown(composer, { key: 'Enter', code: 'Enter', shiftKey: true });
    expect((composer as HTMLInputElement | HTMLTextAreaElement).value).toContain('\n');
    expect(chatSession.send).toHaveBeenCalledTimes(1);
  });
});
