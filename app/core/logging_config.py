"""Configuración centralizada de logging.

El proyecto original usaba ``print()`` para reportar el estado ("Conexion
con Earth Engine exitosa.", etc.). Esto no permite filtrar por severidad,
no queda registrado en disco y no es útil para depurar un problema que
ocurrió hace varias ejecuciones. Este módulo reemplaza esos ``print`` por
un logger real que escribe en consola y en ``logs/terra_intel.log``.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

_LOG_DIR = Path(__file__).resolve().parent.parent.parent / "logs"
_LOG_FILE = _LOG_DIR / "terra_intel.log"
_FORMATO = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"

_configurado = False


def configurar_logging(nivel: int = logging.INFO) -> None:
    """Configura el logger raíz de la aplicación (idempotente)."""
    global _configurado
    if _configurado:
        return

    _LOG_DIR.mkdir(parents=True, exist_ok=True)

    formateador = logging.Formatter(_FORMATO, datefmt="%Y-%m-%d %H:%M:%S")

    manejador_archivo = logging.FileHandler(_LOG_FILE, encoding="utf-8")
    manejador_archivo.setFormatter(formateador)

    manejador_consola = logging.StreamHandler(sys.stdout)
    manejador_consola.setFormatter(formateador)

    raiz = logging.getLogger("terra_intel")
    raiz.setLevel(nivel)
    raiz.addHandler(manejador_archivo)
    raiz.addHandler(manejador_consola)
    raiz.propagate = False

    _configurado = True


def obtener_logger(nombre: str) -> logging.Logger:
    """Devuelve un logger hijo con el prefijo ``terra_intel.<nombre>``."""
    configurar_logging()
    return logging.getLogger(f"terra_intel.{nombre}")
