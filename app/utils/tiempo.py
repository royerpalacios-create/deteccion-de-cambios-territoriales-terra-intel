"""Medición de tiempos por fase, para ver dónde se va el tiempo de un análisis."""
from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from typing import Iterator


@contextmanager
def cronometro(descripcion: str, logger: logging.Logger) -> Iterator[None]:
    """Registra en el log cuánto tardó el bloque, aunque termine con error.

    >>> with cronometro("clasificación", logger):
    ...     clasificar()
    """
    inicio = time.perf_counter()
    try:
        yield
    finally:
        logger.info("Tiempo | %s: %.1f s", descripcion, time.perf_counter() - inicio)
