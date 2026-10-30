"use client";

import { useCallback, useEffect, useRef, useState, type WheelEvent } from "react";
import { Composer } from "@/components/Composer";
import { ChevronIcon, ComposeIcon, SidebarIcon } from "@/components/Icons";
import { KnowledgePanel } from "@/components/KnowledgePanel";
import { MemoryPanel } from "@/components/MemoryPanel";
import { Sidebar } from "@/components/Sidebar";
import { TurnView } from "@/components/TurnView";
import { API, deleteThread, fetchSnapshot, fetchThreads, sendFeedback, type Feedback, type ThreadEntry } from "@/lib/api";
import type { StreamEvent } from "@/lib/events";
import { applyEvent, closeInterrupted, hydrateTurns, newAssistantTurn, type AssistantTurn, type Turn } from "@/lib/reducer";
import { readSse } from "@/lib/sse";

const THREAD_KEY = "prax-chatbot:thread_id";
const SUGGESTIONS = ["Qual o clima em São Paulo?", "Vai chover no Rio hoje?", "O que você consegue fazer?"];
const TITLE_DELAY_MS = 3000; // o título é gerado em segundo plano, depois da resposta

function newThreadId() {
  return crypto.randomUUID();
}

export default function Page() {
  const [threadId, setThreadId] = useState<string>("");
  const [threads, setThreads] = useState<ThreadEntry[]>([]);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [summary, setSummary] = useState<string | null>(null);
  const [checkpointAlive, setCheckpointAlive] = useState(true);
  const [ready, setReady] = useState(false); // snapshot já respondeu; antes disso enviar sobrescreveria a tela
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [navToggled, setNavToggled] = useState(false); // inverte o padrão do CSS: aberta no desktop, fechada no celular
  const [panel, setPanel] = useState<"documents" | "memories" | null>(null);
  const activeThread = useRef(""); // para ignorar a resposta que chega depois de trocar de conversa
  const abort = useRef<AbortController | null>(null);
  const feed = useRef<HTMLElement>(null);
  const followStream = useRef(true);
  const lastScrollTop = useRef(0);

  const refreshThreads = useCallback(async () => {
    try { setThreads(await fetchThreads()); } catch { /* back fora do ar: a lista fica como está */ }
  }, []);

  // thread_id vive no browser; o histórico vive no back — o front nunca o reenvia.
  useEffect(() => {
    let id = "";
    try { id = localStorage.getItem(THREAD_KEY) ?? ""; } catch {}
    if (!id) { id = newThreadId(); try { localStorage.setItem(THREAD_KEY, id); } catch {} }
    activeThread.current = id;
    setThreadId(id);
    void refreshThreads();
    void loadSnapshot(id);
  }, [refreshThreads]);

  useEffect(() => {
    const el = feed.current;
    if (!el || !followStream.current) return;
    el.scrollTop = el.scrollHeight;
    lastScrollTop.current = el.scrollTop;
  }, [turns, error]);

  // Rolar para cima solta o stream; descer até perto do fim retoma (a folga cobre a linha que chega no meio do gesto).
  function onFeedScroll() {
    const el = feed.current;
    if (!el || el.scrollTop === lastScrollTop.current) return; // o scroll foi o do próprio acompanhamento
    if (el.scrollTop < lastScrollTop.current) followStream.current = false;
    else if (el.scrollHeight - el.scrollTop - el.clientHeight <= 40) followStream.current = true;
    lastScrollTop.current = el.scrollTop;
  }

  // Na roda, solta já no evento: um token pode sobrescrever a rolagem antes de ela aparecer em scrollTop.
  function onFeedWheel(e: WheelEvent<HTMLElement>) {
    if (e.deltaY < 0 && e.currentTarget.scrollTop > 0) followStream.current = false;
  }

  async function loadSnapshot(id: string) {
    try {
      const snap = await fetchSnapshot(id);
      if (activeThread.current !== id) return;
      setSummary(snap.summary ?? null);
      setCheckpointAlive(snap.checkpoint_alive);
      setTurns(hydrateTurns(snap.transcript ?? []));
    } catch { /* back fora do ar: a UI ainda abre */ }
    finally { if (activeThread.current === id) setReady(true); }
  }

  function switchThread(id: string) {
    activeThread.current = id;
    followStream.current = true;
    try { localStorage.setItem(THREAD_KEY, id); } catch {}
    setThreadId(id); setTurns([]); setSummary(null); setError(null); setCheckpointAlive(true);
  }

  function resetThread() {
    switchThread(newThreadId());
    setReady(true);
  }

  function openThread(id: string) {
    if (id === threadId) return;
    switchThread(id);
    setReady(false);
    void loadSnapshot(id);
  }

  async function removeThread(id: string) {
    try {
      await deleteThread(id);
      if (id === threadId) resetThread();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
    void refreshThreads();
  }

  function rate(turnIndex: number, runId: string, value: Feedback) {
    setTurns((t) => t.map((turn, i) => (i === turnIndex && turn.role === "assistant" ? { ...turn, feedback: value } : turn)));
    void sendFeedback(threadId, runId, value).catch(() => setError("não consegui registrar sua avaliação"));
  }

  async function send(message: string) {
    if (busy || !ready) return;
    setError(null); setBusy(true);
    followStream.current = true;
    const controller = new AbortController();
    abort.current = controller;

    let assistant: AssistantTurn = newAssistantTurn(true);
    setTurns((t) => [...t, { role: "user", text: message }, assistant]);
    const replaceLast = (next: AssistantTurn) => setTurns((t) => [...t.slice(0, -1), next]);

    try {
      const res = await fetch(`${API}/agent/execute`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message, thread_id: threadId }),
        signal: controller.signal,
      }).catch((err) => {
        if (err instanceof DOMException && err.name === "AbortError") throw err;
        throw new Error(`a API não respondeu em ${API}`);
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
      // Parar não é erro: o fetch abortado fecha a conexão, e o back cancela a chamada à OpenAI (zombie request, Aula 02).
      if (!(err instanceof DOMException && err.name === "AbortError")) setError(err instanceof Error ? err.message : String(err));
      replaceLast(closeInterrupted(assistant));
    } finally {
      abort.current = null;
      setBusy(false);
      void refreshThreads();
      setTimeout(() => void refreshThreads(), TITLE_DELAY_MS);
    }
  }

  async function loadSnapshotSummary(id: string) {
    try {
      const snap = await fetchSnapshot(id);
      if (activeThread.current === id) { setSummary(snap.summary ?? null); setCheckpointAlive(snap.checkpoint_alive); }
    } catch {}
  }

  const isEmpty = turns.length === 0;
  const expired = !checkpointAlive && !busy;

  return (
    <div className="app" data-nav-toggled={navToggled || undefined}>
      <Sidebar
        threads={threads}
        activeId={threadId}
        busy={busy}
        onNew={() => { resetThread(); setNavToggled(false); }}
        onOpen={(id) => { openThread(id); setNavToggled(false); }}
        onDelete={(id) => void removeThread(id)}
        onToggle={() => setNavToggled((t) => !t)}
        onOpenPanel={(p) => { setPanel(p); setNavToggled(false); }}
      />
      <div className="backdrop" onClick={() => setNavToggled(false)} />

      <div className="main" data-empty={isEmpty || undefined} data-ready={ready || undefined}>
        <header className="topbar">
          <button type="button" className="icon-button when-collapsed" onClick={() => setNavToggled((t) => !t)} aria-label="Abrir barra lateral"><SidebarIcon /></button>
          <span className="brand when-collapsed">Prax</span>
          <button type="button" className="icon-button when-collapsed" onClick={resetThread} disabled={busy} aria-label="Nova conversa"><ComposeIcon /></button>
        </header>

        {/* key={summary}: a cada compactação o painel remonta e pisca, para dar para ver acontecendo. */}
        {summary && (
          <details className="memory" key={summary} open={isEmpty}>
            <summary><ChevronIcon />Resumo injetado no system prompt</summary>
            <div className="memory-body">
              {expired && <p className="memory-note">As mensagens saíram da memória de curto prazo; o agente continua a partir deste resumo.</p>}
              <p>{summary}</p>
            </div>
          </details>
        )}

        <main className="feed" ref={feed} onScroll={onFeedScroll} onWheel={onFeedWheel}>
          <div className="column" role="log" aria-live="polite" aria-busy={busy}>
            {isEmpty && <h1 className="hero">Como posso ajudar?</h1>}
            {expired && !summary && !isEmpty && (
              <p className="expired-note">O agente não lembra mais destas mensagens: o histórico de curto prazo expirou.</p>
            )}
            {turns.map((turn, i) => <TurnView turn={turn} key={i} onFeedback={(runId, value) => rate(i, runId, value)} />)}
            {error && (
              <div className="error" role="alert">
                <strong>Não consegui concluir a resposta.</strong>
                <code>{error}</code>
              </div>
            )}
          </div>
        </main>

        <Composer disabled={!ready} streaming={busy} onSend={(message) => void send(message)} onStop={() => abort.current?.abort()} />

        {isEmpty && (
          <div className="suggestions">
            {SUGGESTIONS.map((s) => <button type="button" key={s} onClick={() => void send(s)}>{s}</button>)}
          </div>
        )}
      </div>

      {panel === "documents" && <KnowledgePanel onClose={() => setPanel(null)} />}
      {panel === "memories" && <MemoryPanel onClose={() => setPanel(null)} />}
    </div>
  );
}
