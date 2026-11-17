"""Servicio RS-2: clasificación de cobertura terrestre con Earth Engine.

Migración de ``clasificacion_cobertura.py`` a un servicio con estado
(número de árboles, escala, bandas configurables desde la UI en vez de
constantes fijas).

Estrategia de muestras de entrenamiento
----------------------------------------
En versiones anteriores las muestras eran puntos fijos de Puno, lo que hacía
que el clasificador fuera poco preciso fuera de esa zona. Ahora se usan dos
enfoques según lo que pase el llamador:

1. **Muestras explícitas** — si el llamador pasa un ``ee.FeatureCollection``
   propio, se usa tal cual (ideal para puntos de campo validados).
2. **Muestras automáticas generadas sobre el ROI** — si no se pasan muestras,
   :func:`generar_muestras_sobre_roi` extrae *n* puntos aleatorios por clase
   directamente del mosaico T2 usando índices espectrales (NDVI, NDWI, NDBI).
   Esto funciona en cualquier zona del Perú (y del mundo) sin coordenadas
   hardcodeadas.
"""
from __future__ import annotations

from typing import Dict, Iterable, List

from app.core.exceptions import ValidacionError
from app.core.logging_config import obtener_logger
from app.models.cobertura import BANDAS_CLASIFICACION, CLASES_COBERTURA, PROPIEDAD_CLASE

logger = obtener_logger("clasificacion_service")

# Número de puntos de muestra por clase al usar el método automático
PUNTOS_POR_CLASE = 40


def _crear_punto_entrenamiento(longitud: float, latitud: float, clase: int):
    import ee

    return ee.Feature(ee.Geometry.Point([longitud, latitud]), {PROPIEDAD_CLASE: clase})


# ── Muestras legacy para Puno (conservadas por compatibilidad) ────────────────
def obtener_muestras_entrenamiento_puno():
    """Devuelve muestras semilla fijas para la zona de Puno.

    .. deprecated::
        Usar :func:`generar_muestras_sobre_roi` para cualquier área.
        Esta función se conserva solo por compatibilidad con código antiguo.
    """
    import ee

    clases = CLASES_COBERTURA
    puntos = [
        _crear_punto_entrenamiento(-69.9820, -15.8320, clases["agua"].id),
        _crear_punto_entrenamiento(-69.9745, -15.8240, clases["agua"].id),
        _crear_punto_entrenamiento(-70.0280, -15.8730, clases["vegetacion"].id),
        _crear_punto_entrenamiento(-70.0450, -15.8590, clases["vegetacion"].id),
        _crear_punto_entrenamiento(-70.0200, -15.8400, clases["urbano"].id),
        _crear_punto_entrenamiento(-70.0110, -15.8350, clases["urbano"].id),
        _crear_punto_entrenamiento(-70.0450, -15.8120, clases["suelo_desnudo"].id),
        _crear_punto_entrenamiento(-70.0500, -15.8040, clases["suelo_desnudo"].id),
    ]
    return ee.FeatureCollection(puntos)


def generar_muestras_sobre_roi(mosaico_t2, roi, puntos_por_clase: int = PUNTOS_POR_CLASE):
    """Genera muestras de entrenamiento automáticas sobre el ROI dado.

    Etiqueta cada píxel del mosaico T2 con umbrales de índices espectrales y toma
    hasta ``puntos_por_clase`` puntos **por clase** con ``stratifiedSample``:

    - **Agua**          NDWI > 0.15  (McFeeters 1996)
    - **Vegetación**    NDVI > 0.30  y NDWI < 0.10
    - **Urbano**        NDBI > 0.05, NDVI < 0.15 y NDWI < 0.05
    - **Suelo desnudo** NDBI < 0.05, NDVI < 0.15 y NDWI < 0.05

    Se usa ``stratifiedSample`` y no ``sample(numPixels=...)`` porque este último
    reparte los puntos sobre *toda* la región y luego descarta los enmascarados:
    una clase poco frecuente (por ejemplo el agua en una zona árida) se queda con
    unos pocos puntos o con ninguno, y el entrenamiento falla con "No valid
    training data were found".

    Nota metodológica: las etiquetas salen de umbrales sobre las mismas bandas con
    las que se entrena, así que el Random Forest aprende a reproducir esas reglas.
    Es útil para comparar dos fechas con un criterio consistente en cualquier zona,
    pero no equivale a entrenar con puntos validados en campo (ver ``muestras=``).

    Returns
    -------
    ee.FeatureCollection
        Puntos con la propiedad ``"clase"`` listos para entrenar.
    """
    import ee

    clases = CLASES_COBERTURA
    ndvi = mosaico_t2.normalizedDifference(["B8", "B4"])
    ndwi = mosaico_t2.normalizedDifference(["B3", "B8"])
    ndbi = mosaico_t2.normalizedDifference(["B11", "B8"])

    sin_veg_ni_agua = ndvi.lt(0.15).And(ndwi.lt(0.05))
    etiquetas = (
        ee.Image(0)
        .where(sin_veg_ni_agua.And(ndbi.lt(0.05)), clases["suelo_desnudo"].id)
        .where(sin_veg_ni_agua.And(ndbi.gt(0.05)), clases["urbano"].id)
        .where(ndvi.gt(0.30).And(ndwi.lt(0.10)), clases["vegetacion"].id)
        .where(ndwi.gt(0.15), clases["agua"].id)
        .rename(PROPIEDAD_CLASE)
        .toInt()
    )
    etiquetas = etiquetas.updateMask(etiquetas.gt(0))

    return etiquetas.stratifiedSample(
        numPoints=puntos_por_clase,
        classBand=PROPIEDAD_CLASE,
        region=roi,
        scale=30,
        seed=42,
        geometries=True,
    )


class ClasificacionService:
    """Entrena y aplica un clasificador Random Forest de cobertura terrestre."""

    def __init__(self, numero_arboles: int = 100, escala_metros: int = 10,
                 bandas: Iterable[str] = BANDAS_CLASIFICACION) -> None:
        if numero_arboles <= 0:
            raise ValidacionError("El número de árboles debe ser mayor que cero.")
        self.numero_arboles = numero_arboles
        self.escala_metros = escala_metros
        self.bandas: List[str] = list(bandas)

    def preparar_imagen(self, imagen):
        if not self.bandas:
            raise ValidacionError("Se requiere al menos una banda para clasificar cobertura.")
        return imagen.select(self.bandas)

    def entrenar(self, imagen, muestras):
        import ee

        datos_entrenamiento = self.preparar_imagen(imagen).sampleRegions(
            collection=muestras,
            properties=[PROPIEDAD_CLASE],
            scale=self.escala_metros,
            geometries=True,
        )
        logger.info("Entrenando Random Forest (%d árboles, escala %dm).",
                    self.numero_arboles, self.escala_metros)
        return ee.Classifier.smileRandomForest(numberOfTrees=self.numero_arboles).train(
            features=datos_entrenamiento,
            classProperty=PROPIEDAD_CLASE,
            inputProperties=self.bandas,
        )

    def clasificar(self, imagen, clasificador):
        return self.preparar_imagen(imagen).classify(clasificador).rename("cobertura")

    def clasificar_mosaicos_temporales(self, mosaico_t1, mosaico_t2,
                                       muestras=None, roi=None) -> Dict[str, object]:
        """Clasifica T1 y T2.

        Prioridad de muestras:
        1. ``muestras`` explícitas (``ee.FeatureCollection``).
        2. Generación automática sobre ``roi`` usando índices espectrales de T2.
        3. Muestras legacy de Puno (solo si no se pasa ``roi`` — compatibilidad).
        """
        if muestras is not None:
            muestras_entrenamiento = muestras
            logger.info("Usando muestras de entrenamiento proporcionadas por el usuario.")
        elif roi is not None:
            logger.info("Generando muestras de entrenamiento automáticas sobre el ROI.")
            muestras_entrenamiento = generar_muestras_sobre_roi(mosaico_t2, roi)
        else:
            logger.warning(
                "No se proporcionó ROI ni muestras; usando muestras legacy de Puno. "
                "Esto puede dar resultados imprecisos fuera de esa zona."
            )
            muestras_entrenamiento = obtener_muestras_entrenamiento_puno()

        clasificador = self.entrenar(mosaico_t2, muestras_entrenamiento)
        return {
            "clasificacion_t1": self.clasificar(mosaico_t1, clasificador),
            "clasificacion_t2": self.clasificar(mosaico_t2, clasificador),
        }

