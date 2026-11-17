"""Servicio RS-3: detección de cambios territoriales entre dos épocas.

Es la migración del método ``procesar_deteccion`` que antes vivía dentro de
``TerraIntelApp`` (mezclado con código de Tkinter). Aquí solo queda la
lógica de análisis geoespacial: matriz de transición de clases, cálculo del
histograma de cambios y construcción de la capa de cambios (transparente
donde no hubo cambio). No importa nada de la UI.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List

from app.core.logging_config import obtener_logger
from app.models.cobertura import CATEGORIAS_CAMBIO, CLASES_COBERTURA
from app.models.proyecto import EstadisticaCambio
from app.utils.stats import construir_estadisticas_cambios

logger = obtener_logger("deteccion_cambios_service")


@dataclass
class ResultadoDeteccion:
    """Resultado completo de una corrida de detección de cambios."""

    mapa_t1: object
    mapa_t2: object
    categoria: object
    url_overlay: str
    estadisticas: List[EstadisticaCambio]


class DeteccionCambiosService:
    """Compara dos clasificaciones de cobertura y produce una capa de cambios."""

    def __init__(self, escala_metros: int = 10) -> None:
        self.escala_metros = escala_metros

    def detectar(self, mapa_t1, mapa_t2, roi, centro: tuple[float, float]) -> ResultadoDeteccion:
        """Ejecuta la matriz de transición y calcula estadísticas por categoría.

        ``centro`` es ``(longitud, latitud)``, usado solo para anotar las
        filas de estadísticas con una referencia geográfica legible.
        """
        import ee

        mapa_t1 = mapa_t1.rename("t1")
        mapa_t2 = mapa_t2.rename("t2")

        id_urbano = CLASES_COBERTURA["urbano"].id
        id_vegetacion = CLASES_COBERTURA["vegetacion"].id
        id_agua = CLASES_COBERTURA["agua"].id

        combo = mapa_t1.addBands(mapa_t2)
        categoria = combo.expression(
            "(t1 == t2) ? 0 : "
            "(t2 == URBANO) ? 1 : "
            "(t1 == VEGETACION) ? 2 : "
            "(t2 == VEGETACION) ? 3 : "
            "(((t1 == AGUA) ? 1 : 0) + ((t2 == AGUA) ? 1 : 0) == 1) ? 4 : 5",
            {
                "t1": combo.select("t1"),
                "t2": combo.select("t2"),
                "URBANO": id_urbano,
                "VEGETACION": id_vegetacion,
                "AGUA": id_agua,
            },
        ).rename("categoria").toInt()

        histograma = categoria.reduceRegion(
            reducer=ee.Reducer.frequencyHistogram(),
            geometry=roi,
            scale=self.escala_metros,
            maxPixels=1e9,
        ).get("categoria").getInfo() or {}

        total_pixeles = sum(histograma.values())
        estadisticas = construir_estadisticas_cambios(histograma, total_pixeles, centro)

        categoria_visible = categoria.updateMask(categoria.neq(0))
        paleta_categorias = [CATEGORIAS_CAMBIO[i].color for i in range(1, 6)]
        url_overlay = categoria_visible.getThumbURL({
            "min": 1,
            "max": 5,
            "palette": paleta_categorias,
            "dimensions": "800x800",
            "region": roi,
            "format": "png",
        })

        logger.info("Detección completada: %d categorías con área relevante.", len(estadisticas))

        return ResultadoDeteccion(
            mapa_t1=mapa_t1,
            mapa_t2=mapa_t2,
            categoria=categoria,
            url_overlay=url_overlay,
            estadisticas=estadisticas,
        )
