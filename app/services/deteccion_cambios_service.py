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
from app.models.proyecto import EstadisticaCambio, ResumenTransicion
from app.utils.stats import (
    categorizar_transicion,
    construir_estadisticas_cambios,
    construir_histograma_categorias,
    construir_resumen_transicion,
)

logger = obtener_logger("deteccion_cambios_service")


@dataclass
class ResultadoDeteccion:
    """Resultado completo de una corrida de detección de cambios."""

    mapa_t1: object
    mapa_t2: object
    categoria: object
    url_overlay: str
    estadisticas: List[EstadisticaCambio]
    resumen_transicion: ResumenTransicion | None = None


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

        clases = sorted(CLASES_COBERTURA.values(), key=lambda clase: clase.id)
        codigos = [t1.id * 10 + t2.id for t1 in clases for t2 in clases]
        categorias = [
            categorizar_transicion(t1.id, t2.id)
            for t1 in clases
            for t2 in clases
        ]
        codigo_transicion = mapa_t1.multiply(10).add(mapa_t2).rename("transicion").toInt()
        categoria = codigo_transicion.remap(
            codigos, categorias, bandName="transicion",
        ).rename("categoria").toInt()

        imagen_resumen = (
            ee.Image.pixelArea().divide(10000).rename("area_ha")
            .addBands(codigo_transicion)
        )
        reductor = (
            ee.Reducer.sum()
            .combine(ee.Reducer.count(), sharedInputs=True)
            .group(groupField=1, groupName="transicion")
        )
        reduccion = imagen_resumen.reduceRegion(
            reducer=reductor,
            geometry=roi,
            scale=self.escala_metros,
            maxPixels=1e9,
        ).getInfo() or {}
        transiciones = {
            int(grupo["transicion"]): (int(grupo["count"]), float(grupo["sum"]))
            for grupo in reduccion.get("groups", [])
        }
        resumen_transicion = construir_resumen_transicion(transiciones)
        histograma_categorias = construir_histograma_categorias(transiciones)
        estadisticas = construir_estadisticas_cambios(
            histograma_categorias,
            resumen_transicion.total_pixeles,
            centro,
        )

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

        logger.info(
            "Detección completada: %d categorías con área relevante y %s píxeles válidos.",
            len(estadisticas),
            resumen_transicion.total_pixeles if resumen_transicion.total_pixeles is not None else 0,
        )

        return ResultadoDeteccion(
            mapa_t1=mapa_t1,
            mapa_t2=mapa_t2,
            categoria=categoria,
            url_overlay=url_overlay,
            estadisticas=estadisticas,
            resumen_transicion=resumen_transicion,
        )
