"""Excepciones propias del dominio de la aplicación.

Centralizar las excepciones evita usar `Exception` genérico en toda la
base de código y permite que la interfaz reaccione de forma distinta según
el tipo de error (por ejemplo, un error de Earth Engine se muestra distinto
a un error de validación de fechas).
"""
from __future__ import annotations


class TerraIntelError(Exception):
    """Excepción base de la aplicación."""


class EarthEngineNoInicializadoError(TerraIntelError):
    """Se intentó usar Earth Engine antes de inicializarlo correctamente."""


class DatosInsuficientesError(TerraIntelError):
    """No hay suficientes datos (imágenes, muestras, etc.) para continuar."""


class ValidacionError(TerraIntelError):
    """Un valor de entrada (fecha, coordenada, radio, etc.) no es válido."""


class ExportacionError(TerraIntelError):
    """Falló la generación de un archivo de exportación (PDF, Excel, etc.)."""


class ProyectoError(TerraIntelError):
    """Error al guardar o cargar un archivo de proyecto (.tiproj)."""


class GeocodificacionError(TerraIntelError):
    """No se pudo consultar el servicio de búsqueda de lugares (sin internet, límite de uso, etc.)."""
