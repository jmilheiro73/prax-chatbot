/**
 * Cliente SSE sobre `fetch` (EventSource não faz POST).
 *
 * Lê o corpo como stream, corta em frames (`\n\n`) e entrega `{ event, data }` já parseados.
 * Só isto: quem decide o que fazer com cada evento é o reducer da UI.
 */

export interface SseFrame {
  event: string;
  data: string;
}

export async function* readSse(response: Response): AsyncGenerator<SseFrame> {
  if (!response.body) throw new Error("resposta sem corpo");
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    let sep: number;
    while ((sep = buffer.indexOf("\n\n")) !== -1) {
      const raw = buffer.slice(0, sep);
      buffer = buffer.slice(sep + 2);
      const frame = parseFrame(raw);
      if (frame) yield frame;
    }
  }
}

function parseFrame(raw: string): SseFrame | null {
  let event = "message";
  const data: string[] = [];
  for (const line of raw.split("\n")) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) data.push(line.slice(5).trimStart());
  }
  if (data.length === 0) return null;
  return { event, data: data.join("\n") };
}
