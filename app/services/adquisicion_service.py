"""Servicio RS-1: adquisición y preprocesamiento de datos satelitales.

Es una migración directa de la lógica que ya existía en
``adquisicion_datos.py`` del proyecto original (que ya estaba razonablemente
bien escrita), envuelta como servicio para poder inyectarla en la capa de
UI y de análisis en lugar de importarla como funciones sueltas desde
cualquier parte.
"""
from __future__ import annotations

import re
from datetime import date, datetime
from typing import Iterable

from app.core.exceptions import ValidacionError
from app.core.logging_config import obtener_logger

logger = obtener_logger("adquisicion_service")

COLECCION_SENTINEL2 = "COPERNICUS/S2_SR_HARMONIZED"
UMBRAL_NUBES_PORCENTAJE_DEFECTO = 20
# Primera fecha con imágenes Sentinel-2 SR en la colección armonizada de Earth Engine.
FECHA_MINIMA_SENTINEL2 = date(2017, 3, 28)


def validar_rango_fechas(fecha_inicio: str, fecha_fin: str) -> None:
    """Valida que el rango de fechas tenga el formato esperado (YYYY-MM-DD)."""
    formato = "%Y-%m-%d"
    try:
        inicio = datetime.strptime(fecha_inicio, formato)
        fin = datetime.strptime(fecha_fin, formato)
    except ValueError as error:
        raise ValidacionError("Las fechas deben tener el formato YYYY-MM-DD.") from error

    if inicio >= fin:
        raise ValidacionError("La fecha de inicio debe ser anterior a la fecha de fin.")


def validar_periodos(periodo_t1: tuple[str, str], periodo_t2: tuple[str, str],
                     hoy: date | None = None) -> None:
    """Valida los dos periodos de análisis y su relación entre sí.

    Lanza :class:`ValidacionError` con un mensaje que indica qué época falla.
    """
    hoy = hoy or date.today()
    for nombre, (inicio, fin) in (("Época A (T1)", periodo_t1), ("Época B (T2)", periodo_t2)):
        try:
            validar_rango_fechas(inicio, fin)
        except ValidacionError as error:
            raise ValidacionError(f"{nombre}: {error}") from error
        if date.fromisoformat(inicio) < FECHA_MINIMA_SENTINEL2:
            raise ValidacionError(
                f"{nombre}: Sentinel-2 no tiene imágenes antes del {FECHA_MINIMA_SENTINEL2.isoformat()}."
            )
        if date.fromisoformat(fin) > hoy:
            raise ValidacionError(f"{nombre}: la fecha de fin no puede estar en el futuro.")

    if date.fromisoformat(periodo_t1[1]) >= date.fromisoformat(periodo_t2[0]):
        raise ValidacionError("La Época A debe terminar antes de que empiece la Época B.")


def etiqueta_periodo(inicio: str, fin: str) -> str:
    """Texto corto para mostrar un periodo: ``2019`` si es el año completo, o ``inicio → fin``."""
    if inicio[:4] == fin[:4] and inicio.endswith("-01-01") and fin.endswith("-12-31"):
        return inicio[:4]
    return f"{inicio} → {fin}"


def periodo_desde_etiqueta(etiqueta: str) -> tuple[str, str] | None:
    """Inverso de :func:`etiqueta_periodo`; devuelve ``None`` si el texto no tiene ese formato."""
    if re.fullmatch(r"\d{4}", etiqueta):
        return (f"{etiqueta}-01-01", f"{etiqueta}-12-31")
    rango = re.fullmatch(r"(\d{4}-\d{2}-\d{2}) → (\d{4}-\d{2}-\d{2})", etiqueta)
    return (rango.group(1), rango.group(2)) if rango else None


class AdquisicionService:
    """Adquiere mosaicos Sentinel-2 filtrados por nubosidad para un ROI."""

    def __init__(self, umbral_nubes: int = UMBRAL_NUBES_PORCENTAJE_DEFECTO,
                 coleccion: str = COLECCION_SENTINEL2) -> None:
        self.umbral_nubes = umbral_nubes
        self.coleccion = coleccion

    def obtener_mosaico(self, roi, fecha_inicio: str, fecha_fin: str):
        """Obtiene un mosaico Sentinel-2 filtrado por fecha, nubosidad y área."""
        import ee

        validar_rango_fechas(fecha_inicio, fecha_fin)
        logger.info("Adquiriendo mosaico Sentinel-2 %s -> %s (nubes < %s%%)",
                    fecha_inicio, fecha_fin, self.umbral_nubes)

        return (
            ee.ImageCollection(self.coleccion)
            .filterBounds(roi)
            .filterDate(fecha_inicio, fecha_fin)
            .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", self.umbral_nubes))
            .median()
            .clip(roi)
        )

    def adquirir_mosaicos_temporales(
        self,
        roi,
        periodo_t1: tuple[str, str],
        periodo_t2: tuple[str, str],
    ) -> dict[str, object]:
        """Adquiere dos mosaicos Sentinel-2 (t1 y t2) para comparación temporal."""
        mosaico_t1 = self.obtener_mosaico(roi, periodo_t1[0], periodo_t1[1])
        mosaico_t2 = self.obtener_mosaico(roi, periodo_t2[0], periodo_t2[1])
        return {"mosaico_t1": mosaico_t1, "mosaico_t2": mosaico_t2}

    def obtener_thumbnail_url(self, mosaico, roi, dimensiones: str = "800x800",
                               bandas: Iterable[str] = ("B4", "B3", "B2"),
                               vis_min: int = 0, vis_max: int = 3000) -> str:
        """Genera la URL de un thumbnail PNG en color real para un mosaico."""
        return mosaico.getThumbURL({
            "min": vis_min,
            "max": vis_max,
            "dimensions": dimensiones,
            "bands": list(bandas),
            "region": roi,
        })
