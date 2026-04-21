import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

function splitCompactMarkdown(text: string): string {
  let normalized = text;

  for (let attempt = 0; attempt < 4; attempt += 1) {
    const next = normalized
      .replace(/([^\n])\s+(#{1,6}\s+)/g, "$1\n\n$2")
      .replace(/(#{1,6}[^\n]+?)\s+(-\s+)/g, "$1\n$2")
      .replace(/(#{1,6}[^\n]+?)\s+(\d+\.\s+)/g, "$1\n$2")
      .replace(/([.!?`:])\s+(-\s+)/g, "$1\n$2")
      .replace(/([.!?`:])\s+(\d+\.\s+)/g, "$1\n\n$2")
      .replace(/(\n-\s[^\n]+?)\s+(-\s+)/g, "$1\n$2")
      .replace(/(\n\d+\.\s[^\n]+?)\s+(\d+\.\s+)/g, "$1\n$2");

    if (next === normalized) {
      return normalized;
    }

    normalized = next;
  }

  return normalized;
}

export function normalizeChatMarkdown(content: string): string {
  let text = String(content ?? "").replace(/\r\n?/g, "\n").trim();
  if (!text) return "";

  const wrappedFence = text.match(/^```(?:markdown|md|mdx|text)?\s*\n([\s\S]*?)\n```$/i);
  if (wrappedFence && /(^|[\n ])(#{1,6}\s|[-*+]\s|\d+\.\s|\*\*|`)/m.test(wrappedFence[1])) {
    text = wrappedFence[1].trim();
  }

  text = splitCompactMarkdown(text);

  const output: string[] = [];
  for (const rawLine of text.split("\n")) {
    const line = rawLine.trimEnd();
    const trimmed = line.trim();

    if (!trimmed) {
      if (output[output.length - 1] !== "") {
        output.push("");
      }
      continue;
    }

    const isHeading = /^#{1,6}\s/.test(trimmed);
    const isOrderedList = /^\d+\.\s/.test(trimmed);
    if ((isHeading || isOrderedList) && output.length > 0 && output[output.length - 1] !== "") {
      output.push("");
    }

    output.push(trimmed);
  }

  return output.join("\n").replace(/\n{3,}/g, "\n\n").trim();
}

const markdownComponents: Components = {
  h1: ({ children }) => <h1 className="mt-4 text-[15px] font-semibold text-slate-900 first:mt-0">{children}</h1>,
  h2: ({ children }) => <h2 className="mt-4 text-[14px] font-semibold text-slate-900 first:mt-0">{children}</h2>,
  h3: ({ children }) => <h3 className="mt-4 text-[13px] font-semibold uppercase tracking-[0.08em] text-slate-700 first:mt-0">{children}</h3>,
  h4: ({ children }) => <h4 className="mt-3 text-[13px] font-semibold text-slate-800 first:mt-0">{children}</h4>,
  p: ({ children }) => <p className="mt-2 whitespace-pre-wrap first:mt-0">{children}</p>,
  ul: ({ children }) => <ul className="mt-2 list-disc space-y-1 pl-5 first:mt-0">{children}</ul>,
  ol: ({ children }) => <ol className="mt-2 list-decimal space-y-1 pl-5 first:mt-0">{children}</ol>,
  li: ({ children }) => <li className="pl-1">{children}</li>,
  strong: ({ children }) => <strong className="font-semibold text-slate-900">{children}</strong>,
  a: ({ children, href }) => (
    <a className="font-medium text-indigo-700 underline underline-offset-2" href={href} rel="noreferrer" target="_blank">
      {children}
    </a>
  ),
  blockquote: ({ children }) => <blockquote className="mt-3 border-l-2 border-slate-300 pl-3 italic text-slate-600">{children}</blockquote>,
  hr: () => <hr className="my-3 border-slate-200" />,
  pre: ({ children }) => <pre className="mt-3 overflow-x-auto rounded-xl bg-slate-900 px-3 py-2.5 text-[12px] leading-5 text-slate-50">{children}</pre>,
  code: ({ children, className }) => {
    const codeText = String(children ?? "").replace(/\n$/, "");
    const isBlockCode = codeText.includes("\n") || Boolean(className);

    if (isBlockCode) {
      return <code className="font-mono text-[12px] text-slate-50">{codeText}</code>;
    }

    return <code className="rounded bg-slate-100 px-1 py-0.5 font-mono text-[12px] text-slate-700">{codeText}</code>;
  },
};

export interface ChatMarkdownProps {
  content: string;
}

export function ChatMarkdown({ content }: ChatMarkdownProps) {
  return (
    <div className="text-[13px] leading-6 text-slate-800">
      <ReactMarkdown components={markdownComponents} remarkPlugins={[remarkGfm]}>
        {normalizeChatMarkdown(content)}
      </ReactMarkdown>
    </div>
  );
}
