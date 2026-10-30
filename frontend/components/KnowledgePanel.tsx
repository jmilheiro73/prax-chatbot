"use client";

import { ChangeEvent, useCallback, useEffect, useState } from "react";
import { deleteDocument, fetchDocuments, submitDocument, type KnowledgeDocument } from "@/lib/api";
import { TrashIcon } from "./Icons";
import { Panel } from "./Panel";

const STATUS: Record<KnowledgeDocument["status"], string> = {
  queued: "na fila",
  chunking: "dividindo em trechos",
  embedding: "gerando embeddings",
  ready: "pronto",
  error: "erro",
};
const POLL_MS = 1500;

/** O upload responde 202 e o worker segue em segundo plano (Aula 14): por isso a lista se atualiza sozinha. */
export function KnowledgePanel({ onClose }: { onClose: () => void }) {
  const [documents, setDocuments] = useState<KnowledgeDocument[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setDocuments(await fetchDocuments());
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);

  const processing = documents?.some((d) => d.status !== "ready" && d.status !== "error") ?? false;
  useEffect(() => {
    if (!processing) return;
    const timer = setInterval(() => void refresh(), POLL_MS);
    return () => clearInterval(timer);
  }, [processing, refresh]);

  async function onFiles(e: ChangeEvent<HTMLInputElement>) {
    const files = Array.from(e.target.files ?? []);
    e.target.value = ""; // sem isto, escolher o mesmo arquivo de novo não dispara o evento
    setError(null);
    try {
      for (const file of files) await submitDocument(file.name, await file.text());
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
    await refresh();
  }

  async function remove(id: string) {
    await deleteDocument(id);
    await refresh();
  }

  return (
    <Panel title="Documentos" onClose={onClose}>
      <p className="panel-note">O Prax busca nestes arquivos para responder. Aceita <code>.md</code> e <code>.txt</code>.</p>
      <label className="file-button">
        Enviar arquivos
        <input type="file" accept=".md,.markdown,.txt,text/plain,text/markdown" multiple onChange={onFiles} />
      </label>
      {error && <p className="panel-error" role="alert">Não deu certo: {error}</p>}
      {documents?.length === 0 && <p className="panel-empty">Nenhum documento ainda.</p>}
      <ul className="panel-list">
        {documents?.map((d) => (
          <li key={d.id}>
            <div className="panel-item">
              <strong title={d.name}>{d.name}</strong>
              <span data-status={d.status}>
                {STATUS[d.status]}
                {d.status === "ready" && ` · ${d.chunk_count} trecho(s)`}
                {d.status === "ready" && d.reused_chunks > 0 && ` · ${d.reused_chunks} sem mudança`}
                {d.status === "error" && d.error && `: ${d.error}`}
              </span>
            </div>
            <button type="button" className="icon-button" onClick={() => void remove(d.id)} aria-label={`Apagar ${d.name}`} title="Apagar"><TrashIcon /></button>
          </li>
        ))}
      </ul>
    </Panel>
  );
}
