import { useState, useRef, useEffect } from "react"
import { useChatSession } from "../../hooks/useChatSession"
import type { ChatMessage } from "../../hooks/useChatSession"

export interface ChatPanelProps {
  speaker: string | null
  conceptId: string | null
}

export function ChatPanel({ speaker, conceptId }: ChatPanelProps) {
  const { messages, sending, send, clear } = useChatSession()
  const [inputText, setInputText] = useState("")
  const messagesEndRef = useRef<HTMLDivElement>(null)

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    if (messagesEndRef.current && typeof messagesEndRef.current.scrollIntoView === "function") {
      messagesEndRef.current.scrollIntoView({ behavior: "smooth" })
    }
  }, [messages])

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!inputText.trim() || sending) return
    send(inputText)
    setInputText("")
  }

  const containerStyle: React.CSSProperties = {
    display: "flex",
    flexDirection: "column",
    height: "100%",
    fontFamily: "system-ui, -apple-system, sans-serif",
    color: "#0f172a",
  }

  const headerStyle: React.CSSProperties = {
    padding: "12px 16px",
    borderBottom: "1px solid #e2e8f0",
    fontSize: 14,
    fontWeight: 700,
  }

  const messageListStyle: React.CSSProperties = {
    flex: 1,
    overflowY: "auto",
    padding: 16,
    display: "flex",
    flexDirection: "column",
    gap: 12,
  }

  const inputRowStyle: React.CSSProperties = {
    display: "flex",
    gap: 8,
    padding: "12px 16px",
    borderTop: "1px solid #e2e8f0",
  }

  const inputStyle: React.CSSProperties = {
    flex: 1,
    padding: "8px 10px",
    border: "1px solid #cbd5e1",
    borderRadius: 8,
    fontSize: 14,
  }

  const btnStyle: React.CSSProperties = {
    padding: "8px 14px",
    borderRadius: 8,
    fontSize: 13,
    fontWeight: 600,
    cursor: "pointer",
    border: "1px solid #6366f1",
    background: "#6366f1",
    color: "#fff",
  }

  const disabledBtnStyle: React.CSSProperties = {
    ...btnStyle,
    opacity: 0.5,
    cursor: "not-allowed",
  }

  const clearBtnStyle: React.CSSProperties = {
    padding: "8px 14px",
    borderRadius: 8,
    fontSize: 13,
    fontWeight: 600,
    cursor: "pointer",
    border: "1px solid #cbd5e1",
    background: "#fff",
    color: "#374151",
  }

  const userMsgStyle: React.CSSProperties = {
    alignSelf: "flex-end",
    background: "#eff6ff",
    border: "1px solid #bfdbfe",
    borderRadius: 10,
    padding: "8px 12px",
    maxWidth: "80%",
  }

  const assistantMsgStyle: React.CSSProperties = {
    alignSelf: "flex-start",
    background: "#f8fafc",
    border: "1px solid #e2e8f0",
    borderRadius: 10,
    padding: "8px 12px",
    maxWidth: "80%",
  }

  const headerText = `AI Assistant${speaker ? ` — ${speaker}` : ""}${conceptId ? ` / ${conceptId}` : ""}`
  const canSend = inputText.trim() !== "" && !sending

  return (
    <div style={containerStyle}>
      <div style={headerStyle}>{headerText}</div>
      <div style={messageListStyle} data-testid="message-list">
        {messages.length === 0 && (
          <div style={{ color: "#94a3b8", fontSize: 13 }}>
            No messages yet. Start a conversation.
          </div>
        )}
        {messages.map((msg: ChatMessage, i: number) => (
          <div
            key={i}
            style={msg.role === "user" ? userMsgStyle : assistantMsgStyle}
          >
            <div
              style={{
                fontSize: 10,
                fontWeight: 700,
                color: "#64748b",
                marginBottom: 4,
                textTransform: "uppercase",
              }}
            >
              {msg.role}
            </div>
            <div style={{ fontSize: 13, lineHeight: 1.45 }}>{msg.content}</div>
            <div style={{ fontSize: 10, color: "#94a3b8", marginTop: 4 }}>
              {msg.timestamp}
            </div>
          </div>
        ))}
        <div ref={messagesEndRef} />
      </div>
      <form onSubmit={handleSubmit} style={inputRowStyle}>
        <input
          style={inputStyle}
          value={inputText}
          onChange={(e) => setInputText(e.target.value)}
          placeholder="Type a message..."
          aria-label="Chat input"
        />
        <button
          type="submit"
          style={canSend ? btnStyle : disabledBtnStyle}
          disabled={!canSend}
        >
          Send
        </button>
        <button
          type="button"
          style={clearBtnStyle}
          onClick={clear}
        >
          Clear session
        </button>
      </form>
    </div>
  )
}
