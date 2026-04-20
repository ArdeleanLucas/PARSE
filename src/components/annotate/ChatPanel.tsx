import { useState, useRef, useEffect } from "react"
import { useChatSession } from "../../hooks/useChatSession"
import type { ChatMessage } from "../../hooks/useChatSession"
import { getAuthStatus, startAuthFlow, saveApiKey, logoutAuth } from "../../api/client"
import type { AuthStatus } from "../../api/types"
import { ContextRing } from "../shared/ContextRing"

export interface ChatPanelProps {
  speaker: string | null
  conceptId: string | null
}

type AuthState = "checking" | "unauthenticated" | "entering-xai" | "entering-openai" | "oauth" | "authenticated"

export function ChatPanel({ speaker, conceptId }: ChatPanelProps) {
  const { messages, sending, tokensUsed, tokensLimit, send, clear } = useChatSession()
  const [inputText, setInputText] = useState("")
  const messagesEndRef = useRef<HTMLDivElement>(null)

  const [authState, setAuthState] = useState<AuthState>("checking")
  const [apiKeyInput, setApiKeyInput] = useState("")
  const [authError, setAuthError] = useState("")
  const [oauthInfo, setOauthInfo] = useState<{ user_code?: string; verification_uri?: string }>({})
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  // Check auth on mount
  useEffect(() => {
    getAuthStatus()
      .then((s: AuthStatus) => {
        setAuthState(s.authenticated ? "authenticated" : "unauthenticated")
      })
      .catch(() => setAuthState("unauthenticated"))
  }, [])

  // Clean up poll on unmount
  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current)
    }
  }, [])

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

  const handleSaveKey = async () => {
    setAuthError("")
    const provider = authState === "entering-xai" ? "xai" : "openai"
    try {
      const result = await saveApiKey(apiKeyInput, provider)
      if (result.authenticated) {
        setAuthState("authenticated")
        setApiKeyInput("")
      } else {
        setAuthError("Failed to save key")
      }
    } catch (err) {
      setAuthError(err instanceof Error ? err.message : "Failed to save key")
    }
  }

  const handleStartOAuth = async () => {
    setAuthError("")
    setAuthState("oauth")
    try {
      await startAuthFlow()
      const status = await getAuthStatus()
      if (status.user_code) {
        setOauthInfo({ user_code: status.user_code, verification_uri: status.verification_uri })
      }
      // Start polling
      pollRef.current = setInterval(async () => {
        try {
          const s = await getAuthStatus()
          if (s.authenticated) {
            if (pollRef.current) clearInterval(pollRef.current)
            pollRef.current = null
            setAuthState("authenticated")
          }
        } catch {
          // keep polling
        }
      }, 5000)
    } catch (err) {
      setAuthError(err instanceof Error ? err.message : "OAuth start failed")
    }
  }

  const handleSignOut = async () => {
    try {
      await logoutAuth()
    } catch {
      // ignore
    }
    if (pollRef.current) clearInterval(pollRef.current)
    pollRef.current = null
    setAuthState("unauthenticated")
    setApiKeyInput("")
    setAuthError("")
    setOauthInfo({})
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
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
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

  const authBtnStyle: React.CSSProperties = {
    padding: "10px 20px",
    borderRadius: 8,
    fontSize: 14,
    fontWeight: 600,
    cursor: "pointer",
    border: "1px solid #6366f1",
    background: "#6366f1",
    color: "#fff",
    width: "100%",
  }

  const secondaryBtnStyle: React.CSSProperties = {
    ...authBtnStyle,
    background: "#fff",
    color: "#6366f1",
  }

  const signOutStyle: React.CSSProperties = {
    fontSize: 12,
    color: "#6366f1",
    cursor: "pointer",
    background: "none",
    border: "none",
    padding: 0,
    fontWeight: 500,
  }

  const headerText = `AI Assistant${speaker ? ` — ${speaker}` : ""}${conceptId ? ` / ${conceptId}` : ""}`
  const canSend = inputText.trim() !== "" && !sending

  // Auth screen
  if (authState !== "authenticated") {
    return (
      <div style={containerStyle}>
        <div style={headerStyle}>
          <span>{headerText}</span>
        </div>
        <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", padding: 32 }}>
          <div style={{ maxWidth: 340, width: "100%", textAlign: "center" }}>
            {authState === "checking" && (
              <div style={{ color: "#94a3b8", fontSize: 14 }}>Checking authentication...</div>
            )}

            {authState === "unauthenticated" && (
              <>
                <div style={{ fontSize: 18, fontWeight: 700, marginBottom: 24 }}>Connect AI Assistant</div>
                <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                  <button style={authBtnStyle} onClick={() => { setAuthState("entering-xai"); setAuthError(""); setApiKeyInput(""); }}>
                    Use xAI API Key
                  </button>
                  <div style={{ fontSize: 12, color: "#94a3b8" }}>or</div>
                  <button style={secondaryBtnStyle} onClick={() => { setAuthState("entering-openai"); setAuthError(""); setApiKeyInput(""); }}>
                    Use OpenAI API Key
                  </button>
                  <div style={{ fontSize: 12, color: "#94a3b8" }}>or</div>
                  <button style={secondaryBtnStyle} onClick={handleStartOAuth}>
                    Sign in with OpenAI (OAuth)
                  </button>
                </div>
              </>
            )}

            {(authState === "entering-xai" || authState === "entering-openai") && (
              <>
                <div style={{ fontSize: 18, fontWeight: 700, marginBottom: 16 }}>
                  {authState === "entering-xai" ? "xAI API Key" : "OpenAI API Key"}
                </div>
                <input
                  type="password"
                  style={{ ...inputStyle, width: "100%", marginBottom: 12, boxSizing: "border-box" }}
                  placeholder={authState === "entering-xai" ? "xai-..." : "sk-..."}
                  value={apiKeyInput}
                  onChange={(e) => setApiKeyInput(e.target.value)}
                  aria-label={authState === "entering-xai" ? "xAI API Key" : "OpenAI API Key"}
                />
                <div style={{ display: "flex", gap: 8 }}>
                  <button
                    style={secondaryBtnStyle}
                    onClick={() => { setAuthState("unauthenticated"); setAuthError(""); setApiKeyInput(""); }}
                  >
                    Back
                  </button>
                  <button
                    style={apiKeyInput.trim() ? authBtnStyle : { ...authBtnStyle, opacity: 0.5, cursor: "not-allowed" }}
                    disabled={!apiKeyInput.trim()}
                    onClick={handleSaveKey}
                  >
                    Connect
                  </button>
                </div>
              </>
            )}

            {authState === "oauth" && (
              <>
                <div style={{ fontSize: 18, fontWeight: 700, marginBottom: 16 }}>OpenAI Sign In</div>
                {oauthInfo.user_code ? (
                  <div>
                    <div style={{ fontSize: 13, color: "#64748b", marginBottom: 8 }}>
                      Enter this code at the verification page:
                    </div>
                    <div style={{ fontSize: 24, fontWeight: 700, letterSpacing: 2, marginBottom: 12 }}>
                      {oauthInfo.user_code}
                    </div>
                    {oauthInfo.verification_uri && (
                      <div style={{ fontSize: 12, color: "#6366f1", marginBottom: 16, wordBreak: "break-all" }}>
                        {oauthInfo.verification_uri}
                      </div>
                    )}
                    <div style={{ fontSize: 12, color: "#94a3b8" }}>Waiting for confirmation...</div>
                  </div>
                ) : (
                  <div style={{ color: "#94a3b8", fontSize: 14 }}>Starting OAuth flow...</div>
                )}
                <button
                  style={{ ...secondaryBtnStyle, marginTop: 16 }}
                  onClick={() => {
                    if (pollRef.current) clearInterval(pollRef.current)
                    pollRef.current = null
                    setAuthState("unauthenticated")
                    setOauthInfo({})
                    setAuthError("")
                  }}
                >
                  Back
                </button>
              </>
            )}

            {authError && (
              <div style={{ color: "#dc2626", fontSize: 13, marginTop: 12 }}>{authError}</div>
            )}
          </div>
        </div>
      </div>
    )
  }

  // Authenticated chat UI
  return (
    <div style={containerStyle}>
      <div style={headerStyle}>
        <span>{headerText}</span>
        <span style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <ContextRing used={tokensUsed} limit={tokensLimit} />
          <button style={signOutStyle} onClick={handleSignOut}>Sign out</button>
        </span>
      </div>
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
