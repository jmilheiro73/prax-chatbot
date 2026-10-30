"use client";

import { useState } from "react";
import type { ThreadEntry } from "@/lib/api";
import { BrainIcon, ComposeIcon, FileIcon, SidebarIcon, TrashIcon } from "./Icons";

interface SidebarProps {
  threads: ThreadEntry[];
  activeId: string;
  busy: boolean;
  onNew: () => void;
  onOpen: (id: string) => void;
  onDelete: (id: string) => void;
  onToggle: () => void;
  onOpenPanel: (panel: "documents" | "memories") => void;
}

export function Sidebar({ threads, activeId, busy, onNew, onOpen, onDelete, onToggle, onOpenPanel }: SidebarProps) {
  // Apagar pede um segundo clique: a conversa some da lista e a tela não tem desfazer.
  const [confirming, setConfirming] = useState<string | null>(null);

  return (
    <aside className="sidebar">
      <div className="side-top">
        <span className="brand">Prax</span>
        <button type="button" className="icon-button" onClick={onToggle} aria-label="Fechar barra lateral"><SidebarIcon /></button>
      </div>
      <button type="button" className="nav-item" onClick={onNew} disabled={busy}><ComposeIcon /><span>Nova conversa</span></button>
      <button type="button" className="nav-item" onClick={() => onOpenPanel("documents")}><FileIcon /><span>Documentos</span></button>
      <button type="button" className="nav-item" onClick={() => onOpenPanel("memories")}><BrainIcon /><span>Memórias</span></button>
      {threads.length > 0 && <p className="side-label">Conversas</p>}
      <nav className="threads" aria-label="Conversas">
        {threads.map((t) => (
          <div className="thread-row" key={t.thread_id} data-active={t.thread_id === activeId || undefined}>
            <button
              type="button"
              className="nav-item"
              title={t.title}
              aria-current={t.thread_id === activeId ? "page" : undefined}
              onClick={() => onOpen(t.thread_id)}
              disabled={busy}
            >
              <span>{t.title}</span>
            </button>
            <button
              type="button"
              className="thread-delete"
              data-confirming={confirming === t.thread_id || undefined}
              aria-label={confirming === t.thread_id ? `Confirmar: apagar ${t.title}` : `Apagar ${t.title}`}
              title={confirming === t.thread_id ? "Clique de novo para apagar" : "Apagar"}
              disabled={busy}
              onBlur={() => setConfirming(null)}
              onClick={() => {
                if (confirming === t.thread_id) {
                  setConfirming(null);
                  onDelete(t.thread_id);
                } else {
                  setConfirming(t.thread_id);
                }
              }}
            >
              <TrashIcon />
            </button>
          </div>
        ))}
      </nav>
      {activeId && <span className="thread" title={`thread_id: ${activeId}`}>thread {activeId.slice(0, 8)}</span>}
    </aside>
  );
}
