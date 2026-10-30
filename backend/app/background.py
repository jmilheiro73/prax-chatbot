"""Trabalho fora do caminho crítico (Aula 11): o usuário não espera por título nem por extração de memória.

Fire-and-forget com referência guardada: sem ela o event loop pode coletar a task no meio.
Sem fila nem retry: se falhar, perde-se um título ou um fato, e o erro vai para o log.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Coroutine

logger = logging.getLogger(__name__)


class BackgroundTasks:
    def __init__(self) -> None:
        self._tasks: set[asyncio.Task] = set()

    def spawn(self, coro: Coroutine, name: str) -> None:
        task = asyncio.create_task(coro, name=name)
        self._tasks.add(task)
        task.add_done_callback(self._finished)

    def _finished(self, task: asyncio.Task) -> None:
        self._tasks.discard(task)
        if not task.cancelled() and task.exception() is not None:
            logger.error("task em segundo plano falhou: %s", task.get_name(), exc_info=task.exception())

    async def drain(self) -> None:
        """Espera o que está rodando. O shutdown e os testes usam."""
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
