"use client";
import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { usePathname } from "next/navigation";
import { apiJson } from "@/lib/api";

export interface SkillMeta {
  id: string;
  name: string;
  short_label: string;
  description: string;
  color: string;
  max_steps: number;
  allowed_tools: string[];
  requires_literature: boolean;
  example_prompt: string;
}

export interface AgentStatusInfo {
  version: string;
  llm_configured: boolean;
  model: string;
  quota: {
    allowed: boolean;
    reason?: string | null;
    used_hourly: number;
    remaining_hourly: number;
    hourly_limit: number;
    used_daily: number;
    remaining_daily: number;
    daily_limit: number;
    reset_in_sec: number;
  };
  literature_primary: string;
  literature_fallback: string;
  clinical_trials: string;
}

export interface AgentStep {
  step?: number;
  type: "thinking" | "reflection" | "tool";
  name: string;
  tool?: string;
  args?: string;
  status: "running" | "done" | "error" | "skipped";
  detail?: string;
  ms?: number;
}

export interface AgentTurn {
  id: string;
  session_id?: string;
  query: string;
  status: "streaming" | "ok" | "needs_input" | "out_of_scope" | "stopped" | "error";
  skill_id?: string;
  skill_name?: string;
  short_label?: string;
  color?: string;
  mode_requested?: string;
  mode_effective?: string;
  quota_notice?: string | null;
  quota?: AgentStatusInfo["quota"];
  steps: AgentStep[];
  facts: Array<{ label: string; value: string }>;
  table: { columns: Array<{ key: string; label: string }>; rows: any[] };
  kprl_table?: { columns: Array<{ key: string; label: string }>; rows: any[] } | null;
  comparison?: any;
  literature: any[];
  clinical_trials: any[];
  links: Array<{ label: string; href: string }>;
  summary: string;
  verification?: any;
  usage?: { prompt_tokens: number; completion_tokens: number; total_tokens: number };
  suggestions: string[];
  elapsed_ms?: number;
  error?: string;
}

const DEFAULT_SKILLS: SkillMeta[] = [
  { id: "disease-repurposing", name: "Disease-to-Evidence Repurposing", short_label: "Disease -> Evidence", description: "", color: "#2563eb", max_steps: 6, allowed_tools: [], requires_literature: true, example_prompt: "" },
  { id: "toxicity-rescue", name: "Compound Safety & Toxicity Rescue", short_label: "Safety & Rescue", description: "", color: "#dc2626", max_steps: 5, allowed_tools: [], requires_literature: true, example_prompt: "" },
  { id: "target-to-lead", name: "Target-to-Lead & Genetic Mimicry", short_label: "Target -> Lead", description: "", color: "#d97706", max_steps: 5, allowed_tools: [], requires_literature: true, example_prompt: "" },
  { id: "structure-moa-evidence", name: "Structure Similarity & MoA Validation", short_label: "Structure -> MoA", description: "", color: "#4f46e5", max_steps: 4, allowed_tools: [], requires_literature: true, example_prompt: "" },
  { id: "literature-evidence", name: "Bidirectional Literature & Clinical Audit", short_label: "Literature & Trials", description: "", color: "#0284c7", max_steps: 5, allowed_tools: [], requires_literature: true, example_prompt: "" },
  { id: "compound-compare", name: "Head-to-Head Compound Comparison", short_label: "Compare Drugs", description: "", color: "#0d9488", max_steps: 5, allowed_tools: [], requires_literature: true, example_prompt: "" },
];

function makeId(prefix = "np"): string {
  return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
}

interface AgentCtxValue {
  prompt: string;
  setPrompt: (s: string) => void;
  agentMode: "auto" | "fast";
  setAgentMode: (m: "auto" | "fast") => void;
  selectedSkill: string | null;
  setSelectedSkill: (s: string | null) => void;
  includeLiterature: boolean;
  setIncludeLiterature: (v: boolean) => void;
  skills: SkillMeta[];
  statusInfo: AgentStatusInfo | null;
  open: boolean;
  setOpen: (v: boolean) => void;
  loading: boolean;
  turns: AgentTurn[];
  result: AgentTurn | null;
  error: string;
  focusTick: number;
  sessionId: string;
  fill: (text: string, skillId?: string | null) => void;
  run: (overrideText?: string, opts?: { skillId?: string | null; mode?: "auto" | "fast" }) => Promise<void>;
  stop: () => void;
  newSession: () => void;
  clearResult: () => void;
}

const AgentContext = createContext<AgentCtxValue | null>(null);

export function AgentProvider({ children }: { children: React.ReactNode }) {
  const pathname = usePathname() || "/";
  const [prompt, setPrompt] = useState("");
  const [agentMode, setAgentMode] = useState<"auto" | "fast">("auto");
  const [selectedSkill, setSelectedSkill] = useState<string | null>(null);
  const [includeLiterature, setIncludeLiterature] = useState(true);
  const [skills, setSkills] = useState<SkillMeta[]>(DEFAULT_SKILLS);
  const [statusInfo, setStatusInfo] = useState<AgentStatusInfo | null>(null);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [turns, setTurns] = useState<AgentTurn[]>([]);
  const [error, setError] = useState("");
  const [focusTick, setFocusTick] = useState(0);
  const [sessionId, setSessionId] = useState<string>("");
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    try {
      const saved = window.sessionStorage.getItem("np_session_id");
      if (saved) {
        setSessionId(saved);
      } else {
        const fresh = makeId("sess");
        window.sessionStorage.setItem("np_session_id", fresh);
        setSessionId(fresh);
      }
    } catch {
      setSessionId(makeId("sess"));
    }

    apiJson<AgentStatusInfo>("/api/v1/agent/status", undefined, 10000)
      .then((d) => setStatusInfo(d))
      .catch(() => {});
    apiJson<{ skills: SkillMeta[] }>("/api/v1/agent/skills", undefined, 10000)
      .then((d) => {
        if (d?.skills?.length) setSkills(d.skills);
      })
      .catch(() => {});
  }, []);

  const fill = useCallback(
    (text: string, skillId?: string | null) => {
      setPrompt(text);
      if (skillId !== undefined) setSelectedSkill(skillId);
      setError("");
      setFocusTick((t) => t + 1);
      if (pathname !== "/") {
        setOpen(true);
      }
    },
    [pathname]
  );

  const stop = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    setLoading(false);
    setTurns((prev) =>
      prev.map((t) =>
        t.status === "streaming"
          ? { ...t, status: "stopped", summary: t.summary || "Execution stopped by user." }
          : t
      )
    );
  }, []);

  const newSession = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    setLoading(false);
    const oldSid = sessionId;
    if (oldSid) {
      fetch(`/api/v1/agent/session/${encodeURIComponent(oldSid)}`, { method: "DELETE" }).catch(() => {});
    }
    const fresh = makeId("sess");
    setSessionId(fresh);
    try {
      window.sessionStorage.setItem("np_session_id", fresh);
    } catch {}
    setTurns([]);
    setError("");
  }, [sessionId]);

  const run = useCallback(
    async (overrideText?: string, opts?: { skillId?: string | null; mode?: "auto" | "fast" }) => {
      const q = (overrideText !== undefined ? overrideText : prompt).trim();
      if (!q) return;
      setPrompt("");

      abortRef.current?.abort();
      const ctrl = new AbortController();
      abortRef.current = ctrl;

      const turnId = makeId("turn");
      const sid = sessionId || makeId("sess");
      if (!sessionId) setSessionId(sid);

      const useMode = opts?.mode || agentMode;
      const useSkill = opts?.skillId !== undefined ? opts.skillId : selectedSkill;

      const initialTurn: AgentTurn = {
        id: turnId,
        session_id: sid,
        query: q,
        status: "streaming",
        mode_requested: useMode,
        steps: [],
        facts: [],
        table: { columns: [], rows: [] },
        literature: [],
        clinical_trials: [],
        links: [],
        summary: "",
        suggestions: [],
      };

      setTurns((prev) => [...prev, initialTurn]);
      setLoading(true);
      setError("");

      const patchTurn = (updater: (t: AgentTurn) => AgentTurn) => {
        setTurns((prev) => prev.map((t) => (t.id === turnId ? updater(t) : t)));
      };

      try {
        const res = await fetch("/api/v1/agent/stream", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            text: q,
            session_id: sid,
            mode: useMode,
            skill_id: useSkill || null,
            include_literature: includeLiterature,
          }),
          signal: ctrl.signal,
        });

        if (!res.ok || !res.body) {
          const msg = await res.text().catch(() => res.statusText);
          throw new Error(`HTTP ${res.status}: ${msg.slice(0, 140)}`);
        }

        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        const handleEvent = (evName: string, payload: any) => {
          if (evName === "session") {
            if (payload.session_id) setSessionId(payload.session_id);
            if (payload.quota) {
              setStatusInfo((prev) => (prev ? { ...prev, quota: payload.quota } : prev));
            }
            patchTurn((t) => ({
              ...t,
              session_id: payload.session_id || t.session_id,
              mode_effective: payload.mode_effective,
              quota_notice: payload.quota_notice,
              quota: payload.quota,
            }));
          } else if (evName === "skill_selected") {
            patchTurn((t) => ({
              ...t,
              skill_id: payload.skill_id,
              skill_name: payload.skill_name,
              short_label: payload.short_label,
              color: payload.color,
            }));
          } else if (evName === "thinking") {
            patchTurn((t) => ({
              ...t,
              steps: [
                ...t.steps,
                { type: "thinking", name: "Agent Reasoning", detail: payload.text, status: "done" },
              ],
            }));
          } else if (evName === "reflection") {
            patchTurn((t) => ({
              ...t,
              steps: [
                ...t.steps,
                { type: "reflection", name: "Safety / Policy Reflection", tool: "nephrosafe_policy", detail: payload.text, status: "done" },
              ],
            }));
          } else if (evName === "tool_start") {
            patchTurn((t) => ({
              ...t,
              steps: [
                ...t.steps,
                {
                  step: payload.step,
                  type: "tool",
                  name: payload.tool,
                  tool: payload.tool,
                  args: payload.args,
                  status: "running",
                },
              ],
            }));
          } else if (evName === "tool_result") {
            patchTurn((t) => {
              const idx = t.steps.findIndex((s) => s.type === "tool" && s.step === payload.step);
              const updatedStep: AgentStep = {
                step: payload.step,
                type: "tool",
                name: payload.tool,
                tool: payload.tool,
                args: idx >= 0 ? t.steps[idx].args : undefined,
                status: payload.status || "done",
                detail: payload.detail,
                ms: payload.ms,
              };
              const nextSteps =
                idx >= 0
                  ? t.steps.map((s, i) => (i === idx ? updatedStep : s))
                  : [...t.steps, updatedStep];
              return {
                ...t,
                steps: nextSteps,
                table: payload.table?.rows?.length ? payload.table : t.table,
                facts: payload.facts?.length ? payload.facts : t.facts,
                kprl_table: payload.kprl_table || t.kprl_table,
                comparison: payload.comparison || t.comparison,
                literature: payload.literature ? [...t.literature, payload.literature] : t.literature,
                clinical_trials: payload.clinical_trials ? [...t.clinical_trials, payload.clinical_trials] : t.clinical_trials,
                links: payload.links ? [...t.links, ...payload.links.filter((l: any) => !t.links.some((x) => x.href === l.href))] : t.links,
              };
            });
          } else if (evName === "verification") {
            patchTurn((t) => ({ ...t, verification: payload }));
          } else if (evName === "done") {
            if (payload.quota) {
              setStatusInfo((prev) => (prev ? { ...prev, quota: payload.quota } : prev));
            }
            patchTurn((t) => ({
              ...t,
              ...payload,
              status: payload.status || "ok",
              steps: payload.steps?.length ? payload.steps : t.steps,
            }));
          } else if (evName === "error") {
            patchTurn((t) => ({
              ...t,
              status: "error",
              error: payload.message || "Agent execution failed",
              summary: t.summary || payload.message || "Execution error",
            }));
          }
        };

        while (true) {
          const { done, value } = await reader.read();
          if (done) {
            if (buffer.trim()) {
              buffer += "\n\n";
            } else {
              break;
            }
          } else {
            buffer += decoder.decode(value, { stream: true });
          }
          const frames = buffer.split(/\r?\n\r?\n/);
          buffer = frames.pop() || "";
          for (const frame of frames) {
            if (!frame.trim() || frame.startsWith(":")) continue;
            let evName = "message";
            const dataLines: string[] = [];
            for (const line of frame.split(/\r?\n/)) {
              if (line.startsWith("event:")) evName = line.slice(6).trim();
              else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
            }
            if (dataLines.length) {
              try {
                handleEvent(evName, JSON.parse(dataLines.join("\n")));
              } catch {}
            }
          }
          if (done) break;
        }
      } catch (err: any) {
        if (err?.name === "AbortError") {
          patchTurn((t) => ({ ...t, status: "stopped", summary: t.summary || "Stopped by user." }));
        } else {
          const msg = String(err?.message || err);
          setError(msg);
          patchTurn((t) => ({ ...t, status: "error", error: msg, summary: t.summary || msg }));
        }
      } finally {
        setLoading(false);
        if (abortRef.current === ctrl) abortRef.current = null;
      }
    },
    [prompt, sessionId, agentMode, selectedSkill, includeLiterature]
  );

  const result = turns.length ? turns[turns.length - 1] : null;

  return (
    <AgentContext.Provider
      value={{
        prompt,
        setPrompt,
        agentMode,
        setAgentMode,
        selectedSkill,
        setSelectedSkill,
        includeLiterature,
        setIncludeLiterature,
        skills,
        statusInfo,
        open,
        setOpen,
        loading,
        turns,
        result,
        error,
        focusTick,
        sessionId,
        fill,
        run,
        stop,
        newSession,
        clearResult: newSession,
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
