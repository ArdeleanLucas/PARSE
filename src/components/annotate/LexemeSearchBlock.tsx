import { useEffect, useState } from 'react';
import { Loader2, Search, X } from 'lucide-react';

import { searchLexeme, type LexemeSearchCandidate } from '../../api/client';
import { usePlaybackStore } from '../../stores/playbackStore';

export interface LexemeSearchBlockProps {
  speaker: string;
  conceptId: string | number;
}

export function LexemeSearchBlock({ speaker, conceptId }: LexemeSearchBlockProps) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<LexemeSearchCandidate[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const requestSeek = usePlaybackStore((s) => s.requestSeek);

  useEffect(() => {
    const q = query.trim();
    if (!q || !speaker) {
      setResults([]);
      setError(null);
      return;
    }
    const variants = q.split(/[\s,;/]+/).filter(Boolean);
    if (variants.length === 0) {
      setResults([]);
      setError(null);
      return;
    }
    const t = setTimeout(async () => {
      setLoading(true);
      setError(null);
      try {
        const res = await searchLexeme(speaker, variants, { conceptId: String(conceptId) });
        setResults(res.candidates);
      } catch (err) {
        setResults([]);
        setError(err instanceof Error ? err.message : 'Search failed');
      } finally {
        setLoading(false);
      }
    }, 300);
    return () => clearTimeout(t);
  }, [query, speaker, conceptId]);

  return (
    <div className="mb-3">
      <div className="mb-1.5 flex items-center gap-1.5 rounded-md border border-slate-200 bg-white px-2 py-1.5">
        <Search className="h-3 w-3 shrink-0 text-slate-400" />
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search & anchor lexeme…"
          aria-label="Search lexeme variants"
          className="min-w-0 flex-1 bg-transparent text-[11px] focus:outline-none"
        />
        {loading && <Loader2 className="h-3 w-3 shrink-0 animate-spin text-slate-400" />}
        {query && !loading && (
          <button onClick={() => setQuery('')} aria-label="Clear search" className="shrink-0 text-slate-400 hover:text-slate-600">
            <X className="h-3 w-3" />
          </button>
        )}
      </div>
      {(error || (query.trim() && !loading && results.length === 0) || results.length > 0) && (
        <div className="max-h-56 overflow-y-auto rounded-md border border-slate-200 bg-white" role="listbox">
          {error && <div className="px-2 py-1.5 text-[10px] text-rose-600">{error}</div>}
          {!error && !loading && results.length === 0 && query.trim() && (
            <div className="px-2 py-1.5 text-[10px] text-slate-400">No matches</div>
          )}
          {results.map((r, i) => (
            <button
              key={`${r.tier}:${r.start}:${i}`}
              role="option"
              onClick={() => requestSeek(r.start)}
              className="flex w-full items-center justify-between gap-2 px-2 py-1.5 text-left hover:bg-indigo-50"
            >
              <div className="flex min-w-0 flex-col gap-0.5">
                <span className="truncate text-[11px] font-semibold text-slate-700">{r.matched_text}</span>
                <span className="text-[9px] text-slate-400">
                  {r.tier} · {r.start.toFixed(2)}s · &ldquo;{r.matched_variant}&rdquo;
                </span>
              </div>
              <span className="shrink-0 rounded-full bg-indigo-50 px-1.5 py-0.5 font-mono text-[9px] text-indigo-700">
                {Math.round(r.score * 100)}%
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
