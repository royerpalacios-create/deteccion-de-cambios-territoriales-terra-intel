"""Pipeline por consola: RS-1 -> RS-2 -> RS-3, sin interfaz gráfica.

Es el equivalente moderno del antiguo ``Proyecto.py`` de la raíz del
proyecto, reescrito para usar los servicios de ``app`` en vez de funciones
sueltas importadas directamente. Se invoca con::

    python main.py --console
"""
from __future__ import annotations

from pathlib import Path

from app.core.config import GestorConfiguracion
from app.core.logging_config import configurar_logging, obtener_logger
from app.models.area_estudio import crear_area_estudio_puno
from app.models.cobertura import obtener_parametros_visualizacion
from app.services.adquisicion_service import AdquisicionService
from app.services.clasificacion_service import ClasificacionService
from app.services.earth_engine_service import EarthEngineService

logger = obtener_logger("pipeline_consola")

RAIZ_PROYECTO = Path(__file__).resolve().parent.parent


def ejecutar_pipeline_consola() -> None:
    configurar_logging()
    config = GestorConfiguracion().config

    ee_service = EarthEngineService(config.proyecto_earth_engine)
    if not ee_service.inicializar():
        logger.error("No se pudo conectar con Earth Engine: %s", ee_service.ultimo_error)
        print(f"❌ No se pudo conectar con Earth Engine: {ee_service.ultimo_error}")
        print("Ejecuta: python -c \"import ee; ee.Authenticate()\"")
        return

    print("✅ Conexión con Earth Engine exitosa.")

    import geemap

    area_estudio = crear_area_estudio_puno()
    roi = area_estudio.geometria()

    adquisicion = AdquisicionService(umbral_nubes=config.umbral_nubes)
    mosaicos = adquisicion.adquirir_mosaicos_temporales(
        roi, periodo_t1=("2018-01-01", "2018-12-31"), periodo_t2=("2023-01-01", "2023-12-31"),
    )
    mosaico_t1, mosaico_t2 = mosaicos["mosaico_t1"], mosaicos["mosaico_t2"]
    print("✅ Mosaicos Sentinel-2 adquiridos correctamente (RS-1).")

    clasificacion = ClasificacionService()
    clasificaciones = clasificacion.clasificar_mosaicos_temporales(mosaico_t1, mosaico_t2)
    mapa_t1, mapa_t2 = clasificaciones["clasificacion_t1"], clasificaciones["clasificacion_t2"]
    print("✅ Clasificación de cobertura terrestre RS-2 generada correctamente.")

    cambios = mapa_t2.subtract(mapa_t1)
    print("✅ Comparación temporal realizada (RS-3).")

    mapa = geemap.Map(center=[area_estudio.latitud, area_estudio.longitud], zoom=11)
    mapa.addLayer(mosaico_t1, {"bands": ["B4", "B3", "B2"], "min": 0, "max": 3000}, "Sentinel 2018")
    mapa.addLayer(mosaico_t2, {"bands": ["B4", "B3", "B2"], "min": 0, "max": 3000}, "Sentinel 2023")

    parametros_cobertura = obtener_parametros_visualizacion()
    mapa.addLayer(mapa_t1, parametros_cobertura, "Cobertura terrestre 2018")
    mapa.addLayer(mapa_t2, parametros_cobertura, "Cobertura terrestre 2023")
    mapa.addLayer(
        cambios,
        {"min": -3, "max": 3, "palette": ["8c510a", "f6e8c3", "ffffff", "c7eae5", "01665e"]},
        "Cambios de cobertura",
    )
    mapa.addLayerControl()

    directorio_exports = RAIZ_PROYECTO / "exports"
    directorio_exports.mkdir(parents=True, exist_ok=True)
    ruta_salida = directorio_exports / "mapa_cambios.html"
    mapa.to_html(str(ruta_salida))

    print("\n--- Sistema de Detección de Cambios Territoriales ---")
    print("Módulos RS-1, RS-2 y RS-3 ejecutados con éxito.")
    print(f"Mapa guardado correctamente en: {ruta_salida}")
    print("Ábrelo en tu navegador para verlo.")
