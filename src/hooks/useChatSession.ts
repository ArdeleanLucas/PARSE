import { useState, useEffect, useRef, useCallback } from "react"
import { startChatSession, runChat, pollChat, getChatSession } from "../api/client"

export interface ChatMessage {
  role: "user" | "assistant"
  content: string
  timestamp: string
}

export interface UseChatSessionResult {
  messages: ChatMessage[]
  sessionId: string | null
  sending: boolean
  statusMessage: string | null
  error: string | null
  tokensUsed: number | null
  tokensLimit: number | null
  send: (text: string) => Promise<void>
  clear: () => void
}

const SESSION_KEY = "parse-chat-session-id"
const POLL_INTERVAL_MS = 2000
// How many consecutive polls with no message change before giving up.
// Each poll is POLL_INTERVAL_MS, so 30 idle polls = 60 s of silence.
const MAX_IDLE_POLLS = 30

export function extractAssistantContent(raw: unknown): string {
  if (typeof raw === "string") return raw
  if (raw && typeof raw === "object") {
    const r = raw as Record<string, unknown>
    const assistant = r.assistant
    if (assistant && typeof assistant === "object") {
      const content = (assistant as Record<string, unknown>).content
      if (typeof content === "string") return content
    }
    if (typeof r.content === "string") return r.content
    if (typeof r.message === "string") return r.message
  }
  return ""
}

export function useChatSession(): UseChatSessionResult {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [sessionId, setSessionId] = useState<string | null>(
    () => sessionStorage.getItem(SESSION_KEY),
  )
  const [sending, setSending] = useState(false)
  const [statusMessage, setStatusMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [tokensUsed, setTokensUsed] = useState<number | null>(null)
  const [tokensLimit, setTokensLimit] = useState<number | null>(null)
  const abortRef = useRef<AbortController | null>(null)

  const refreshTokens = useCallback(async (sid: string) => {
    try {
      const s = await getChatSession(sid)
      setTokensUsed(s.tokensUsed)
      setTokensLimit(s.tokensLimit)
    } catch {
      // Token refresh is best-effort — the chat works fine without the ring.
    }
  }, [])

  // Initialize session on mount
  useEffect(() => {
    const controller = new AbortController()
    abortRef.current = controller

    const init = async () => {
      try {
        const stored = sessionStorage.getItem(SESSION_KEY)
        const resp = await startChatSession(stored ?? undefined)
        if (!controller.signal.aborted) {
          setSessionId(resp.session_id)
          sessionStorage.setItem(SESSION_KEY, resp.session_id)
        }
      } catch {
        // Session init failed — will retry on send
      }
    }
    init()

    return () => {
      controller.abort()
      abortRef.current = null
    }
  }, [])

  const send = useCallback(async (text: string) => {
    if (!text.trim()) return
    setError(null)
    setSending(true)

    const userMsg: ChatMessage = {
      role: "user",
      content: text,
      timestamp: new Date().toISOString(),
    }
    setMessages((prev) => [...prev, userMsg])

    try {
      // Ensure session exists
      let sid = sessionId
      if (!sid) {
        const resp = await startChatSession()
        sid = resp.session_id
        setSessionId(sid)
        sessionStorage.setItem(SESSION_KEY, sid)
      }

      const job = await runChat(sid, text)

      // Poll for completion.  Timeout is activity-based: idlePolls resets
      // to zero whenever the server's status message changes, so long-running
      // tool calls (STT, imports) never time out as long as they keep
      // reporting progress.
      let idlePolls = 0
      let lastMessage: string | undefined
      const pollOnce = (): Promise<string> =>
        new Promise((resolve, reject) => {
          const tick = () => {
            if (abortRef.current?.signal.aborted) {
              reject(new Error("Aborted"))
              return
            }
            pollChat(job.job_id)
              .then((status) => {
                // Reset idle counter whenever the server reports new activity.
                if (status.message !== lastMessage) {
                  idlePolls = 0
                  lastMessage = status.message
                  setStatusMessage(status.message ?? null)
                } else {
                  idlePolls++
                }

                if (
                  status.status === "done"
                  || status.status === "completed"
                  || status.status === "complete"
                ) {
                  resolve(extractAssistantContent(status.result))
                } else if (status.status === "error") {
                  reject(new Error(status.error ?? extractAssistantContent(status.result) ?? "Chat error"))
                } else if (idlePolls >= MAX_IDLE_POLLS) {
                  reject(new Error("Chat timed out — no response after 60 s of inactivity"))
                } else {
                  setTimeout(tick, POLL_INTERVAL_MS)
                }
              })
              .catch(reject)
          }
          setTimeout(tick, POLL_INTERVAL_MS)
        })

      const result = await pollOnce()

      const assistantMsg: ChatMessage = {
        role: "assistant",
        content: result,
        timestamp: new Date().toISOString(),
      }
      setMessages((prev) => [...prev, assistantMsg])

      // Refresh context-window usage from the server-side session state.
      void refreshTokens(sid)

      // Sync tags from server after every agent response
      try {
        const { useTagStore } = await import("../stores/tagStore")
        useTagStore.getState().syncFromServer()
      } catch {
        // non-fatal
      }
    } catch (e) {
      if (!(e instanceof Error && e.message === "Aborted")) {
        setError(e instanceof Error ? e.message : "Send failed")
      }
    } finally {
      setSending(false)
      setStatusMessage(null)
    }
  }, [sessionId])

  const clear = useCallback(() => {
    setMessages([])
    setSessionId(null)
    setError(null)
    setTokensUsed(null)
    setTokensLimit(null)
    sessionStorage.removeItem(SESSION_KEY)
  }, [])

  return { messages, sessionId, sending, statusMessage, error, tokensUsed, tokensLimit, send, clear }
}
