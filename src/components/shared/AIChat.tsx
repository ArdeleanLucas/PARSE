import React, { useEffect, useRef, useState } from 'react';
import {
  AlertCircle,
  ArrowLeft,
  CheckCircle2,
  ChevronDown,
  KeyRound,
  Loader2,
  Send,
  ShieldCheck,
  Sparkles,
  Zap,
} from 'lucide-react';

import { getAuthStatus, pollAuth, saveApiKey, startAuthFlow } from '../../api/client';
import type { UseChatSessionResult } from '../../hooks/useChatSession';
import { ChatMarkdown } from './ChatMarkdown';

export interface AIChatProps {
  height: number;
  minimized: boolean;
  onResizeStart: (e: React.MouseEvent) => void;
  onMinimize: () => void;
  conceptName: string;
  conceptId: number | string;
  speakerCount: number;
  chatSession: UseChatSessionResult;
}

const QUICK_ACTIONS = [
  'Analyze cognates',
  'Explain why Fail01 diverges',
  'Suggest borrowings',
  'Help decide grouping',
  'Compare IPA alignments',
];

type AIProvider = 'xai' | 'openai';
type AIConnectionView = 'welcome' | 'form-xai' | 'form-openai' | 'connected';
type TestStatus = 'idle' | 'testing' | 'success' | 'error';
interface ChatMessage { id: number; role: 'ai' | 'user'; content: string; streaming?: boolean; }

const PROVIDER_META: Record<AIProvider, { label: string; model: string; badgeClass: string }> = {
  xai: { label: 'xAI', model: 'grok-4.2 reasoning', badgeClass: 'bg-emerald-50 text-emerald-700 ring-emerald-200' },
  openai: { label: 'OpenAI', model: 'gpt-5.4', badgeClass: 'bg-emerald-50 text-emerald-700 ring-emerald-200' },
};

export function resolveAuthProvider(raw: string | undefined | null): AIProvider {
  return raw === 'xai' ? 'xai' : 'openai';
}

export const AIChat: React.FC<AIChatProps> = ({
  height,
  minimized,
  onResizeStart,
  onMinimize,
  conceptName,
  conceptId,
  speakerCount,
  chatSession,
}) => {
  const [view, setView] = useState<AIConnectionView>('welcome');
  const [provider, setProvider] = useState<AIProvider | null>(null);
  const [apiKey, setApiKey] = useState('');
  const [testStatus, setTestStatus] = useState<TestStatus>('idle');
  const [testMessage, setTestMessage] = useState('');
  const [oauthPending, setOauthPending] = useState(false);
  const [oauthCode, setOauthCode] = useState('');
  const [oauthUri, setOauthUri] = useState('');
  const oauthPollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const isConnected = view === 'connected' && provider !== null;
  const hasData = speakerCount > 0;

  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [collapsedInput, setCollapsedInput] = useState('');
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (isConnected && messages.length === 0) {
      const greet = hasData
        ? `Hi, I'm PARSE AI. I'm looking at concept "${conceptName}" across ${speakerCount} speakers. Ask me to analyze cognates, flag likely borrowings, or explain the similarity scores.`
        : `Hi, I'm PARSE AI. Let's get you set up so I can help analyze concepts, suggest cognates, and explain similarities. Import speakers or load a dataset and I'll start working with your data right away.`;
      setMessages([{ id: 1, role: 'ai', content: greet }]);
    }
  }, [isConnected, hasData, conceptName, speakerCount, messages.length]);

  const handleConnect = async (p: AIProvider) => {
    if (!apiKey.trim()) return;
    setTestStatus('testing');
    setTestMessage('');
    try {
      const result = await saveApiKey(apiKey.trim(), p);
      if (result && result.authenticated) {
        setProvider(p);
        setView('connected');
        setTestStatus('idle');
        setTestMessage('');
      } else {
        setTestStatus('error');
        setTestMessage('Key was saved but could not be verified.');
      }
    } catch (err) {
      setTestStatus('error');
      setTestMessage(err instanceof Error ? err.message : 'Connection failed.');
    }
  };

  const handleTestConnection = async () => {
    if (!apiKey.trim()) return;
    setTestStatus('testing');
    setTestMessage('');
    try {
      await saveApiKey(apiKey.trim(), provider ?? (view === 'form-xai' ? 'xai' : 'openai'));
      setTestStatus('success');
      setTestMessage('Connection verified — key saved.');
    } catch (err) {
      setTestStatus('error');
      setTestMessage(err instanceof Error ? err.message : 'Connection failed.');
    }
  };

  const handleDisconnect = () => {
    setView('welcome');
    setProvider(null);
    setApiKey('');
    setTestStatus('idle');
    setTestMessage('');
    setMessages([]);
  };

  const goToProviderForm = (p: AIProvider) => {
    setProvider(p);
    setView(p === 'xai' ? 'form-xai' : 'form-openai');
    setTestStatus('idle');
    setTestMessage('');
  };

  const backToWelcome = () => {
    setView('welcome');
    setTestStatus('idle');
    setTestMessage('');
  };

  useEffect(() => {
    getAuthStatus().then(s => {
      if (s.authenticated) {
        setProvider(resolveAuthProvider(s.provider));
        setView('connected');
      } else if (s.flow_active) {
        setOauthCode(s.user_code ?? '');
        setOauthUri(s.verification_uri ?? '');
        setOauthPending(true);
        oauthPollRef.current = setInterval(async () => {
          try {
            const result = await pollAuth();
            if (result.status === 'complete') {
              if (oauthPollRef.current) clearInterval(oauthPollRef.current);
              oauthPollRef.current = null;
              setOauthPending(false);
              const after = await getAuthStatus().catch(() => null);
              setProvider(resolveAuthProvider(after?.provider));
              setView('connected');
            } else if (result.status === 'expired' || result.status === 'error') {
              if (oauthPollRef.current) clearInterval(oauthPollRef.current);
              oauthPollRef.current = null;
              setOauthPending(false);
              setTestMessage(result.error ?? (result.status === 'expired' ? 'Login code expired — try again' : 'OAuth failed'));
            }
          } catch {
            // keep polling
          }
        }, 5000);
      }
    }).catch(() => {
      // leave view at welcome
    });

    return () => {
      if (oauthPollRef.current) clearInterval(oauthPollRef.current);
    };
  }, []);

  const handleCodexSignIn = async () => {
    setOauthPending(true);
    setOauthCode('');
    setOauthUri('');
    setTestMessage('');
    try {
      await startAuthFlow();
      const status = await getAuthStatus();
      if (status.user_code) {
        setOauthCode(status.user_code);
        setOauthUri(status.verification_uri ?? '');
      }
      oauthPollRef.current = setInterval(async () => {
        try {
          const result = await pollAuth();
          if (result.status === 'complete') {
            if (oauthPollRef.current) clearInterval(oauthPollRef.current);
            oauthPollRef.current = null;
            setOauthPending(false);
            const after = await getAuthStatus().catch(() => null);
            setProvider(resolveAuthProvider(after?.provider));
            setView('connected');
          } else if (result.status === 'expired' || result.status === 'error') {
            if (oauthPollRef.current) clearInterval(oauthPollRef.current);
            oauthPollRef.current = null;
            setOauthPending(false);
            setTestMessage(result.error ?? (result.status === 'expired' ? 'Login code expired — try again' : 'OAuth failed'));
          }
        } catch {
          // keep polling
        }
      }, 5000);
    } catch (err) {
      setOauthPending(false);
      setTestStatus('error');
      setTestMessage(err instanceof Error ? err.message : 'OAuth start failed.');
    }
  };

  useEffect(() => {
    if (!minimized) {
      scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
    }
  }, [chatSession.messages, minimized]);

  const send = (text: string) => {
    const q = text.trim();
    if (!q || chatSession.sending) return;
    setInput('');
    setCollapsedInput('');
    void chatSession.send(q);
  };

  if (minimized) {
    return (
      <div className="relative flex h-14 shrink-0 items-center border-t border-slate-200 bg-slate-50/80 backdrop-blur-sm transition-all duration-300 shadow-[0_-1px_0_rgba(15,23,42,0.02)]">
        <form
          onClick={() => onMinimize()}
          onSubmit={e => {
            e.preventDefault();
            if (collapsedInput.trim()) {
              onMinimize();
              setTimeout(() => send(collapsedInput), 250);
            }
          }}
          className="mx-auto flex w-full max-w-4xl items-center gap-3 px-6"
        >
          <span className="text-[11px] font-semibold uppercase tracking-[0.12em] text-slate-400">PARSE AI</span>
          <div className="h-4 w-px bg-slate-200" />
          {chatSession.sending ? (
            <div className="flex flex-1 items-center gap-1.5 text-[13px] text-slate-500" aria-live="polite" aria-label="PARSE AI is thinking">
              <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-slate-400 [animation-delay:-0.3s]" />
              <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-slate-400 [animation-delay:-0.15s]" />
              <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-slate-400" />
              <span className="ml-1.5 font-medium">Thinking…</span>
            </div>
          ) : (
            <input
              value={collapsedInput}
              onChange={e => setCollapsedInput(e.target.value)}
              onClick={e => e.stopPropagation()}
              onFocus={() => onMinimize()}
              placeholder={`Ask PARSE AI about ${conceptName} (#${conceptId})…`}
              className="flex-1 bg-transparent text-[13px] text-slate-700 placeholder:text-slate-400 focus:outline-none"
            />
          )}
          <button
            type="submit"
            onClick={e => e.stopPropagation()}
            disabled={chatSession.sending}
            className="grid h-8 w-8 place-items-center rounded-md text-slate-400 transition hover:bg-slate-200/60 hover:text-slate-700 disabled:opacity-40"
            title="Send"
          >
            <Send className="h-3.5 w-3.5" />
          </button>
        </form>
      </div>
    );
  }

  return (
    <div
      className="relative flex flex-col overflow-hidden border-t-2 border-slate-200 bg-indigo-50/40 backdrop-blur-md transition-[height] duration-300 ease-[cubic-bezier(0.22,1,0.36,1)] shadow-[0_-12px_40px_-12px_rgba(15,23,42,0.18)]"
      style={{ height }}
    >
      <div onMouseDown={onResizeStart} className="group absolute inset-x-0 top-0 z-10 flex h-2.5 cursor-ns-resize items-center justify-center">
        <div className="h-1 w-12 rounded-full bg-slate-300 transition group-hover:bg-slate-500" />
      </div>

      <div className="flex shrink-0 items-center justify-between border-b border-slate-200/70 px-6 pt-4 pb-3">
        <div className="flex items-center gap-3">
          <div>
            <div className="flex items-center gap-2">
              <div className="text-[13px] font-semibold tracking-tight text-slate-900">PARSE AI</div>
              {isConnected && provider && (
                <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium ring-1 ${PROVIDER_META[provider].badgeClass}`}>
                  <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
                  Connected to {PROVIDER_META[provider].label}
                </span>
              )}
            </div>
            <div className="mt-0.5 text-[11px] text-slate-500">
              {isConnected && provider ? (
                <>
                  Model: <span className="font-mono text-slate-600">{PROVIDER_META[provider].model}</span>
                  {hasData && (
                    <>
                      <span className="mx-1.5 text-slate-300">•</span>
                      Asking about <span className="font-semibold text-slate-700">{conceptName}</span>
                      <span className="font-mono text-slate-400"> (#{conceptId})</span>
                      <span className="mx-1.5 text-slate-300">•</span>
                      {speakerCount} speakers
                    </>
                  )}
                </>
              ) : (
                <>Not connected — choose a provider to begin</>
              )}
            </div>
          </div>
        </div>
        <div className="flex items-center gap-1">
          {isConnected && (
            <>
              <button
                onClick={() => setView('welcome')}
                className="rounded-md px-2 py-1 text-[11px] font-medium text-slate-500 transition hover:bg-white/70 hover:text-slate-800"
                title="Switch provider"
              >
                Switch provider
              </button>
              <button
                onClick={handleDisconnect}
                className="rounded-md px-2 py-1 text-[11px] font-medium text-slate-500 transition hover:bg-white/70 hover:text-rose-600"
                title="Disconnect"
              >
                Disconnect
              </button>
              <div className="mx-1 h-4 w-px bg-slate-200" />
            </>
          )}
          <button
            onClick={onMinimize}
            title="Minimize"
            className="grid h-7 w-7 place-items-center rounded-md text-slate-400 hover:bg-white/60 hover:text-slate-700"
          >
            <ChevronDown className="h-4 w-4" />
          </button>
        </div>
      </div>

      {view === 'welcome' && (
        <div className="flex-1 overflow-y-auto px-6 py-8">
          <div className="mx-auto max-w-2xl">
            <div className="mb-6 text-center">
              <div className="mx-auto mb-3 grid h-10 w-10 place-items-center rounded-full bg-slate-900 text-white">
                <Sparkles className="h-5 w-5" />
              </div>
              <h2 className="text-[18px] font-semibold tracking-tight text-slate-900">Connect PARSE AI</h2>
              <p className="mx-auto mt-2 max-w-md text-[13px] leading-relaxed text-slate-500">
                To use PARSE AI for analysis, cognate suggestions, and decision support,
                connect one of the supported providers.
              </p>
            </div>

            <div className="grid gap-3 sm:grid-cols-2">
              <button
                onClick={() => goToProviderForm('xai')}
                className="group flex flex-col items-start gap-3 rounded-xl border border-slate-200 bg-white p-5 text-left transition hover:border-slate-400 hover:shadow-[0_4px_16px_-4px_rgba(15,23,42,0.12)]"
              >
                <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-slate-900 text-white">
                  <Zap className="h-4 w-4" />
                </div>
                <div>
                  <div className="text-[13px] font-semibold text-slate-900">xAI / Grok</div>
                  <div className="mt-0.5 text-[11px] leading-relaxed text-slate-500">
                    Sign in with your xAI account to use Grok reasoning models.
                  </div>
                </div>
                <span className="mt-auto inline-flex items-center gap-1.5 rounded-lg bg-slate-900 px-3 py-1.5 text-[11px] font-semibold text-white transition group-hover:bg-slate-700">
                  Connect with xAI Account
                </span>
              </button>

              <button
                onClick={() => goToProviderForm('openai')}
                className="group flex flex-col items-start gap-3 rounded-xl border border-slate-200 bg-white p-5 text-left transition hover:border-slate-400 hover:shadow-[0_4px_16px_-4px_rgba(15,23,42,0.12)]"
              >
                <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-slate-900 text-white">
                  <KeyRound className="h-4 w-4" />
                </div>
                <div>
                  <div className="text-[13px] font-semibold text-slate-900">OpenAI API</div>
                  <div className="mt-0.5 text-[11px] leading-relaxed text-slate-500">
                    Use your own OpenAI API key or sign in with Codex.
                  </div>
                </div>
                <span className="mt-auto inline-flex items-center gap-1.5 rounded-lg bg-white px-3 py-1.5 text-[11px] font-semibold text-slate-900 ring-1 ring-slate-300 transition group-hover:bg-slate-50">
                  Use OpenAI API Key
                </span>
              </button>
            </div>

            <div className="mt-5 flex items-center justify-center gap-1.5 text-[11px] text-slate-400">
              <ShieldCheck className="h-3.5 w-3.5" />
              Your API keys are stored securely in the browser and never sent to our servers.
            </div>
          </div>
        </div>
      )}

      {(view === 'form-xai' || view === 'form-openai') && (
        <div className="flex-1 overflow-y-auto px-6 py-8">
          <div className="mx-auto max-w-md">
            <button onClick={backToWelcome} className="mb-4 inline-flex items-center gap-1 text-[11px] font-medium text-slate-500 transition hover:text-slate-900">
              <ArrowLeft className="h-3.5 w-3.5" /> Back
            </button>

            <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-[0_1px_0_rgba(15,23,42,0.03)]">
              <div className="mb-4">
                <div className="text-[13px] font-semibold text-slate-900">
                  Connect to {view === 'form-xai' ? 'xAI / Grok' : 'OpenAI'}
                </div>
                <div className="mt-0.5 text-[11px] text-slate-500">
                  {view === 'form-xai'
                    ? 'Authenticate with your xAI account to enable Grok models.'
                    : 'Paste your API key or sign in with Codex OAuth.'}
                </div>
              </div>

              {view === 'form-xai' && (
                <div className="space-y-3">
                  <label className="block">
                    <span className="text-[11px] font-medium text-slate-600">xAI API Key</span>
                    <input
                      type="password"
                      value={apiKey}
                      onChange={e => {
                        setApiKey(e.target.value);
                        setTestStatus('idle');
                      }}
                      placeholder="xai-..."
                      className="mt-1 w-full rounded-lg border border-slate-200 bg-slate-50/60 px-3 py-2 font-mono text-[12px] text-slate-800 placeholder:text-slate-400 focus:border-slate-400 focus:bg-white focus:outline-none focus:ring-2 focus:ring-slate-100"
                    />
                  </label>
                  <div className="flex items-center gap-2">
                    <button
                      onClick={handleTestConnection}
                      disabled={!apiKey.trim() || testStatus === 'testing'}
                      className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-[11px] font-semibold text-slate-700 transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      {testStatus === 'testing' && <Loader2 className="h-3 w-3 animate-spin" />}
                      {testStatus === 'success' && <CheckCircle2 className="h-3 w-3 text-emerald-600" />}
                      {testStatus === 'error' && <AlertCircle className="h-3 w-3 text-rose-600" />}
                      Test Connection
                    </button>
                    <button
                      onClick={() => handleConnect('xai')}
                      disabled={!apiKey.trim()}
                      className="inline-flex items-center gap-1.5 rounded-lg bg-slate-900 px-3 py-1.5 text-[11px] font-semibold text-white transition hover:bg-slate-700 disabled:cursor-not-allowed disabled:bg-slate-300"
                    >
                      <Zap className="h-3.5 w-3.5" /> Connect
                    </button>
                  </div>
                  {testMessage && (
                    <div className={`text-[11px] ${testStatus === 'success' ? 'text-emerald-600' : 'text-rose-600'}`}>
                      {testMessage}
                    </div>
                  )}
                </div>
              )}

              {view === 'form-openai' && (
                <div className="space-y-3">
                  <label className="block">
                    <span className="text-[11px] font-medium text-slate-600">OpenAI API Key</span>
                    <input
                      type="password"
                      value={apiKey}
                      onChange={e => {
                        setApiKey(e.target.value);
                        setTestStatus('idle');
                      }}
                      placeholder="sk-..."
                      className="mt-1 w-full rounded-lg border border-slate-200 bg-slate-50/60 px-3 py-2 font-mono text-[12px] text-slate-800 placeholder:text-slate-400 focus:border-slate-400 focus:bg-white focus:outline-none focus:ring-2 focus:ring-slate-100"
                    />
                  </label>

                  <div className="flex items-center gap-2">
                    <button
                      onClick={handleTestConnection}
                      disabled={!apiKey.trim() || testStatus === 'testing'}
                      className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-[11px] font-semibold text-slate-700 transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      {testStatus === 'testing' && <Loader2 className="h-3 w-3 animate-spin" />}
                      {testStatus === 'success' && <CheckCircle2 className="h-3 w-3 text-emerald-600" />}
                      {testStatus === 'error' && <AlertCircle className="h-3 w-3 text-rose-600" />}
                      Test Connection
                    </button>
                    <button
                      onClick={() => handleConnect('openai')}
                      disabled={!apiKey.trim()}
                      className="inline-flex items-center gap-1.5 rounded-lg bg-slate-900 px-3 py-1.5 text-[11px] font-semibold text-white transition hover:bg-slate-700 disabled:cursor-not-allowed disabled:bg-slate-300"
                    >
                      Save Key
                    </button>
                  </div>

                  {testMessage && (
                    <div className={`text-[11px] ${testStatus === 'success' ? 'text-emerald-600' : 'text-rose-600'}`}>
                      {testMessage}
                    </div>
                  )}

                  <div className="flex items-center gap-3 py-1">
                    <div className="h-px flex-1 bg-slate-200" />
                    <span className="text-[10px] uppercase tracking-wider text-slate-400">or</span>
                    <div className="h-px flex-1 bg-slate-200" />
                  </div>

                  <button
                    onClick={handleCodexSignIn}
                    disabled={oauthPending}
                    className="inline-flex w-full items-center justify-center gap-2 rounded-lg border border-slate-300 bg-white px-4 py-2.5 text-[12px] font-semibold text-slate-800 transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {oauthPending ? 'Waiting for sign-in...' : 'Sign in with Codex'}
                  </button>
                  {oauthPending && oauthCode && (
                    <div className="mt-3 rounded-lg border border-slate-200 bg-slate-50 p-4 text-center">
                      <div className="text-[11px] text-slate-500 mb-1">Enter this code:</div>
                      <div className="text-lg font-mono font-bold tracking-widest text-slate-900">
                        {oauthCode}
                      </div>
                      {oauthUri && (
                        <a href={oauthUri} target="_blank" rel="noreferrer" className="mt-1 block text-[11px] text-indigo-600 hover:underline">
                          {oauthUri}
                        </a>
                      )}
                      <div className="mt-2 text-[10px] text-slate-400">Waiting for confirmation...</div>
                    </div>
                  )}
                </div>
              )}
            </div>

            <div className="mt-4 flex items-center justify-center gap-1.5 text-[11px] text-slate-400">
              <ShieldCheck className="h-3.5 w-3.5" />
              Keys are saved to your local server config.
            </div>
          </div>
        </div>
      )}

      {view === 'connected' && (
        <>
          <div ref={scrollRef} className="flex-1 overflow-y-auto px-6 py-4">
            <div className="mx-auto max-w-3xl space-y-3">
              {chatSession.messages.length === 0 && !chatSession.sending && messages.length > 0 && messages.map(m => (
                <div key={m.id} className="flex justify-start">
                  <div className="max-w-[78%] rounded-2xl bg-white px-4 py-2.5 text-[13px] leading-relaxed text-slate-800 ring-1 ring-slate-200/70 shadow-sm">
                    <ChatMarkdown content={m.content} />
                  </div>
                </div>
              ))}
              {chatSession.messages.map((m, i) => (
                <div key={`${m.timestamp}-${i}`} className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                  <div className={`max-w-[78%] rounded-2xl px-4 py-2.5 text-[13px] leading-relaxed ${
                    m.role === 'user'
                      ? 'bg-slate-900 text-white'
                      : 'bg-white text-slate-800 ring-1 ring-slate-200/70 shadow-sm'
                  }`}>
                    {m.role === 'assistant' ? <ChatMarkdown content={m.content} /> : m.content}
                    {chatSession.sending && i === chatSession.messages.length - 1 && m.role === 'assistant' && (
                      <span className="ml-0.5 inline-block h-3.5 w-[2px] translate-y-0.5 animate-pulse bg-slate-500" />
                    )}
                  </div>
                </div>
              ))}
              {chatSession.sending &&
                (chatSession.messages.length === 0 ||
                  chatSession.messages[chatSession.messages.length - 1].role === 'user') && (
                  <div className="flex justify-start" aria-live="polite" aria-label="PARSE AI is thinking">
                    <div className="flex max-w-[78%] items-center gap-1.5 rounded-2xl bg-white px-4 py-3 ring-1 ring-slate-200/70 shadow-sm">
                      <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-slate-400 [animation-delay:-0.3s]" />
                      <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-slate-400 [animation-delay:-0.15s]" />
                      <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-slate-400" />
                      <span className="ml-1.5 text-[12px] font-medium text-slate-500">Thinking…</span>
                    </div>
                  </div>
                )}
            </div>
          </div>

          {chatSession.error && (
            <div className="shrink-0 px-6 py-2">
              <div className="mx-auto max-w-3xl rounded-lg border border-rose-200 bg-rose-50 px-4 py-2.5 text-[12px] text-rose-700">
                <span className="font-semibold">Error:</span> {chatSession.error}
              </div>
            </div>
          )}

          <div className="shrink-0 border-t border-slate-200/70 bg-white/50 px-6 py-3 backdrop-blur-sm">
            <div className="mx-auto max-w-3xl">
              <div className="mb-2 flex flex-wrap gap-1.5">
                {QUICK_ACTIONS.map(a => (
                  <button
                    key={a}
                    onClick={() => send(a)}
                    className="rounded-full border border-slate-200 bg-white px-3 py-1 text-[11px] font-medium text-slate-600 transition hover:border-slate-300 hover:bg-slate-50 hover:text-slate-900"
                  >
                    {a}
                  </button>
                ))}
              </div>
              <form
                onSubmit={e => {
                  e.preventDefault();
                  send(input);
                }}
                className="flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-3 py-2 focus-within:border-slate-400 focus-within:ring-2 focus-within:ring-slate-100"
              >
                <input
                  value={input}
                  onChange={e => setInput(e.target.value)}
                  placeholder={hasData ? `Ask PARSE AI about ${conceptName}…` : 'Ask PARSE AI anything to get started…'}
                  className="flex-1 bg-transparent text-[13px] text-slate-800 placeholder:text-slate-400 focus:outline-none"
                  autoFocus
                />
                <button
                  type="submit"
                  disabled={!input.trim()}
                  className="inline-flex items-center gap-1 rounded-lg bg-slate-900 px-3 py-1.5 text-[11px] font-semibold text-white transition hover:bg-slate-700 disabled:cursor-not-allowed disabled:bg-slate-300"
                >
                  Send <Send className="h-3 w-3" />
                </button>
              </form>
            </div>
          </div>
        </>
      )}
    </div>
  );
};
