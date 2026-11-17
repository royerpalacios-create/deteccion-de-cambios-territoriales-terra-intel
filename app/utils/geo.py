"""Geometría de mapas web: proyección Web Mercator, teselas y escalas.

Los mapas de OpenStreetMap, Google Maps, Esri, etc. dividen el mundo en
**teselas** (*tiles*) de 256 × 256 píxeles. En el zoom ``z`` el mundo es una
cuadrícula de ``2^z × 2^z`` teselas, es decir ``256 · 2^z`` píxeles por lado.
Cada tesela se identifica con ``(z, x, y)``, con ``(0, 0)`` arriba a la izquierda.

Todo aquí son funciones puras (sin Qt ni red) para poder probarlas con rigor.
"""
from __future__ import annotations

import math

TAM_TESELA = 256
RADIO_TIERRA_M = 6_378_137.0          # esfera de la proyección Web Mercator (EPSG:3857)
LATITUD_MAXIMA = 85.0511287798066     # límite de Mercator: más allá el mapa sería infinito


def lado_mundo_px(zoom: int) -> int:
    """Píxeles por lado del mapa del mundo completo en ``zoom``."""
    return TAM_TESELA * (2 ** zoom)


def lonlat_a_mundo(lon: float, lat: float, zoom: int) -> tuple[float, float]:
    """Convierte (lon, lat) en grados a píxeles del mundo ``(x, y)`` en ``zoom``."""
    n = lado_mundo_px(zoom)
    lat = max(-LATITUD_MAXIMA, min(LATITUD_MAXIMA, lat))
    seno = math.sin(math.radians(lat))
    x = (lon + 180.0) / 360.0 * n
    y = (0.5 - math.log((1 + seno) / (1 - seno)) / (4 * math.pi)) * n
    return x, y


def mundo_a_lonlat(x: float, y: float, zoom: int) -> tuple[float, float]:
    """Inversa de :func:`lonlat_a_mundo`."""
    n = lado_mundo_px(zoom)
    lon = x / n * 360.0 - 180.0
    lat = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / n))))
    return lon, lat


def tesela_de(lon: float, lat: float, zoom: int) -> tuple[int, int]:
    """Índices ``(x, y)`` de la tesela que contiene el punto."""
    x, y = lonlat_a_mundo(lon, lat, zoom)
    maximo = 2 ** zoom - 1
    return min(maximo, int(x // TAM_TESELA)), min(maximo, int(y // TAM_TESELA))


def metros_por_pixel(lat: float, zoom: int) -> float:
    """Metros que cubre un píxel a esa latitud (Mercator estira los polos: se escala con cos φ)."""
    return 2 * math.pi * RADIO_TIERRA_M * math.cos(math.radians(lat)) / lado_mundo_px(zoom)


def limites_cuadrado(lon: float, lat: float, radio_m: float) -> tuple[float, float, float, float]:
    """Rectángulo ``(lon_min, lat_min, lon_max, lat_max)`` del cuadrado de lado ``2·radio`` centrado en el punto.

    Equivale al ``buffer(radio).bounds()`` del área de estudio en Earth Engine
    (círculo geodésico sobre la esfera y su caja envolvente en lon/lat).
    """
    angulo = radio_m / RADIO_TIERRA_M
    dlat = math.degrees(angulo)
    dlon = math.degrees(math.asin(min(1.0, math.sin(angulo) / math.cos(math.radians(lat)))))
    return lon - dlon, lat - dlat, lon + dlon, lat + dlat


def zoom_para_ajustar(lat: float, radio_m: float, ancho_px: int, alto_px: int,
                      ocupacion: float = 0.6, zoom_min: int = 3, zoom_max: int = 18) -> int:
    """Mayor zoom entero en el que el cuadrado de lado ``2·radio`` ocupa a lo sumo ``ocupacion`` de la vista."""
    disponible = ocupacion * min(ancho_px, alto_px)
    for zoom in range(zoom_max, zoom_min - 1, -1):
        if 2 * radio_m / metros_por_pixel(lat, zoom) <= disponible:
            return zoom
    return zoom_min


_LONGITUDES_ESCALA_M = [m * 10 ** e for e in range(-1, 7) for m in (1, 2, 5)]


def barra_escala(lat: float, zoom: int, ancho_objetivo_px: int = 110) -> tuple[float, int]:
    """Longitud "redonda" (1, 2, 5 × 10^n metros) y su ancho en píxeles, para la barra de escala.

    Elige la mayor longitud de la lista que cabe en ``ancho_objetivo_px``.
    """
    mpp = metros_por_pixel(lat, zoom)
    elegida = _LONGITUDES_ESCALA_M[0]
    for metros in _LONGITUDES_ESCALA_M:
        if metros / mpp <= ancho_objetivo_px:
            elegida = metros
        else:
            break
    return elegida, round(elegida / mpp)


def formatear_distancia(metros: float) -> str:
    return f"{metros / 1000:g} km" if metros >= 1000 else f"{metros:g} m"
