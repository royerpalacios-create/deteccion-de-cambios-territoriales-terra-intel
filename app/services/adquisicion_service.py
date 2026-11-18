"""Servicio RS-1: adquisición y preprocesamiento de datos satelitales.

Flujo por época (idéntico para T1 y T2, Tabla 1 y §4.2 del informe)::

    bounds(ROI) → fechas → calendario (mayo–septiembre) → escena (< 20 % nubes)
    → unión Cloud Score+ (cs_cdf) → máscara de píxel (cs_cdf ≥ 0,6)
    → bandas B2, B3, B4, B8, B11, B12 → median() → clip(ROI)

Convención de fechas: ``fecha_fin`` es **exclusiva** (es la de ``ee.Filter.filterDate``).
Con el calendario mayo–septiembre, el último día del año queda fuera de la temporada de
todos modos, por lo que ``2019-01-01 → 2019-12-31`` y ``2019-01-01 → 2020-01-01`` dan el
mismo mosaico.

Si la unión con Cloud Score+ falla (sin coincidencias o sin la banda ``cs_cdf``) el servicio
lanza un error accionable: nunca degrada en silencio al filtro de escena.
"""
from __future__ import annotations

import re
from datetime import date, datetime
from typing import Iterable

from app.core.exceptions import DatosInsuficientesError, ValidacionError
from app.core.logging_config import obtener_logger

logger = obtener_logger("adquisicion_service")

COLECCION_SENTINEL2 = "COPERNICUS/S2_SR_HARMONIZED"
COLECCION_CLOUD_SCORE_PLUS = "GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED"
BANDA_CLOUD_SCORE = "cs_cdf"
UMBRAL_NUBES_PORCENTAJE_DEFECTO = 20
# Temporada seca del altiplano (Tabla 1): mayo–septiembre, ambos meses incluidos.
MESES_TEMPORADA_DEFECTO: tuple[int, int] = (5, 9)
# Un píxel se conserva si cs_cdf >= umbral (Cloud Score+, §4.2).
UMBRAL_CLOUD_SCORE_DEFECTO = 0.6
# Las seis bandas del informe; deben coincidir con BANDAS_CLASIFICACION (lo verifica un test).
BANDAS_INFORME: tuple[str, ...] = ("B2", "B3", "B4", "B8", "B11", "B12")
# Resolución nominal del informe (m). La escala real de análisis la fija el área (main_window).
ESCALA_INFORME_M = 10
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
    """Adquiere mosaicos Sentinel-2 SR (temporada seca, Cloud Score+) para un ROI."""

    def __init__(self, umbral_nubes: int = UMBRAL_NUBES_PORCENTAJE_DEFECTO,
                 coleccion: str = COLECCION_SENTINEL2,
                 meses_temporada: tuple[int, int] = MESES_TEMPORADA_DEFECTO,
                 umbral_cloud_score: float = UMBRAL_CLOUD_SCORE_DEFECTO,
                 bandas: Iterable[str] = BANDAS_INFORME,
                 escala_metros: int = ESCALA_INFORME_M) -> None:
        self.umbral_nubes = umbral_nubes
        self.coleccion = coleccion
        self.meses_temporada = self._validar_meses(meses_temporada)
        self.umbral_cloud_score = self._validar_umbral_cs(umbral_cloud_score)
        self.bandas = tuple(bandas)
        self.escala_metros = escala_metros
        # Metadata efectiva de cada mosaico obtenido, indexada por (inicio, fin).
        self.metadata_por_periodo: dict[tuple[str, str], dict] = {}

    @staticmethod
    def _validar_meses(meses: tuple[int, int]) -> tuple[int, int]:
        try:
            primero, ultimo = (int(meses[0]), int(meses[1]))
        except (TypeError, ValueError, IndexError) as error:
            raise ValidacionError("meses_temporada debe ser un par (mes_inicial, mes_final).") from error
        if not (1 <= primero <= ultimo <= 12):
            raise ValidacionError(
                f"meses_temporada={meses!r} no es válido: se espera 1 ≤ mes_inicial ≤ mes_final ≤ 12."
            )
        return primero, ultimo

    @staticmethod
    def _validar_umbral_cs(umbral: float) -> float:
        if not isinstance(umbral, (int, float)) or isinstance(umbral, bool) or not (0 < umbral <= 1):
            raise ValidacionError(f"umbral_cloud_score={umbral!r} no es válido: debe estar en (0, 1].")
        return float(umbral)

    def metadata_efectiva(self, fecha_inicio: str, fecha_fin: str) -> dict:
        """Parámetros efectivos con los que se construye el mosaico de un periodo (para P2/P3)."""
        return {
            "coleccion": self.coleccion,
            "coleccion_cloud_score": COLECCION_CLOUD_SCORE_PLUS,
            "fecha_inicio": fecha_inicio,
            "fecha_fin": fecha_fin,
            "fecha_fin_exclusiva": True,
            "meses_temporada": list(self.meses_temporada),
            "umbral_nubes_escena": self.umbral_nubes,
            "banda_cloud_score": BANDA_CLOUD_SCORE,
            "umbral_cloud_score": self.umbral_cloud_score,
            "bandas": list(self.bandas),
            "escala_m": self.escala_metros,
            "reductor": "median",
        }

    def obtener_mosaico(self, roi, fecha_inicio: str, fecha_fin: str):
        """Mosaico mediana de Sentinel-2 SR para un periodo y un ROI.

        Lanza :class:`DatosInsuficientesError` si no hay escenas en la temporada o si la unión
        con Cloud Score+ no cubre todas las escenas.
        """
        import ee

        validar_rango_fechas(fecha_inicio, fecha_fin)
        mes_a, mes_b = self.meses_temporada
        logger.info(
            "Adquiriendo mosaico Sentinel-2 %s -> %s (meses %d–%d, escena < %s%%, cs_cdf >= %s)",
            fecha_inicio, fecha_fin, mes_a, mes_b, self.umbral_nubes, self.umbral_cloud_score,
        )

        escenas = (
            ee.ImageCollection(self.coleccion)
            .filterBounds(roi)
            .filterDate(fecha_inicio, fecha_fin)
            .filter(ee.Filter.calendarRange(mes_a, mes_b, "month"))
            .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", self.umbral_nubes))
        )
        n_escenas = int(escenas.size().getInfo() or 0)
        if n_escenas == 0:
            raise DatosInsuficientesError(
                f"No hay escenas Sentinel-2 para {fecha_inicio} → {fecha_fin} en los meses "
                f"{mes_a}–{mes_b} con nubosidad de escena < {self.umbral_nubes} %. "
                "Amplía el periodo, revisa el área o relaja el umbral de nubes."
            )

        cloud_score = (
            ee.ImageCollection(COLECCION_CLOUD_SCORE_PLUS)
            .filterBounds(roi)
            .filterDate(fecha_inicio, fecha_fin)
        )
        unidas = escenas.linkCollection(cloud_score, [BANDA_CLOUD_SCORE])
        n_unidas = int(
            unidas.filter(ee.Filter.listContains("system:band_names", BANDA_CLOUD_SCORE))
            .size().getInfo() or 0
        )
        if n_unidas < n_escenas:
            raise DatosInsuficientesError(
                f"La unión con Cloud Score+ ({COLECCION_CLOUD_SCORE_PLUS}) solo cubre {n_unidas} de "
                f"{n_escenas} escenas de {fecha_inicio} → {fecha_fin} (por system:index, banda "
                f"'{BANDA_CLOUD_SCORE}'). No se usa el filtro de escena como sustituto: revisa que "
                "tu cuenta de Earth Engine acceda a esa colección y que cubra el periodo."
            )

        umbral = self.umbral_cloud_score

        def enmascarar(imagen):
            return imagen.updateMask(imagen.select(BANDA_CLOUD_SCORE).gte(umbral))

        mosaico = (
            unidas.map(enmascarar)
            .select(list(self.bandas))
            .median()
            .clip(roi)
        )
        metadata = self.metadata_efectiva(fecha_inicio, fecha_fin)
        metadata["n_escenas"] = n_escenas
        metadata["n_escenas_con_cloud_score"] = n_unidas
        self.metadata_por_periodo[(fecha_inicio, fecha_fin)] = metadata
        return mosaico

    def adquirir_mosaicos_temporales(
        self,
        roi,
        periodo_t1: tuple[str, str],
        periodo_t2: tuple[str, str],
    ) -> dict[str, object]:
        """Adquiere los mosaicos t1 y t2 con exactamente el mismo flujo, y su metadata."""
        mosaico_t1 = self.obtener_mosaico(roi, periodo_t1[0], periodo_t1[1])
        mosaico_t2 = self.obtener_mosaico(roi, periodo_t2[0], periodo_t2[1])
        return {
            "mosaico_t1": mosaico_t1,
            "mosaico_t2": mosaico_t2,
            "metadata": {
                "t1": self.metadata_por_periodo[tuple(periodo_t1)],
                "t2": self.metadata_por_periodo[tuple(periodo_t2)],
            },
        }

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
