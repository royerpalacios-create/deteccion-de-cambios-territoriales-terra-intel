"""Ejecución de tareas lentas (Earth Engine, descargas) fuera del hilo de la UI.

Qt solo permite tocar widgets desde el hilo principal. :class:`Trabajo` corre
una función en un hilo *daemon* (igual que el ``threading.Thread`` de la
versión Tk, así cerrar la ventana no espera a que termine una consulta lenta)
y devuelve el resultado mediante señales, que Qt entrega en el hilo de la UI.
"""
from __future__ import annotations

import threading
from typing import Any, Callable

from PyQt6.QtCore import QObject, pyqtSignal

from app.core.logging_config import obtener_logger

logger = obtener_logger("trabajo")


class Trabajo(QObject):
    terminado = pyqtSignal(object)   # resultado de la función
    fallo = pyqtSignal(object)       # excepción lanzada por la función

    def __init__(self, funcion: Callable[[], Any], parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._funcion = funcion

    def iniciar(self) -> None:
        threading.Thread(target=self._correr, daemon=True).start()

    def _correr(self) -> None:
        try:
            resultado = self._funcion()
        except Exception as error:  # se reenvía a la UI para mostrarla al usuario
            logger.exception("Error en tarea en segundo plano")
            self.fallo.emit(error)
        else:
            self.terminado.emit(resultado)
