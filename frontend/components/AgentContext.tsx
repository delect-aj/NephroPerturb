"use client";
import React, { createContext, useCallback, useContext, useState } from "react";
import { usePathname } from "next/navigation";

interface AgentCtxValue {
  prompt: string;
  setPrompt: (s: string) => void;
  useLLM: boolean;
  setUseLLM: (v: boolean) => void;
  open: boolean;
  setOpen: (v: boolean) => void;
  loading: boolean;
  result: any;
  error: string;
  focusTick: number;
  fill: (text: string) => void;
  run: (overrideText?: string) => Promise<void>;
  clearResult: () => void;
}

const AgentContext = createContext<AgentCtxValue | null>(null);

export function AgentProvider({ children }: { children: React.ReactNode }) {
  const pathname = usePathname() || "/";
  const [prompt, setPrompt] = useState("");
  const [useLLM, setUseLLM] = useState(false);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState("");
  const [focusTick, setFocusTick] = useState(0);

  const fill = useCallback(
    (text: string) => {
      setPrompt(text);
      setError("");
      setFocusTick((t) => t + 1);
      if (pathname !== "/") {
        setOpen(true);
      }
    },
    [pathname]
  );

  const run = useCallback(
    async (overrideText?: string) => {
      const q = (overrideText !== undefined ? overrideText : prompt).trim();
      if (!q) return;
      if (overrideText !== undefined) {
        setPrompt(overrideText);
      }
      setLoading(true);
      setError("");
      try {
        const res = await fetch("/api/v1/agent/run", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ text: q, use_llm: useLLM }),
        });
        const body = await res.json();
        if (!res.ok) throw new Error(body.detail || "Agent execution failed");
        setResult(body);
      } catch (err: any) {
        setError(String(err?.message || err));
      } finally {
        setLoading(false);
      }
    },
    [prompt, useLLM]
  );

  const clearResult = useCallback(() => {
    setResult(null);
    setError("");
  }, []);

  return (
    <AgentContext.Provider
      value={{
        prompt,
        setPrompt,
        useLLM,
        setUseLLM,
        open,
        setOpen,
        loading,
        result,
        error,
        focusTick,
        fill,
        run,
        clearResult,
      }}
    >
      {children}
    </AgentContext.Provider>
  );
}

export function useAgent() {
  const ctx = useContext(AgentContext);
  if (!ctx) throw new Error("useAgent must be used inside AgentProvider");
  return ctx;
}
