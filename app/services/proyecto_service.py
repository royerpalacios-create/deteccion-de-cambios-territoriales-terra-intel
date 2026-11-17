"""Servicio: guardar/abrir archivos de proyecto (.tiproj) y lista de recientes.

Funcionalidad nueva: el proyecto original no tenía manera de guardar una
sesión de trabajo ni de reabrirla; cada vez que se cerraba la app se perdía
todo el contexto (coordenadas usadas, resultados obtenidos).
"""
from __future__ import annotations

import re
from pathlib import Path

from app.core.config import GestorConfiguracion
from app.models.proyecto import Proyecto


def nombre_archivo_seguro(nombre: str) -> str:
    """Convierte un nombre libre ("Lima – Centro", "a/b:c") en un nombre de archivo válido."""
    limpio = re.sub(r"[^\w\-]+", "_", nombre.strip()).strip("_")
    return limpio or "proyecto"


class ProyectoService:
    """Guarda/abre :class:`Proyecto` y mantiene la lista de recientes en la config."""

    def __init__(self, gestor_config: GestorConfiguracion, directorio_datos: Path) -> None:
        self._gestor_config = gestor_config
        self.directorio_datos = directorio_datos
        self.directorio_datos.mkdir(parents=True, exist_ok=True)

    def guardar(self, proyecto: Proyecto, ruta: Path | None = None) -> Path:
        destino = ruta or (self.directorio_datos / f"{nombre_archivo_seguro(proyecto.nombre)}.tiproj")
        ruta_final = proyecto.guardar(destino)
        self._gestor_config.config.agregar_proyecto_reciente(str(ruta_final))
        self._gestor_config.guardar()
        return ruta_final

    def abrir(self, ruta: Path) -> Proyecto:
        proyecto = Proyecto.cargar(ruta)
        self._gestor_config.config.agregar_proyecto_reciente(str(ruta))
        self._gestor_config.guardar()
        return proyecto

    def recientes(self) -> list[Path]:
        return [Path(r) for r in self._gestor_config.config.proyectos_recientes if Path(r).exists()]
