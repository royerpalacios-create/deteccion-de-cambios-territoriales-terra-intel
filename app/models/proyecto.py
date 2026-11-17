"""Modelo de dominio: proyecto de trabajo y resultado de una detección.

``Proyecto`` es lo que se guarda/abre desde el menú Archivo. No serializa
las imágenes de Earth Engine (no es posible ni deseable meterlas en JSON),
sino los parámetros necesarios para reproducir el análisis: coordenadas,
periodos de tiempo y, si ya se ejecutó, un resumen de las estadísticas de
cambio obtenidas.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from app.core.exceptions import ProyectoError

EXTENSION_PROYECTO = ".tiproj"


@dataclass
class EstadisticaCambio:
    """Una fila de la tabla/leyenda de cambios (una categoría detectada)."""

    titulo: str
    coords: str
    porcentaje: str
    nivel: str
    color: str
    detalle: str

    def a_diccionario(self) -> dict[str, Any]:
        return {
            "titulo": self.titulo,
            "coords": self.coords,
            "porcentaje": self.porcentaje,
            "nivel": self.nivel,
            "color": self.color,
            "detalle": self.detalle,
        }


@dataclass(frozen=True)
class CeldaTransicion:
    """Valor de una celda de la matriz T1→T2 sobre píxeles válidos."""

    pixeles: int
    area_ha: float
    porcentaje: float


@dataclass(frozen=True)
class BalanceCobertura:
    """Balance de área de una clase entre T1 y T2."""

    clase: str
    area_t1_ha: float | None
    area_t2_ha: float | None
    entradas_ha: float | None
    salidas_ha: float | None
    neto_ha: float | None
    persistencia_ha: float | None
    persistencia_pct: float | None


@dataclass(frozen=True)
class ResumenTransicion:
    """Matriz de áreas y balance por clase; ``None`` representa no-data."""

    clases: tuple[str, ...]
    matriz: tuple[tuple[CeldaTransicion | None, ...], ...]
    balance: tuple[BalanceCobertura, ...]
    total_pixeles: int | None
    area_total_ha: float | None


@dataclass
class Proyecto:
    """Proyecto de trabajo de TERRA_INTEL."""

    nombre: str
    longitud: float
    latitud: float
    periodo_t1: str = "2019"
    periodo_t2: str = "2024"
    creado: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    estadisticas: list[EstadisticaCambio] = field(default_factory=list)
    ruta: Path | None = field(default=None, compare=False)

    def a_diccionario(self) -> dict[str, Any]:
        return {
            "nombre": self.nombre,
            "longitud": self.longitud,
            "latitud": self.latitud,
            "periodo_t1": self.periodo_t1,
            "periodo_t2": self.periodo_t2,
            "creado": self.creado,
            "estadisticas": [e.a_diccionario() for e in self.estadisticas],
        }

    def guardar(self, ruta: Path) -> Path:
        ruta = ruta if ruta.suffix == EXTENSION_PROYECTO else ruta.with_suffix(EXTENSION_PROYECTO)
        try:
            ruta.parent.mkdir(parents=True, exist_ok=True)
            ruta.write_text(json.dumps(self.a_diccionario(), indent=2, ensure_ascii=False), encoding="utf-8")
        except OSError as error:
            raise ProyectoError(f"No se pudo guardar el proyecto en {ruta}: {error}") from error
        self.ruta = ruta
        return ruta

    @classmethod
    def cargar(cls, ruta: Path) -> "Proyecto":
        try:
            datos = json.loads(ruta.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ProyectoError(f"No se pudo abrir el proyecto {ruta}: {error}") from error

        estadisticas = [EstadisticaCambio(**e) for e in datos.get("estadisticas", [])]
        proyecto = cls(
            nombre=datos["nombre"],
            longitud=datos["longitud"],
            latitud=datos["latitud"],
            periodo_t1=datos.get("periodo_t1", "2019"),
            periodo_t2=datos.get("periodo_t2", "2024"),
            creado=datos.get("creado", ""),
            estadisticas=estadisticas,
        )
        proyecto.ruta = ruta
        return proyecto
