/**
 * Contrato de eventos (P1 · AC-04/AC-05/AC-06).
 *
 * O back manda o StreamEvent inteiro do LangChain (`astream_events` v2) em cada frame SSE.
 * Aqui só modelamos o que o front usa. Qualquer `event` fora de `on_chat_model_*` / `on_tool_*`
 * é erro (AC-06) — o servidor prometeu `include_types=["chat_model", "tool"]`.
 */

export type ChatModelEventName =
  | "on_chat_model_start"
  | "on_chat_model_stream"
  | "on_chat_model_end";

export type ToolEventName = "on_tool_start" | "on_tool_end" | "on_tool_error";

export type StreamEventName = ChatModelEventName | ToolEventName;

/** Conteúdo de mensagem no LangChain 1.x: string ou lista de blocos. */
export type MessageContent = string | Array<{ type?: string; text?: string } | string>;

export interface ToolCall {
  id?: string;
  name: string;
  args: Record<string, unknown>;
}

export interface SerializedMessage {
  type?: string;
  content: MessageContent;
  tool_calls?: ToolCall[];
  tool_call_id?: string;
  name?: string;
  status?: string; // no ToolMessage: "success" ou "error"
  usage_metadata?: { total_tokens?: number } | null;
}

export interface StreamEvent {
  event: string;
  name: string;
  run_id: string;
  tags?: string[];
  metadata?: Record<string, unknown>;
  parent_ids?: string[];
  data: {
    input?: unknown;
    output?: unknown;
    chunk?: SerializedMessage;
  };
}

export function isChatModelEvent(name: string): name is ChatModelEventName {
  return name.startsWith("on_chat_model_");
}

export function isToolEvent(name: string): name is ToolEventName {
  return name.startsWith("on_tool_");
}

export function contentToText(content: MessageContent | undefined): string {
  if (!content) return "";
  if (typeof content === "string") return content;
  return content
    .map((block) => (typeof block === "string" ? block : block.type === "text" ? block.text ?? "" : ""))
    .join("");
}
