"""Utilidades de imagen: carga (archivo/URL), redimensión y composición.

Incluye la corrección de un bug real del proyecto original: en
``interfaz.py``, ``mostrar_resultado_deteccion`` ignoraba por completo las
imágenes reales descargadas (satélite T1, satélite T2 y capa de cambios) y
en su lugar dibujaba círculos de relleno con ``ImageDraw`` a modo de
maqueta. Es decir, el resultado de la detección de cambios nunca se veía
realmente en pantalla. Las funciones ``componer_overlay`` y
``componer_swipe`` de este módulo sí usan las imágenes reales.
"""
from __future__ import annotations

import io
import os
import time
from typing import Union

import requests
from PIL import Image

Origen = Union[str, "os.PathLike[str]"]

# Los thumbnails de Earth Engine (earthengine.googleapis.com) no son un
# archivo estático: el servidor calcula/renderiza la imagen en el momento
# de responder la petición. Para un área de varios km² a 10m de resolución
# esto puede tardar bastante más que los 30s que se usaban antes (causaba
# "Read timed out. (read timeout=30)"). Por eso el timeout por defecto es
# de 2 minutos, con un par de reintentos ante fallas de red transitorias.
TIMEOUT_DEFECTO_SEGUNDOS = 120
REINTENTOS_DEFECTO = 2


def abrir_imagen(origen: Origen, timeout_segundos: int = TIMEOUT_DEFECTO_SEGUNDOS,
                  reintentos: int = REINTENTOS_DEFECTO) -> Image.Image:
    """Abre una imagen desde una ruta local o desde una URL http(s).

    Si ``origen`` es una URL, reintenta ante timeouts o errores de conexión
    transitorios antes de propagar la excepción.
    """
    if isinstance(origen, str) and origen.startswith(("http://", "https://")):
        ultimo_error: Exception | None = None
        for intento in range(reintentos + 1):
            try:
                respuesta = requests.get(origen, timeout=timeout_segundos)
                respuesta.raise_for_status()
                return Image.open(io.BytesIO(respuesta.content))
            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as error:
                ultimo_error = error
                if intento < reintentos:
                    time.sleep(2 * (intento + 1))  # espera creciente entre reintentos
        raise ultimo_error  # type: ignore[misc]
    return Image.open(origen)


def redimensionar_manteniendo_aspecto(imagen: Image.Image, ancho_max: int, alto_max: int) -> Image.Image:
    """Redimensiona ``imagen`` para que quepa en ``ancho_max x alto_max``."""
    ancho, alto = imagen.size
    if ancho <= 0 or alto <= 0:
        return imagen
    proporcion = ancho / alto

    nuevo_ancho, nuevo_alto = ancho, alto
    if nuevo_ancho > ancho_max:
        nuevo_ancho = ancho_max
        nuevo_alto = int(nuevo_ancho / proporcion)
    if nuevo_alto > alto_max:
        nuevo_alto = alto_max
        nuevo_ancho = int(nuevo_alto * proporcion)

    return imagen.resize((max(nuevo_ancho, 1), max(nuevo_alto, 1)), Image.Resampling.LANCZOS)


def componer_overlay(imagen_base: Image.Image, capa_cambios: Image.Image, opacidad: float = 1.0) -> Image.Image:
    """Superpone la capa de cambios (transparente donde no hubo cambio) sobre la base.

    Args:
        imagen_base: imagen satelital (normalmente la época T2), en RGBA.
        capa_cambios: capa de cambios con canal alfa (0 = sin cambio), en RGBA.
        opacidad: 0.0 (invisible) a 1.0 (totalmente opaca) para la capa de cambios.
    """
    base = imagen_base.convert("RGBA")
    capa = capa_cambios.convert("RGBA").resize(base.size, Image.Resampling.LANCZOS)

    if opacidad < 1.0:
        r, g, b, alfa = capa.split()
        alfa = alfa.point(lambda valor: int(valor * max(0.0, min(opacidad, 1.0))))
        capa = Image.merge("RGBA", (r, g, b, alfa))

    return Image.alpha_composite(base, capa)


def componer_swipe(
    imagen_izquierda: Image.Image,
    imagen_derecha: Image.Image,
    ancho_total: int,
    alto_total: int,
    posicion_relativa: float,
) -> Image.Image:
    """Combina dos imágenes lado a lado en la posición ``posicion_relativa`` (0-1).

    A la izquierda del corte se muestra ``imagen_izquierda`` y a la derecha
    ``imagen_derecha``, ambas redimensionadas para cubrir ``ancho_total x
    alto_total`` (recortadas si es necesario, para que el corte quede recto).
    """
    posicion_relativa = max(0.0, min(1.0, posicion_relativa))
    lienzo = Image.new("RGBA", (ancho_total, alto_total), (5, 20, 36, 255))

    def _cubrir(imagen: Image.Image) -> Image.Image:
        imagen = imagen.convert("RGBA")
        escala = max(ancho_total / imagen.width, alto_total / imagen.height)
        nuevo_tamano = (max(int(imagen.width * escala), 1), max(int(imagen.height * escala), 1))
        imagen = imagen.resize(nuevo_tamano, Image.Resampling.LANCZOS)
        x = (imagen.width - ancho_total) // 2
        y = (imagen.height - alto_total) // 2
        return imagen.crop((x, y, x + ancho_total, y + alto_total))

    izquierda = _cubrir(imagen_izquierda)
    derecha = _cubrir(imagen_derecha)

    corte_x = int(ancho_total * posicion_relativa)
    if corte_x > 0:
        lienzo.paste(izquierda.crop((0, 0, corte_x, alto_total)), (0, 0))
    if corte_x < ancho_total:
        lienzo.paste(derecha.crop((corte_x, 0, ancho_total, alto_total)), (corte_x, 0))

    return lienzo
