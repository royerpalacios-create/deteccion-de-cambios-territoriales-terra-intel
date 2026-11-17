"""Modelo de dominio: área de estudio (ROI) para la adquisición de datos.

Reemplaza el dataclass equivalente que vivía dentro de
``adquisicion_datos.py``. El único método que depende de Earth Engine
(``geometria``) importa ``ee`` de forma perezosa (dentro del método) para
que el resto del modelo se pueda instanciar y probar sin tener Earth
Engine inicializado.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

# Constantes de Puno conservadas por compatibilidad con tests existentes
LONGITUD_PUNO = -70.01
LATITUD_PUNO = -15.84
RADIO_BUFFER_METROS = 10_000

# Presupuesto de píxeles por época. Con radio 10 km a 10 m/píxel hay 4 M de píxeles;
# por encima de eso Earth Engine tarda mucho o rechaza la operación (maxPixels).
PIXELES_MAXIMOS_ANALISIS = 4_000_000
ESCALA_MINIMA_METROS = 10   # resolución nativa de las bandas usadas de Sentinel-2


@dataclass(frozen=True)
class AreaDeEstudio:
    """Representa el área de interés (ROI) para la adquisición de datos."""

    longitud: float
    latitud: float
    radio_metros: float
    nombre: str = "Área de estudio"

    def __post_init__(self) -> None:
        if self.radio_metros <= 0:
            raise ValueError("El radio del área de estudio debe ser mayor que cero.")
        if not (-180 <= self.longitud <= 180):
            raise ValueError("La longitud debe estar en el rango [-180, 180].")
        if not (-90 <= self.latitud <= 90):
            raise ValueError("La latitud debe estar en el rango [-90, 90].")

    def geometria(self):
        """Construye la geometría de Earth Engine para esta área de estudio."""
        import ee  # import perezoso: solo se necesita al usar EE de verdad

        return ee.Geometry.Point([self.longitud, self.latitud]).buffer(self.radio_metros).bounds()

    def centro(self) -> tuple[float, float]:
        """Devuelve ``(longitud, latitud)`` del centro del área."""
        return (self.longitud, self.latitud)


def estimar_pixeles(radio_metros: float, escala_metros: float) -> int:
    """Píxeles por época: el área es un cuadrado de lado 2r, así que crece como (2r/escala)²."""
    return int((2 * radio_metros / escala_metros) ** 2)


def calcular_escala_metros(radio_metros: float, max_pixeles: int = PIXELES_MAXIMOS_ANALISIS) -> int:
    """Escala de análisis (m/píxel): la más fina, múltiplo de 10, que respeta el presupuesto de píxeles.

    Se despeja de ``(2r / escala)² <= max_pixeles``. Cuando el área es grande se baja la
    resolución en lugar de pedirle a Earth Engine un cálculo que no va a terminar.
    """
    escala_minima = (2 * radio_metros) / math.sqrt(max_pixeles)
    return max(ESCALA_MINIMA_METROS, math.ceil(escala_minima / 10) * 10)


def crear_area_estudio(
    longitud: float,
    latitud: float,
    radio_metros: float = RADIO_BUFFER_METROS,
    nombre: str = "Área de estudio",
) -> AreaDeEstudio:
    """Crea un área de estudio para cualquier ubicación del Perú (o el mundo)."""
    return AreaDeEstudio(longitud=longitud, latitud=latitud, radio_metros=radio_metros, nombre=nombre)


# Alias de compatibilidad — mantiene el nombre original para no romper tests
def crear_area_estudio_puno(
    longitud: float = LONGITUD_PUNO,
    latitud: float = LATITUD_PUNO,
    radio_metros: float = RADIO_BUFFER_METROS,
    nombre: str = "Puno",
) -> AreaDeEstudio:
    """Crea el área de estudio centrada en Puno (alias de compatibilidad)."""
    return crear_area_estudio(longitud=longitud, latitud=latitud,
                              radio_metros=radio_metros, nombre=nombre)

