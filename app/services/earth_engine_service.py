"""Servicio: ciclo de vida de la conexión con Google Earth Engine.

Antes, tanto ``Proyecto.py`` como ``interfaz.py`` llamaban a
``ee.Initialize(project="dctiis")`` con el id de proyecto escrito a mano.
Ahora el id de proyecto viene de :class:`~app.core.config.AppConfig`, y el
estado de conexión (conectado / no conectado / motivo del error) se puede
consultar en cualquier momento desde la UI (barra de estado).
"""
from __future__ import annotations

from app.core.exceptions import EarthEngineNoInicializadoError
from app.core.logging_config import obtener_logger

logger = obtener_logger("earth_engine_service")


class EarthEngineService:
    """Encapsula la inicialización y el estado de conexión de Earth Engine."""

    def __init__(self, proyecto_ee: str) -> None:
        self._proyecto_ee = proyecto_ee
        self._conectado = False
        self._ultimo_error: str | None = None

    @property
    def conectado(self) -> bool:
        return self._conectado

    @property
    def ultimo_error(self) -> str | None:
        return self._ultimo_error

    def inicializar(self) -> bool:
        """Intenta inicializar Earth Engine. Devuelve ``True`` si conectó."""
        try:
            import ee

            ee.Initialize(project=self._proyecto_ee)
            self._conectado = True
            self._ultimo_error = None
            logger.info("Conexión con Earth Engine exitosa (proyecto=%s).", self._proyecto_ee)
        except Exception as error:  # Earth Engine lanza varios tipos de excepción propios
            self._conectado = False
            self._ultimo_error = str(error)
            logger.warning("No se pudo inicializar Earth Engine: %s", error)
        return self._conectado

    def requerir_conexion(self) -> None:
        """Lanza :class:`EarthEngineNoInicializadoError` si no hay conexión."""
        if not self._conectado:
            raise EarthEngineNoInicializadoError(
                "Earth Engine no está conectado. Ejecuta "
                "'python -c \"import ee; ee.Authenticate()\"' y reinicia la aplicación."
            )
