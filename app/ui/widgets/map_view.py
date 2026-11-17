"""Mapa navegable estilo Google Maps / OpenStreetMap, hecho con Qt puro.

- Arrastrar para mover, rueda o doble clic para acercar, teclado (flechas, + / -).
- Clic para elegir un punto (cuando la selección está habilitada).
- Capas base intercambiables (calles / satélite) y barra de escala.
- Dibuja el área de estudio (cuadrado de lado 2·radio) y capas de imagen georreferenciadas
  (por ejemplo la capa de cambios detectados) encima del mapa.

Cómo funciona un mapa web: el mundo es una cuadrícula de teselas de 256 px (ver
``app.utils.geo``). En cada repintado se calcula qué teselas cubren la ventana, se dibujan
las que ya están en caché y se piden las que faltan en hilos de fondo. Mientras llega una
tesela se dibuja un trozo ampliado de su "padre" (la tesela del zoom anterior), así el mapa
nunca queda en blanco al moverse o acercar.
"""
from __future__ import annotations

import queue
import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional

from PyQt6.QtCore import QObject, QPointF, QRect, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QImage, QKeyEvent, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import QComboBox, QPushButton, QSizePolicy, QWidget

from app.core.logging_config import obtener_logger
from app.services.teselas_service import (
    CacheLRU, FUENTE_POR_DEFECTO, FUENTES_MAPA, FuenteMapa, ServicioTeselas,
)
from app.ui.theme import PALETA_OSCURA, Paleta, fuente
from app.utils.geo import (
    LATITUD_MAXIMA, TAM_TESELA, barra_escala, formatear_distancia, limites_cuadrado,
    lonlat_a_mundo, mundo_a_lonlat, zoom_para_ajustar,
)

logger = obtener_logger("mapa")

ZOOM_MIN = 3
TESELAS_EN_MEMORIA = 250      # 250 × 256×256×4 B ≈ 65 MB como máximo (la vista usa ~20 y sus "padres")
REINTENTO_TRAS_FALLO_S = 15.0
Clave = tuple[str, int, int, int]     # (fuente, z, x, y)


@dataclass
class CapaImagen:
    """Imagen georreferenciada dibujada sobre el mapa (``limites`` = lon_min, lat_min, lon_max, lat_max)."""

    imagen: QImage
    limites: tuple[float, float, float, float]
    opacidad: float = 1.0


class _Descargador(QObject):
    """Cola de descargas con hilos *daemon* (no frenan el cierre de la app).

    Usa una **pila** (LIFO): al mover el mapa rápido, lo último que se pidió es lo que está
    en pantalla, así que se atiende primero. Las peticiones que ya no se ven se descartan.
    """

    listo = pyqtSignal(object, object, str)    # clave, QImage | None, "ok" | "fallo" | "omitida"

    def __init__(self, servicio: ServicioTeselas, trabajadores: int = 6, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._servicio = servicio
        self._n = trabajadores
        self._cola: queue.LifoQueue = queue.LifoQueue()
        self._pendientes: set[Clave] = set()
        self._hilos: list[threading.Thread] = []
        self._cerrado = False

    def pedir(self, fuente_mapa: FuenteMapa, clave: Clave, vigente: Callable[[Clave], bool]) -> None:
        if self._cerrado or clave in self._pendientes:
            return
        if not self._hilos:
            self._hilos = [threading.Thread(target=self._bucle, daemon=True, name=f"teselas-{i}")
                           for i in range(self._n)]
            for hilo in self._hilos:
                hilo.start()
        self._pendientes.add(clave)
        self._cola.put((fuente_mapa, clave, vigente))

    def cerrar(self) -> None:
        self._cerrado = True
        for _ in self._hilos:
            self._cola.put(None)

    def _bucle(self) -> None:
        while True:
            item = self._cola.get()
            if item is None:
                return
            fuente_mapa, clave, vigente = item
            imagen, estado = None, "omitida"
            try:
                if vigente(clave):
                    _, z, x, y = clave
                    imagen = QImage.fromData(self._servicio.obtener_bytes(fuente_mapa, z, x, y))
                    estado = "ok" if not imagen.isNull() else "fallo"
            except Exception as error:      # red caída, 404, límite de uso...: se reintenta más tarde
                logger.debug("Tesela %s no disponible: %s", clave, error)
                estado = "fallo"
            finally:
                self._pendientes.discard(clave)
            if self._cerrado:
                return
            try:
                self.listo.emit(clave, imagen if estado == "ok" else None, estado)
            except RuntimeError:            # el widget ya se destruyó
                return


class MapaNavegable(QWidget):
    punto_elegido = pyqtSignal(float, float)    # lon, lat del clic (si la selección está habilitada)
    vista_cambiada = pyqtSignal()

    def __init__(self, servicio: ServicioTeselas | None = None, paleta: Paleta = PALETA_OSCURA,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._paleta = paleta
        self.setMinimumSize(280, 220)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self._fuente = FUENTES_MAPA[FUENTE_POR_DEFECTO]
        self._lon, self._lat, self._zoom = -75.0, -10.0, 5       # vista inicial: Perú
        self._area: Optional[tuple[float, float, float]] = None   # (lon, lat, radio_m)
        self._capas: list[CapaImagen] = []
        self._seleccion = False

        self._cache: CacheLRU[Clave, QPixmap] = CacheLRU(TESELAS_EN_MEMORIA)
        self._fallidas: dict[Clave, float] = {}
        self._visibles: set[Clave] = set()
        self._errores_seguidos = 0
        self._descargador = _Descargador(servicio or ServicioTeselas(), parent=self)
        self._descargador.listo.connect(self._al_llegar_tesela)
        descargador = self._descargador
        self.destroyed.connect(lambda *_: descargador.cerrar())
        self._temporizador_reintento = QTimer(self)
        self._temporizador_reintento.setSingleShot(True)
        self._temporizador_reintento.timeout.connect(self.update)

        self._press: Optional[QPointF] = None
        self._press_centro: tuple[float, float] = (0.0, 0.0)
        self._arrastrando = False
        self._cursor: Optional[QPointF] = None
        self._rueda = 0

        self._construir_controles()
        self._actualizar_cursor()

    # ------------------------------------------------------------- controles
    def _construir_controles(self) -> None:
        def boton(texto: str, ayuda: str, comando: Callable[[], None]) -> QPushButton:
            b = QPushButton(texto, self)
            b.setFixedSize(34, 34)
            b.setStyleSheet("padding: 0px;")      # el relleno global de los botones no deja espacio al símbolo
            b.setFont(fuente(16, True))
            b.setToolTip(ayuda)
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _marcado=False: comando())
            return b

        self._btn_mas = boton("+", "Acercar", lambda: self._cambiar_zoom(self._zoom + 1))
        self._btn_menos = boton("−", "Alejar", lambda: self._cambiar_zoom(self._zoom - 1))
        self._btn_ajustar = boton("⌖", "Ajustar al área de estudio", self.ajustar_a_area)
        self._combo_fuente = QComboBox(self)
        self._combo_fuente.setFont(fuente(11))
        self._combo_fuente.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        for f in FUENTES_MAPA.values():
            self._combo_fuente.addItem(f.nombre, f.clave)
        self._combo_fuente.currentIndexChanged.connect(
            lambda _i: self.set_fuente(self._combo_fuente.currentData()))

    def resizeEvent(self, evento) -> None:  # noqa: N802
        super().resizeEvent(evento)
        self._btn_mas.move(10, 10)
        self._btn_menos.move(10, 10 + 36)
        self._btn_ajustar.move(10, 10 + 72)
        self._combo_fuente.setFixedWidth(200)
        self._combo_fuente.move(self.width() - 210, 10)

    # ------------------------------------------------------------- API pública
    @property
    def lon(self) -> float:
        return self._lon

    @property
    def lat(self) -> float:
        return self._lat

    @property
    def zoom(self) -> int:
        return self._zoom

    def set_paleta(self, paleta: Paleta) -> None:
        self._paleta = paleta
        self.update()

    def habilitar_seleccion(self, activa: bool) -> None:
        self._seleccion = activa
        self._actualizar_cursor()

    def centrar(self, lon: float, lat: float, zoom: int | None = None) -> None:
        self._lon, self._lat = lon, max(-LATITUD_MAXIMA, min(LATITUD_MAXIMA, lat))
        if zoom is not None:
            self._zoom = max(ZOOM_MIN, min(self._fuente.zoom_max, zoom))
        self.vista_cambiada.emit()
        self.update()

    def set_area(self, lon: float, lat: float, radio_m: float) -> None:
        self._area = (lon, lat, radio_m)
        self.update()

    def limpiar_area(self) -> None:
        self._area = None
        self.update()

    def ajustar_a_area(self) -> None:
        """Centra el mapa en el área de estudio con el zoom justo para que se vea completa."""
        if self._area is None:
            return
        lon, lat, radio = self._area
        zoom = zoom_para_ajustar(lat, radio, self.width(), self.height(), zoom_max=self._fuente.zoom_max)
        self.centrar(lon, lat, zoom)

    def set_capas(self, capas: list[CapaImagen]) -> None:
        self._capas = list(capas)
        self.update()

    def set_fuente(self, clave: str) -> None:
        if clave not in FUENTES_MAPA or clave == self._fuente.clave:
            return
        self._fuente = FUENTES_MAPA[clave]
        self._errores_seguidos = 0
        self._zoom = min(self._zoom, self._fuente.zoom_max)
        indice = self._combo_fuente.findData(clave)
        if indice >= 0 and self._combo_fuente.currentIndex() != indice:
            self._combo_fuente.blockSignals(True)
            self._combo_fuente.setCurrentIndex(indice)
            self._combo_fuente.blockSignals(False)
        self.update()

    def rect_area(self) -> Optional[QRectF]:
        """Rectángulo del área de estudio en coordenadas del widget (``None`` si no hay área)."""
        if self._area is None:
            return None
        lon, lat, radio = self._area
        ox, oy = self._origen()
        return self._rect_geografico(limites_cuadrado(lon, lat, radio), ox, oy)

    def cerrar(self) -> None:
        self._descargador.cerrar()

    # --------------------------------------------------------- geometría de vista
    def _centro_mundo(self) -> tuple[float, float]:
        return lonlat_a_mundo(self._lon, self._lat, self._zoom)

    def _origen(self) -> tuple[int, int]:
        """Píxel del mundo que cae en la esquina superior izquierda del widget (entero: sin costuras)."""
        cx, cy = self._centro_mundo()
        return round(cx - self.width() / 2), round(cy - self.height() / 2)

    def _lonlat_en(self, pos: QPointF) -> tuple[float, float]:
        ox, oy = self._origen()
        return mundo_a_lonlat(ox + pos.x(), oy + pos.y(), self._zoom)

    def _rect_geografico(self, limites: tuple[float, float, float, float], ox: int, oy: int) -> QRectF:
        lon_min, lat_min, lon_max, lat_max = limites
        x1, y1 = lonlat_a_mundo(lon_min, lat_max, self._zoom)
        x2, y2 = lonlat_a_mundo(lon_max, lat_min, self._zoom)
        return QRectF(x1 - ox, y1 - oy, x2 - x1, y2 - y1)

    def _mover_a_mundo(self, cx: float, cy: float) -> None:
        n = TAM_TESELA * (2 ** self._zoom)
        cy = max(0.0, min(float(n), cy))
        self._lon, self._lat = mundo_a_lonlat(cx % n, cy, self._zoom)
        self.vista_cambiada.emit()
        self.update()

    def _cambiar_zoom(self, nuevo: int, ancla: QPointF | None = None) -> None:
        """Cambia el zoom manteniendo fijo el punto bajo ``ancla`` (el cursor, o el centro)."""
        nuevo = max(ZOOM_MIN, min(self._fuente.zoom_max, nuevo))
        if nuevo == self._zoom:
            return
        ancla = ancla or QPointF(self.width() / 2, self.height() / 2)
        lon_a, lat_a = self._lonlat_en(ancla)
        self._zoom = nuevo
        px, py = lonlat_a_mundo(lon_a, lat_a, nuevo)
        self._mover_a_mundo(px - (ancla.x() - self.width() / 2), py - (ancla.y() - self.height() / 2))

    # ------------------------------------------------------------------ teselas
    def _vigente(self, clave: Clave) -> bool:
        return clave in self._visibles

    def _pedir(self, clave: Clave) -> None:
        fallo = self._fallidas.get(clave)
        if fallo is not None and time.monotonic() - fallo < REINTENTO_TRAS_FALLO_S:
            return
        fuente_mapa = FUENTES_MAPA[clave[0]]
        self._descargador.pedir(fuente_mapa, clave, self._vigente)

    def _al_llegar_tesela(self, clave: Clave, imagen: Optional[QImage], estado: str) -> None:
        if estado == "ok" and imagen is not None:
            self._cache.put(clave, QPixmap.fromImage(imagen))
            self._fallidas.pop(clave, None)
            self._errores_seguidos = 0
        elif estado == "fallo":
            self._fallidas[clave] = time.monotonic()
            self._errores_seguidos += 1
            self._temporizador_reintento.start(int(REINTENTO_TRAS_FALLO_S * 1000) + 200)
        self.update()

    def _dibujar_tesela(self, p: QPainter, clave: Clave, destino: QRect) -> None:
        pixmap = self._cache.get(clave)
        if pixmap is not None:
            p.drawPixmap(destino, pixmap)
            return
        nombre, z, x, y = clave
        for k in range(1, 4):                       # sustituto: trozo ampliado de la tesela "padre"
            if z - k < 0:
                break
            padre = self._cache.peek((nombre, z - k, x >> k, y >> k))
            if padre is not None:
                lado = TAM_TESELA / (2 ** k)
                origen = QRectF((x % 2 ** k) * lado, (y % 2 ** k) * lado, lado, lado)
                p.drawPixmap(QRectF(destino), padre, origen)
                return
        p.fillRect(destino, QColor(self._paleta.fondo_superficie))
        p.setPen(QColor(self._paleta.borde))
        p.drawRect(destino.adjusted(0, 0, -1, -1))

    # ------------------------------------------------------------------- dibujo
    def paintEvent(self, _evento) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHints(QPainter.RenderHint.SmoothPixmapTransform | QPainter.RenderHint.TextAntialiasing
                         | QPainter.RenderHint.Antialiasing)
        ancho, alto = self.width(), self.height()
        p.fillRect(self.rect(), QColor(self._paleta.fondo_principal))

        ox, oy = self._origen()
        n = 2 ** self._zoom
        visibles: set[Clave] = set()
        faltantes: list[Clave] = []
        for ty in range(max(0, oy // TAM_TESELA), min(n - 1, (oy + alto) // TAM_TESELA) + 1):
            for tx in range(ox // TAM_TESELA, (ox + ancho) // TAM_TESELA + 1):
                clave = (self._fuente.clave, self._zoom, tx % n, ty)     # el mundo se repite en longitud
                visibles.add(clave)
                if clave not in self._cache:
                    faltantes.append(clave)
                self._dibujar_tesela(p, clave, QRect(tx * TAM_TESELA - ox, ty * TAM_TESELA - oy, TAM_TESELA, TAM_TESELA))
        self._visibles = visibles
        for clave in faltantes:
            self._pedir(clave)

        for capa in self._capas:
            p.setOpacity(capa.opacidad)
            p.drawImage(self._rect_geografico(capa.limites, ox, oy), capa.imagen)
        p.setOpacity(1.0)

        self._dibujar_area(p)
        self._dibujar_informacion(p, ancho, alto)
        p.setPen(QColor(self._paleta.borde))
        p.drawRect(0, 0, ancho - 1, alto - 1)
        p.end()

    def _dibujar_area(self, p: QPainter) -> None:
        rect = self.rect_area()
        if rect is None or self._area is None:
            return
        acento = QColor(self._paleta.acento)
        relleno = QColor(acento)
        relleno.setAlpha(35)
        p.fillRect(rect, relleno)
        p.setPen(QPen(acento, 2))
        p.drawRect(rect)
        centro = rect.center()
        p.drawLine(QPointF(centro.x() - 9, centro.y()), QPointF(centro.x() + 9, centro.y()))
        p.drawLine(QPointF(centro.x(), centro.y() - 9), QPointF(centro.x(), centro.y() + 9))
        p.setBrush(acento)
        p.drawEllipse(centro, 3, 3)
        p.setBrush(Qt.BrushStyle.NoBrush)
        lado = formatear_distancia(2 * self._area[2])
        self._rotulo(p, f"{lado} × {lado}", QPointF(rect.left() + 4, rect.bottom() + 4), arriba=False)

    def _rotulo(self, p: QPainter, texto: str, esquina: QPointF, arriba: bool = True) -> None:
        """Texto con fondo translúcido para que se lea sobre cualquier mapa."""
        p.setFont(fuente(11, True))
        caja = p.fontMetrics().boundingRect(texto).adjusted(-6, -3, 6, 3)
        caja.moveTo(int(esquina.x()), int(esquina.y()) - (caja.height() if arriba else 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 150))
        p.drawRoundedRect(QRectF(caja), 4, 4)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QColor("#ffffff"))
        p.drawText(caja, Qt.AlignmentFlag.AlignCenter, texto)

    def _dibujar_informacion(self, p: QPainter, ancho: int, alto: int) -> None:
        lon, lat = (self._lonlat_en(self._cursor) if self._cursor is not None else (self._lon, self._lat))
        metros, px = barra_escala(self._lat, self._zoom)
        x0, y0 = 12, alto - 46
        p.setPen(QPen(QColor(0, 0, 0, 200), 4))
        p.drawLine(x0, y0, x0 + px, y0)
        p.drawLine(x0, y0 - 5, x0, y0 + 5)
        p.drawLine(x0 + px, y0 - 5, x0 + px, y0 + 5)
        p.setPen(QPen(QColor("#ffffff"), 2))
        p.drawLine(x0, y0, x0 + px, y0)
        p.drawLine(x0, y0 - 5, x0, y0 + 5)
        p.drawLine(x0 + px, y0 - 5, x0 + px, y0 + 5)
        self._rotulo(p, formatear_distancia(metros), QPointF(x0 + px + 8, y0 + 9))
        self._rotulo(p, f"Lat {lat:.5f}   Lon {lon:.5f}   ·   zoom {self._zoom}", QPointF(12, alto - 10))

        p.setFont(fuente(9))
        atribucion = self._fuente.atribucion
        caja = p.fontMetrics().boundingRect(atribucion).adjusted(-6, -2, 6, 2)
        caja.moveTo(ancho - caja.width() - 6, alto - caja.height() - 6)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 255, 255, 190))
        p.drawRoundedRect(QRectF(caja), 3, 3)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QColor("#222222"))
        p.drawText(caja, Qt.AlignmentFlag.AlignCenter, atribucion)

        if self._errores_seguidos >= 3:
            self._rotulo(p, "Sin conexión: no se pueden descargar los mapas",
                         QPointF(max(8, ancho / 2 - 160), 56), arriba=False)

    # --------------------------------------------------------------- interacción
    def _actualizar_cursor(self) -> None:
        if self._arrastrando:
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        elif self._seleccion:
            self.setCursor(Qt.CursorShape.CrossCursor)
        else:
            self.setCursor(Qt.CursorShape.OpenHandCursor)

    def mousePressEvent(self, evento) -> None:  # noqa: N802
        if evento.button() == Qt.MouseButton.LeftButton:
            self.setFocus()
            self._press = evento.position()
            self._press_centro = self._centro_mundo()
            self._arrastrando = False

    def mouseMoveEvent(self, evento) -> None:  # noqa: N802
        pos = evento.position()
        self._cursor = pos
        if self._press is not None and (evento.buttons() & Qt.MouseButton.LeftButton):
            delta = pos - self._press
            if not self._arrastrando and abs(delta.x()) + abs(delta.y()) > 4:
                self._arrastrando = True
                self._actualizar_cursor()
            if self._arrastrando:
                self._mover_a_mundo(self._press_centro[0] - delta.x(), self._press_centro[1] - delta.y())
        self.update()

    def mouseReleaseEvent(self, evento) -> None:  # noqa: N802
        if evento.button() == Qt.MouseButton.LeftButton and self._press is not None:
            if not self._arrastrando and self._seleccion:
                lon, lat = self._lonlat_en(evento.position())
                self.punto_elegido.emit(lon, lat)
            self._press = None
            self._arrastrando = False
            self._actualizar_cursor()

    def leaveEvent(self, evento) -> None:  # noqa: N802
        self._cursor = None
        super().leaveEvent(evento)
        self.update()

    def mouseDoubleClickEvent(self, evento) -> None:  # noqa: N802
        if evento.button() == Qt.MouseButton.LeftButton:
            self._cambiar_zoom(self._zoom + 1, evento.position())

    def wheelEvent(self, evento) -> None:  # noqa: N802
        self._rueda += evento.angleDelta().y()
        pasos = int(self._rueda / 120)          # una "muesca" de rueda = 120; los touchpads envían fracciones
        if pasos:
            self._rueda -= pasos * 120
            self._cambiar_zoom(self._zoom + pasos, evento.position())
        evento.accept()

    def keyPressEvent(self, evento: QKeyEvent) -> None:  # noqa: N802
        paso = 100
        cx, cy = self._centro_mundo()
        tecla = evento.key()
        if tecla == Qt.Key.Key_Left:
            self._mover_a_mundo(cx - paso, cy)
        elif tecla == Qt.Key.Key_Right:
            self._mover_a_mundo(cx + paso, cy)
        elif tecla == Qt.Key.Key_Up:
            self._mover_a_mundo(cx, cy - paso)
        elif tecla == Qt.Key.Key_Down:
            self._mover_a_mundo(cx, cy + paso)
        elif tecla in (Qt.Key.Key_Plus, Qt.Key.Key_Equal):
            self._cambiar_zoom(self._zoom + 1)
        elif tecla in (Qt.Key.Key_Minus, Qt.Key.Key_Underscore):
            self._cambiar_zoom(self._zoom - 1)
        else:
            super().keyPressEvent(evento)
