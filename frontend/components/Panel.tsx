"use client";

import { ReactNode, useEffect } from "react";
import { XIcon } from "./Icons";

/** A janela sobre o chat, usada por Documentos e Memórias. */
export function Panel({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) {
  useEffect(() => {
    const onKey = (e: globalThis.KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="panel-backdrop" onClick={onClose}>
      <div className="panel" role="dialog" aria-modal="true" aria-label={title} onClick={(e) => e.stopPropagation()}>
        <header className="panel-head">
          <h2>{title}</h2>
          <button type="button" className="icon-button" onClick={onClose} aria-label="Fechar" autoFocus><XIcon /></button>
        </header>
        <div className="panel-body">{children}</div>
      </div>
    </div>
  );
}
