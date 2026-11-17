"""Búsqueda de lugares por nombre (geocodificación) con Nominatim de OpenStreetMap.

Política de uso de Nominatim: máximo 1 consulta por segundo, ``User-Agent`` propio y
nada de autocompletado. Aquí solo se consulta cuando el usuario pulsa «Buscar».
"""
from __future__ import annotations

from dataclasses import dataclass

import requests

from app.core.exceptions import GeocodificacionError, ValidacionError
from app.services.teselas_service import USER_AGENT

URL_NOMINATIM = "https://nominatim.openstreetmap.org/search"


@dataclass(frozen=True)
class Lugar:
    nombre: str       # nombre completo, tal como lo devuelve el servicio
    latitud: float
    longitud: float

    @property
    def nombre_corto(self) -> str:
        """Primer elemento del nombre ("Miraflores, Lima, Perú" -> "Miraflores")."""
        return self.nombre.split(",")[0].strip()


def buscar_lugar(texto: str, limite: int = 5, pais: str | None = "pe", timeout: float = 8.0) -> list[Lugar]:
    """Busca ``texto`` y devuelve hasta ``limite`` lugares (lista vacía si no hay resultados)."""
    texto = texto.strip()
    if len(texto) < 3:
        raise ValidacionError("Escribe al menos 3 caracteres para buscar.")

    parametros = {"q": texto, "format": "jsonv2", "limit": limite, "accept-language": "es"}
    if pais:
        parametros["countrycodes"] = pais
    try:
        respuesta = requests.get(URL_NOMINATIM, params=parametros, headers={"User-Agent": USER_AGENT},
                                 timeout=timeout)
        respuesta.raise_for_status()
        datos = respuesta.json()
        return [Lugar(item["display_name"], float(item["lat"]), float(item["lon"])) for item in datos]
    except (requests.RequestException, ValueError, KeyError, TypeError) as error:
        raise GeocodificacionError(f"No se pudo consultar el buscador de lugares: {error}") from error
