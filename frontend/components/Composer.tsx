"use client";

import { KeyboardEvent, useLayoutEffect, useRef, useState } from "react";
import { ArrowUpIcon, StopIcon } from "./Icons";

interface ComposerProps {
  disabled: boolean;
  streaming: boolean;
  onSend: (message: string) => void;
  onStop: () => void;
}

/** O campo fica livre durante o stream: dá para ir escrevendo a próxima, só o envio espera. */
export function Composer({ disabled, streaming, onSend, onStop }: ComposerProps) {
  const [input, setInput] = useState("");
  const field = useRef<HTMLTextAreaElement>(null);
  const canSend = !disabled && !streaming && input.trim().length > 0;

  // Cresce com o texto (até o max-height do CSS) e volta a uma linha depois do envio.
  useLayoutEffect(() => {
    const el = field.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${el.scrollHeight}px`;
  }, [input]);

  function submit() {
    if (!canSend) return;
    onSend(input.trim());
    setInput("");
    field.current?.focus();
  }

  function onKeyDown(e: KeyboardEvent) {
    // isComposing: o Enter que fecha um acento/IME não envia.
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      submit();
    }
  }

  return (
    <div className="dock">
      <form className="composer" onSubmit={(e) => { e.preventDefault(); submit(); }}>
        <textarea
          ref={field}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={onKeyDown}
          rows={1}
          placeholder="Pergunte alguma coisa"
          aria-label="Mensagem"
          enterKeyHint="send"
          autoFocus
        />
        {streaming ? (
          <button type="button" className="send" onClick={onStop} aria-label="Parar a resposta" title="Parar"><StopIcon /></button>
        ) : (
          <button type="submit" className="send" disabled={!canSend} aria-label="Enviar"><ArrowUpIcon /></button>
        )}
      </form>
      <p className="hint">O Prax pode cometer erros. Confira informações importantes.</p>
    </div>
  );
}
