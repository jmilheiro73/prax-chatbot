"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { createMemory, deleteMemory, fetchMemories, updateMemory, type MemoryType, type UserMemory } from "@/lib/api";
import { CheckIcon, PencilIcon, TrashIcon, XIcon } from "./Icons";
import { Panel } from "./Panel";

const TYPE_LABEL: Record<MemoryType, string> = { profile: "sempre", fact: "quando for relevante" };

/** Memória editável (Live 05): o que a LLM guardou, o usuário corrige ou apaga. */
export function MemoryPanel({ onClose }: { onClose: () => void }) {
  const [memories, setMemories] = useState<UserMemory[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<{ id: string; content: string } | null>(null);
  const [draft, setDraft] = useState("");
  const [draftType, setDraftType] = useState<MemoryType>("fact");

  const run = useCallback(async (action: () => Promise<unknown>) => {
    setError(null);
    try {
      await action();
      setMemories(await fetchMemories());
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, []);

  useEffect(() => { void run(async () => {}); }, [run]);

  function add(e: FormEvent) {
    e.preventDefault();
    const content = draft.trim();
    if (!content) return;
    setDraft("");
    void run(() => createMemory(draftType, content));
  }

  function saveEdit(e: FormEvent) {
    e.preventDefault();
    if (!editing || !editing.content.trim()) return;
    const { id, content } = editing;
    setEditing(null);
    void run(() => updateMemory(id, content.trim()));
  }

  return (
    <Panel title="Memórias" onClose={onClose}>
      <p className="panel-note">O que o Prax guardou sobre você e usa em qualquer conversa.</p>
      <form className="memory-add" onSubmit={add}>
        <input value={draft} onChange={(e) => setDraft(e.target.value)} placeholder="Adicionar uma memória" aria-label="Nova memória" maxLength={500} />
        <select value={draftType} onChange={(e) => setDraftType(e.target.value as MemoryType)} aria-label="Quando usar">
          <option value="fact">Quando for relevante</option>
          <option value="profile">Sempre</option>
        </select>
        <button type="submit" className="file-button" disabled={!draft.trim()}>Adicionar</button>
      </form>
      {error && <p className="panel-error" role="alert">Não deu certo: {error}</p>}
      {memories?.length === 0 && <p className="panel-empty">Nenhuma memória ainda.</p>}
      <ul className="panel-list">
        {memories?.map((m) =>
          editing?.id === m.id ? (
            <li key={m.id}>
              <form className="memory-edit" onSubmit={saveEdit}>
                <input value={editing.content} onChange={(e) => setEditing({ id: m.id, content: e.target.value })} aria-label="Editar memória" maxLength={500} autoFocus />
                <button type="submit" className="icon-button" aria-label="Salvar" title="Salvar"><CheckIcon /></button>
                <button type="button" className="icon-button" onClick={() => setEditing(null)} aria-label="Cancelar" title="Cancelar"><XIcon /></button>
              </form>
            </li>
          ) : (
            <li key={m.id}>
              <div className="panel-item">
                <strong className="memory-content">{m.content}</strong>
                <span>{TYPE_LABEL[m.type]}</span>
              </div>
              <button type="button" className="icon-button" onClick={() => setEditing({ id: m.id, content: m.content })} aria-label={`Editar: ${m.content}`} title="Editar"><PencilIcon /></button>
              <button type="button" className="icon-button" onClick={() => void run(() => deleteMemory(m.id))} aria-label={`Apagar: ${m.content}`} title="Apagar"><TrashIcon /></button>
            </li>
          ),
        )}
      </ul>
    </Panel>
  );
}
