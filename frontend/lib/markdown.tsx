/**
 * Markdown mínimo para a resposta do modelo, sem dependência nova.
 *
 * Tudo vira elemento React (nada de HTML cru), então o texto do modelo nunca é interpretado como HTML.
 * Cobre parágrafo, título, lista e bloco de código; inline: **negrito**, *itálico*, `código` e [link](https://…).
 * O rascunho também passa por aqui: marcação ainda aberta aparece crua até chegar o token que a fecha.
 */

import type { ReactNode } from "react";

const FENCE = /^\s*```/;
const HEADING = /^(#{1,6})\s+(.*)$/;
const UL_ITEM = /^\s*[-*+]\s+(.*)$/;
const OL_ITEM = /^\s*(\d+)[.)]\s+(.*)$/;
// Link só http(s): o React não bloqueia `javascript:` em href, e o texto vem do modelo.
const INLINE = /`([^`\n]+)`|\*\*(.+?)\*\*|(?<![\w*])\*([^*\s](?:[^*\n]*[^*\s])?)\*(?![\w*])|\[([^\]\n]+)\]\((https?:\/\/[^\s)]+)\)/g;

export function Markdown({ text }: { text: string }) {
  return <>{parseBlocks(text)}</>;
}

function isBlockStart(line: string) {
  return FENCE.test(line) || HEADING.test(line) || UL_ITEM.test(line) || OL_ITEM.test(line);
}

function parseBlocks(text: string): ReactNode[] {
  const lines = text.split("\n");
  const out: ReactNode[] = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];
    const key = out.length;

    if (!line.trim()) {
      i++;
    } else if (FENCE.test(line)) {
      const code: string[] = [];
      i++;
      while (i < lines.length && !FENCE.test(lines[i])) code.push(lines[i++]);
      i++; // a cerca de fechamento (no rascunho, pode ainda não ter chegado)
      out.push(<pre key={key}><code>{code.join("\n")}</code></pre>);
    } else if (HEADING.test(line)) {
      const [, level, title] = line.match(HEADING)!;
      const Tag = level.length <= 2 ? "h3" : "h4";
      out.push(<Tag key={key}>{parseInline(title)}</Tag>);
      i++;
    } else if (UL_ITEM.test(line) || OL_ITEM.test(line)) {
      const ordered = OL_ITEM.test(line);
      const pattern = ordered ? OL_ITEM : UL_ITEM;
      const start = ordered ? Number(line.match(OL_ITEM)![1]) : undefined; // lista quebrada no meio não recomeça do 1
      const items: ReactNode[] = [];
      for (let m; i < lines.length && (m = lines[i].match(pattern)); i++) {
        items.push(<li key={items.length}>{parseInline(m[m.length - 1])}</li>);
      }
      out.push(ordered ? <ol key={key} start={start}>{items}</ol> : <ul key={key}>{items}</ul>);
    } else {
      const paragraph: string[] = [];
      while (i < lines.length && lines[i].trim() && !isBlockStart(lines[i])) paragraph.push(lines[i++]);
      out.push(<p key={key}>{parseInline(paragraph.join("\n"))}</p>);
    }
  }
  return out;
}

function parseInline(text: string): ReactNode[] {
  const out: ReactNode[] = [];
  let last = 0;

  for (const m of text.matchAll(INLINE)) {
    if (m.index > last) out.push(text.slice(last, m.index));
    const [whole, code, bold, italic, label, href] = m;
    if (code) out.push(<code key={m.index}>{code}</code>);
    else if (bold) out.push(<strong key={m.index}>{parseInline(bold)}</strong>);
    else if (italic) out.push(<em key={m.index}>{parseInline(italic)}</em>);
    else out.push(<a key={m.index} href={href} target="_blank" rel="noopener noreferrer">{label}</a>);
    last = m.index + whole.length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}
