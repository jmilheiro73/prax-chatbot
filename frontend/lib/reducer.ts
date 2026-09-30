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
}

export interface UserTurn {
  role: "user";
  text: string;
}

export type Turn = UserTurn | AssistantTurn;

export function applyEvent(turn: AssistantTurn, ev: StreamEvent): AssistantTurn {
  if (isChatModelEvent(ev.event)) return applyChatModel(turn, ev);
  if (isToolEvent(ev.event)) return applyTool(turn, ev);
  // AC-06: tipo fora do contrato é bug de contrato, não algo a ignorar em silêncio.
  throw new Error(`evento fora do contrato: ${ev.event}`);
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
      return { ...turn, blocks };
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
      if (idx !== -1) blocks[idx] = { ...(blocks[idx] as ToolBlock), status: "done", output: text };
      return { ...turn, blocks };
    }
    case "on_tool_error":
      if (idx !== -1) blocks[idx] = { ...(blocks[idx] as ToolBlock), status: "error", output: String(ev.data.output ?? "erro") };
      return { ...turn, blocks };
  }
  return turn;
}
