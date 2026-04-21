import { useState, useRef, useEffect } from "react"
import { useChatSession } from "../../hooks/useChatSession"
import type { ChatMessage } from "../../hooks/useChatSession"
import { getAuthStatus, startAuthFlow, pollAuth, saveApiKey, logoutAuth } from "../../api/client"
import type { AuthStatus } from "../../api/types"
import { ContextRing } from "../shared/ContextRing"

export interface ChatPanelProps {
  speaker: string | null
  conceptId: string | null
}

type AuthState = "checking" | "unauthenticated" | "entering-xai" | "entering-openai" | "oauth" | "authenticated"

const primaryBtnClass =
  "rounded-md border border-indigo-600 bg-indigo-600 px-3.5 py-2 text-[13px] font-semibold text-white hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-50"
const clearBtnClass =
  "rounded-md border border-slate-300 bg-white px-3.5 py-2 text-[13px] font-semibold text-slate-700 hover:bg-slate-50"
const inputClass =
  "flex-1 rounded-md border border-slate-300 bg-white px-2.5 py-2 text-sm text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-100"
const authPrimaryBtnClass =
  "w-full rounded-md border border-indigo-600 bg-indigo-600 px-5 py-2.5 text-sm font-semibold text-white hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-50"
const authSecondaryBtnClass =
  "w-full rounded-md border border-indigo-600 bg-white px-5 py-2.5 text-sm font-semibold text-indigo-600 hover:bg-slate-50"

export function ChatPanel({ speaker, conceptId }: ChatPanelProps) {
  const { messages, sending, tokensUsed, tokensLimit, send, clear } = useChatSession()
  const [inputText, setInputText] = useState("")
  const messagesEndRef = useRef<HTMLDivElement>(null)

  const [authState, setAuthState] = useState<AuthState>("checking")
  const [apiKeyInput, setApiKeyInput] = useState("")
  const [authError, setAuthError] = useState("")
  const [oauthInfo, setOauthInfo] = useState<{ user_code?: string; verification_uri?: string }>({})
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    // Retry up to ~10 s so a brief backend restart during a code update
    // doesn't incorrectly drop a persisted API key.
    let attempt = 0
    const delays = [500, 1000, 2000, 3000, 4000]
    let cancelled = false

    const tryFetch = () => {
      getAuthStatus()
        .then((s: AuthStatus) => {
          if (cancelled) return
          if (s.authenticated) {
            setAuthState("authenticated")
          } else if (s.flow_active) {
            // OAuth device flow was started before this mount (e.g. HMR reload).
            // Resume polling so the token is picked up without re-entering the code.
            setOauthInfo({ user_code: s.user_code, verification_uri: s.verification_uri })
            setAuthState("oauth")
            if (!pollRef.current) {
              pollRef.current = setInterval(async () => {
                try {
                  const result = await pollAuth()
                  if (result.status === "complete") {
                    if (pollRef.current) clearInterval(pollRef.current)
                    pollRef.current = null
                    setAuthState("authenticated")
                  } else if (result.status === "expired" || result.status === "error") {
                    if (pollRef.current) clearInterval(pollRef.current)
                    pollRef.current = null
                    setAuthState("unauthenticated")
                    setAuthError(result.error ?? (result.status === "expired" ? "Login code expired — try again" : "OAuth failed"))
                    setOauthInfo({})
                  }
                } catch { /* transient — keep polling */ }
              }, 5000)
            }
          } else {
            setAuthState("unauthenticated")
          }
        })
        .catch(() => {
          if (cancelled) return
          if (attempt < delays.length) {
            setTimeout(tryFetch, delays[attempt++])
          } else {
            setAuthState("unauthenticated")
          }
        })
    }
    tryFetch()
    return () => { cancelled = true }
  }, [])

  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current)
    }
  }, [])

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
      pollRef.current = setInterval(async () => {
        try {
          // pollAuth drives the actual OpenAI device-token exchange.
          // getAuthStatus alone only reads cached server state, so without
          // this call _auth_state.status stays "pending" forever.
          const result = await pollAuth()
          if (result.status === "complete") {
            if (pollRef.current) clearInterval(pollRef.current)
            pollRef.current = null
            setAuthState("authenticated")
            return
          }
          if (result.status === "expired" || result.status === "error") {
            if (pollRef.current) clearInterval(pollRef.current)
            pollRef.current = null
            setAuthState("unauthenticated")
            setAuthError(result.error ?? (result.status === "expired" ? "Login code expired — try again" : "OAuth failed"))
            setOauthInfo({})
          }
        } catch {
          // keep polling — transient network failures shouldn't abort the flow
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

  const headerText = `AI Assistant${speaker ? ` — ${speaker}` : ""}${conceptId ? ` / ${conceptId}` : ""}`
  const canSend = inputText.trim() !== "" && !sending

  const headerRow = (
    <div className="flex items-center justify-between border-b border-slate-200 bg-white px-4 py-3 text-sm font-bold text-slate-900">
      <span>{headerText}</span>
      {authState === "authenticated" && (
        <span className="flex items-center gap-3">
          <ContextRing used={tokensUsed} limit={tokensLimit} />
          <button
            onClick={handleSignOut}
            className="border-none bg-transparent p-0 text-xs font-medium text-indigo-600 hover:text-indigo-700"
          >
            Sign out
          </button>
        </span>
      )}
    </div>
  )

  // Auth screen
  if (authState !== "authenticated") {
    return (
      <div className="flex h-full flex-col bg-white text-slate-900">
        {headerRow}
        <div className="flex flex-1 items-center justify-center p-8">
          <div className="w-full max-w-[340px] text-center">
            {authState === "checking" && (
              <div className="text-sm text-slate-400">Checking authentication...</div>
            )}

            {authState === "unauthenticated" && (
              <>
                <div className="mb-6 text-lg font-bold">Connect AI Assistant</div>
                <div className="flex flex-col gap-3">
                  <button
                    className={authPrimaryBtnClass}
                    onClick={() => { setAuthState("entering-xai"); setAuthError(""); setApiKeyInput(""); }}
                  >
                    Use xAI API Key
                  </button>
                  <div className="text-xs text-slate-400">or</div>
                  <button
                    className={authSecondaryBtnClass}
                    onClick={() => { setAuthState("entering-openai"); setAuthError(""); setApiKeyInput(""); }}
                  >
                    Use OpenAI API Key
                  </button>
                  <div className="text-xs text-slate-400">or</div>
                  <button className={authSecondaryBtnClass} onClick={handleStartOAuth}>
                    Sign in with OpenAI (OAuth)
                  </button>
                </div>
              </>
            )}

            {(authState === "entering-xai" || authState === "entering-openai") && (
              <>
                <div className="mb-4 text-lg font-bold">
                  {authState === "entering-xai" ? "xAI API Key" : "OpenAI API Key"}
                </div>
                <input
                  type="password"
                  className={`${inputClass} mb-3 w-full`}
                  placeholder={authState === "entering-xai" ? "xai-..." : "sk-..."}
                  value={apiKeyInput}
                  onChange={(e) => setApiKeyInput(e.target.value)}
                  aria-label={authState === "entering-xai" ? "xAI API Key" : "OpenAI API Key"}
                />
                <div className="flex gap-2">
                  <button
                    className={authSecondaryBtnClass}
                    onClick={() => { setAuthState("unauthenticated"); setAuthError(""); setApiKeyInput(""); }}
                  >
                    Back
                  </button>
                  <button
                    className={authPrimaryBtnClass}
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
                <div className="mb-4 text-lg font-bold">OpenAI Sign In</div>
                {oauthInfo.user_code ? (
                  <div>
                    <div className="mb-2 text-[13px] text-slate-500">Enter this code at the verification page:</div>
                    <div className="mb-3 text-2xl font-bold tracking-widest">{oauthInfo.user_code}</div>
                    {oauthInfo.verification_uri && (
                      <div className="mb-4 break-all text-xs text-indigo-600">{oauthInfo.verification_uri}</div>
                    )}
                    <div className="text-xs text-slate-400">Waiting for confirmation...</div>
                  </div>
                ) : (
                  <div className="text-sm text-slate-400">Starting OAuth flow...</div>
                )}
                <button
                  className={`${authSecondaryBtnClass} mt-4`}
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
              <div className="mt-3 text-[13px] text-rose-600">{authError}</div>
            )}
          </div>
        </div>
      </div>
    )
  }

  // Authenticated chat UI
  return (
    <div className="flex h-full flex-col bg-white text-slate-900">
      {headerRow}
      <div className="flex flex-1 flex-col gap-3 overflow-y-auto p-4" data-testid="message-list">
        {messages.length === 0 && (
          <div className="text-[13px] text-slate-400">No messages yet. Start a conversation.</div>
        )}
        {messages.map((msg: ChatMessage, i: number) => (
          <div
            key={i}
            className={
              msg.role === "user"
                ? "max-w-[80%] self-end rounded-xl border border-indigo-200 bg-indigo-50 px-3 py-2"
                : "max-w-[80%] self-start rounded-xl border border-slate-200 bg-slate-50 px-3 py-2"
            }
          >
            <div className="mb-1 text-[10px] font-bold uppercase text-slate-500">{msg.role}</div>
            <div className="text-[13px] leading-snug">{msg.content}</div>
            <div className="mt-1 text-[10px] text-slate-400">{msg.timestamp}</div>
          </div>
        ))}
        {sending && (messages.length === 0 || messages[messages.length - 1].role === "user") && (
          <div
            className="flex max-w-[80%] items-center gap-1.5 self-start rounded-xl border border-slate-200 bg-slate-50 px-3 py-2.5"
            aria-live="polite"
            aria-label="PARSE AI is thinking"
            data-testid="thinking-indicator"
          >
            <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-slate-400 [animation-delay:-0.3s]" />
            <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-slate-400 [animation-delay:-0.15s]" />
            <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-slate-400" />
            <span className="ml-1.5 text-[12px] font-medium text-slate-500">Thinking…</span>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>
      <form onSubmit={handleSubmit} className="flex gap-2 border-t border-slate-200 bg-white px-4 py-3">
        <input
          className={inputClass}
          value={inputText}
          onChange={(e) => setInputText(e.target.value)}
          placeholder="Type a message..."
          aria-label="Chat input"
        />
        <button type="submit" className={primaryBtnClass} disabled={!canSend}>
          Send
        </button>
        <button type="button" className={clearBtnClass} onClick={clear}>
          Clear session
        </button>
      </form>
    </div>
  )
}
