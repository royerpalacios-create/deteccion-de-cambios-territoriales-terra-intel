"""Área central de visualización: comparación satelital y capa de cambios.

Compone las imágenes reales (T1, T2 y capa de cambios) con
``app.utils.image_utils`` (PIL, sin cambios) y las pinta con ``QPainter``.

Diferencias respecto a la versión Tk:

- Cada ``mostrar_*`` guarda *cómo* componer la vista; al redimensionar la
  ventana se recompone solo (antes la imagen quedaba con el tamaño viejo).
- Las etiquetas y líneas guía se dibujan como "anotaciones" sobre la imagen,
  y :meth:`guardar_captura` guarda lo que se ve en pantalla, etiquetas incluidas.
"""
from __future__ import annotations

from typing import Callable, Optional

from PIL import Image
from PyQt6.QtCore import QRect, Qt
from PyQt6.QtGui import QColor, QImage, QPainter, QPen
from PyQt6.QtWidgets import QSizePolicy, QWidget

from app.ui.theme import Paleta, fuente
from app.utils.image_utils import componer_overlay, componer_swipe, redimensionar_manteniendo_aspecto

# Una anotación recibe (painter, ancho, alto) y dibuja encima de la imagen.
Anotacion = Callable[[QPainter, int, int], None]
# Una vista recibe (ancho, alto) y devuelve (imagen PIL | None, anotaciones).
Vista = Callable[[int, int], tuple[Optional[Image.Image], list[Anotacion]]]


def pil_a_qimage(imagen: Image.Image) -> QImage:
    """Convierte una imagen PIL a ``QImage`` (copia independiente del buffer)."""
    rgb = imagen.convert("RGB")
    qimg = QImage(rgb.tobytes("raw", "RGB"), rgb.width, rgb.height, rgb.width * 3, QImage.Format.Format_RGB888)
    return qimg.copy()


def pil_a_qimage_rgba(imagen: Image.Image) -> QImage:
    """Como :func:`pil_a_qimage` pero conserva la transparencia (capas superpuestas)."""
    rgba = imagen.convert("RGBA")
    qimg = QImage(rgba.tobytes("raw", "RGBA"), rgba.width, rgba.height, rgba.width * 4, QImage.Format.Format_RGBA8888)
    return qimg.copy()


class MapCanvas(QWidget):
    def __init__(self, paleta: Paleta, parent=None) -> None:
        super().__init__(parent)
        self._paleta = paleta
        self.setMinimumSize(240, 200)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self._vista: Optional[Vista] = None
        self._fondo: Optional[QImage] = None
        self._anotaciones: list[Anotacion] = []

        # Imágenes fuente (PIL, RGBA) cacheadas tras cargar / detectar.
        self.imagen_t1: Optional[Image.Image] = None
        self.imagen_t2: Optional[Image.Image] = None
        self.imagen_cambios: Optional[Image.Image] = None
        # Periodos mostrados en las etiquetas (los fija la ventana principal tras cargar).
        self.etiqueta_t1 = ""
        self.etiqueta_t2 = ""

    # ------------------------------------------------------------ tema
    def set_paleta(self, paleta: Paleta) -> None:
        self._paleta = paleta
        self._recomponer()

    # ------------------------------------------------------------ estados
    def mostrar_bienvenida(self) -> None:
        def vista(_ancho: int, _alto: int):
            paleta = self._paleta
            return None, [
                _texto_centrado("TERRA_INTEL", -20, 32, True, lambda: paleta.texto_primario),
                _texto_centrado(
                    "Carga dos imágenes satelitales (o usa Earth Engine)\n"
                    "y presiona 'DETECTAR CAMBIOS' para analizar",
                    40, 16, False, lambda: paleta.texto_secundario,
                ),
            ]

        self._establecer_vista(vista)

    def mostrar_error(self, mensaje: str) -> None:
        self._establecer_vista(lambda _a, _h: (
            None, [_texto_centrado(f"Error:\n{mensaje}", 0, 14, False, lambda: self._paleta.alerta)]
        ))

    # ------------------------------------------------------- comparación
    def mostrar_comparacion_lado_a_lado(self, imagen_t1: Image.Image, imagen_t2: Image.Image,
                                         etiqueta_t1: str, etiqueta_t2: str) -> None:
        """Vista previa simple lado a lado (antes de ejecutar la detección)."""
        def vista(ancho: int, alto: int):
            paleta = self._paleta
            img1 = redimensionar_manteniendo_aspecto(imagen_t1, ancho // 2, alto)
            img2 = redimensionar_manteniendo_aspecto(imagen_t2, ancho // 2, alto)
            lienzo = Image.new("RGBA", (ancho, alto), self._color_rgba(paleta.fondo_principal))
            lienzo.paste(img1, ((ancho // 2 - img1.width) // 2, (alto - img1.height) // 2))
            lienzo.paste(img2, (ancho // 2 + (ancho // 2 - img2.width) // 2, (alto - img2.height) // 2))

            def divisoria(p: QPainter, an: int, al: int) -> None:
                p.setPen(QPen(QColor(paleta.acento), 2, Qt.PenStyle.DashLine))
                p.drawLine(an // 2, 0, an // 2, al)

            return lienzo, [
                divisoria,
                _texto_esquina(etiqueta_t1, 20, 20, "nw", 16, lambda: paleta.texto_primario),
                _texto_esquina(etiqueta_t2, ancho // 2 + 20, 20, "nw", 16, lambda: paleta.advertencia),
            ]

        self._establecer_vista(vista)

    def mostrar_resultado_overlay(self, mostrar_t1: bool, mostrar_t2: bool,
                                   mostrar_cambios: bool, opacidad_cambios: float) -> None:
        """Muestra la Época A, la Época B, o la Época B con la capa de cambios encima.

        Respeta ambos checkboxes del panel de capas: solo Época A → 2019 sola;
        solo Época B → 2024 (con cambios encima si corresponde); ninguna → fondo.
        """
        if self.imagen_t2 is None:
            return
        def vista(ancho: int, alto: int):
            paleta = self._paleta
            etiqueta = ""
            if mostrar_t2:
                base = self.imagen_t2
                etiqueta = f"ÉPOCA B{self._sufijo(self.etiqueta_t2)}"
                if mostrar_cambios and self.imagen_cambios is not None:
                    base = componer_overlay(base, self.imagen_cambios, opacidad_cambios)
                    etiqueta = f"ÉPOCA B{self._sufijo(self.etiqueta_t2)} + Capa de cambios"
            elif mostrar_t1 and self.imagen_t1 is not None:
                base = self.imagen_t1
                etiqueta = f"ÉPOCA A{self._sufijo(self.etiqueta_t1)}"
            else:
                base = Image.new("RGBA", self.imagen_t2.size, (5, 20, 36, 255))
                etiqueta = "Sin capas visibles"

            compuesta = redimensionar_manteniendo_aspecto(base.convert("RGBA"), ancho, alto)
            lienzo = Image.new("RGBA", (ancho, alto), self._color_rgba(paleta.fondo_principal))
            lienzo.paste(compuesta, ((ancho - compuesta.width) // 2, (alto - compuesta.height) // 2), compuesta)
            return lienzo, [_texto_esquina(etiqueta, 20, 20, "nw", 14, lambda: paleta.texto_primario)]

        self._establecer_vista(vista)

    def mostrar_resultado_swipe(self, posicion_relativa: float, mostrar_cambios: bool,
                                 opacidad_cambios: float) -> None:
        """Comparación deslizante real entre T1 y (T2 + cambios)."""
        if self.imagen_t1 is None or self.imagen_t2 is None:
            return
        def vista(ancho: int, alto: int):
            paleta = self._paleta
            derecha = self.imagen_t2
            if mostrar_cambios and self.imagen_cambios is not None:
                derecha = componer_overlay(self.imagen_t2, self.imagen_cambios, opacidad_cambios)
            lienzo = componer_swipe(self.imagen_t1, derecha, ancho, alto, posicion_relativa)
            corte_x = int(ancho * max(0.0, min(1.0, posicion_relativa)))

            def corte(p: QPainter, _an: int, al: int) -> None:
                p.setPen(QPen(QColor(paleta.acento), 2))
                p.drawLine(corte_x, 0, corte_x, al)

            return lienzo, [
                corte,
                _texto_esquina("ANTES", 20, 20, "nw", 14, lambda: paleta.texto_primario),
                _texto_esquina("DESPUÉS", ancho - 20, 20, "ne", 14, lambda: paleta.advertencia),
            ]

        self._establecer_vista(vista)

    # ---------------------------------------------------------- helpers
    def guardar_captura(self, ruta) -> None:
        """Guarda como PNG lo que está dibujado ahora (imagen + etiquetas)."""
        if self._fondo is None:
            return
        self.grab().save(str(ruta), "PNG")

    def _establecer_vista(self, vista: Vista) -> None:
        self._vista = vista
        self._recomponer()

    def _recomponer(self) -> None:
        ancho, alto = self.width(), self.height()
        if self._vista is None or ancho <= 1 or alto <= 1:
            self.update()
            return
        imagen, self._anotaciones = self._vista(ancho, alto)
        self._fondo = pil_a_qimage(imagen) if imagen is not None else None
        self.update()

    def resizeEvent(self, evento) -> None:  # noqa: N802 (nombre impuesto por Qt)
        super().resizeEvent(evento)
        self._recomponer()

    def paintEvent(self, _evento) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        ancho, alto = self.width(), self.height()
        p.fillRect(self.rect(), QColor(self._paleta.fondo_principal))
        if self._fondo is not None:
            p.drawImage(0, 0, self._fondo)
        for anotar in self._anotaciones:
            anotar(p, ancho, alto)
        p.setPen(QColor(self._paleta.borde))
        p.drawRect(0, 0, ancho - 1, alto - 1)
        p.end()

    @staticmethod
    def _sufijo(periodo: str) -> str:
        return f" — {periodo}" if periodo else ""

    @staticmethod
    def _color_rgba(color_hex: str) -> tuple[int, int, int, int]:
        color_hex = color_hex.lstrip("#")
        r, g, b = (int(color_hex[i:i + 2], 16) for i in (0, 2, 4))
        return (r, g, b, 255)


# ------------------------------------------------- anotaciones (texto sobre la imagen)
def _texto_esquina(texto: str, x: int, y: int, ancla: str, px: int, color: Callable[[], str]) -> Anotacion:
    """Texto anclado a una esquina: ``nw`` (izq.-arriba) o ``ne`` (der.-arriba) respecto a (x, y)."""
    def dibujar(p: QPainter, ancho: int, alto: int) -> None:
        p.setFont(fuente(px, True))
        p.setPen(QColor(color()))
        if ancla == "ne":
            p.drawText(QRect(0, y, x, alto), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop, texto)
        else:
            p.drawText(QRect(x, y, max(0, ancho - x), alto), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, texto)
    return dibujar


def _texto_centrado(texto: str, desplazamiento_y: int, px: int, negrita: bool,
                    color: Callable[[], str]) -> Anotacion:
    """Texto (varias líneas) centrado en el lienzo, desplazado ``desplazamiento_y`` px."""
    def dibujar(p: QPainter, ancho: int, alto: int) -> None:
        p.setFont(fuente(px, negrita))
        p.setPen(QColor(color()))
        centro_y = alto // 2 + desplazamiento_y
        p.drawText(QRect(0, centro_y - 200, ancho, 400), Qt.AlignmentFlag.AlignCenter, texto)
    return dibujar
