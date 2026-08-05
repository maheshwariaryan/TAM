"use client";

import { useMemo, useState } from "react";
import { Bot, ChevronRight, Sparkles, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useGlobalStore } from "@/lib/store/use-global-store";
import { useThemeStore } from "@/lib/store/use-theme-store";

type ChatMessage = {
  role: "user" | "assistant";
  text: string;
  mode?: string;
};

export function TamLlmSidebar() {
  const { deal, dealId, period, basis } = useGlobalStore();
  const theme = useThemeStore((s) => s.theme);
  const isDark = theme === "dark";
  const [open, setOpen] = useState(false);
  const [launching, setLaunching] = useState(false);
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      role: "assistant",
      text: "I am TAM LLM. Ask me anything about this company: trends, risk drivers, tie-outs, and what changed since last refresh.",
      mode: "system",
    },
  ]);

  const prompts = useMemo(
    () => [
      `What are the biggest risk drivers for ${deal}?`,
      "Summarize what changed since the last run.",
      "Give me an executive one-minute deal brief.",
      "What should I validate before IC discussion?",
    ],
    [deal]
  );

  const ask = async (input?: string) => {
    const text = (input ?? question).trim();
    if (!text || loading) return;

    setLoading(true);
    setMessages((prev) => [...prev, { role: "user", text }]);
    setQuestion("");

    try {
      const res = await fetch("/api/inquiry/assistant", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: text, deal, dealId, period, basis }),
      });
      const json = (await res.json()) as { answer?: string; mode?: string };
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          text: json.answer ?? "I could not generate a response.",
          mode: json.mode,
        },
      ]);
    } catch {
      setMessages((prev) => [...prev, { role: "assistant", text: "Assistant is temporarily unavailable.", mode: "error" }]);
    } finally {
      setLoading(false);
    }
  };

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => {
          if (launching) return;
          setLaunching(true);
          window.setTimeout(() => {
            setOpen(true);
            setLaunching(false);
          }, 260);
        }}
        className={`fixed bottom-6 right-6 z-40 inline-flex items-center gap-2 overflow-hidden rounded-full px-4 py-3 text-sm font-semibold transition hover:-translate-y-0.5 ${launching ? "tam-ai-launch" : ""}`}
      >
        <span
          className={`absolute inset-0 rounded-full transition-colors ${
            isDark
              ? "border border-slate-300/80 bg-white"
              : "border border-cyan-300/40 bg-slate-900"
          }`}
        />
        {launching ? <span className="tam-ai-shockwave pointer-events-none absolute inset-0 rounded-full" /> : null}
        <span
          className={`tam-ai-ping relative inline-flex h-6 w-6 items-center justify-center rounded-full ${
            isDark ? "bg-slate-200 text-slate-900" : "bg-cyan-400/20 text-cyan-100"
          }`}
        >
          <Bot className="h-4 w-4" />
        </span>
        <span className={`relative ${isDark ? "text-slate-900" : "text-cyan-100"}`}>Open TAM LLM</span>
        <ChevronRight className={`relative h-4 w-4 ${isDark ? "text-slate-900" : "text-cyan-100"}`} />
      </button>
    );
  }

  return (
    <div className="tam-ai-slide fixed bottom-4 right-4 top-24 z-50 flex w-[380px] max-w-[calc(100vw-2rem)] flex-col overflow-hidden rounded-2xl border border-slate-300 bg-white/95 text-slate-900 shadow-[0_16px_50px_rgba(2,132,199,0.25)] backdrop-blur-xl">
      <div className="relative shrink-0 border-b border-slate-200 p-4">
        <div className="pointer-events-none absolute -right-8 -top-8 h-24 w-24 rounded-full border border-cyan-300/35 tam-ai-orbit" />
        <div className="pointer-events-none absolute right-8 top-5 h-10 w-10 rounded-full border border-emerald-300/40 tam-ai-orbit-rev" />

        <div className="flex items-start justify-between gap-2">
          <div>
            <p className="inline-flex items-center gap-1 text-xs uppercase tracking-[0.18em] text-cyan-700">
              <Sparkles className="h-3 w-3" /> TAM LLM
            </p>
            <p className="mt-1 text-sm font-semibold">Live Deal Copilot</p>
            <p className="text-xs text-slate-500">{deal} • {period} • {basis}</p>
          </div>
          <button type="button" className="rounded p-1 text-slate-500 hover:bg-slate-100 hover:text-slate-900" onClick={() => setOpen(false)}>
            <X className="h-4 w-4" />
          </button>
        </div>
      </div>

      <div className="max-h-44 shrink-0 space-y-2 overflow-y-auto border-b border-slate-200 p-3">
        {prompts.map((prompt) => (
          <button
            key={prompt}
            type="button"
            disabled={loading}
            onClick={() => ask(prompt)}
            className="w-full rounded-md border border-cyan-100 bg-cyan-50 px-3 py-2 text-left text-xs text-cyan-900 transition hover:bg-cyan-100 disabled:opacity-50"
          >
            {prompt}
          </button>
        ))}
      </div>

      <div className="min-h-0 flex-1 space-y-2 overflow-y-auto p-3">
        {messages.map((message, idx) => (
          <div
            key={idx}
            className={`rounded-xl p-2.5 text-sm ${
              message.role === "user"
                ? "ml-8 border border-cyan-200 bg-cyan-100"
                : "mr-8 border border-slate-200 bg-white"
            }`}
          >
            <p className="mb-1 text-[10px] uppercase tracking-wide text-slate-500">
              {message.role}
              {message.mode ? ` (${message.mode})` : ""}
            </p>
            <p className="text-slate-800">{message.text}</p>
          </div>
        ))}
        {loading ? <div className="rounded-xl border border-cyan-200 bg-cyan-50 p-2 text-xs text-cyan-900">TAM LLM is reasoning...</div> : null}
      </div>

      <div className="shrink-0 space-y-2 border-t border-slate-200 p-3">
        <textarea
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="Ask TAM LLM about trends, risk, tie-outs, or storyline..."
          className="min-h-16 max-h-28 w-full rounded-lg border border-slate-300 bg-white p-2 text-sm text-slate-900 outline-none placeholder:text-slate-500 focus:border-cyan-500"
        />
        <Button className="w-full" onClick={() => ask()} disabled={loading || question.trim().length < 2}>
          Ask TAM LLM
        </Button>
      </div>
    </div>
  );
}
