import { AlertCircle, CheckCircle2, KeyRound, Loader2, ShieldCheck, Zap } from "lucide-react";
import { useState } from "react";
import { getAuthStatus, saveApiKey } from "../../../api/client";
import type { ProviderApiKeyFormProps } from "./types";

export function ProviderApiKeyForm({
  defaultProvider = "xai",
  onCancel,
  onSaved,
}: ProviderApiKeyFormProps) {
  const [provider, setProvider] = useState<"xai" | "openai">(defaultProvider);
  const [apiKey, setApiKey] = useState("");
  const [status, setStatus] = useState<"idle" | "testing" | "success" | "error">("idle");
  const [message, setMessage] = useState<string | null>(null);

  async function handleTestAndSave() {
    if (!apiKey.trim()) return;
    setStatus("testing");
    setMessage(null);
    try {
      await saveApiKey(apiKey.trim(), provider);
      const freshStatus = await getAuthStatus();
      setStatus("success");
      setMessage("Key saved and connected.");
      await onSaved(freshStatus);
    } catch (error) {
      setStatus("error");
      setMessage(error instanceof Error ? error.message : "Failed to save API key.");
    }
  }

  return (
    <div className="space-y-3 rounded-xl border border-slate-200 bg-white p-6 shadow-[0_1px_0_rgba(15,23,42,0.03)]">
      <div className="text-[11px] text-slate-500">
        Either xAI or OpenAI works for Grokipedia. xAI is tried first; OpenAI is the fallback.
      </div>

      <div className="flex gap-2 rounded-lg bg-slate-100 p-0.5">
        <button
          type="button"
          onClick={() => setProvider("xai")}
          className={`flex flex-1 items-center justify-center gap-1 rounded-md px-3 py-1 text-[11px] font-semibold transition ${
            provider === "xai" ? "bg-white text-slate-900 shadow-sm" : "text-slate-600 hover:text-slate-900"
          }`}
        >
          <Zap className="h-3 w-3" /> xAI / Grok
        </button>
        <button
          type="button"
          onClick={() => setProvider("openai")}
          className={`flex flex-1 items-center justify-center gap-1 rounded-md px-3 py-1 text-[11px] font-semibold transition ${
            provider === "openai" ? "bg-white text-slate-900 shadow-sm" : "text-slate-600 hover:text-slate-900"
          }`}
        >
          <KeyRound className="h-3 w-3" /> OpenAI
        </button>
      </div>

      <label className="block">
        <span className="text-[11px] font-medium text-slate-600">{provider === "xai" ? "xAI API Key" : "OpenAI API Key"}</span>
        <input
          type="password"
          value={apiKey}
          onChange={(event) => {
            setApiKey(event.target.value);
            setStatus("idle");
            setMessage(null);
          }}
          placeholder={provider === "xai" ? "xai-..." : "sk-..."}
          className="mt-1 w-full rounded-lg border border-slate-200 bg-slate-50/60 px-3 py-2 font-mono text-[12px] text-slate-800 placeholder:text-slate-400 focus:border-slate-400 focus:bg-white focus:outline-none focus:ring-2 focus:ring-slate-100"
        />
      </label>

      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={() => void handleTestAndSave()}
          disabled={!apiKey.trim() || status === "testing"}
          className="inline-flex items-center gap-1.5 rounded-lg bg-slate-900 px-3 py-1.5 text-[11px] font-semibold text-white transition hover:bg-slate-700 disabled:cursor-not-allowed disabled:bg-slate-300"
        >
          {status === "testing" && <Loader2 className="h-3 w-3 animate-spin" />}
          {status === "success" && <CheckCircle2 className="h-3 w-3 text-emerald-300" />}
          {status === "error" && <AlertCircle className="h-3 w-3 text-rose-300" />}
          Test & save
        </button>
        <button
          type="button"
          onClick={onCancel}
          className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-[11px] font-semibold text-slate-700 hover:bg-slate-50"
        >
          Cancel
        </button>
      </div>

      {message && (
        <div className={`text-[11px] ${status === "success" ? "text-emerald-600" : "text-rose-600"}`}>
          {message}
        </div>
      )}

      <div className="flex items-center gap-1.5 text-[11px] text-slate-400">
        <ShieldCheck className="h-3 w-3" />
        Stored locally in <code className="font-mono">config/auth_tokens.json</code>. Same key powers the chat assistant.
      </div>
    </div>
  );
}
