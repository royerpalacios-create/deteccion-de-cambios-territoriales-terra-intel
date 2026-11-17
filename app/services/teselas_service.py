"""Descarga y caché de teselas de mapa (OpenStreetMap, Esri, ...).

Dos niveles de caché, de más rápido a más lento:

1. **Memoria** (:class:`CacheLRU`): las últimas N teselas ya decodificadas.
2. **Disco** (opcional): cada tesela descargada se guarda una vez y no se vuelve a pedir.

No depende de Qt: la interfaz decodifica y dibuja.

Sobre el uso de los servidores: OpenStreetMap exige identificar la aplicación con un
``User-Agent`` y no admite descargas masivas; Esri pide mostrar su atribución. Por eso
la caché en disco no es solo una optimización: reduce la carga sobre servicios gratuitos.
"""
from __future__ import annotations

import os
import threading
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Generic, Hashable, TypeVar

import requests

from app.core.logging_config import obtener_logger

logger = obtener_logger("teselas")

USER_AGENT = "TERRA_INTEL/2.0 (proyecto academico de deteccion de cambios; Python requests)"

K = TypeVar("K", bound=Hashable)
V = TypeVar("V")


@dataclass(frozen=True)
class FuenteMapa:
    clave: str
    nombre: str
    url: str            # con {z}, {x}, {y} (el orden depende del proveedor)
    atribucion: str
    zoom_max: int = 18

    def url_tesela(self, z: int, x: int, y: int) -> str:
        return self.url.format(z=z, x=x, y=y)


FUENTES_MAPA: dict[str, FuenteMapa] = {
    "osm": FuenteMapa(
        "osm", "Calles (OpenStreetMap)", "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
        "© Colaboradores de OpenStreetMap", zoom_max=19,
    ),
    "esri": FuenteMapa(
        "esri", "Satélite (Esri)",
        "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        "Imágenes © Esri, Maxar, Earthstar Geographics", zoom_max=18,
    ),
}
FUENTE_POR_DEFECTO = "osm"


class CacheLRU(Generic[K, V]):
    """Caché de tamaño fijo que descarta el elemento **menos recientemente usado**.

    Un diccionario (acceso O(1) por clave) que además recuerda el orden de uso. Leer o
    escribir una clave la mueve al final; al pasarse de la capacidad se saca la del
    principio. ``OrderedDict`` lo logra con una tabla hash y una lista doblemente enlazada.
    """

    def __init__(self, capacidad: int) -> None:
        if capacidad < 1:
            raise ValueError("La capacidad debe ser al menos 1.")
        self._capacidad = capacidad
        self._datos: OrderedDict[K, V] = OrderedDict()

    def get(self, clave: K) -> V | None:
        if clave not in self._datos:
            return None
        self._datos.move_to_end(clave)
        return self._datos[clave]

    def put(self, clave: K, valor: V) -> None:
        self._datos[clave] = valor
        self._datos.move_to_end(clave)
        while len(self._datos) > self._capacidad:
            self._datos.popitem(last=False)

    def peek(self, clave: K) -> V | None:
        """Lee sin alterar el orden de uso."""
        return self._datos.get(clave)

    def __contains__(self, clave: K) -> bool:
        return clave in self._datos

    def __len__(self) -> int:
        return len(self._datos)

    def claves(self) -> list[K]:
        return list(self._datos)


def _parece_imagen(datos: bytes) -> bool:
    """PNG o JPEG por su cabecera: evita guardar como tesela una página de error con código 200."""
    return datos.startswith(b"\x89PNG\r\n\x1a\n") or datos.startswith(b"\xff\xd8\xff")


class ServicioTeselas:
    """Obtiene los bytes de una tesela: disco primero, red después. Seguro entre hilos."""

    def __init__(self, directorio_cache: Path | None = None, timeout: float = 10.0) -> None:
        self.directorio_cache = directorio_cache
        self.timeout = timeout
        self._local = threading.local()

    def _sesion(self) -> requests.Session:
        # Una sesión por hilo: reutiliza la conexión TLS sin compartir estado entre hilos.
        if not hasattr(self._local, "sesion"):
            sesion = requests.Session()
            sesion.headers["User-Agent"] = USER_AGENT
            self._local.sesion = sesion
        return self._local.sesion

    def ruta_cache(self, fuente: FuenteMapa, z: int, x: int, y: int) -> Path | None:
        if self.directorio_cache is None:
            return None
        return self.directorio_cache / fuente.clave / str(z) / str(x) / f"{y}.tile"

    def obtener_bytes(self, fuente: FuenteMapa, z: int, x: int, y: int) -> bytes:
        """Devuelve la tesela; lanza ``requests.RequestException`` o ``ValueError`` si falla."""
        ruta = self.ruta_cache(fuente, z, x, y)
        if ruta is not None and ruta.exists():
            datos = ruta.read_bytes()
            if _parece_imagen(datos):
                return datos

        respuesta = self._sesion().get(fuente.url_tesela(z, x, y), timeout=self.timeout)
        respuesta.raise_for_status()
        datos = respuesta.content
        if not _parece_imagen(datos):
            raise ValueError(f"La respuesta para {fuente.clave}/{z}/{x}/{y} no es una imagen")

        if ruta is not None:
            try:
                ruta.parent.mkdir(parents=True, exist_ok=True)
                temporal = ruta.with_suffix(f".{os.getpid()}.{threading.get_ident()}.tmp")
                temporal.write_bytes(datos)
                temporal.replace(ruta)          # escritura atómica: nunca queda una tesela a medias
            except OSError:
                logger.warning("No se pudo guardar la tesela en la caché de disco.", exc_info=True)
        return datos
