"use client";

import { useState } from "react";
import type { Feedback } from "@/lib/api";
import { Markdown } from "@/lib/markdown";
import { answerRunId, type AssistantTurn, type Block, type TextBlock, type ToolBlock, type Turn } from "@/lib/reducer";
import { CheckIcon, ChevronIcon, CopyIcon, ThumbDownIcon, ThumbUpIcon, XIcon } from "./Icons";
import { isWeather, WeatherCard } from "./WeatherCard";

const TOOL_STATUS = { running: "executando…", done: "concluída", error: "erro" } as const;

export function TurnView({ turn, onFeedback }: { turn: Turn; onFeedback: (runId: string, value: Feedback) => void }) {
  if (turn.role === "user") {
    return <div className="turn user"><div className="bubble">{turn.text}</div></div>;
  }
  // Falhou antes do primeiro token: não há o que mostrar, o erro aparece logo abaixo.
  if (turn.blocks.length === 0 && !turn.streaming) return null;
  const text = turn.blocks.flatMap((b) => (b.kind === "text" ? [b.final ?? b.draft] : [])).join("\n\n");
  const runId = answerRunId(turn);
  return (
    <div className="turn assistant">
      {turn.blocks.map((b, j) => <BlockView block={b} key={j} />)}
      {isThinking(turn) && <div className="thinking" role="status" aria-label="Pensando" />}
      {!turn.streaming && text && (
        <div className="turn-actions">
          <CopyButton text={text} />
          {runId && !turn.interrupted && <FeedbackButtons value={turn.feedback} onChange={(value) => onFeedback(runId, value)} />}
          {turn.tokens > 0 && <span className="turn-tokens" title="Tokens gastos nesta resposta, segundo a API">{turn.tokens} tokens</span>}
        </div>
      )}
    </div>
  );
}

/** Antes do primeiro token e depois da tool nada chega pelo stream: sem isto a tela parece travada. */
function isThinking(turn: AssistantTurn) {
  if (!turn.streaming) return false;
  const last = turn.blocks.at(-1);
  return !last || (last.kind === "tool_call" && last.status !== "running");
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);

  function copy() {
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    }).catch(() => {});
  }

  return (
    <button type="button" className="icon-button" onClick={copy} aria-label={copied ? "Copiado" : "Copiar resposta"} title={copied ? "Copiado" : "Copiar"}>
      {copied ? <CheckIcon /> : <CopyIcon />}
    </button>
  );
}

/** 👍/👎 é o sinal de eval online (Live 08); o 👎 alimenta o dataset pelo `evals/export_feedback.py`. */
function FeedbackButtons({ value, onChange }: { value: Feedback; onChange: (value: Feedback) => void }) {
  return (
    <>
      <button type="button" className="icon-button" aria-pressed={value === "up"} aria-label="Boa resposta" title="Boa resposta" onClick={() => onChange(value === "up" ? null : "up")}><ThumbUpIcon /></button>
      <button type="button" className="icon-button" aria-pressed={value === "down"} aria-label="Resposta ruim" title="Resposta ruim" onClick={() => onChange(value === "down" ? null : "down")}><ThumbDownIcon /></button>
    </>
  );
}

/** Renderers separados por família de evento (AC-06): texto do modelo × tool. */
function BlockView({ block }: { block: Block }) {
  return block.kind === "text" ? <TextView block={block} /> : <ToolView block={block} />;
}

function TextView({ block }: { block: TextBlock }) {
  return (
    <div className={`text ${block.final === null ? "draft" : ""}`}>
      <Markdown text={block.final ?? block.draft} />
    </div>
  );
}

/** Uma linha discreta com o resultado à vista (AC-07); clicar abre entrada e resultado completos. */
function ToolView({ block }: { block: ToolBlock }) {
  const result = block.output === null ? null : parseOutput(block.output);
  if (block.status === "done" && block.name === "get_weather" && isWeather(result)) return <WeatherCard weather={result} />;
  return (
    <details className="tool" data-status={block.status}>
      <summary>
        <span className="tool-icon">
          {block.status === "running" ? <span className="spinner" /> : block.status === "done" ? <CheckIcon /> : <XIcon />}
        </span>
        <code>{block.name}</code>
        <span className="tool-status">{TOOL_STATUS[block.status]}</span>
        {result !== null && <span className="tool-preview">{preview(block.name, result)}</span>}
        <ChevronIcon />
      </summary>
      <div className="tool-body">
        <span className="label">entrada</span>
        <ToolData value={block.input} />
        {result !== null && (
          <>
            <span className="label">resultado</span>
            <ToolData value={result} />
          </>
        )}
      </div>
    </details>
  );
}

interface SearchHit {
  document: string;
  section: string;
  text: string;
}

function isSearchHits(value: unknown): value is SearchHit[] {
  return Array.isArray(value) && value.length > 0 && value.every((v) => typeof v === "object" && v !== null && "document" in v && "text" in v);
}

/** Objeto plano vira pares chave/valor; trechos viram fontes; o resto sai como veio. */
function ToolData({ value }: { value: unknown }) {
  if (isSearchHits(value)) {
    return (
      <ul className="sources">
        {value.map((hit, i) => (
          <li key={i}>
            <strong>{[hit.document, hit.section].filter(Boolean).join(" › ")}</strong>
            <span>{hit.text}</span>
          </li>
        ))}
      </ul>
    );
  }
  if (isFlatObject(value)) {
    return (
      <dl className="kv">
        {Object.entries(value).map(([k, v]) => <div key={k}><dt>{k}</dt><dd>{String(v)}</dd></div>)}
      </dl>
    );
  }
  return <pre>{typeof value === "string" ? value : JSON.stringify(value, null, 2)}</pre>;
}

function preview(name: string, value: unknown) {
  if (isSearchHits(value)) {
    const documents = [...new Set(value.map((hit) => hit.document))];
    return `${value.length} trecho(s) em ${documents.join(", ")}`;
  }
  if (name === "search_documents" && Array.isArray(value)) return "nenhum trecho encontrado";
  if (name === "list_documents" && Array.isArray(value)) return `${value.length} documento(s)`;
  if (name === "delegate_research" && isObject(value) && typeof value.summary === "string") return value.summary;
  if (isFlatObject(value)) return Object.values(value).map(String).join(" · ");
  return typeof value === "string" ? value : JSON.stringify(value);
}

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isFlatObject(value: unknown): value is Record<string, unknown> {
  if (!isObject(value)) return false;
  const values = Object.values(value);
  return values.length > 0 && values.every((v) => typeof v !== "object" || v === null);
}

/** A tool devolve dict, mas o `ToolMessage` traz como texto JSON. */
function parseOutput(output: string): unknown {
  try { return JSON.parse(output); } catch { return output; }
}
