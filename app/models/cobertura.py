"""Modelo de dominio: clases de cobertura terrestre y categorías de cambio.

Reúne en un solo lugar dos catálogos que antes estaban duplicados/repartidos
entre ``clasificacion_cobertura.py`` (clases de cobertura) e ``interfaz.py``
(categorías de cambio con sus colores de leyenda).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

BANDAS_CLASIFICACION: List[str] = ["B2", "B3", "B4", "B8", "B11", "B12"]
PROPIEDAD_CLASE = "clase"


@dataclass(frozen=True)
class ClaseCobertura:
    """Representa una clase de cobertura terrestre del proyecto."""

    id: int
    nombre: str
    color: str


CLASES_COBERTURA: Dict[str, ClaseCobertura] = {
    "agua": ClaseCobertura(1, "Agua", "1f78b4"),
    "vegetacion": ClaseCobertura(2, "Vegetación", "33a02c"),
    "urbano": ClaseCobertura(3, "Urbano", "e31a1c"),
    "suelo_desnudo": ClaseCobertura(4, "Suelo desnudo", "b15928"),
}


@dataclass(frozen=True)
class CategoriaCambio:
    """Categoría legible de cambio territorial entre dos épocas."""

    id: int
    nombre: str
    color: str  # hex con "#" incluido, listo para usar en la UI


CATEGORIAS_CAMBIO: Dict[int, CategoriaCambio] = {
    0: CategoriaCambio(0, "Sin cambios", "#3a3f4d"),
    1: CategoriaCambio(1, "Urbanización", "#ff6b6b"),
    2: CategoriaCambio(2, "Pérdida de vegetación", "#ffb95f"),
    3: CategoriaCambio(3, "Ganancia de vegetación", "#4edea3"),
    4: CategoriaCambio(4, "Cambio en cuerpo de agua", "#4ea8de"),
    5: CategoriaCambio(5, "Otro cambio", "#c9a0ff"),
}


def obtener_parametros_visualizacion() -> Dict[str, object]:
    """Parámetros de visualización (min/max/palette) para el mapa de cobertura."""
    clases_ordenadas = sorted(CLASES_COBERTURA.values(), key=lambda c: c.id)
    return {
        "min": 1,
        "max": len(clases_ordenadas),
        "palette": [c.color for c in clases_ordenadas],
    }
