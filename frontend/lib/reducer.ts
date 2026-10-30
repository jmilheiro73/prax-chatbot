/**
 * Máquina de estados da conversa (P1 · AC-06 / AC-07).
 *
 * Um turno do assistente é uma lista de BLOCOS em ordem de chegada:
 *   - `text`      rascunho (tokens concatenados) -> final (o `on_chat_model_end` substitui)
 *   - `tool_call` a chamada (nome + input), depois o resultado (`on_tool_end`)
 *
 * Cada passada do modelo (run_id) tem o seu bloco de texto: a passada que só pede a tool
 * não tem texto; a passada final tem. Tool call, resultado e texto final são estados separados.
 */

import {
  contentToText,
  isChatModelEvent,
  isToolEvent,
  type SerializedMessage,
  type StreamEvent,
} from "./events";

export interface TextBlock {
  kind: "text";
  runId: string;
  draft: string;
  final: string | null;
}

export interface ToolBlock {
  kind: "tool_call";
  runId: string;
  callId?: string;
  name: string;
  input: unknown;
  status: "running" | "done" | "error";
  output: string | null;
}

export type Block = TextBlock | ToolBlock;

export interface AssistantTurn {
  role: "assistant";
  blocks: Block[];
  streaming: boolean;
  tokens: number; // soma do `usage` real de cada passada do modelo (Aula 02), não uma estimativa
  feedback: "up" | "down" | null;
  interrupted: boolean; // parou antes do fim: não chegou ao evento terminal, então o back não gravou esta resposta
}

export interface UserTurn {
  role: "user";
  text: string;
}

export type Turn = UserTurn | AssistantTurn;

/** Uma linha do transcript durável (`GET /agent/threads/{id}`). */
export interface TranscriptMessage extends SerializedMessage {
  run_id?: string | null;
  feedback?: "up" | "down" | null;
  usage?: { total_tokens?: number } | null;
}

export function newAssistantTurn(streaming: boolean): AssistantTurn {
  return { role: "assistant", blocks: [], streaming, tokens: 0, feedback: null, interrupted: false };
}

/** Fecha um turno que parou no meio (botão parar ou erro): nada fica com o cursor nem em "executando…". */
export function closeInterrupted(turn: AssistantTurn): AssistantTurn {
  const blocks = turn.blocks.map((b): Block => {
    if (b.kind === "text") return b.final === null ? { ...b, final: b.draft } : b;
    return b.status === "running" ? { ...b, status: "error", output: "interrompida" } : b;
  });
  return { ...turn, blocks, streaming: false, interrupted: true };
}

/** O run do último texto: é por ele que o back acha a resposta ao receber 👍 ou 👎. */
export function answerRunId(turn: AssistantTurn): string | null {
  const text = [...turn.blocks].reverse().find((b) => b.kind === "text");
  return text ? text.runId : null;
}

export function applyEvent(turn: AssistantTurn, ev: StreamEvent): AssistantTurn {
  if (isChatModelEvent(ev.event)) return applyChatModel(turn, ev);
  if (isToolEvent(ev.event)) return applyTool(turn, ev);
  // AC-06: tipo fora do contrato é bug de contrato, não algo a ignorar em silêncio.
  throw new Error(`evento fora do contrato: ${ev.event}`);
}

/**
 * Reconstrói os turnos a partir do transcript durável, no mesmo formato do stream:
 * tudo entre duas mensagens humanas é um turno só, com texto e tools na ordem original.
 */
export function hydrateTurns(messages: TranscriptMessage[]): Turn[] {
  const turns: Turn[] = [];
  for (const m of messages) {
    if (m.type === "human") {
      turns.push({ role: "user", text: contentToText(m.content) });
      continue;
    }
    let turn = turns.at(-1);
    if (turn?.role !== "assistant") {
      turn = newAssistantTurn(false);
      turns.push(turn);
    }
    if (m.type === "ai") {
      const runId = m.run_id ?? "hydrated";
      const text = contentToText(m.content);
      if (text) turn.blocks.push({ kind: "text", runId, draft: text, final: text });
      for (const call of m.tool_calls ?? []) {
        // Sem resultado até o fim do transcript, a tool foi interrompida (o usuário parou o stream).
        turn.blocks.push({ kind: "tool_call", runId, callId: call.id, name: call.name, input: call.args, status: "error", output: "interrompida" });
      }
      turn.tokens += m.usage?.total_tokens ?? 0;
      turn.feedback = m.feedback ?? turn.feedback;
    } else if (m.type === "tool") {
      const call = turn.blocks.find((b): b is ToolBlock => b.kind === "tool_call" && b.callId === m.tool_call_id);
      if (call) {
        call.output = contentToText(m.content);
        call.status = m.status === "error" ? "error" : "done";
      }
    }
  }
  return turns.filter((t) => t.role === "user" || t.blocks.length > 0);
}

function applyChatModel(turn: AssistantTurn, ev: StreamEvent): AssistantTurn {
  const blocks = [...turn.blocks];
  const idx = blocks.findIndex((b) => b.kind === "text" && b.runId === ev.run_id);

  switch (ev.event) {
    case "on_chat_model_start":
      return turn; // o bloco nasce no primeiro token; passada só-tool não gera texto vazio
    case "on_chat_model_stream": {
      const piece = contentToText(ev.data.chunk?.content);
      if (!piece) return turn;
      if (idx === -1) blocks.push({ kind: "text", runId: ev.run_id, draft: piece, final: null });
      else blocks[idx] = { ...(blocks[idx] as TextBlock), draft: (blocks[idx] as TextBlock).draft + piece };
      return { ...turn, blocks };
    }
    case "on_chat_model_end": {
      const output = ev.data.output as SerializedMessage | undefined;
      const text = contentToText(output?.content);
      if (idx !== -1) blocks[idx] = { ...(blocks[idx] as TextBlock), final: text }; // substitui o rascunho
      else if (text) blocks.push({ kind: "text", runId: ev.run_id, draft: text, final: text });
      return { ...turn, blocks, tokens: turn.tokens + (output?.usage_metadata?.total_tokens ?? 0) };
    }
  }
  return turn;
}

function applyTool(turn: AssistantTurn, ev: StreamEvent): AssistantTurn {
  const blocks = [...turn.blocks];
  const idx = blocks.findIndex((b) => b.kind === "tool_call" && b.runId === ev.run_id);

  switch (ev.event) {
    case "on_tool_start":
      blocks.push({ kind: "tool_call", runId: ev.run_id, name: ev.name, input: ev.data.input, status: "running", output: null });
      return { ...turn, blocks };
    case "on_tool_end": {
      const output = ev.data.output as SerializedMessage | string | undefined;
      const text = typeof output === "string" ? output : contentToText(output?.content);
      const failed = typeof output === "object" && output?.status === "error";
      if (idx !== -1) blocks[idx] = { ...(blocks[idx] as ToolBlock), status: failed ? "error" : "done", output: text };
      return { ...turn, blocks };
    }
    case "on_tool_error":
      if (idx !== -1) blocks[idx] = { ...(blocks[idx] as ToolBlock), status: "error", output: String(ev.data.output ?? "erro") };
      return { ...turn, blocks };
  }
  return turn;
}
