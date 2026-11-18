"""Servicio RS-2: clasificación de cobertura terrestre con Earth Engine.

Método (informe §4.3, Tablas 1–2 y 8)
-------------------------------------
1. **Etiquetas**: moda anual de Dynamic World (``GOOGLE/DYNAMICWORLD/V1``,
   banda ``label``) de cada año (T1 y T2), remapeada a las 4 clases de la app.
   Nieve/hielo (clase 8) y píxeles enmascarados se excluyen.
2. **Muestreo**: hasta ``PUNTOS_POR_CLASE_Y_EPOCA`` puntos por clase y por época,
   escala 10 m, semilla 42. Cada punto conserva su época en la propiedad
   ``epoca``.
3. **Partición**: se aparta un 30 % (holdout) ANTES de entrenar.
4. **Modelo**: un único Random Forest (100 árboles) entrenado con el 70 % de
   T1+T2 y aplicado a ambos mosaicos.
5. **Validación**: matriz de error, concordancia y kappa calculados sobre el
   holdout (nunca sobre el entrenamiento), global y por época.

Importante: la referencia es un *mapa* (Dynamic World), no datos de campo. Lo que
se mide es **concordancia con Dynamic World**, no exactitud respecto al terreno.
Ninguna cifra (n, concordancia, kappa) está escrita a mano: todas se calculan.
"""
from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from app.core.exceptions import ValidacionError
from app.core.logging_config import obtener_logger
from app.models.cobertura import BANDAS_CLASIFICACION, CLASES_COBERTURA, PROPIEDAD_CLASE

logger = obtener_logger("clasificacion_service")

# ── Parámetros del experimento (Tabla 1 del informe) ─────────────────────────
DW_COLECCION = "GOOGLE/DYNAMICWORLD/V1"
DW_BANDA_ETIQUETA = "label"

# Códigos nativos de Dynamic World -> id de clase de la app (ver cobertura.py)
#   0 agua                                   -> 1 Agua
#   1 árboles, 2 pasto, 3 veg. inundada,
#   4 cultivos, 5 arbustos                   -> 2 Vegetación
#   6 área construida                        -> 3 Urbano
#   7 suelo desnudo                          -> 4 Suelo desnudo
#   8 nieve/hielo                            -> excluido (no aparece en el mapeo)
MAPEO_DW_A_APP: Dict[int, int] = {
    0: CLASES_COBERTURA["agua"].id,
    1: CLASES_COBERTURA["vegetacion"].id,
    2: CLASES_COBERTURA["vegetacion"].id,
    3: CLASES_COBERTURA["vegetacion"].id,
    4: CLASES_COBERTURA["vegetacion"].id,
    5: CLASES_COBERTURA["vegetacion"].id,
    6: CLASES_COBERTURA["urbano"].id,
    7: CLASES_COBERTURA["suelo_desnudo"].id,
}

PUNTOS_POR_CLASE_Y_EPOCA = 150   # "hasta 150": el número real puede ser menor
ESCALA_MUESTREO_M = 10
SEMILLA = 42
FRACCION_HOLDOUT = 0.30
PROPIEDAD_EPOCA = "epoca"
PROPIEDAD_AZAR = "azar"
PROPIEDAD_PREDICCION = "classification"   # nombre por defecto de .classify() sobre tablas

ADVERTENCIA_REFERENCIA = (
    "Concordancia con Dynamic World (mapa de referencia), no exactitud "
    "respecto a datos de campo."
)


def _crear_punto_entrenamiento(longitud: float, latitud: float, clase: int):
    import ee

    return ee.Feature(ee.Geometry.Point([longitud, latitud]), {PROPIEDAD_CLASE: clase})


# ── Muestras legacy para Puno (conservadas por compatibilidad) ────────────────
def obtener_muestras_entrenamiento_puno():
    """Muestras semilla fijas para Puno.

    .. deprecated::
        Solo para código antiguo. El experimento usa Dynamic World.
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


# ── Etiquetas Dynamic World ───────────────────────────────────────────────────
def etiquetas_dynamic_world(roi, anio: int):
    """Moda anual (año calendario completo) de Dynamic World, en IDs de la app.

    ``remap`` deja enmascarado todo valor que no esté en ``MAPEO_DW_A_APP``, por
    lo que nieve/hielo (8) y los píxeles sin dato quedan fuera del muestreo.
    """
    import ee

    origen = sorted(MAPEO_DW_A_APP)
    destino = [MAPEO_DW_A_APP[c] for c in origen]
    moda = (
        ee.ImageCollection(DW_COLECCION)
        .filterBounds(roi)
        .filterDate(f"{anio}-01-01", f"{anio + 1}-01-01")
        .select(DW_BANDA_ETIQUETA)
        .mode()
    )
    return moda.remap(origen, destino).rename(PROPIEDAD_CLASE).toInt().clip(roi)


def muestrear_epoca(mosaico, etiquetas, roi, epoca: str, bandas: Sequence[str],
                    puntos_por_clase: int = PUNTOS_POR_CLASE_Y_EPOCA,
                    escala: int = ESCALA_MUESTREO_M, semilla: int = SEMILLA):
    """Muestreo estratificado de UNA época: predictores del mosaico + etiqueta DW.

    Devuelve puntos con las bandas, la propiedad ``clase`` y la propiedad
    ``epoca`` (para validar por separado después).
    """
    pila = mosaico.select(list(bandas)).addBands(etiquetas)
    puntos = pila.stratifiedSample(
        numPoints=puntos_por_clase,
        classBand=PROPIEDAD_CLASE,
        region=roi,
        scale=escala,
        seed=semilla,
        geometries=True,
    )
    return puntos.map(lambda f: f.set(PROPIEDAD_EPOCA, epoca))


def dividir_train_holdout(muestras, fraccion_holdout: float = FRACCION_HOLDOUT,
                          semilla: int = SEMILLA):
    """Parte las muestras (T1+T2 juntas) en entrenamiento y holdout, con semilla."""
    import ee

    corte = round(1.0 - fraccion_holdout, 6)
    con_azar = muestras.randomColumn(PROPIEDAD_AZAR, semilla)
    entrenamiento = con_azar.filter(ee.Filter.lt(PROPIEDAD_AZAR, corte))
    holdout = con_azar.filter(ee.Filter.gte(PROPIEDAD_AZAR, corte))
    return entrenamiento, holdout


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

    # ── Entrenamiento ─────────────────────────────────────────────────────────
    def entrenar(self, imagen, muestras):
        """Camino con muestras explícitas del usuario (puntos de campo): usa sampleRegions."""
        datos_entrenamiento = self.preparar_imagen(imagen).sampleRegions(
            collection=muestras,
            properties=[PROPIEDAD_CLASE],
            scale=self.escala_metros,
            geometries=True,
        )
        return self._entrenar_con_tabla(datos_entrenamiento)

    def _entrenar_con_tabla(self, tabla_entrenamiento):
        import ee

        logger.info("Entrenando Random Forest (%d árboles, semilla %d).",
                    self.numero_arboles, SEMILLA)
        return ee.Classifier.smileRandomForest(
            numberOfTrees=self.numero_arboles, seed=SEMILLA,
        ).train(
            features=tabla_entrenamiento,
            classProperty=PROPIEDAD_CLASE,
            inputProperties=self.bandas,
        )

    def clasificar(self, imagen, clasificador):
        return self.preparar_imagen(imagen).classify(clasificador).rename("cobertura")

    # ── Validación sobre el holdout ───────────────────────────────────────────
    def calcular_validacion(self, clasificador, muestras, entrenamiento, holdout,
                            epocas: Sequence[str]) -> Dict[str, object]:
        """Mide concordancia con Dynamic World SOLO sobre el holdout.

        Hace una única llamada ``getInfo`` con todo lo necesario. El orden de
        filas/columnas de la matriz de error es el de ``ids_clases``.
        """
        import ee

        ids_clases = sorted(c.id for c in CLASES_COBERTURA.values())
        predichos = holdout.classify(clasificador)

        def resumen(coleccion):
            matriz = coleccion.errorMatrix(PROPIEDAD_CLASE, PROPIEDAD_PREDICCION, ids_clases)
            return ee.Dictionary({
                "n": coleccion.size(),
                "matriz_error": matriz.array(),
                "concordancia": matriz.accuracy(),
                "kappa": matriz.kappa(),
            })

        bloque = {
            "n_total": muestras.size(),
            "n_entrenamiento": entrenamiento.size(),
            "n_holdout": holdout.size(),
            "global": resumen(predichos),
            "por_epoca": ee.Dictionary({
                e: resumen(predichos.filter(ee.Filter.eq(PROPIEDAD_EPOCA, e))) for e in epocas
            }),
            "muestras_por_epoca_clase": ee.Dictionary({
                e: muestras.filter(ee.Filter.eq(PROPIEDAD_EPOCA, e))
                           .aggregate_histogram(PROPIEDAD_CLASE) for e in epocas
            }),
        }
        try:
            calculado = ee.Dictionary(bloque).getInfo()
        except Exception as exc:  # EE lanza ee.EEException; evitamos depender del tipo
            raise ValidacionError(
                "No se pudo calcular la validación (¿pocas muestras en alguna clase/época "
                f"o ROI sin datos tras la máscara de nubes?): {exc}"
            ) from exc

        return {
            "fuente": "Dynamic World",
            "advertencia": ADVERTENCIA_REFERENCIA,
            "ids_clases": ids_clases,
            "semilla": SEMILLA,
            "parametros": {
                "arboles": self.numero_arboles,
                "escala_m": ESCALA_MUESTREO_M,
                "puntos_por_clase_y_epoca_max": PUNTOS_POR_CLASE_Y_EPOCA,
                "fraccion_holdout": FRACCION_HOLDOUT,
                "mapeo_dw_a_app": {str(k): v for k, v in MAPEO_DW_A_APP.items()},
            },
            "planificadas_max": PUNTOS_POR_CLASE_Y_EPOCA * len(ids_clases) * len(epocas),
            **calculado,
        }

    # ── Orquestación ──────────────────────────────────────────────────────────
    def clasificar_mosaicos_temporales(self, mosaico_t1, mosaico_t2, muestras=None,
                                       roi=None, anios: Optional[Tuple[int, int]] = None,
                                       validar: bool = True) -> Dict[str, object]:
        """Clasifica T1 y T2.

        Prioridad:
        1. ``muestras`` explícitas (puntos de campo): se entrena con T2, sin validación DW.
        2. ``roi`` + ``anios=(año_T1, año_T2)``: método del informe (Dynamic World,
           T1+T2, holdout 30 %).
        3. Muestras legacy de Puno (solo sin ``roi``; compatibilidad).
        """
        validacion: Optional[Dict[str, object]] = None

        if muestras is not None:
            logger.info("Usando muestras de entrenamiento proporcionadas por el usuario.")
            clasificador = self.entrenar(mosaico_t2, muestras)
        elif roi is not None:
            if anios is None:
                raise ValidacionError(
                    "Para etiquetar con Dynamic World se requiere anios=(año_T1, año_T2)."
                )
            anio_t1, anio_t2 = anios
            epocas = (str(anio_t1), str(anio_t2))
            puntos = [
                muestrear_epoca(mosaico, etiquetas_dynamic_world(roi, anio), roi, epoca,
                                self.bandas)
                for mosaico, anio, epoca in ((mosaico_t1, anio_t1, epocas[0]),
                                             (mosaico_t2, anio_t2, epocas[1]))
            ]
            combinadas = puntos[0].merge(puntos[1])
            entrenamiento, holdout = dividir_train_holdout(combinadas)
            clasificador = self._entrenar_con_tabla(entrenamiento)
            if validar:
                validacion = self.calcular_validacion(
                    clasificador, combinadas, entrenamiento, holdout, epocas,
                )
        else:
            logger.warning(
                "No se proporcionó ROI ni muestras; usando muestras legacy de Puno. "
                "Esto puede dar resultados imprecisos fuera de esa zona."
            )
            clasificador = self.entrenar(mosaico_t2, obtener_muestras_entrenamiento_puno())

        return {
            "clasificacion_t1": self.clasificar(mosaico_t1, clasificador),
            "clasificacion_t2": self.clasificar(mosaico_t2, clasificador),
            "validacion": validacion,
        }