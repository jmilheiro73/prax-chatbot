"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import type { StreamEvent } from "@/lib/events";
import { applyEvent, type AssistantTurn, type Block, type Turn } from "@/lib/reducer";
import { readSse } from "@/lib/sse";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const THREAD_KEY = "prax-chatbot:thread_id";

function newThreadId() {
  return crypto.randomUUID();
}

export default function Page() {
  const [threadId, setThreadId] = useState<string>("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [summary, setSummary] = useState<string | null>(null);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const bottom = useRef<HTMLDivElement>(null);

  // thread_id vive no browser; o histórico vive no back (checkpoint) — o front nunca o reenvia.
  useEffect(() => {
    let id = "";
    try { id = localStorage.getItem(THREAD_KEY) ?? ""; } catch {}
    if (!id) { id = newThreadId(); try { localStorage.setItem(THREAD_KEY, id); } catch {} }
    setThreadId(id);
    void loadSnapshot(id);
  }, []);

  useEffect(() => { bottom.current?.scrollIntoView({ behavior: "smooth" }); }, [turns]);

  async function loadSnapshot(id: string) {
    try {
      const r = await fetch(`${API}/agent/threads/${id}`);
      if (!r.ok) return;
      const snap = await r.json();
      setSummary(snap.summary ?? null);
      // Hidratação simples: reconstrói os turnos a partir do checkpoint quente (se ainda existir).
      const hydrated: Turn[] = [];
      for (const m of snap.messages as Array<{ type: string; content: unknown; tool_calls?: unknown[] }>) {
        const text = typeof m.content === "string" ? m.content : "";
        if (m.type === "human") hydrated.push({ role: "user", text });
        else if (m.type === "ai" && text) hydrated.push({ role: "assistant", streaming: false, blocks: [{ kind: "text", runId: "hydrated", draft: text, final: text }] });
      }
      setTurns(hydrated);
    } catch { /* back fora do ar: a UI ainda abre */ }
  }

  function resetThread() {
    const id = newThreadId();
    try { localStorage.setItem(THREAD_KEY, id); } catch {}
    setThreadId(id); setTurns([]); setSummary(null); setError(null);
  }

  async function send(e: FormEvent) {
    e.preventDefault();
    const message = input.trim();
    if (!message || busy) return;
    setInput(""); setError(null); setBusy(true);

    let assistant: AssistantTurn = { role: "assistant", blocks: [], streaming: true };
    setTurns((t) => [...t, { role: "user", text: message }, assistant]);
    const replaceLast = (next: AssistantTurn) => setTurns((t) => [...t.slice(0, -1), next]);

    try {
      const res = await fetch(`${API}/agent/execute`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message, thread_id: threadId }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);

      for await (const frame of readSse(res)) {
        const ev = JSON.parse(frame.data) as StreamEvent;
        if (ev.event !== frame.event) throw new Error(`frame '${frame.event}' com payload '${ev.event}'`);
        assistant = applyEvent(assistant, ev); // lança em tipo desconhecido (AC-06)
        replaceLast(assistant);
      }
      assistant = { ...assistant, streaming: false };
      replaceLast(assistant);
      void loadSnapshotSummary(threadId);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      replaceLast({ ...assistant, streaming: false });
    } finally {
      setBusy(false);
    }
  }

  async function loadSnapshotSummary(id: string) {
    try {
      const r = await fetch(`${API}/agent/threads/${id}`);
      if (r.ok) setSummary((await r.json()).summary ?? null);
    } catch {}
  }

  return (
    <main>
      <header>
        <h1>Prax Chatbot</h1>
        <span className="thread">thread {threadId.slice(0, 8)} <button onClick={resetThread}>nova conversa</button></span>
      </header>
      {summary && <div className="summary"><strong>summary injetado no system prompt:</strong>{"\n"}{summary}</div>}

      {turns.map((turn, i) =>
        turn.role === "user" ? (
          <div className="turn user" key={i}><div className="bubble">{turn.text}</div></div>
        ) : (
          <div className="turn" key={i}><div className="assistant">
            {turn.blocks.length === 0 && turn.streaming && <div className="text draft"></div>}
            {turn.blocks.map((b, j) => <BlockView block={b} key={j} />)}
          </div></div>
        ),
      )}
      {error && <div className="error">Erro: {error}</div>}
      <div ref={bottom} />

      <form onSubmit={send}>
        <div className="row">
          <input value={input} onChange={(e) => setInput(e.target.value)} placeholder="Qual o clima em São Paulo?" disabled={busy} autoFocus />
          <button type="submit" disabled={busy || !input.trim()}>{busy ? "…" : "Enviar"}</button>
        </div>
      </form>
    </main>
  );
}

/** Renderers separados por família de evento (AC-06): texto do modelo × tool. */
function BlockView({ block }: { block: Block }) {
  if (block.kind === "text") {
    const isDraft = block.final === null;
    return <div className={`block text ${isDraft ? "draft" : ""}`}>{isDraft ? block.draft : block.final}</div>;
  }
  return (
    <div className="block tool">
      <div className="head">
        <span>🔧 {block.name}</span>
        <span className="status">{block.status === "running" ? "executando…" : block.status === "done" ? "concluída" : "erro"}</span>
      </div>
      <div className="label">input</div>
      <pre>{JSON.stringify(block.input, null, 2)}</pre>
      {block.output !== null && (<><div className="label">resultado</div><pre>{block.output}</pre></>)}
    </div>
  );
}
