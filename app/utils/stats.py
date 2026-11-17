"""Utilidades puras (sin dependencias externas) para estadísticas de cambio.

Esta función se extrajo tal cual estaba (con el mismo comportamiento) de
``TerraIntelApp.construir_estadisticas_cambios`` en el ``interfaz.py``
original, para poder probarla con ``pytest`` sin necesitar Earth Engine,
Tkinter ni ninguna otra dependencia pesada.
"""
from __future__ import annotations

from typing import Dict, List

from app.models.proyecto import EstadisticaCambio

_UMBRAL_ALTO = 15.0
_UMBRAL_MEDIO = 5.0
_PORCENTAJE_MINIMO_RELEVANTE = 1.0


def construir_estadisticas_cambios(
    histograma: Dict[str, float],
    total_pixeles: float,
    centro: tuple[float, float],
) -> List[EstadisticaCambio]:
    """Convierte un histograma {clase_diferencia: conteo} en filas de resumen.

    Args:
        histograma: diccionario donde la clave es la diferencia de clase
            (como string, tal como la devuelve Earth Engine) y el valor es
            el número de píxeles con esa diferencia.
        total_pixeles: total de píxeles analizados (suma de todos los
            valores del histograma).
        centro: tupla ``(longitud, latitud)`` usada solo para mostrar unas
            coordenadas de referencia en cada fila.

    Returns:
        Lista de :class:`EstadisticaCambio`, ordenada de mayor a menor
        porcentaje de área afectada. Si no hay cambios relevantes, devuelve
        una única fila indicándolo.
    """
    filas: List[EstadisticaCambio] = []
    lon, lat = centro

    items_ordenados = sorted(histograma.items(), key=lambda item: item[1], reverse=True)

    for diferencia_str, conteo in items_ordenados:
        diferencia = int(float(diferencia_str))
        if diferencia == 0 or total_pixeles == 0:
            continue

        porcentaje = (conteo / total_pixeles) * 100
        if porcentaje < _PORCENTAJE_MINIMO_RELEVANTE:
            continue

        if porcentaje > _UMBRAL_ALTO:
            nivel, color = "ALTO", "#ff6b6b"
        elif porcentaje > _UMBRAL_MEDIO:
            nivel, color = "MEDIO", "#ffb95f"
        else:
            nivel, color = "BAJO", "#909097"

        filas.append(EstadisticaCambio(
            titulo=f"Cambio de cobertura (Δclase {diferencia:+d})",
            coords=f"{lat:.3f}, {lon:.3f}",
            porcentaje=f"{porcentaje:.1f}%",
            nivel=nivel,
            color=color,
            detalle=f"{int(conteo)} px afectados",
        ))

    if not filas:
        filas = [EstadisticaCambio(
            titulo="Sin cambios significativos",
            coords=f"{lat:.3f}, {lon:.3f}",
            porcentaje="0.0%",
            nivel="BAJO",
            color="#909097",
            detalle="No se detectaron variaciones relevantes",
        )]

    return filas
