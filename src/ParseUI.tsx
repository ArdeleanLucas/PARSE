import React, { useState, useMemo, useRef, useEffect } from 'react';
import {
  Search, ChevronLeft, ChevronRight, Check, Flag, Split, GitMerge,
  RotateCw, Play, RefreshCw, Save, Upload,
  Layers, ChevronDown, ChevronUp, Plus, X, AlertCircle,
  CheckCircle2, ArrowUpDown, Volume2, Filter, Send,
  Database, Users as UsersIcon, Cpu, KeyRound, Loader2, ArrowLeft, ShieldCheck, Zap, Sparkles,
  PanelRightClose, Tag, Tags, Import, AudioLines, Type, Mic,
  Workflow, Network, Trash2, ChevronDown as CDown,
  Video, Scissors, Activity, SlidersHorizontal, Download,
  Pause, SkipBack, SkipForward, ZoomIn, ZoomOut, MessageSquare, Anchor,
  Sun, Moon, XCircle
} from 'lucide-react';
import type { AnnotationInterval, AnnotationRecord, Tag as StoreTag } from './api/types';
import { getLingPyExport, saveApiKey, getAuthStatus, pollAuth, startAuthFlow, startSTT, startCompute, startNormalize, pollSTT, pollNormalize, pollCompute } from './api/client';
import { useChatSession, type UseChatSessionResult } from './hooks/useChatSession';
import { useSpectrogram } from './hooks/useSpectrogram';
import { useWaveSurfer } from './hooks/useWaveSurfer';
import { useAnnotationStore } from './stores/annotationStore';
import { useAnnotationSync } from './hooks/useAnnotationSync';
import { useComputeJob } from './hooks/useComputeJob';
import { useActionJob, formatEta } from './hooks/useActionJob';
import type { PollResult } from './hooks/useActionJob';
import { useConfigStore } from './stores/configStore';
import { useEnrichmentStore } from './stores/enrichmentStore';
import { usePlaybackStore } from './stores/playbackStore';
import { useTagStore } from './stores/tagStore';
import { useUIStore } from './stores/uiStore';
import { Modal } from './components/shared/Modal';
import { ChatMarkdown } from './components/shared/ChatMarkdown';
import { SpeakerImport } from './components/compare/SpeakerImport';

type TagState = 'all' | 'untagged' | 'review' | 'confirmed' | 'problematic';
type ConceptTag = 'untagged' | 'review' | 'confirmed' | 'problematic';
type ModeTab = 'all' | 'unreviewed' | 'flagged' | 'borrowings';
type AppMode = 'annotate' | 'compare' | 'tags';

interface LingTag {
  id: string; name: string; color: string; dotClass: string; count: number;
}

interface Concept {
  id: number;
  key: string;
  name: string;
  tag: ConceptTag;
}

interface SpeakerForm {
  speaker: string; ipa: string; utterances: number;
  arabicSim: number; persianSim: number;
  cognate: 'A' | 'B' | 'C' | '—'; flagged: boolean;
}

// No fallback data — workspace must supply real speakers and concepts via /api/config.

const tagDot: Record<ConceptTag, string> = {
  untagged: 'bg-slate-300', review: 'bg-amber-400',
  confirmed: 'bg-emerald-500', problematic: 'bg-rose-500',
};
const simColor = (v: number) =>
  v >= 0.8 ? 'text-emerald-600' : v >= 0.5 ? 'text-amber-600' : 'text-slate-400';
const simBar = (v: number) =>
  v >= 0.8 ? 'bg-emerald-500' : v >= 0.5 ? 'bg-amber-400' : 'bg-slate-300';

const REVIEW_TAG_IDS = new Set(['review', 'review-needed']);
const COMPARE_NOTES_STORAGE_KEY = 'parseui-compare-notes-v1';

function overlaps(a: AnnotationInterval, b: AnnotationInterval): boolean {
  return a.start <= b.end && b.start <= a.end;
}


function conceptMatchesIntervalText(concept: Concept, text: string): boolean {
  const normalizedText = text.trim().toLowerCase();
  const normalizedName = concept.name.trim().toLowerCase();
  const normalizedKey = concept.key.trim().toLowerCase();

  return normalizedText === normalizedName
    || normalizedText === normalizedKey
    || normalizedText.includes(normalizedName);
}

function getConceptStatus(tags: StoreTag[]): ConceptTag {
  if (tags.some((tag) => tag.id === 'problematic')) return 'problematic';
  if (tags.some((tag) => tag.id === 'confirmed')) return 'confirmed';
  if (tags.some((tag) => REVIEW_TAG_IDS.has(tag.id))) return 'review';
  return 'untagged';
}

function findAnnotationForConcept(record: AnnotationRecord | null | undefined, concept: Concept) {
  if (!record) {
    return { conceptInterval: null, ipaInterval: null, orthoInterval: null };
  }

  const conceptIntervals = record.tiers.concept?.intervals ?? [];
  const conceptInterval = conceptIntervals.find((interval) => conceptMatchesIntervalText(concept, interval.text)) ?? null;

  if (!conceptInterval) {
    return { conceptInterval: null, ipaInterval: null, orthoInterval: null };
  }

  const ipaInterval = (record.tiers.ipa?.intervals ?? []).find((interval) => overlaps(interval, conceptInterval)) ?? null;
  const orthoInterval = (record.tiers.ortho?.intervals ?? []).find((interval) => overlaps(interval, conceptInterval)) ?? null;

  return { conceptInterval, ipaInterval, orthoInterval };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function buildSpeakerForm(
  record: AnnotationRecord | null | undefined,
  concept: Concept,
  speaker: string,
  enrichments: Record<string, unknown>,
  flagged: boolean,
): SpeakerForm {
  const conceptIntervals = (record?.tiers.concept?.intervals ?? []).filter((interval) => conceptMatchesIntervalText(concept, interval.text));
  const ipaIntervals = record?.tiers.ipa?.intervals ?? [];
  const matchingIpaIntervals = ipaIntervals.filter((ipaInterval) => conceptIntervals.some((conceptInterval) => overlaps(ipaInterval, conceptInterval)));

  const similarityRoot = isRecord(enrichments.similarity) ? enrichments.similarity : null;
  const conceptSimilarity = similarityRoot && isRecord(similarityRoot[concept.key]) ? similarityRoot[concept.key] as Record<string, unknown> : null;
  const speakerSimilarity = conceptSimilarity && isRecord(conceptSimilarity[speaker]) ? conceptSimilarity[speaker] as Record<string, unknown> : null;
  const arabicSim = typeof speakerSimilarity?.ar === 'number' ? speakerSimilarity.ar : 0;
  const persianSim = typeof speakerSimilarity?.tr === 'number' ? speakerSimilarity.tr : 0;

  const cognateSets = isRecord(enrichments.cognate_sets) ? enrichments.cognate_sets : null;
  const conceptCognates = cognateSets && isRecord(cognateSets[concept.key]) ? cognateSets[concept.key] as Record<string, unknown> : null;
  let cognate: SpeakerForm['cognate'] = '—';
  if (conceptCognates) {
    for (const [group, members] of Object.entries(conceptCognates)) {
      if (Array.isArray(members) && members.includes(speaker) && (group === 'A' || group === 'B' || group === 'C')) {
        cognate = group;
        break;
      }
    }
  }

  return {
    speaker,
    ipa: matchingIpaIntervals[0]?.text ?? '',
    utterances: matchingIpaIntervals.length,
    arabicSim,
    persianSim,
    cognate,
    flagged,
  };
}

interface ReferenceFormDisplay {
  script: string;
  ipa: string;
  audioUrl: string | null;
  available: boolean;
}

function parseReferenceForm(raw: unknown): ReferenceFormDisplay {
  if (typeof raw === 'string') {
    return { script: '', ipa: raw.trim(), audioUrl: null, available: raw.trim().length > 0 };
  }

  if (Array.isArray(raw)) {
    return raw.length > 0 ? parseReferenceForm(raw[0]) : { script: '', ipa: '', audioUrl: null, available: false };
  }

  if (!isRecord(raw)) {
    return { script: '', ipa: '', audioUrl: null, available: false };
  }

  const script = [raw.script, raw.orthography, raw.form, raw.text].find((value) => typeof value === 'string' && value.trim().length > 0);
  const ipa = [raw.ipa, raw.phonetic, raw.transcription].find((value) => typeof value === 'string' && value.trim().length > 0);
  const audioUrl = [raw.audioUrl, raw.audio, raw.url].find((value) => typeof value === 'string' && value.trim().length > 0);

  return {
    script: typeof script === 'string' ? script : '',
    ipa: typeof ipa === 'string' ? ipa : '',
    audioUrl: typeof audioUrl === 'string' ? audioUrl : null,
    available: Boolean(script || ipa),
  };
}

function resolveReferenceForms(enrichments: Record<string, unknown>, concept: Concept) {
  const root = isRecord(enrichments.reference_forms) ? enrichments.reference_forms as Record<string, unknown> : null;
  const conceptEntry = root ? root[concept.key] ?? root[concept.name] : null;
  const conceptRecord = isRecord(conceptEntry) ? conceptEntry : {};

  return {
    arabic: parseReferenceForm(conceptRecord.ar ?? conceptRecord.arabic),
    persian: parseReferenceForm(conceptRecord.fa ?? conceptRecord.persian),
  };
}

const SimBar: React.FC<{ value: number }> = ({ value }) => (
  <div className="flex items-center gap-2">
    <div className="h-1.5 w-14 rounded-full bg-slate-100 overflow-hidden">
      <div className={`h-full rounded-full ${simBar(value)}`} style={{ width: `${value * 100}%` }} />
    </div>
    <span className={`text-xs font-mono tabular-nums ${simColor(value)}`}>{value.toFixed(2)}</span>
  </div>
);

const Pill: React.FC<{ children: React.ReactNode; tone?: 'slate'|'emerald'|'indigo' }> = ({ children, tone='slate' }) => {
  const tones: Record<string,string> = {
    slate: 'bg-slate-100 text-slate-600 ring-slate-200',
    emerald: 'bg-emerald-50 text-emerald-700 ring-emerald-200',
    indigo: 'bg-indigo-50 text-indigo-700 ring-indigo-200',
  };
  return <span className={`inline-flex items-center gap-1.5 rounded-md px-2 py-0.5 text-[11px] font-medium ring-1 ${tones[tone]}`}>{children}</span>;
};

const SectionCard: React.FC<{ title: string; aside?: React.ReactNode; children: React.ReactNode }> = ({ title, aside, children }) => (
  <section className="rounded-xl border border-slate-200/80 bg-white shadow-[0_1px_0_rgba(15,23,42,0.03)]">
    <header className="flex items-center justify-between px-5 pt-4 pb-3">
      <h3 className="text-[11px] font-semibold uppercase tracking-[0.09em] text-slate-500">{title}</h3>
      {aside}
    </header>
    <div className="px-5 pb-5">{children}</div>
  </section>
);

// ---------- AI Chat Panel ----------
interface AIChatProps {
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
  xai:    { label: 'xAI',    model: 'grok-4.2 reasoning', badgeClass: 'bg-emerald-50 text-emerald-700 ring-emerald-200' },
  openai: { label: 'OpenAI', model: 'gpt-5.4',            badgeClass: 'bg-emerald-50 text-emerald-700 ring-emerald-200' },
};

const AIChat: React.FC<AIChatProps> = ({ height, minimized, onResizeStart, onMinimize, conceptName, conceptId, speakerCount, chatSession }) => {
  // Connection state machine
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

  // Seed welcome message once connected, tailored to empty-project case
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

  // Restore auth state on mount and cleanup poll on unmount.
  useEffect(() => {
    getAuthStatus().then(s => {
      if (s.authenticated) {
        setProvider('openai');
        setView('connected');
      } else if (s.flow_active) {
        // OAuth was started before this mount (page reload mid-flow) — resume.
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
              setProvider('openai');
              setView('connected');
            } else if (result.status === 'expired' || result.status === 'error') {
              if (oauthPollRef.current) clearInterval(oauthPollRef.current);
              oauthPollRef.current = null;
              setOauthPending(false);
              setTestMessage(result.error ?? (result.status === 'expired' ? 'Login code expired — try again' : 'OAuth failed'));
            }
          } catch { /* keep polling */ }
        }, 5000);
      }
    }).catch(() => { /* leave view at welcome */ });
    return () => { if (oauthPollRef.current) clearInterval(oauthPollRef.current); };
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
            setProvider('openai');
            setView('connected');
          } else if (result.status === 'expired' || result.status === 'error') {
            if (oauthPollRef.current) clearInterval(oauthPollRef.current);
            oauthPollRef.current = null;
            setOauthPending(false);
            setTestMessage(result.error ?? (result.status === 'expired' ? 'Login code expired — try again' : 'OAuth failed'));
          }
        } catch { /* keep polling */ }
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

  // ---------- Collapsed: thin command bar ----------
  if (minimized) {
    return (
      <div
        className="relative flex h-14 shrink-0 items-center border-t border-slate-200 bg-slate-50/80 backdrop-blur-sm transition-all duration-300 shadow-[0_-1px_0_rgba(15,23,42,0.02)]"
      >
        <form
          onClick={() => onMinimize()}
          onSubmit={e => { e.preventDefault(); if (collapsedInput.trim()) { onMinimize(); setTimeout(() => send(collapsedInput), 250); } }}
          className="mx-auto flex w-full max-w-4xl items-center gap-3 px-6"
        >
          <span className="text-[11px] font-semibold uppercase tracking-[0.12em] text-slate-400">PARSE AI</span>
          <div className="h-4 w-px bg-slate-200"/>
          {chatSession.sending ? (
            <div
              className="flex flex-1 items-center gap-1.5 text-[13px] text-slate-500"
              aria-live="polite"
              aria-label="PARSE AI is thinking"
            >
              <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-slate-400 [animation-delay:-0.3s]"/>
              <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-slate-400 [animation-delay:-0.15s]"/>
              <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-slate-400"/>
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
            <Send className="h-3.5 w-3.5"/>
          </button>
        </form>
      </div>
    );
  }

  // ---------- Expanded: elevated panel ----------
  return (
    <div
      className="relative flex flex-col overflow-hidden border-t-2 border-slate-200 bg-indigo-50/40 backdrop-blur-md transition-[height] duration-300 ease-[cubic-bezier(0.22,1,0.36,1)] shadow-[0_-12px_40px_-12px_rgba(15,23,42,0.18)]"
      style={{ height }}
    >
      {/* Resize handle */}
      <div
        onMouseDown={onResizeStart}
        className="group absolute inset-x-0 top-0 z-10 flex h-2.5 cursor-ns-resize items-center justify-center"
      >
        <div className="h-1 w-12 rounded-full bg-slate-300 transition group-hover:bg-slate-500"/>
      </div>

      {/* Header */}
      <div className="flex shrink-0 items-center justify-between border-b border-slate-200/70 px-6 pt-4 pb-3">
        <div className="flex items-center gap-3">
          <div>
            <div className="flex items-center gap-2">
              <div className="text-[13px] font-semibold tracking-tight text-slate-900">PARSE AI</div>
              {isConnected && provider && (
                <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium ring-1 ${PROVIDER_META[provider].badgeClass}`}>
                  <span className="h-1.5 w-1.5 rounded-full bg-emerald-500"/>
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
              <div className="mx-1 h-4 w-px bg-slate-200"/>
            </>
          )}
          <button
            onClick={onMinimize}
            title="Minimize"
            className="grid h-7 w-7 place-items-center rounded-md text-slate-400 hover:bg-white/60 hover:text-slate-700"
          >
            <ChevronDown className="h-4 w-4"/>
          </button>
        </div>
      </div>

      {/* Body — state machine */}
      {view === 'welcome' && (
        <div className="flex-1 overflow-y-auto px-6 py-8">
          <div className="mx-auto max-w-2xl">
            <div className="mb-6 text-center">
              <div className="mx-auto mb-3 grid h-10 w-10 place-items-center rounded-full bg-slate-900 text-white">
                <Sparkles className="h-5 w-5"/>
              </div>
              <h2 className="text-[18px] font-semibold tracking-tight text-slate-900">Connect PARSE AI</h2>
              <p className="mx-auto mt-2 max-w-md text-[13px] leading-relaxed text-slate-500">
                To use PARSE AI for analysis, cognate suggestions, and decision support,
                connect one of the supported providers.
              </p>
            </div>

            <div className="grid gap-3 sm:grid-cols-2">
              {/* xAI card */}
              <button
                onClick={() => goToProviderForm('xai')}
                className="group flex flex-col items-start gap-3 rounded-xl border border-slate-200 bg-white p-5 text-left transition hover:border-slate-400 hover:shadow-[0_4px_16px_-4px_rgba(15,23,42,0.12)]"
              >
                <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-slate-900 text-white">
                  <Zap className="h-4 w-4"/>
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

              {/* OpenAI card */}
              <button
                onClick={() => goToProviderForm('openai')}
                className="group flex flex-col items-start gap-3 rounded-xl border border-slate-200 bg-white p-5 text-left transition hover:border-slate-400 hover:shadow-[0_4px_16px_-4px_rgba(15,23,42,0.12)]"
              >
                <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-slate-900 text-white">
                  <KeyRound className="h-4 w-4"/>
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
              <ShieldCheck className="h-3.5 w-3.5"/>
              Your API keys are stored securely in the browser and never sent to our servers.
            </div>
          </div>
        </div>
      )}

      {(view === 'form-xai' || view === 'form-openai') && (
        <div className="flex-1 overflow-y-auto px-6 py-8">
          <div className="mx-auto max-w-md">
            <button
              onClick={backToWelcome}
              className="mb-4 inline-flex items-center gap-1 text-[11px] font-medium text-slate-500 transition hover:text-slate-900"
            >
              <ArrowLeft className="h-3.5 w-3.5"/> Back
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
                      onChange={e => { setApiKey(e.target.value); setTestStatus('idle'); }}
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
                      {testStatus === 'testing' && <Loader2 className="h-3 w-3 animate-spin"/>}
                      {testStatus === 'success' && <CheckCircle2 className="h-3 w-3 text-emerald-600"/>}
                      {testStatus === 'error' && <AlertCircle className="h-3 w-3 text-rose-600"/>}
                      Test Connection
                    </button>
                    <button
                      onClick={() => handleConnect('xai')}
                      disabled={!apiKey.trim()}
                      className="inline-flex items-center gap-1.5 rounded-lg bg-slate-900 px-3 py-1.5 text-[11px] font-semibold text-white transition hover:bg-slate-700 disabled:cursor-not-allowed disabled:bg-slate-300"
                    >
                      <Zap className="h-3.5 w-3.5"/> Connect
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
                      onChange={e => { setApiKey(e.target.value); setTestStatus('idle'); }}
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
                      {testStatus === 'testing' && <Loader2 className="h-3 w-3 animate-spin"/>}
                      {testStatus === 'success' && <CheckCircle2 className="h-3 w-3 text-emerald-600"/>}
                      {testStatus === 'error' && <AlertCircle className="h-3 w-3 text-rose-600"/>}
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
                    <div className="h-px flex-1 bg-slate-200"/>
                    <span className="text-[10px] uppercase tracking-wider text-slate-400">or</span>
                    <div className="h-px flex-1 bg-slate-200"/>
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
                        <a href={oauthUri} target="_blank" rel="noreferrer"
                           className="mt-1 block text-[11px] text-indigo-600 hover:underline">
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
              <ShieldCheck className="h-3.5 w-3.5"/>
              Keys are saved to your local server config.
            </div>
          </div>
        </div>
      )}

      {view === 'connected' && (
        <>
          {/* Messages */}
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
                      <span className="ml-0.5 inline-block h-3.5 w-[2px] translate-y-0.5 animate-pulse bg-slate-500"/>
                    )}
                  </div>
                </div>
              ))}
              {chatSession.sending &&
                (chatSession.messages.length === 0 ||
                  chatSession.messages[chatSession.messages.length - 1].role === 'user') && (
                  <div className="flex justify-start" aria-live="polite" aria-label="PARSE AI is thinking">
                    <div className="flex max-w-[78%] items-center gap-1.5 rounded-2xl bg-white px-4 py-3 ring-1 ring-slate-200/70 shadow-sm">
                      <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-slate-400 [animation-delay:-0.3s]"/>
                      <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-slate-400 [animation-delay:-0.15s]"/>
                      <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-slate-400"/>
                      <span className="ml-1.5 text-[12px] font-medium text-slate-500">Thinking…</span>
                    </div>
                  </div>
                )}
            </div>
          </div>

          {/* Error display */}
          {chatSession.error && (
            <div className="shrink-0 px-6 py-2">
              <div className="mx-auto max-w-3xl rounded-lg border border-rose-200 bg-rose-50 px-4 py-2.5 text-[12px] text-rose-700">
                <span className="font-semibold">Error:</span> {chatSession.error}
              </div>
            </div>
          )}

          {/* Quick actions + input */}
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
                onSubmit={e => { e.preventDefault(); send(input); }}
                className="flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-3 py-2 focus-within:border-slate-400 focus-within:ring-2 focus-within:ring-slate-100"
              >
                <input
                  value={input}
                  onChange={e => setInput(e.target.value)}
                  placeholder={hasData ? `Ask PARSE AI about ${conceptName}…` : `Ask PARSE AI anything to get started…`}
                  className="flex-1 bg-transparent text-[13px] text-slate-800 placeholder:text-slate-400 focus:outline-none"
                  autoFocus
                />
                <button
                  type="submit"
                  disabled={!input.trim()}
                  className="inline-flex items-center gap-1 rounded-lg bg-slate-900 px-3 py-1.5 text-[11px] font-semibold text-white transition hover:bg-slate-700 disabled:cursor-not-allowed disabled:bg-slate-300"
                >
                  Send <Send className="h-3 w-3"/>
                </button>
              </form>
            </div>
          </div>
        </>
      )}
    </div>
  );
};

// ---------- Manage Tags View ----------
interface ManageTagsProps {
  tags: LingTag[];
  concepts: Concept[];
  onCreateTag: (name: string, color: string) => void;
  tagSearch: string; setTagSearch: (s: string) => void;
  newTagName: string; setNewTagName: (s: string) => void;
  newTagColor: string; setNewTagColor: (s: string) => void;
  showUntagged: boolean; setShowUntagged: (b: boolean) => void;
  selectedTagId: string | null; setSelectedTagId: (s: string | null) => void;
  conceptSearch: string; setConceptSearch: (s: string) => void;
  tagConcept: (tagId: string, conceptKey: string) => void;
  untagConcept: (tagId: string, conceptKey: string) => void;
}

const SWATCHES = ['#6366f1','#10b981','#f59e0b','#f43f5e','#8b5cf6','#06b6d4','#ec4899','#64748b'];

const ManageTagsView: React.FC<ManageTagsProps> = ({
  tags, concepts, onCreateTag, tagSearch, setTagSearch, newTagName, setNewTagName,
  newTagColor, setNewTagColor, showUntagged, setShowUntagged,
  selectedTagId, setSelectedTagId, conceptSearch, setConceptSearch,
  tagConcept, untagConcept,
}) => {
  const [checkedConceptIds, setCheckedConceptIds] = useState<Set<string>>(new Set());
  const filteredTags = tags.filter(t => t.name.toLowerCase().includes(tagSearch.toLowerCase()));
  const selectedTag = tags.find(t => t.id === selectedTagId);
  const filteredConcepts = concepts.filter(c => c.name.toLowerCase().includes(conceptSearch.toLowerCase()));

  return (
    <div className="flex flex-1 min-h-0 bg-slate-50">
      {/* LEFT: tags panel */}
      <div className="w-[360px] shrink-0 overflow-y-auto border-r border-slate-200 bg-white">
        <div className="p-6">
          <h2 className="text-[11px] font-semibold uppercase tracking-[0.12em] text-slate-500">Linguistic tags</h2>
          <p className="mt-1 text-xs text-slate-400">Organize concepts by review state, borrowing, or custom labels.</p>

          <div className="relative mt-5">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-slate-400"/>
            <input
              value={tagSearch}
              onChange={e => setTagSearch(e.target.value)}
              placeholder="Filter tags…"
              className="w-full rounded-lg border border-slate-200 bg-slate-50/60 py-2 pl-9 pr-3 text-xs text-slate-700 placeholder:text-slate-400 focus:border-indigo-300 focus:bg-white focus:outline-none focus:ring-2 focus:ring-indigo-100"
            />
          </div>

          {/* Create new tag */}
          <div className="mt-4 rounded-xl border border-slate-200 bg-slate-50/40 p-3">
            <div className="text-[10px] font-semibold uppercase tracking-wider text-slate-500">Create tag</div>
            <div className="mt-2 flex items-center gap-2">
              <input
                value={newTagName}
                onChange={e => setNewTagName(e.target.value)}
                placeholder="New tag name…"
                className="flex-1 rounded-md border border-slate-200 bg-white px-2.5 py-1.5 text-xs text-slate-700 placeholder:text-slate-400 focus:border-indigo-300 focus:outline-none focus:ring-2 focus:ring-indigo-100"
              />
              <div className="relative">
                <div
                  className="h-7 w-7 rounded-md ring-2 ring-white"
                  style={{ background: newTagColor, boxShadow: '0 0 0 1px rgb(226 232 240)' }}
                />
              </div>
            </div>
            <div className="mt-2 flex gap-1.5">
              {SWATCHES.map(c => (
                <button
                  key={c}
                  onClick={() => setNewTagColor(c)}
                  className={`h-5 w-5 rounded-full transition ${newTagColor===c ? 'ring-2 ring-offset-1 ring-slate-400' : 'ring-1 ring-slate-200 hover:scale-110'}`}
                  style={{ background: c }}
                />
              ))}
            </div>
            <button
              onClick={() => onCreateTag(newTagName, newTagColor)}
              disabled={!newTagName.trim()}
              className="mt-3 inline-flex w-full items-center justify-center gap-1.5 rounded-md bg-indigo-600 py-1.5 text-[11px] font-semibold text-white hover:bg-indigo-700 disabled:cursor-not-allowed disabled:bg-slate-200"
            >
              <Plus className="h-3 w-3"/> Create
            </button>
          </div>

          {/* Toggle */}
          <div className="mt-5 flex items-center justify-between rounded-lg bg-slate-50 px-3 py-2">
            <span className="text-xs font-medium text-slate-700">Show untagged</span>
            <button
              onClick={() => setShowUntagged(!showUntagged)}
              className={`relative h-5 w-9 rounded-full transition ${showUntagged ? 'bg-indigo-600' : 'bg-slate-300'}`}
            >
              <span className={`absolute top-0.5 h-4 w-4 rounded-full bg-white shadow transition-all ${showUntagged ? 'left-4' : 'left-0.5'}`}/>
            </button>
          </div>

          {/* Tag list */}
          <div className="mt-5">
            <div className="text-[10px] font-semibold uppercase tracking-wider text-slate-500">Tags · {filteredTags.length}</div>
            <div className="mt-2 space-y-1">
              {filteredTags.map(t => {
                const active = selectedTagId === t.id;
                return (
                  <button
                    key={t.id}
                    onClick={() => setSelectedTagId(t.id)}
                    className={`group flex w-full items-center gap-3 rounded-lg px-3 py-2 text-left transition ${active ? 'bg-indigo-50 ring-1 ring-indigo-200' : 'hover:bg-slate-50'}`}
                  >
                    <span className="h-2.5 w-2.5 rounded-full ring-2 ring-white" style={{ background: t.color, boxShadow: '0 0 0 1px rgb(226 232 240)' }}/>
                    <span className={`flex-1 text-[13px] ${active ? 'font-semibold text-indigo-900' : 'font-medium text-slate-700'}`}>{t.name}</span>
                    <span className="rounded-md bg-slate-100 px-1.5 py-0.5 font-mono text-[10px] text-slate-500">{t.count}</span>
                  </button>
                );
              })}
            </div>
          </div>
        </div>
      </div>

      {/* RIGHT: main content */}
      <div className="flex-1 overflow-y-auto">
        {!selectedTag ? (
          <div className="grid h-full place-items-center px-10 py-20">
            <div className="text-center">
              <div className="mx-auto grid h-14 w-14 place-items-center rounded-2xl bg-gradient-to-br from-indigo-50 to-violet-50 ring-1 ring-indigo-100">
                <Tag className="h-6 w-6 text-indigo-500"/>
              </div>
              <h3 className="mt-5 text-lg font-semibold text-slate-900">Select a tag to assign concepts</h3>
              <p className="mt-2 max-w-md text-sm text-slate-500">
                Choose a linguistic tag on the left to browse and bulk-assign it across your {concepts.length} concepts.
                You can also create a new tag above.
              </p>
            </div>
          </div>
        ) : (
          <div className="px-10 py-8">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <span className="h-3 w-3 rounded-full ring-2 ring-white" style={{ background: selectedTag.color, boxShadow: '0 0 0 1px rgb(226 232 240)' }}/>
                <h1 className="text-2xl font-semibold tracking-tight text-slate-900">{selectedTag.name}</h1>
                <Pill tone="indigo">{selectedTag.count} concepts</Pill>
              </div>
              <div className="flex gap-2">
                <button
                  onClick={() => setCheckedConceptIds(new Set())}
                  className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-50">
                  <X className="h-3.5 w-3.5"/> Clear selection
                </button>
                <button
                  onClick={() => {
                    if (!selectedTagId) return;
                    checkedConceptIds.forEach(id => tagConcept(selectedTagId, id));
                    setCheckedConceptIds(new Set());
                  }}
                  className="inline-flex items-center gap-1.5 rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-indigo-700">
                  <Check className="h-3.5 w-3.5"/> Apply to selected
                </button>
              </div>
            </div>

            <div className="relative mt-6">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400"/>
              <input
                value={conceptSearch}
                onChange={e => setConceptSearch(e.target.value)}
                placeholder="Search concepts to assign…"
                className="w-full rounded-xl border border-slate-200 bg-white py-2.5 pl-10 pr-4 text-sm text-slate-700 placeholder:text-slate-400 focus:border-indigo-300 focus:outline-none focus:ring-4 focus:ring-indigo-50"
              />
            </div>

            <div className="mt-6 grid grid-cols-2 gap-2 lg:grid-cols-3 xl:grid-cols-4">
              {filteredConcepts.map(c => (
                <label
                  key={c.id}
                  className="group flex cursor-pointer items-center gap-3 rounded-xl border border-slate-200 bg-white p-3 transition hover:border-indigo-300 hover:shadow-sm"
                >
                  <input
                    type="checkbox"
                    checked={checkedConceptIds.has(c.key)}
                    onChange={e => {
                      const next = new Set(checkedConceptIds);
                      if (e.target.checked) {
                        next.add(c.key);
                        if (selectedTagId) tagConcept(selectedTagId, c.key);
                      } else {
                        next.delete(c.key);
                        if (selectedTagId) untagConcept(selectedTagId, c.key);
                      }
                      setCheckedConceptIds(next);
                    }}
                    className="h-4 w-4 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
                  />
                  <span className={`h-1.5 w-1.5 rounded-full ${tagDot[c.tag]}`}/>
                  <span className="flex-1 text-sm font-medium text-slate-800">{c.name}</span>
                  <span className="font-mono text-[10px] text-slate-300">#{c.id}</span>
                </label>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

// ---------- Annotate View ----------
interface AnnotateViewProps {
  concept: Concept;
  speaker: string;
  totalConcepts: number;
  onPrev: () => void;
  onNext: () => void;
  audioUrl: string;
  peaksUrl?: string;
}

const AnnotateView: React.FC<AnnotateViewProps> = ({ concept, speaker, totalConcepts, onPrev, onNext, audioUrl, peaksUrl }) => {
  const record = useAnnotationStore(s => s.records[speaker] ?? null);
  const setInterval = useAnnotationStore(s => s.setInterval);
  const saveSpeaker = useAnnotationStore(s => s.saveSpeaker);
  const tagConcept = useTagStore(s => s.tagConcept);

  const { conceptInterval, ipaInterval, orthoInterval } = useMemo(
    () => findAnnotationForConcept(record, concept),
    [record, concept]
  );
  const [ipa, setIpa] = useState(ipaInterval?.text ?? '');
  const [ortho, setOrtho] = useState(orthoInterval?.text ?? '');
  useEffect(() => {
    setIpa(ipaInterval?.text ?? '');
    setOrtho(orthoInterval?.text ?? '');
  }, [speaker, concept.key, ipaInterval, orthoInterval]);

  const [spectroOn, setSpectroOn] = useState(false);
  const [audioReady, setAudioReady] = useState(false);
  const [activeRegion] = useState<string | null>(null);
  const [lexAnchor, setLexAnchor] = useState<'word' | 'concept'>('concept');
  const [zoom, setZoom] = useState(10); // minPxPerSec

  const containerRef = useRef<HTMLDivElement>(null);
  const spectroCanvasRef = useRef<HTMLCanvasElement | null>(null);

  const isPlaying = usePlaybackStore(s => s.isPlaying);
  const currentTime = usePlaybackStore(s => s.currentTime);
  const duration = usePlaybackStore(s => s.duration);
  const selectedRegion = usePlaybackStore(s => s.selectedRegion);
  const annotated = Boolean(conceptInterval && ipaInterval);

  const { playPause, skip, setZoom: wsSetZoom, setRate, wsRef } = useWaveSurfer({
    containerRef,
    audioUrl,
    peaksUrl,
    onTimeUpdate: t => usePlaybackStore.setState({ currentTime: t }),
    onReady: d => { usePlaybackStore.setState({ duration: d }); setAudioReady(true); },
    onPlayStateChange: p => usePlaybackStore.setState({ isPlaying: p }),
    onRegionUpdate: (start, end) => usePlaybackStore.setState({ selectedRegion: { start, end } }),
  });

  useSpectrogram({ enabled: spectroOn && audioReady, wsRef, canvasRef: spectroCanvasRef });

  const fmt = (t: number) => {
    const m = Math.floor(t / 60).toString().padStart(2, '0');
    const s = Math.floor(t % 60).toString().padStart(2, '0');
    const ms = Math.floor((t * 100) % 100).toString().padStart(2, '0');
    return `${m}:${s}.${ms}`;
  };

  return (
    <main className="flex-1 overflow-y-auto bg-slate-50">
      {/* ======= WAVEFORM / VIRTUAL TIMELINE ======= */}
      <section className="border-b border-slate-200 bg-white">
        {/* Toolbar */}
        <div className="flex items-center justify-between border-b border-slate-100 px-5 py-2.5">
          <div className="flex items-center gap-1">
            <button
              title="Previous segment"
              className="grid h-7 w-7 place-items-center rounded-md text-slate-500 hover:bg-slate-100 hover:text-slate-800"
              onClick={() => {
                const intervals = record?.tiers.concept?.intervals ?? [];
                const prev = intervals
                  .filter(iv => iv.end < currentTime - 0.1)
                  .sort((a, b) => b.end - a.end)[0];
                if (prev) {
                  skip(-(currentTime - prev.start));
                } else {
                  skip(-currentTime);
                }
              }}
            >
              <SkipBack className="h-3.5 w-3.5"/>
            </button>
            <button
              title="Next segment"
              className="grid h-7 w-7 place-items-center rounded-md text-slate-500 hover:bg-slate-100 hover:text-slate-800"
              onClick={() => {
                const intervals = record?.tiers.concept?.intervals ?? [];
                const next = intervals
                  .filter(iv => iv.start > currentTime + 0.1)
                  .sort((a, b) => a.start - b.start)[0];
                if (next) {
                  skip(next.start - currentTime);
                }
              }}
            >
              <SkipForward className="h-3.5 w-3.5"/>
            </button>
            <div className="mx-2 h-5 w-px bg-slate-200"/>
            <button onClick={() => { const z = Math.max(10, zoom - 20); setZoom(z); wsSetZoom(z); }} title="Zoom out" className="grid h-7 w-7 place-items-center rounded-md text-slate-500 hover:bg-slate-100 hover:text-slate-800">
              <ZoomOut className="h-3.5 w-3.5"/>
            </button>
            <div className="rounded bg-slate-100 px-2 py-0.5 font-mono text-[10px] text-slate-500">{zoom}px/s</div>
            <button onClick={() => { const z = Math.min(500, zoom + 20); setZoom(z); wsSetZoom(z); }} title="Zoom in" className="grid h-7 w-7 place-items-center rounded-md text-slate-500 hover:bg-slate-100 hover:text-slate-800">
              <ZoomIn className="h-3.5 w-3.5"/>
            </button>
            <div className="mx-2 h-5 w-px bg-slate-200"/>
            {/* Lexical anchor align — word vs concept alignment */}
            <div className="inline-flex items-center gap-1 rounded-md bg-slate-100 p-0.5" title="Lexical anchor align — snap regions to concept boundaries or individual word anchors">
              <Anchor className="ml-1 h-3 w-3 text-slate-400"/>
              <button onClick={() => setLexAnchor('concept')} className={`rounded px-2 py-0.5 text-[10px] font-semibold transition ${lexAnchor==='concept' ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-500'}`}>Concept</button>
              <button onClick={() => setLexAnchor('word')} className={`rounded px-2 py-0.5 text-[10px] font-semibold transition ${lexAnchor==='word' ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-500'}`}>Word</button>
            </div>
          </div>

          <div className="flex items-center gap-1.5">
            <button
              onClick={() => setSpectroOn(v => !v)}
              title="Toggle spectrogram"
              className={`inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-[10px] font-semibold transition ${spectroOn ? 'bg-indigo-600 text-white' : 'border border-slate-200 bg-white text-slate-600 hover:bg-slate-50'}`}
            >
              <Activity className="h-3 w-3"/> Spectrogram
            </button>
          </div>
        </div>

        {/* Waveform container — WaveSurfer owns this div */}
        <div className="relative px-5 pt-4 pb-2">
          <div className="relative">
            <div
              ref={containerRef}
              className="relative w-full overflow-hidden rounded-lg ring-1 ring-slate-100"
              style={{ minHeight: 110 }}
            />
            {spectroOn && (
              <canvas
                ref={spectroCanvasRef}
                className="pointer-events-none absolute inset-0 rounded-lg"
                style={{ width: '100%', height: '100%', opacity: 0.6, mixBlendMode: 'multiply' }}
              />
            )}
          </div>
        </div>
      </section>

      {/* ======= CONCEPT HEADER ======= */}
      <section className="px-8 pt-6">
        <div className="mx-auto max-w-4xl">
          <div className="flex items-center gap-3">
            <button onClick={onPrev} className="grid h-9 w-9 place-items-center rounded-lg border border-slate-200 bg-white text-slate-500 hover:text-slate-800">
              <ChevronLeft className="h-4 w-4"/>
            </button>
            <div className="flex-1">
              <div className="flex items-center gap-2 text-[11px] font-medium uppercase tracking-wider text-slate-400">
                Concept <span className="font-mono">#{concept.id}</span> <span>·</span> {concept.id} of {totalConcepts}
              </div>
              <div className="mt-0.5 flex items-center gap-3">
                <h1 className="text-[32px] font-semibold tracking-tight text-slate-900">{concept.name}</h1>
                <span className="inline-flex items-center gap-1 rounded-md bg-slate-100 px-2 py-0.5 font-mono text-[11px] font-semibold text-slate-700">
                  {speaker}
                </span>
                {annotated ? (
                  <span className="inline-flex items-center gap-1 rounded-md bg-emerald-50 px-2 py-0.5 text-[11px] font-semibold text-emerald-700 ring-1 ring-emerald-200">
                    Annotated
                  </span>
                ) : (
                  <span className="inline-flex items-center gap-1 rounded-md bg-rose-50 px-2 py-0.5 text-[11px] font-semibold text-rose-600 ring-1 ring-rose-200">
                    Missing
                  </span>
                )}
              </div>
              <div className="mt-1 flex items-center gap-1 font-mono text-[11px] text-slate-400">
                <span className="text-[9px] uppercase tracking-wider text-slate-400">Source</span>
                <span className="text-slate-500">{speaker}.wav</span>
              </div>
            </div>
            <button onClick={onNext} className="grid h-9 w-9 place-items-center rounded-lg border border-slate-200 bg-white text-slate-500 hover:text-slate-800">
              <ChevronRight className="h-4 w-4"/>
            </button>
          </div>
        </div>
      </section>

      {/* ======= TRANSCRIPTION FIELDS ======= */}
      <section className="px-8 py-6">
        <div className="mx-auto max-w-4xl space-y-5">
          <div>
            <label className="text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-500">IPA Transcription</label>
            <input
              value={ipa}
              onChange={e => setIpa(e.target.value)}
              placeholder="Enter IPA…"
              dir="ltr"
              className="mt-2 w-full rounded-xl border border-slate-200 bg-white px-4 py-3 font-mono text-lg text-slate-900 placeholder:text-slate-300 focus:border-indigo-300 focus:outline-none focus:ring-4 focus:ring-indigo-50"
            />
          </div>

          <div>
            <label className="text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-500">Orthographic (Kurdish)</label>
            <input
              value={ortho}
              onChange={e => setOrtho(e.target.value)}
              placeholder="Enter orthographic form…"
              dir="rtl"
              className="mt-2 w-full rounded-xl border border-slate-200 bg-white px-4 py-3 font-serif text-xl text-slate-900 placeholder:text-slate-300 focus:border-indigo-300 focus:outline-none focus:ring-4 focus:ring-indigo-50"
            />
          </div>

          {/* Action buttons */}
          <div className="flex items-center gap-3 pt-2">
            <button
              onClick={() => {
                if (!selectedRegion) return;
                const interval = { start: selectedRegion.start, end: selectedRegion.end };
                setInterval(speaker, 'ipa', { ...interval, text: ipa });
                setInterval(speaker, 'ortho', { ...interval, text: ortho });
                setInterval(speaker, 'concept', { ...interval, text: concept.name });
                void saveSpeaker(speaker);
              }}
              className="inline-flex items-center gap-2 rounded-xl bg-indigo-600 px-5 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:bg-indigo-700"
            >
              <Save className="h-4 w-4"/> Save Annotation
            </button>
            <button
              onClick={() => tagConcept('confirmed', concept.key)}
              className="inline-flex items-center gap-2 rounded-xl border border-rose-200 bg-white px-5 py-2.5 text-sm font-semibold text-rose-600 transition hover:bg-rose-50"
            >
              <Check className="h-4 w-4"/> Mark Done
            </button>
            <div className="ml-auto text-[11px] text-slate-400">
              Region <span className="font-mono text-slate-600">{selectedRegion ? `${fmt(selectedRegion.start)}–${fmt(selectedRegion.end)}` : (activeRegion ?? '—')}</span> · Anchor: <span className="font-mono text-slate-600">{lexAnchor}</span>
            </div>
          </div>
        </div>
      </section>

      {/* ======= BOTTOM PLAYBACK BAR ======= */}
      <section className="sticky bottom-0 border-t border-slate-200 bg-white/95 backdrop-blur">
        <div className="mx-auto flex max-w-4xl items-center gap-3 px-8 py-3">
          <button onClick={() => skip(-5)} title="-5s" className="grid h-8 w-8 place-items-center rounded-md text-slate-500 hover:bg-slate-100 hover:text-slate-800"><SkipBack className="h-4 w-4"/></button>
          <button onClick={() => skip(-1)} title="-1s" className="grid h-8 w-8 place-items-center rounded-md text-slate-500 hover:bg-slate-100 hover:text-slate-800"><ChevronLeft className="h-4 w-4"/></button>
          <button
            onClick={() => playPause()}
            className="grid h-10 w-10 place-items-center rounded-full bg-slate-900 text-white shadow-sm hover:bg-slate-700"
          >
            {isPlaying ? <Pause className="h-4 w-4"/> : <Play className="h-4 w-4 translate-x-[1px]"/>}
          </button>
          <button onClick={() => skip(1)} title="+1s" className="grid h-8 w-8 place-items-center rounded-md text-slate-500 hover:bg-slate-100 hover:text-slate-800"><ChevronRight className="h-4 w-4"/></button>
          <button onClick={() => skip(5)} title="+5s" className="grid h-8 w-8 place-items-center rounded-md text-slate-500 hover:bg-slate-100 hover:text-slate-800"><SkipForward className="h-4 w-4"/></button>

          <div className="ml-2 font-mono text-[11px] tabular-nums text-slate-500">
            {fmt(currentTime)} <span className="text-slate-300">/</span> {fmt(duration)}
          </div>

          <div className="ml-auto flex items-center gap-2">
            <select defaultValue="1" onChange={e => setRate(Number(e.target.value))} className="rounded-md border border-slate-200 bg-white px-2 py-1 text-[11px] font-semibold text-slate-600 focus:border-indigo-300 focus:outline-none">
              <option value="0.5">0.5x</option>
              <option value="0.75">0.75x</option>
              <option value="1">1.0x</option>
              <option value="1.25">1.25x</option>
              <option value="1.5">1.5x</option>
              <option value="2">2.0x</option>
            </select>
            <button className="inline-flex items-center gap-1.5 rounded-md border border-slate-200 bg-white px-2.5 py-1 text-[11px] font-semibold text-slate-600 hover:bg-slate-50">
              <MessageSquare className="h-3 w-3"/> Chat
            </button>
          </div>
        </div>
      </section>
    </main>
  );
};

// ---------- Main Component ----------
export function ParseUI() {
  // — Stores —
  const loadConfig       = useConfigStore(s => s.load);
  const rawSpeakers      = useConfigStore(s => s.config?.speakers ?? []);
  const rawConcepts      = useConfigStore(s => s.config?.concepts ?? []);
  const storeTags        = useTagStore(s => s.tags);
  const storeAddTag      = useTagStore(s => s.addTag);
  const hydrateTagStore  = useTagStore(s => s.hydrate);
  const tagConcept       = useTagStore(s => s.tagConcept);
  const untagConcept     = useTagStore(s => s.untagConcept);
  const getTagsForConcept = useTagStore(s => s.getTagsForConcept);
  const annotationRecords = useAnnotationStore(s => s.records);
  const enrichmentData = useEnrichmentStore(s => s.data);
  const setActiveSpeakerUI = useUIStore(s => s.setActiveSpeaker);
  // — Chat session (one instance for the whole UI) —
  const chatSession = useChatSession();
  // — Annotation sync (auto-loads record when activeSpeaker changes) —
  useAnnotationSync();
  // — Bootstrap —
  useEffect(() => {
    loadConfig().catch(console.error);
    hydrateTagStore();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const [query, setQuery] = useState('');
  const [sortMode, setSortMode] = useState<'az'|'1n'>('1n');
  const [tagFilter, setTagFilter] = useState<TagState>('all');
  const [conceptId, setConceptId] = useState(1);
  const [modeTab, setModeTab] = useState<ModeTab>('all');
  const [selectedSpeakers, setSelectedSpeakers] = useState<string[]>([]);
  const [speakerPicker, setSpeakerPicker] = useState<string | null>(null);
  const [computeMode, setComputeMode] = useState('cognates');
  const { start: startComputeJob, state: computeJobState, reset: resetComputeJob } = useComputeJob(computeMode);
  const [notes, setNotes] = useState('');
  const [borrowingsOpen, setBorrowingsOpen] = useState(true);
  const [panelOpen, setPanelOpen] = useState(true);

  // Auto-select speakers when config loads and we have none selected
  useEffect(() => {
    if (rawSpeakers.length > 0 && selectedSpeakers.length === 0) {
      setSelectedSpeakers(rawSpeakers);
      setSpeakerPicker(rawSpeakers.find(s => !rawSpeakers.includes(s)) ?? rawSpeakers[0] ?? null);
    }
  }, [rawSpeakers]); // eslint-disable-line react-hooks/exhaustive-deps
  const [currentMode, setCurrentMode] = useState<AppMode>('compare');
  const [modeMenuOpen, setModeMenuOpen] = useState(false);
  const [actionsMenuOpen, setActionsMenuOpen] = useState(false);
  const activeActionSpeaker = selectedSpeakers[0] ?? null;
  const loadSpeaker = useAnnotationStore((s) => s.loadSpeaker);
  const loadEnrichments = useEnrichmentStore((s) => s.load);

  const reloadSpeakerAnnotation = async (speakerId: string | null) => {
    if (!speakerId) {
      return;
    }

    useAnnotationStore.setState((store: { dirty: Record<string, boolean> }) => ({
      dirty: { ...store.dirty, [speakerId]: true },
    }));
    await loadSpeaker(speakerId);
  };

  const normalizeJob = useActionJob({
    start: () => {
      if (!activeActionSpeaker) return Promise.reject(new Error('No speaker selected'));
      return startNormalize(activeActionSpeaker);
    },
    poll: (id) => pollNormalize(id) as Promise<PollResult>,
    label: 'Normalizing audio…',
    onComplete: () => reloadSpeakerAnnotation(activeActionSpeaker),
  });

  const sttJob = useActionJob({
    start: () => {
      if (!activeActionSpeaker) return Promise.reject(new Error('No speaker selected'));
      return startSTT(activeActionSpeaker, `${activeActionSpeaker}.wav`, 'ckb');
    },
    poll: (id) => pollSTT(id) as Promise<PollResult>,
    label: 'Running STT…',
    onComplete: () => reloadSpeakerAnnotation(activeActionSpeaker),
  });

  const ipaJob = useActionJob({
    start: () => startCompute('ipa_only'),
    poll: (id) => pollCompute('ipa_only', id),
    label: 'Transcribing IPA…',
    onComplete: loadEnrichments,
  });

  const pipelineJob = useActionJob({
    start: () => startCompute('full_pipeline'),
    poll: (id) => pollCompute('full_pipeline', id),
    label: 'Running full pipeline…',
    onComplete: loadEnrichments,
  });

  const crossSpeakerJob = useActionJob({
    start: () => startCompute('contact-lexemes'),
    poll: (id) => pollCompute('contact-lexemes', id),
    label: 'Matching cross-speaker…',
    onComplete: loadEnrichments,
  });

  const allJobs = [normalizeJob, sttJob, ipaJob, pipelineJob, crossSpeakerJob];
  const activeJobs = allJobs.filter(j => j.state.status !== 'idle');

  const [importModalOpen, setImportModalOpen] = useState(false);
  const [exporting, setExporting] = useState(false);

  const resetProject = () => {
    setActionsMenuOpen(false);
    if (!window.confirm('Reset project? This will clear all in-memory store state. Saved files on disk are not affected.')) return;
    useAnnotationStore.setState({ records: {}, dirty: {}, loading: {} });
    useEnrichmentStore.setState({ data: {}, loading: false });
    useTagStore.setState({ tags: [] });
    usePlaybackStore.setState({ activeSpeaker: null, currentTime: 0 });
    useConfigStore.setState({ config: null, loading: false });
    allJobs.forEach(j => j.reset());
    resetComputeJob();
  };

  const handleExportLingPy = async () => {
    setExporting(true);
    setActionsMenuOpen(false);
    try {
      const blob = await getLingPyExport();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'parse-wordlist.tsv';
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      console.error('[ParseUI] LingPy export failed:', err);
    } finally {
      setExporting(false);
    }
  };

  const [tagSearch, setTagSearch] = useState('');
  const [newTagName, setNewTagName] = useState('');
  const [newTagColor, setNewTagColor] = useState('#6366f1');
  const [showUntagged, setShowUntagged] = useState(true);
  const [selectedTagId, setSelectedTagId] = useState<string | null>(null);
  const [tagConceptSearch, setTagConceptSearch] = useState('');
  const [darkMode, setDarkMode] = useState(false);

  useEffect(() => {
    document.documentElement.classList.toggle('dark', darkMode);
  }, [darkMode]);

  useEffect(() => {
    try {
      const raw = window.localStorage.getItem(COMPARE_NOTES_STORAGE_KEY);
      const stored = raw ? JSON.parse(raw) as Record<string, string> : {};
      setNotes(stored[conceptId.toString()] ?? '');
    } catch {
      setNotes('');
    }
  }, [conceptId]);

  // — Derived: real speakers (no fallback — empty until workspace provides them) —
  const speakers = rawSpeakers;

  // — Derived: real concepts with live tag state —
  const concepts = useMemo<Concept[]>(() => {
    if (rawConcepts.length === 0) return [];
    return rawConcepts.map((c, i) => ({
      id: i + 1,
      key: c.id,
      name: c.label,
      tag: getConceptStatus(getTagsForConcept(c.id)),
    }));
  }, [rawConcepts, getTagsForConcept]);

  // — Derived: tags list from store —
  const tagsList = useMemo<LingTag[]>(() =>
    storeTags.map(t => ({ id: t.id, name: t.label, color: t.color, dotClass: '', count: t.concepts.length })),
    [storeTags]
  );

  // AI bottom panel
  const [aiHeight, setAiHeight] = useState(() => Math.round(window.innerHeight * 0.4));
  const [aiMinimized, setAiMinimized] = useState(true);
  const resizingRef = useRef(false);
  const loadDecisionsRef = useRef<HTMLInputElement>(null);
  const loadDecisionsMenuRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (currentMode === 'annotate') {
      setSelectedSpeakers(sel => sel.length ? [sel[0]] : ['Fail01']);
    }
  }, [currentMode]);

  const onResizeStart = (e: React.MouseEvent) => {
    e.preventDefault();
    resizingRef.current = true;
    const startY = e.clientY;
    const startH = aiHeight;
    const onMove = (ev: MouseEvent) => {
      if (!resizingRef.current) return;
      const dy = startY - ev.clientY;
      const next = Math.min(Math.max(startH + dy, 120), window.innerHeight - 180);
      setAiHeight(next);
    };
    const onUp = () => {
      resizingRef.current = false;
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
    };
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
  };

  const filtered = useMemo(() => {
    let list = concepts.filter(c => c.name.toLowerCase().includes(query.toLowerCase()));
    if (tagFilter !== 'all') list = list.filter(c => c.tag === tagFilter);
    if (modeTab === 'unreviewed') list = list.filter(c => c.tag === 'untagged' || c.tag === 'review');
    if (modeTab === 'flagged') list = list.filter(c => c.tag === 'problematic');
    if (modeTab === 'borrowings') list = list.filter(c => {
      // TODO: wire to real borrowing data from enrichments
      const borrowingRoot = isRecord(enrichmentData?.borrowings) ? enrichmentData.borrowings : {};
      return c.key in borrowingRoot;
    });
    // In annotate mode, show all concepts for the selected speaker (filter by real data when available)
    if (currentMode === 'annotate') {
      // No synthetic filtering — show the full concept list
    }
    if (sortMode === 'az') list = [...list].sort((a,b) => a.name.localeCompare(b.name));
    else list = [...list].sort((a,b) => a.id - b.id);
    return list;
  }, [query, tagFilter, sortMode, modeTab, currentMode, selectedSpeakers, enrichmentData, concepts]);

  const concept = concepts.find(c => c.id === conceptId) ?? concepts[0] ?? { id: 1, key: '1', name: '—', tag: 'untagged' as ConceptTag };
  const referenceForms = useMemo(
    () => resolveReferenceForms(enrichmentData, concept),
    [concept, enrichmentData],
  );
  const borrowingCandidates = useMemo<unknown>(() => {
    const borrowingRoot = isRecord(enrichmentData.borrowings) ? enrichmentData.borrowings
      : isRecord(enrichmentData.borrowing_candidates) ? enrichmentData.borrowing_candidates
      : null;
    if (!borrowingRoot) return null;
    return borrowingRoot[concept.key] ?? borrowingRoot[concept.name] ?? null;
  }, [concept, enrichmentData]);
  const speakerForms = useMemo<SpeakerForm[]>(() => {
    const activeSpeakers = selectedSpeakers.filter((speaker) => speakers.includes(speaker));
    const flagged = getTagsForConcept(concept.key).some((tag) => tag.id === 'problematic');

    return activeSpeakers.map((speaker) => buildSpeakerForm(
      annotationRecords[speaker],
      concept,
      speaker,
      enrichmentData,
      flagged,
    ));
  }, [annotationRecords, concept, enrichmentData, getTagsForConcept, selectedSpeakers, speakers]);
  const reviewed = concepts.filter(c => c.tag === 'confirmed').length;
  const total = concepts.length;

  const goPrev = () => setConceptId(id => Math.max(1, id - 1));
  const goNext = () => setConceptId(id => Math.min(total, id + 1));
  const toggleSpeaker = (s: string) => {
    if (currentMode === 'annotate') {
      setSelectedSpeakers([s]);
      setActiveSpeakerUI(s);
      usePlaybackStore.setState({ activeSpeaker: s });
      return;
    }
    setSelectedSpeakers(sel => sel.includes(s) ? sel.filter(x => x !== s) : [...sel, s]);
  };
  const addSpeaker = () => {
    if (speakerPicker && !selectedSpeakers.includes(speakerPicker)) setSelectedSpeakers([...selectedSpeakers, speakerPicker]);
  };
  const openImportModal = () => {
    setActionsMenuOpen(false);
    setImportModalOpen(true);
  };
  const handleImportComplete = (speakerId: string) => {
    setImportModalOpen(false);
    if (!speakerId) return;
    setSpeakerPicker(speakerId);
    if (currentMode === 'annotate') {
      setSelectedSpeakers([speakerId]);
      setActiveSpeakerUI(speakerId);
      usePlaybackStore.setState({ activeSpeaker: speakerId });
      return;
    }
    setSelectedSpeakers((existing) => existing.includes(speakerId) ? existing : [...existing, speakerId]);
  };

  const modeTabs: { key: ModeTab; label: string }[] = [
    { key: 'all', label: 'All' },
    { key: 'unreviewed', label: 'Unreviewed' },
    { key: 'flagged', label: 'Flagged' },
    { key: 'borrowings', label: 'Borrowings' },
  ];

  return (
    <div className="h-screen overflow-hidden bg-slate-50 text-slate-800 font-sans antialiased flex flex-col">
      {/* ============ MINIMAL TOP BAR ============ */}
      <header className="relative z-50 shrink-0 h-14 border-b border-slate-200/80 bg-white/90 backdrop-blur-xl">
        <div className="flex h-full items-center justify-between px-5">
          <div className="flex items-center gap-5">
            <div className="flex items-center gap-2">
              <div className="grid h-7 w-7 place-items-center rounded-md bg-gradient-to-br from-indigo-500 to-violet-600 text-white shadow-sm">
                <Layers className="h-4 w-4" />
              </div>
              <span className="text-[15px] font-semibold tracking-tight text-slate-900">PARSE Compare</span>
            </div>
            <div className="hidden items-center gap-3 md:flex">
              <div className="text-[11px] font-medium text-slate-500 tabular-nums">{reviewed} / {total} reviewed</div>
              <div className="h-1.5 w-32 overflow-hidden rounded-full bg-slate-100">
                <div className="h-full rounded-full bg-gradient-to-r from-indigo-500 to-violet-500" style={{ width: `${(reviewed/total)*100}%` }}/>
              </div>
            </div>
          </div>

          <nav className="hidden items-center gap-1 rounded-lg bg-slate-100/80 p-0.5 md:flex">
            {modeTabs.map(t => (
              <button
                key={t.key}
                onClick={() => setModeTab(t.key)}
                className={`rounded-md px-3 py-1 text-xs font-medium transition ${modeTab === t.key ? 'bg-white text-slate-900 shadow-sm ring-1 ring-slate-200' : 'text-slate-500 hover:text-slate-800'}`}
              >
                {t.label}
              </button>
            ))}
          </nav>

          <div className="flex items-center gap-2">
            {/* Mode dropdown */}
            <div className="relative">
              <button
                onClick={() => { setModeMenuOpen(v => !v); setActionsMenuOpen(false); }}
                className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-50"
              >
                {currentMode === 'annotate' ? 'Annotate' : currentMode === 'compare' ? 'Compare' : 'Manage Tags'}
                <CDown className="h-3 w-3 text-slate-400"/>
              </button>
              {modeMenuOpen && (
                <>
                  <div className="fixed inset-0 z-30" onClick={() => setModeMenuOpen(false)}/>
                  <div className="absolute right-0 z-[60] mt-1.5 w-48 overflow-hidden rounded-lg border border-slate-200 bg-white p-1 shadow-lg">
                    {([
                      ['annotate','Annotate', Type],
                      ['compare','Compare', Layers],
                      ['tags','Manage Tags', Tags],
                    ] as const).map(([key,label,Icon]) => (
                      <button
                        key={key}
                        onClick={() => { setCurrentMode(key); setModeMenuOpen(false); }}
                        className={`flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-left text-xs transition ${currentMode===key ? 'bg-indigo-50 font-semibold text-indigo-800' : 'text-slate-700 hover:bg-slate-50'}`}
                      >
                        <Icon className="h-3.5 w-3.5 text-slate-400"/>
                        <span className="flex-1">{label}</span>
                        {currentMode===key && <Check className="h-3.5 w-3.5 text-indigo-600"/>}
                      </button>
                    ))}
                  </div>
                </>
              )}
            </div>

            {/* Actions dropdown */}
            <div className="relative">
              <button
                onClick={() => { setActionsMenuOpen(v => !v); setModeMenuOpen(false); }}
                className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-50"
              >
                Actions
                <CDown className="h-3 w-3 text-slate-400"/>
              </button>
              {actionsMenuOpen && (
                <>
                  <div className="fixed inset-0 z-30" onClick={() => setActionsMenuOpen(false)}/>
                  <div className="absolute right-0 z-[60] mt-1.5 w-60 overflow-hidden rounded-lg border border-slate-200 bg-white p-1 shadow-lg">
                    <button
                      onClick={openImportModal}
                      className="flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-left text-xs text-slate-700 hover:bg-slate-50"
                    >
                      <Import className="h-3.5 w-3.5 text-slate-400"/> Import Speaker Data…
                    </button>
                    <button
                      onClick={() => { setActionsMenuOpen(false); void normalizeJob.run(); }}
                      disabled={!activeActionSpeaker || normalizeJob.state.status === 'running'}
                      className="flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-left text-xs text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      <AudioLines className="h-3.5 w-3.5 text-slate-400"/>
                      {normalizeJob.state.status === 'running' ? 'Normalizing…' : 'Run Audio Normalization'}
                    </button>
                    <button
                      onClick={() => { setActionsMenuOpen(false); void sttJob.run(); }}
                      disabled={!activeActionSpeaker || sttJob.state.status === 'running'}
                      className="flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-left text-xs text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      <Mic className="h-3.5 w-3.5 text-slate-400"/>
                      {sttJob.state.status === 'running' ? 'Running STT…' : 'Run Orthographic STT'}
                    </button>
                    <button
                      onClick={() => { setActionsMenuOpen(false); void ipaJob.run(); }}
                      disabled={ipaJob.state.status === 'running'}
                      className="flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-left text-xs text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      <Type className="h-3.5 w-3.5 text-slate-400"/>
                      {ipaJob.state.status === 'running' ? 'Transcribing…' : 'Run IPA Transcription'}
                    </button>
                    <button
                      onClick={() => { setActionsMenuOpen(false); void pipelineJob.run(); }}
                      disabled={pipelineJob.state.status === 'running'}
                      className="flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-left text-xs text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      <Workflow className="h-3.5 w-3.5 text-slate-400"/>
                      {pipelineJob.state.status === 'running' ? 'Running pipeline…' : 'Run Full Pipeline'}
                    </button>
                    <button
                      onClick={() => { setActionsMenuOpen(false); void crossSpeakerJob.run(); }}
                      disabled={crossSpeakerJob.state.status === 'running'}
                      className="flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-left text-xs text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      <Network className="h-3.5 w-3.5 text-slate-400"/>
                      {crossSpeakerJob.state.status === 'running' ? 'Matching…' : 'Run Cross-Speaker Match'}
                    </button>
                    <div className="my-1 border-t border-slate-100"/>
                    <button
                      onClick={() => { setActionsMenuOpen(false); loadDecisionsMenuRef.current?.click(); }}
                      className="flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-left text-xs text-slate-700 hover:bg-slate-50"
                    >
                      <Upload className="h-3.5 w-3.5 text-slate-400"/> Load Decisions
                    </button>
                    <button onClick={() => setActionsMenuOpen(false)} className="flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-left text-xs text-slate-700 hover:bg-slate-50">
                      <Save className="h-3.5 w-3.5 text-slate-400"/> Save Decisions
                    </button>
                    <button
                      onClick={handleExportLingPy}
                      disabled={exporting}
                      className="flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-left text-xs text-indigo-700 hover:bg-indigo-50 disabled:opacity-50"
                    >
                      <Download className="h-3.5 w-3.5 text-indigo-400"/>
                      {exporting ? 'Exporting…' : 'Export LingPy TSV'}
                    </button>
                    <div className="my-1 border-t border-slate-100"/>
                    <button
                      onClick={resetProject}
                      className="flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-left text-xs text-rose-600 hover:bg-rose-50"
                    >
                      <Trash2 className="h-3.5 w-3.5"/> Reset Project
                    </button>
                  </div>
                </>
              )}
            </div>

            {activeJobs.length > 0 && (
              <div className="ml-2 flex flex-col gap-1" data-testid="topbar-action-statuses">
                {activeJobs.map((job, i) => (
                  <div key={i} className="flex items-center gap-2 text-[11px]">
                    {job.state.status === 'running' && (
                      <>
                        <Loader2 className="h-3 w-3 animate-spin text-indigo-500" />
                        <span className="text-slate-600">{job.state.label}</span>
                        <div className="h-1.5 w-20 overflow-hidden rounded-full bg-slate-200">
                          <div
                            className="h-full rounded-full bg-indigo-500 transition-all duration-300"
                            style={{ width: `${Math.round(job.state.progress * 100)}%` }}
                          />
                        </div>
                        <span className="tabular-nums text-slate-400">{Math.round(job.state.progress * 100)}%</span>
                        {job.state.etaMs !== null && job.state.etaMs > 0 && (
                          <span className="tabular-nums text-slate-400" title="Estimated time remaining">
                            · ~{formatEta(job.state.etaMs)} left
                          </span>
                        )}
                      </>
                    )}
                    {job.state.status === 'complete' && (
                      <>
                        <Check className="h-3 w-3 text-emerald-500" />
                        <span className="text-emerald-600">{job.state.label?.replace('…', '')} done</span>
                      </>
                    )}
                    {job.state.status === 'error' && (
                      <>
                        <XCircle className="h-3 w-3 text-rose-500" />
                        <span className="max-w-[200px] truncate text-rose-600">{job.state.error}</span>
                        <button
                          onClick={() => { void job.run(); }}
                          className="text-[10px] text-rose-600 underline hover:text-rose-700"
                        >
                          Retry
                        </button>
                        <button
                          onClick={job.reset}
                          className="text-[10px] text-slate-500 underline hover:text-slate-700"
                        >
                          Dismiss
                        </button>
                      </>
                    )}
                  </div>
                ))}
              </div>
            )}

            <button
              onClick={() => setDarkMode(v => !v)}
              title={darkMode ? 'Switch to light mode' : 'Switch to dark mode'}
              className="grid h-8 w-8 place-items-center rounded-md text-slate-500 hover:bg-slate-100 hover:text-slate-800"
            >
              {darkMode ? <Sun className="h-4 w-4"/> : <Moon className="h-4 w-4"/>}
            </button>
          </div>
        </div>
      </header>

      {/* ============ BODY: left sidebar / main / right panel ============ */}
      <div className="flex min-h-0 flex-1">
        {/* LEFT SIDEBAR */}
        <aside className="w-[250px] shrink-0 border-r border-slate-200/80 bg-white flex flex-col">
          <div className="p-4 shrink-0">
            <div className="relative">
              <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-slate-400" />
              <input value={query} onChange={e => setQuery(e.target.value)} placeholder="Search concepts…"
                className="w-full rounded-lg border border-slate-200 bg-slate-50/60 py-1.5 pl-8 pr-3 text-xs text-slate-700 placeholder:text-slate-400 focus:border-indigo-300 focus:bg-white focus:outline-none focus:ring-2 focus:ring-indigo-100"/>
            </div>
            <div className="mt-3 flex items-center justify-between">
              <div className="inline-flex rounded-md bg-slate-100 p-0.5">
                <button onClick={() => setSortMode('az')} className={`px-2 py-0.5 text-[10px] font-semibold rounded ${sortMode==='az'?'bg-white text-slate-800 shadow-sm':'text-slate-500'}`}>A→Z</button>
                <button onClick={() => setSortMode('1n')} className={`px-2 py-0.5 text-[10px] font-semibold rounded ${sortMode==='1n'?'bg-white text-slate-800 shadow-sm':'text-slate-500'}`}>1→N</button>
              </div>
              <span className="text-[10px] text-slate-400">{filtered.length} concepts</span>
            </div>
          </div>
          <nav className="flex-1 overflow-y-auto px-2 pb-6">
            {filtered.map(c => {
              const active = c.id === conceptId;
              return (
                <button key={c.id} onClick={() => setConceptId(c.id)}
                  className={`group mb-0.5 flex w-full items-center gap-2.5 rounded-md px-2.5 py-1.5 text-left transition ${active ? 'bg-indigo-50 text-indigo-900' : 'text-slate-600 hover:bg-slate-50'}`}>
                  <span className={`h-1.5 w-1.5 rounded-full ${tagDot[c.tag]}`} />
                  <span className={`flex-1 text-[13px] ${active ? 'font-semibold' : 'font-medium'}`}>{c.name}</span>
                  <span className={`font-mono text-[10px] ${active ? 'text-indigo-400' : 'text-slate-300'}`}>#{c.id}</span>
                </button>
              );
            })}
          </nav>
        </aside>

        {/* MAIN + AI STACK */}
        <div className="flex min-w-0 flex-1 flex-col">
          {currentMode === 'tags' ? (
          <>
            <ManageTagsView
              tags={tagsList}
              concepts={concepts}
              onCreateTag={(name, color) => { if (!name.trim()) return; storeAddTag(name, color); setNewTagName(''); }}
              tagSearch={tagSearch}
              setTagSearch={setTagSearch}
              newTagName={newTagName}
              setNewTagName={setNewTagName}
              newTagColor={newTagColor}
              setNewTagColor={setNewTagColor}
              showUntagged={showUntagged}
              setShowUntagged={setShowUntagged}
              selectedTagId={selectedTagId}
              setSelectedTagId={setSelectedTagId}
              conceptSearch={tagConceptSearch}
              setConceptSearch={setTagConceptSearch}
              tagConcept={tagConcept}
              untagConcept={untagConcept}
            />
            <AIChat
              height={aiHeight}
              minimized={aiMinimized}
              onResizeStart={onResizeStart}
              onMinimize={() => setAiMinimized(v => !v)}
              conceptName={concept.name}
              conceptId={concept.id}
              speakerCount={selectedSpeakers.length}
              chatSession={chatSession}
            />
          </>
          ) : currentMode === 'annotate' ? (
          <>
            <AnnotateView
              concept={concept}
              speaker={selectedSpeakers[0] ?? 'Mand01'}
              totalConcepts={total}
              onPrev={goPrev}
              onNext={goNext}
              audioUrl={selectedSpeakers[0] ? `/audio/${selectedSpeakers[0]}.wav` : ''}
              peaksUrl={selectedSpeakers[0] ? `/peaks/${selectedSpeakers[0]}.json` : undefined}
            />
            <AIChat
              height={aiHeight}
              minimized={aiMinimized}
              onResizeStart={onResizeStart}
              onMinimize={() => setAiMinimized(v => !v)}
              conceptName={concept.name}
              conceptId={concept.id}
              speakerCount={selectedSpeakers.length}
              chatSession={chatSession}
            />
          </>
          ) : (
          <>
          <main className="flex-1 overflow-y-auto px-8 py-6">
            <div className="mx-auto max-w-5xl space-y-5">

              <div className="flex items-center justify-between">
                <div className="flex items-center gap-4">
                  <button onClick={goPrev} className="grid h-9 w-9 place-items-center rounded-lg border border-slate-200 bg-white text-slate-500 hover:border-slate-300 hover:text-slate-800">
                    <ChevronLeft className="h-4 w-4"/>
                  </button>
                  <div>
                    <div className="flex items-center gap-2 text-[11px] font-medium uppercase tracking-wider text-slate-400">
                      Concept <span className="font-mono">#{concept.id}</span> <span>·</span> <span>{concept.id} of {total}</span>
                    </div>
                    <h1 className="mt-0.5 text-[28px] font-semibold tracking-tight text-slate-900">{concept.name}</h1>
                  </div>
                  <button onClick={goNext} className="grid h-9 w-9 place-items-center rounded-lg border border-slate-200 bg-white text-slate-500 hover:border-slate-300 hover:text-slate-800">
                    <ChevronRight className="h-4 w-4"/>
                  </button>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => getTagsForConcept(concept.key).some((tag) => tag.id === 'problematic')
                      ? null
                      : tagConcept('problematic', concept.key)}
                    className={`inline-flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs font-semibold transition ${getTagsForConcept(concept.key).some((tag) => tag.id === 'problematic') ? 'border-amber-300 bg-amber-100 text-amber-800' : 'border-amber-200 bg-amber-50 text-amber-700 hover:bg-amber-100'}`}
                  >
                    <Flag className="h-3.5 w-3.5"/> Flag
                  </button>
                  <button
                    onClick={() => getTagsForConcept(concept.key).some((tag) => tag.id === 'confirmed')
                      ? null
                      : tagConcept('confirmed', concept.key)}
                    className={`inline-flex items-center gap-1.5 rounded-lg px-3.5 py-1.5 text-xs font-semibold shadow-sm transition ${getTagsForConcept(concept.key).some((tag) => tag.id === 'confirmed') ? 'bg-emerald-700 text-white' : 'bg-emerald-600 text-white hover:bg-emerald-700'}`}
                  >
                    <Check className="h-3.5 w-3.5"/> Accept concept
                  </button>
                </div>
              </div>

              <SectionCard title="Reference forms">
                <div className="grid grid-cols-2 gap-4">
                  {[
                    { label: 'Arabic', tone: 'text-rose-500', dir: 'rtl' as const, data: referenceForms.arabic },
                    { label: 'Persian', tone: 'text-indigo-500', dir: 'rtl' as const, data: referenceForms.persian },
                  ].map((entry) => (
                    <div key={entry.label} className="rounded-lg border border-slate-100 bg-slate-50/40 p-4">
                      <div className="flex items-center justify-between">
                        <span className={`text-[10px] font-semibold uppercase tracking-wider ${entry.tone}`}>{entry.label}</span>
                        <button
                          title={entry.data.audioUrl ? `Play ${entry.label} reference audio` : 'Reference audio not available'}
                          onClick={() => {
                            if (!entry.data.audioUrl) return;
                            void new Audio(entry.data.audioUrl).play().catch(() => {});
                          }}
                          className="text-slate-300 hover:text-slate-500"
                        >
                          <Volume2 className="h-3.5 w-3.5"/>
                        </button>
                      </div>
                      {entry.data.available ? (
                        <>
                          <div className="mt-2 font-serif text-2xl text-slate-900" dir={entry.dir}>{entry.data.script || '—'}</div>
                          <div className="mt-1 font-mono text-[11px] text-slate-400">/{entry.data.ipa || '—'}/</div>
                        </>
                      ) : (
                        <div className="mt-2 text-sm text-slate-400">No reference data</div>
                      )}
                    </div>
                  ))}
                </div>
              </SectionCard>

              <SectionCard title={`Speaker forms · ${selectedSpeakers.length} selected`}
                aside={<button className="inline-flex items-center gap-1 text-[11px] font-medium text-slate-500 hover:text-slate-800"><ArrowUpDown className="h-3 w-3"/> Sort by similarity</button>}>
                <div className="overflow-hidden rounded-lg border border-slate-100">
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="bg-slate-50/70 text-[10px] uppercase tracking-wider text-slate-500">
                        <th className="px-3 py-2 text-left font-semibold">Speaker</th>
                        <th className="px-3 py-2 text-left font-semibold">IPA & utterances</th>
                        <th className="px-3 py-2 text-left font-semibold">Arabic sim.</th>
                        <th className="px-3 py-2 text-left font-semibold">Persian sim.</th>
                        <th className="px-3 py-2 text-left font-semibold">Cognate</th>
                        <th className="px-3 py-2 text-right font-semibold">Flag</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {speakerForms.map(f => (
                        <tr key={f.speaker} className="bg-white transition hover:bg-indigo-50/30">
                          <td className="px-3 py-2.5 font-mono text-[11px] font-medium text-slate-700">{f.speaker}</td>
                          <td className="px-3 py-2.5">
                            <div className="font-mono text-[13px] text-slate-800">/{f.ipa}/</div>
                            <div className="text-[10px] text-slate-400">{f.utterances} utterance{f.utterances!==1?'s':''}</div>
                          </td>
                          <td className="px-3 py-2.5"><SimBar value={f.arabicSim}/></td>
                          <td className="px-3 py-2.5"><SimBar value={f.persianSim}/></td>
                          <td className="px-3 py-2.5">
                            <span className={`inline-flex h-5 min-w-[20px] items-center justify-center rounded px-1 font-mono text-[10px] font-bold ${
                              f.cognate==='A'?'bg-indigo-100 text-indigo-700':
                              f.cognate==='B'?'bg-violet-100 text-violet-700':
                              f.cognate==='C'?'bg-fuchsia-100 text-fuchsia-700':
                              'bg-slate-100 text-slate-400'
                            }`}>{f.cognate}</span>
                          </td>
                          <td className="px-3 py-2.5 text-right">
                            <button
                              title={`Toggle speaker flag for ${f.speaker}`}
                              onClick={() => f.flagged ? untagConcept('problematic', concept.key) : tagConcept('problematic', concept.key)}
                              className={`inline-grid h-6 w-6 place-items-center rounded-md ${f.flagged?'bg-amber-100 text-amber-600':'text-slate-300 hover:bg-slate-100 hover:text-slate-500'}`}
                            >
                              <Flag className="h-3 w-3"/>
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </SectionCard>

              <SectionCard title="Cognate decision" aside={<Pill tone="indigo">2 groups proposed</Pill>}>
                <div className="flex flex-wrap items-center gap-2">
                  <button
                    className="inline-flex items-center gap-1.5 rounded-lg bg-slate-900 px-3 py-1.5 text-xs font-semibold text-white hover:bg-slate-800"
                    onClick={() => {
                      const patch = { cognate_decisions: { [concept.key]: { decision: 'accepted', ts: Date.now() } } };
                      void useEnrichmentStore.getState().save(patch);
                    }}
                  >
                    <Check className="h-3.5 w-3.5"/> Accept grouping
                  </button>
                  <button
                    className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-50"
                    onClick={() => {
                      const patch = { cognate_decisions: { [concept.key]: { decision: 'split', ts: Date.now() } } };
                      void useEnrichmentStore.getState().save(patch);
                    }}
                  >
                    <Split className="h-3.5 w-3.5"/> Split
                  </button>
                  <button
                    className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-50"
                    onClick={() => {
                      const patch = { cognate_decisions: { [concept.key]: { decision: 'merge', ts: Date.now() } } };
                      void useEnrichmentStore.getState().save(patch);
                    }}
                  >
                    <GitMerge className="h-3.5 w-3.5"/> Merge
                  </button>
                  <button
                    className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-50"
                    onClick={() => {
                      const current = (enrichmentData?.cognate_decisions as Record<string,{decision:string}>)?.[concept.key]?.decision ?? 'accepted';
                      const next = current === 'accepted' ? 'split' : current === 'split' ? 'merge' : 'accepted';
                      const patch = { cognate_decisions: { [concept.key]: { decision: next, ts: Date.now() } } };
                      void useEnrichmentStore.getState().save(patch);
                    }}
                  >
                    <RotateCw className="h-3.5 w-3.5"/> Cycle
                  </button>
                </div>
              </SectionCard>

              <SectionCard title="Potential borrowings"
                aside={<button onClick={() => setBorrowingsOpen(v=>!v)} className="text-slate-400 hover:text-slate-700">{borrowingsOpen ? <ChevronUp className="h-4 w-4"/> : <ChevronDown className="h-4 w-4"/>}</button>}>
                {borrowingsOpen ? (
                  borrowingCandidates != null ? (
                    Array.isArray(borrowingCandidates)
                      ? <div className="space-y-2">
                          {(borrowingCandidates as unknown[]).map((entry, i) => (
                            <div key={i} className="flex items-start gap-3 rounded-lg border border-amber-100 bg-amber-50/40 p-3">
                              <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-amber-500"/>
                              <div className="text-xs text-slate-600">{String(entry)}</div>
                            </div>
                          ))}
                        </div>
                      : <div className="flex items-start gap-3 rounded-lg border border-amber-100 bg-amber-50/40 p-3">
                          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-amber-500"/>
                          <div className="text-xs text-slate-600">{String(borrowingCandidates)}</div>
                        </div>
                  ) : (
                    <div className="text-xs text-slate-400">No borrowing candidates detected for this concept.</div>
                  )
                ) : (
                  <div className="text-xs text-slate-400">{borrowingCandidates != null ? '1 candidate hidden' : 'No borrowing data'}</div>
                )}
              </SectionCard>

              <SectionCard title="Notes">
                <textarea value={notes} onChange={e => setNotes(e.target.value)}
                  onBlur={() => {
                    try {
                      const raw = window.localStorage.getItem(COMPARE_NOTES_STORAGE_KEY);
                      const stored = raw ? JSON.parse(raw) as Record<string, string> : {};
                      stored[conceptId.toString()] = notes;
                      window.localStorage.setItem(COMPARE_NOTES_STORAGE_KEY, JSON.stringify(stored));
                    } catch {
                      // non-fatal localStorage failure
                    }
                  }}
                  placeholder="Add observations, etymological notes, or questions for review…"
                  className="min-h-[90px] w-full resize-none rounded-lg border border-slate-200 bg-slate-50/40 p-3 text-xs text-slate-700 placeholder:text-slate-400 focus:border-indigo-300 focus:bg-white focus:outline-none focus:ring-2 focus:ring-indigo-100"/>
              </SectionCard>

              <div className="flex items-center justify-between border-t border-slate-200 pt-5">
                <span className="text-[11px] text-slate-400">Concept {concept.id} of {total}</span>
                <div className="flex gap-2">
                  <button onClick={goPrev} className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-50">
                    <ChevronLeft className="h-3.5 w-3.5"/> Previous
                  </button>
                  <button onClick={goNext} className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-50">
                    Next <ChevronRight className="h-3.5 w-3.5"/>
                  </button>
                </div>
              </div>
            </div>
          </main>

          {/* BOTTOM AI CHAT */}
          <AIChat
            height={aiHeight}
            minimized={aiMinimized}
            onResizeStart={onResizeStart}
            onMinimize={() => setAiMinimized(v => !v)}
            conceptName={concept.name}
            conceptId={concept.id}
            speakerCount={selectedSpeakers.length}
            chatSession={chatSession}
          />
          </>
          )}
        </div>

        {/* RIGHT PANEL */}
        <aside
          className={`relative shrink-0 border-l border-slate-200/80 bg-white transition-[width] duration-500 ease-[cubic-bezier(0.22,1,0.36,1)] ${panelOpen ? 'w-[250px]' : 'w-[52px]'}`}
        >
          {/* Toggle */}
          <div className="sticky top-0 z-10 flex items-center justify-between border-b border-slate-100 bg-white/90 px-3 py-2.5 backdrop-blur">
            <span className={`text-[10px] font-semibold uppercase tracking-wider text-slate-500 transition-opacity duration-300 ${panelOpen ? 'opacity-100' : 'opacity-0'}`}>
              Controls
            </span>
            <button
              onClick={() => setPanelOpen(v => !v)}
              title={panelOpen ? 'Collapse' : 'Expand'}
              className="grid h-7 w-7 place-items-center rounded-md text-slate-500 transition hover:bg-slate-100 hover:text-slate-800"
            >
              <PanelRightClose className={`h-3.5 w-3.5 transition-transform duration-500 ease-[cubic-bezier(0.22,1,0.36,1)] ${panelOpen ? '' : 'rotate-180'}`}/>
            </button>
          </div>

          {/* Collapsed icon rail */}
          <div className={`absolute inset-x-0 top-[46px] flex flex-col items-center gap-1 py-3 transition-opacity duration-300 ${panelOpen ? 'pointer-events-none opacity-0' : 'opacity-100 delay-200'}`}>
            {[
              { icon: Database, label: 'Project' },
              { icon: UsersIcon, label: 'Speakers' },
              { icon: Cpu, label: 'Compute' },
              { icon: Filter, label: 'Filters' },
              { icon: Save, label: 'Decisions' },
            ].map(({ icon: Icon, label }) => (
              <button
                key={label}
                title={label}
                onClick={() => setPanelOpen(true)}
                className="grid h-9 w-9 place-items-center rounded-lg text-slate-400 transition hover:bg-indigo-50 hover:text-indigo-600"
              >
                <Icon className="h-4 w-4"/>
              </button>
            ))}
          </div>

          {/* Expanded content */}
          <div className={`h-[calc(100%-46px)] overflow-y-auto overflow-x-hidden transition-opacity duration-300 ${panelOpen ? 'opacity-100 delay-200' : 'pointer-events-none opacity-0'}`} style={{ width: 250 }}>
            {/* --- COMMON: Speakers --- */}
            <div className="border-b border-slate-100 p-4">
              <div className="mb-2 flex items-center justify-between">
                <h4 className="text-[10px] font-semibold uppercase tracking-wider text-slate-500">
                  Speakers {currentMode === 'annotate' && <span className="ml-1 rounded bg-indigo-50 px-1 py-0.5 font-mono text-[8px] text-indigo-600">SINGLE</span>}
                </h4>
                <span className="text-[10px] text-slate-400">
                  {currentMode === 'annotate' ? '1' : selectedSpeakers.length} / {speakers.length}
                </span>
              </div>
              <div className="mb-2 flex gap-1">
                <select
                  value={currentMode === 'annotate' ? (selectedSpeakers[0] ?? '') : (speakerPicker ?? '')}
                  onChange={e => {
                    if (currentMode === 'annotate') setSelectedSpeakers([e.target.value]);
                    else setSpeakerPicker(e.target.value);
                  }}
                  className="flex-1 rounded-md border border-slate-200 bg-white px-2 py-1 text-[11px] text-slate-700 focus:border-indigo-300 focus:outline-none">
                  {speakers.map(s => <option key={s}>{s}</option>)}
                </select>
                {currentMode === 'compare' && (
                  <button onClick={addSpeaker} className="grid h-6 w-6 place-items-center rounded-md bg-slate-900 text-white hover:bg-slate-700">
                    <Plus className="h-3 w-3"/>
                  </button>
                )}
              </div>
              <div className="flex flex-wrap gap-1">
                {speakers.map(s => {
                  const active = currentMode === 'annotate' ? selectedSpeakers[0] === s : selectedSpeakers.includes(s);
                  return (
                    <button key={s} onClick={() => toggleSpeaker(s)}
                      className={`inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 font-mono text-[10px] transition ${active ? 'bg-indigo-100 text-indigo-700 ring-1 ring-indigo-200' : 'bg-slate-50 text-slate-400 ring-1 ring-slate-100 hover:text-slate-600'}`}>
                      {s}{active && currentMode === 'compare' && <X className="h-2.5 w-2.5"/>}
                      {active && currentMode === 'annotate' && <Check className="h-2.5 w-2.5"/>}
                    </button>
                  );
                })}
              </div>
              {currentMode === 'annotate' && (
                <p className="mt-2 text-[10px] leading-snug text-slate-400">
                  Concept list scoped to <span className="font-mono text-slate-600">{selectedSpeakers[0]}</span>'s dataset.
                </p>
              )}
            </div>

            {currentMode === 'compare' ? (
              <>
                {/* --- COMPARE: Compute --- */}
                <div className="border-b border-slate-100 p-4">
                  <h4 className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-slate-500">Compute</h4>
                  <select value={computeMode} onChange={e => setComputeMode(e.target.value)}
                    className="w-full rounded-md border border-slate-200 bg-white px-2 py-1.5 text-[11px] text-slate-700 focus:border-indigo-300 focus:outline-none">
                    <option value="cognates">Cognates</option>
                    <option value="similarity">Phonetic similarity</option>
                    <option value="alignment">Alignment</option>
                    <option value="borrowings">Borrowing detection</option>
                  </select>
                  <div className="mt-2 grid grid-cols-2 gap-1.5">
                    <button
                      className="inline-flex items-center justify-center gap-1 rounded-md bg-indigo-600 py-1.5 text-[11px] font-semibold text-white hover:bg-indigo-700 disabled:opacity-50"
                      onClick={() => { void startComputeJob(); }}
                      disabled={computeJobState.status === 'running'}
                    >
                      <Play className="h-3 w-3"/> Run
                    </button>
                    <button
                      className="inline-flex items-center justify-center gap-1 rounded-md border border-slate-200 bg-white py-1.5 text-[11px] font-semibold text-slate-600 hover:bg-slate-50"
                      onClick={() => { void useEnrichmentStore.getState().load(); }}
                    >
                      <RefreshCw className="h-3 w-3"/> Refresh
                    </button>
                  </div>
                  {computeJobState.status === 'running' && (
                    <div className="mt-1 text-[10px] text-indigo-600">
                      Running… {Math.round(computeJobState.progress * 100)}%
                      {computeJobState.etaMs !== null && computeJobState.etaMs > 0 && (
                        <span className="text-slate-400"> · ~{formatEta(computeJobState.etaMs)} left</span>
                      )}
                    </div>
                  )}
                  {computeJobState.status === 'error' && (
                    <div className="mt-1 text-[10px] text-rose-600">{computeJobState.error}</div>
                  )}
                </div>

                {/* --- COMPARE: Status --- */}
                <div className="border-b border-slate-100 p-4">
                  <h4 className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-slate-500">Status</h4>
                  <div className="mb-2 flex items-center gap-2">
                    {speakers.length > 0 || concepts.length > 0 ? (
                      <>
                        <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500"/>
                        <span className="text-[11px] font-semibold text-slate-700">project.json</span>
                        <span className="ml-auto text-[10px] text-slate-400">loaded</span>
                      </>
                    ) : (
                      <>
                        <AlertCircle className="h-3.5 w-3.5 text-amber-500"/>
                        <span className="text-[11px] font-semibold text-slate-700">Workspace empty</span>
                      </>
                    )}
                  </div>
                  {speakers.length === 0 && concepts.length === 0 ? (
                    <div className="rounded-md bg-amber-50 px-3 py-2 text-[11px] text-amber-700">
                      No speakers or concepts imported yet. Use <span className="font-semibold">Import</span> to add data to this workspace.
                    </div>
                  ) : (
                    <div className="grid grid-cols-2 gap-2 text-[11px]">
                      <div className="rounded-md bg-slate-50 px-2 py-1.5">
                        <div className="font-mono text-sm font-semibold text-slate-900">{speakers.length}</div>
                        <div className="text-[9px] uppercase tracking-wider text-slate-400">speakers</div>
                      </div>
                      <div className="rounded-md bg-slate-50 px-2 py-1.5">
                        <div className="font-mono text-sm font-semibold text-slate-900">{concepts.length}</div>
                        <div className="text-[9px] uppercase tracking-wider text-slate-400">concepts</div>
                      </div>
                    </div>
                  )}
                </div>

                {/* --- COMPARE: Filter by tag --- */}
                <div className="border-b border-slate-100 p-4">
                  <h4 className="mb-2 flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
                    <Filter className="h-3 w-3"/> Filter by tag
                  </h4>
                  <div className="space-y-1">
                    {([
                      ['all','All concepts','bg-slate-400'],
                      ['untagged','Untagged','bg-slate-300'],
                      ['review','Review needed','bg-amber-400'],
                      ['confirmed','Confirmed','bg-emerald-500'],
                      ['problematic','Problematic','bg-rose-500'],
                    ] as const).map(([key,label,dot]) => (
                      <button key={key} onClick={() => setTagFilter(key)}
                        className={`flex w-full items-center gap-2 rounded-md px-2 py-1 text-[11px] transition ${tagFilter===key ? 'bg-indigo-50 font-semibold text-indigo-800' : 'text-slate-600 hover:bg-slate-50'}`}>
                        <span className={`h-1.5 w-1.5 rounded-full ${dot}`}/>{label}
                      </button>
                    ))}
                  </div>
                </div>

                <div className="p-4">
                  <h4 className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-slate-500">Decisions</h4>
                  <div className="space-y-1.5">
                    <button
                      className="flex w-full items-center gap-2 rounded-md border border-slate-200 bg-white px-2.5 py-1.5 text-[11px] font-medium text-slate-700 hover:bg-slate-50"
                      onClick={() => loadDecisionsRef.current?.click()}
                    >
                      <Upload className="h-3 w-3"/> Load decisions
                    </button>
                    <button
                      className="flex w-full items-center gap-2 rounded-md bg-emerald-600 px-2.5 py-1.5 text-[11px] font-semibold text-white hover:bg-emerald-700"
                      onClick={() => {
                        const json = JSON.stringify(enrichmentData, null, 2);
                        const blob = new Blob([json], { type: 'application/json' });
                        const url = URL.createObjectURL(blob);
                        const a = document.createElement('a');
                        a.href = url;
                        a.download = 'parse-decisions.json';
                        a.click();
                        URL.revokeObjectURL(url);
                      }}
                    >
                      <Save className="h-3 w-3"/> Save decisions
                    </button>
                    <button
                      onClick={handleExportLingPy}
                      disabled={exporting}
                      className="flex w-full items-center gap-2 rounded-md bg-indigo-600 px-2.5 py-1.5 text-[11px] font-semibold text-white hover:bg-indigo-700 disabled:opacity-50"
                    >
                      <Download className="h-3 w-3"/>
                      {exporting ? 'Exporting…' : 'Export LingPy TSV'}
                    </button>
                  </div>
                </div>
              </>
            ) : (
              <>
                {/* --- ANNOTATE: Phonetic Tools --- */}
                <div className="border-b border-slate-100 p-4">
                  <h4 className="mb-2 flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
                    <Activity className="h-3 w-3"/> Phonetic tools
                  </h4>
                  <p className="mb-3 text-[10px] leading-snug text-slate-400">
                    Tools operate on PARSE's virtual timeline — every action is scoped to the current audio segment.
                  </p>

                  <button className="mb-1.5 flex w-full items-center gap-2 rounded-md bg-indigo-50 px-2.5 py-1.5 text-[11px] font-semibold text-indigo-800 ring-1 ring-indigo-200 hover:bg-indigo-100">
                    <Layers className="h-3.5 w-3.5"/>
                    <span className="flex-1 text-left">Spectrogram workspace</span>
                    <span className="rounded bg-white/70 px-1 font-mono text-[9px] text-indigo-600">ON</span>
                  </button>

                  <div className="space-y-1">
                    {([
                      { icon: AudioLines, label: 'Waveform view', hint: 'Segment-aware' },
                      { icon: Video, label: 'Video clip', hint: 'Synced to timeline' },
                      { icon: Scissors, label: 'Segment controls', hint: 'Split · Trim · Join' },
                      { icon: SlidersHorizontal, label: 'Formant tracker', hint: 'Praat-compatible' },
                      { icon: Mic, label: 'Re-record utterance', hint: 'Overlay on segment' },
                    ] as const).map(({ icon: Icon, label, hint }) => (
                      <button key={label} className="group flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left transition hover:bg-slate-50">
                        <Icon className="h-3.5 w-3.5 text-slate-400 group-hover:text-indigo-600"/>
                        <div className="flex-1 min-w-0">
                          <div className="text-[11px] font-medium text-slate-700 truncate">{label}</div>
                          <div className="text-[9px] text-slate-400 truncate">{hint}</div>
                        </div>
                      </button>
                    ))}
                  </div>
                </div>

                {/* --- ANNOTATE: Tag filter + Save --- */}
                <div className="border-b border-slate-100 p-4">
                  <h4 className="mb-2 flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
                    <Filter className="h-3 w-3"/> Filter concepts
                  </h4>
                  <div className="space-y-1">
                    {([
                      ['all','All concepts','bg-slate-400'],
                      ['untagged','Untagged','bg-slate-300'],
                      ['review','Review needed','bg-amber-400'],
                      ['confirmed','Confirmed','bg-emerald-500'],
                      ['problematic','Problematic','bg-rose-500'],
                    ] as const).map(([key,label,dot]) => (
                      <button key={key} onClick={() => setTagFilter(key)}
                        className={`flex w-full items-center gap-2 rounded-md px-2 py-1 text-[11px] transition ${tagFilter===key ? 'bg-indigo-50 font-semibold text-indigo-800' : 'text-slate-600 hover:bg-slate-50'}`}>
                        <span className={`h-1.5 w-1.5 rounded-full ${dot}`}/>{label}
                      </button>
                    ))}
                  </div>
                </div>

                <div className="p-4">
                  <button
                    className="flex w-full items-center gap-2 rounded-md bg-emerald-600 px-2.5 py-1.5 text-[11px] font-semibold text-white hover:bg-emerald-700"
                    onClick={() => {
                      const speaker = selectedSpeakers[0];
                      if (speaker) void useAnnotationStore.getState().saveSpeaker(speaker);
                    }}
                  >
                    <Save className="h-3 w-3"/> Save annotations
                  </button>
                </div>
              </>
            )}
          </div>
        </aside>
      </div>

      <input
        type="file"
        accept=".json"
        ref={loadDecisionsMenuRef}
        style={{ display: 'none' }}
        onChange={async (e) => {
          const file = e.target.files?.[0];
          if (!file) return;
          try {
            const text = await file.text();
            const data = JSON.parse(text) as Record<string, unknown>;
            await useEnrichmentStore.getState().save(data);
          } catch {
            // non-fatal
          }
          e.target.value = '';
        }}
      />
      <Modal open={importModalOpen} onClose={() => setImportModalOpen(false)} title="Import Speaker">
        <SpeakerImport onImportComplete={handleImportComplete} />
      </Modal>
      <input
        type="file"
        accept=".json"
        ref={loadDecisionsRef}
        style={{ display: 'none' }}
        onChange={async (e) => {
          const file = e.target.files?.[0];
          if (!file) return;
          try {
            const text = await file.text();
            const data = JSON.parse(text) as Record<string, unknown>;
            await useEnrichmentStore.getState().save(data);
          } catch {
            // non-fatal
          }
          e.target.value = '';
        }}
      />
    </div>
  );
}
