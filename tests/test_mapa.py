"""Widget MapaNavegable: arrastre, zoom, clic, área, capas y modo sin conexión."""
import time

import pytest

pytest.importorskip("PyQt6.QtWidgets")

from PIL import Image  # noqa: E402
from PyQt6.QtCore import QEvent, QPoint, QPointF, Qt  # noqa: E402
from PyQt6.QtGui import QColor, QMouseEvent, QPixmap, QWheelEvent  # noqa: E402
from PyQt6.QtTest import QTest  # noqa: E402

from app.services.teselas_service import FUENTES_MAPA, FuenteMapa, ServicioTeselas  # noqa: E402
from app.ui.widgets.map_canvas import pil_a_qimage_rgba  # noqa: E402
from app.ui.widgets.map_view import CapaImagen, MapaNavegable  # noqa: E402
from app.utils.geo import LATITUD_MAXIMA, limites_cuadrado, lonlat_a_mundo, metros_por_pixel, tesela_de  # noqa: E402
from servidor_teselas import ServidorTeselas  # noqa: E402

LIMA = (-77.0428, -12.0464)


def esperar(qapp, condicion, timeout=6.0):
    limite = time.monotonic() + timeout
    while not condicion():
        assert time.monotonic() < limite, "Tiempo de espera agotado"
        qapp.processEvents()
        time.sleep(0.01)


def todas_cargadas(w):
    return bool(w._visibles) and all(k in w._cache for k in w._visibles)


@pytest.fixture
def servidor():
    with ServidorTeselas() as s:
        yield s


@pytest.fixture
def mapa(qapp, servidor, tmp_path, monkeypatch):
    monkeypatch.setitem(FUENTES_MAPA, "local", FuenteMapa("local", "Local", servidor.url, "© prueba", 18))
    w = MapaNavegable(ServicioTeselas(tmp_path, timeout=2))
    w.resize(768, 512)
    w.set_fuente("local")
    w.show()
    w.centrar(*LIMA, 10)
    yield w
    w.cerrar()
    w.close()


def evento_raton(tipo, pos, botones=Qt.MouseButton.LeftButton, boton=Qt.MouseButton.LeftButton):
    return QMouseEvent(tipo, QPointF(pos), QPointF(pos), boton, botones, Qt.KeyboardModifier.NoModifier)


def arrastrar(w, desde, hasta):
    w.mousePressEvent(evento_raton(QEvent.Type.MouseButtonPress, desde))
    w.mouseMoveEvent(evento_raton(QEvent.Type.MouseMove, hasta))
    w.mouseReleaseEvent(evento_raton(QEvent.Type.MouseButtonRelease, hasta, botones=Qt.MouseButton.NoButton))


def test_descarga_y_dibuja_las_teselas_visibles(qapp, mapa, servidor):
    esperar(qapp, lambda: todas_cargadas(mapa))
    assert len(servidor.peticiones) >= len(mapa._visibles)
    centro = mapa.grab().toImage().pixelColor(384, 256)
    assert centro != QColor(mapa._paleta.fondo_principal)         # hay una tesela, no el fondo vacío


def test_al_mover_se_piden_solo_las_teselas_nuevas(qapp, mapa, servidor):
    esperar(qapp, lambda: todas_cargadas(mapa))
    antes = len(servidor.peticiones)
    mapa.update(); qapp.processEvents()
    assert len(servidor.peticiones) == antes                      # mismas teselas: todo sale de la caché


def test_arrastrar_mueve_el_mapa_y_no_selecciona(qapp, mapa):
    elegidos = []
    mapa.habilitar_seleccion(True)
    mapa.punto_elegido.connect(lambda lon, lat: elegidos.append((lon, lat)))
    x0, y0 = lonlat_a_mundo(mapa.lon, mapa.lat, mapa.zoom)
    arrastrar(mapa, QPoint(300, 200), QPoint(200, 150))           # 100 px a la izquierda, 50 arriba
    x1, y1 = lonlat_a_mundo(mapa.lon, mapa.lat, mapa.zoom)
    assert (x1 - x0, y1 - y0) == pytest.approx((100, 50), abs=0.01)   # el contenido sigue al cursor
    assert elegidos == []


def test_clic_emite_el_punto_bajo_el_cursor_solo_si_la_seleccion_esta_activa(qapp, mapa):
    elegidos = []
    mapa.punto_elegido.connect(lambda lon, lat: elegidos.append((lon, lat)))
    QTest.mouseClick(mapa, Qt.MouseButton.LeftButton, pos=QPoint(384, 256))
    assert elegidos == []                                          # selección deshabilitada

    mapa.habilitar_seleccion(True)
    QTest.mouseClick(mapa, Qt.MouseButton.LeftButton, pos=QPoint(384, 256))
    QTest.mouseClick(mapa, Qt.MouseButton.LeftButton, pos=QPoint(484, 256))
    centro, derecha = elegidos
    assert centro == pytest.approx(mapa._lonlat_en(QPointF(384, 256)), abs=1e-9)
    assert centro == pytest.approx((mapa.lon, mapa.lat), abs=1e-3)
    assert derecha[0] > centro[0] and derecha[1] == pytest.approx(centro[1], abs=1e-9)


def test_zoom_mantiene_fijo_el_punto_bajo_el_cursor(qapp, mapa):
    cursor = QPointF(600, 100)
    antes = mapa._lonlat_en(cursor)
    mapa._cambiar_zoom(mapa.zoom + 2, cursor)
    assert mapa.zoom == 12
    assert mapa._lonlat_en(cursor) == pytest.approx(antes, abs=1e-7)


def test_rueda_y_doble_clic_acercan_y_los_limites_se_respetan(qapp, mapa):
    def rueda(delta):
        return QWheelEvent(QPointF(100, 100), QPointF(100, 100), QPoint(0, 0), QPoint(0, delta),
                           Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
                           Qt.ScrollPhase.NoScrollPhase, False)

    mapa.wheelEvent(rueda(120))
    assert mapa.zoom == 11
    mapa.wheelEvent(rueda(-60)); mapa.wheelEvent(rueda(-60))      # un touchpad envía fracciones: suman una muesca
    assert mapa.zoom == 10
    mapa.mouseDoubleClickEvent(evento_raton(QEvent.Type.MouseButtonDblClick, QPoint(200, 200)))
    assert mapa.zoom == 11
    mapa._cambiar_zoom(99)
    assert mapa.zoom == 18                                         # tope de la fuente
    mapa._cambiar_zoom(-5)
    assert mapa.zoom == 3                                          # mínimo del mapa


def test_teclado_mueve_y_hace_zoom(qapp, mapa):
    lon = mapa.lon
    QTest.keyClick(mapa, Qt.Key.Key_Right)
    assert mapa.lon > lon
    QTest.keyClick(mapa, Qt.Key.Key_Plus)
    assert mapa.zoom == 11
    QTest.keyClick(mapa, Qt.Key.Key_Minus)
    assert mapa.zoom == 10


def test_no_se_puede_pasar_de_los_polos(qapp, mapa):
    mapa._mover_a_mundo(0, -5_000)
    assert mapa.lat == pytest.approx(LATITUD_MAXIMA, abs=1e-6)
    mapa._mover_a_mundo(0, 10 ** 9)
    assert mapa.lat == pytest.approx(-LATITUD_MAXIMA, abs=1e-6)


def test_el_area_mide_lo_que_debe_en_pantalla(qapp, mapa):
    mapa.set_area(*LIMA, 10_000)
    mapa.centrar(*LIMA, 11)
    rect = mapa.rect_area()
    esperado = 2 * 10_000 / metros_por_pixel(LIMA[1], 11)
    assert rect.width() == pytest.approx(esperado, rel=3e-3) and rect.height() == pytest.approx(esperado, rel=3e-3)
    assert rect.center().x() == pytest.approx(384, abs=1) and rect.center().y() == pytest.approx(256, abs=1)
    mapa.limpiar_area()
    assert mapa.rect_area() is None


def test_ajustar_deja_el_area_completa_y_bien_encuadrada(qapp, mapa):
    for radio in (2_000, 10_000, 60_000):
        mapa.set_area(*LIMA, radio)
        mapa.ajustar_a_area()
        rect = mapa.rect_area()
        assert mapa.rect().contains(rect.toRect()) and rect.width() <= 0.6 * 512 + 1
        assert rect.width() > 0.25 * 512 or mapa.zoom == 18          # y no queda diminuta


def es_rojo(color: QColor) -> bool:
    """Rojo dominante (el relleno translúcido del área lo mezcla un poco con verde)."""
    return color.red() > 200 and color.green() < 70 and color.blue() < 70


def test_la_capa_se_dibuja_exactamente_dentro_de_sus_limites(qapp, mapa):
    mapa.set_area(*LIMA, 10_000)
    mapa.centrar(*LIMA, 11)
    rojo = pil_a_qimage_rgba(Image.new("RGBA", (50, 50), (255, 0, 0, 255)))
    mapa.set_capas([CapaImagen(rojo, limites_cuadrado(*LIMA, 10_000), 1.0)])
    esperar(qapp, lambda: todas_cargadas(mapa))
    imagen = mapa.grab().toImage()
    rect = mapa.rect_area()
    cx, cy = int(rect.center().x()), int(rect.center().y())
    assert es_rojo(imagen.pixelColor(cx + 20, cy + 20))
    assert es_rojo(imagen.pixelColor(int(rect.left()) + 6, int(rect.top()) + 6))       # justo dentro de la esquina
    assert not es_rojo(imagen.pixelColor(int(rect.left()) - 12, int(rect.top()) - 12))  # y nada fuera

    mapa.set_capas([CapaImagen(rojo, limites_cuadrado(*LIMA, 10_000), 0.0)])           # opacidad cero: invisible
    assert not es_rojo(mapa.grab().toImage().pixelColor(cx + 20, cy + 20))


def test_mientras_llega_una_tesela_se_dibuja_un_trozo_de_su_padre(qapp, tmp_path, monkeypatch):
    caido = FuenteMapa("caido", "Caído", "http://127.0.0.1:9/{z}/{x}/{y}.png", "")      # nada responde
    monkeypatch.setitem(FUENTES_MAPA, "caido", caido)
    w = MapaNavegable(ServicioTeselas(tmp_path, timeout=1))
    w.resize(512, 512)
    w.set_fuente("caido")
    w.show()
    w.centrar(*LIMA, 12)
    x, y = tesela_de(*LIMA, 12)
    padre = QPixmap(256, 256)
    padre.fill(QColor(200, 0, 200))
    w._cache.put(("caido", 11, x >> 1, y >> 1), padre)
    w.update(); qapp.processEvents()
    assert w.grab().toImage().pixelColor(256, 256) == QColor(200, 0, 200)
    w.cerrar(); w.close()


def test_sin_conexion_no_cuelga_y_avisa(qapp, tmp_path, monkeypatch):
    monkeypatch.setitem(FUENTES_MAPA, "caido", FuenteMapa("caido", "Caído", "http://127.0.0.1:9/{z}/{x}/{y}.png", ""))
    w = MapaNavegable(ServicioTeselas(tmp_path, timeout=1))
    w.resize(768, 512)
    w.set_fuente("caido")
    w.show()
    w.centrar(*LIMA, 10)
    esperar(qapp, lambda: w._errores_seguidos >= 3)
    w.grab()                                                       # dibujar con el aviso no lanza errores
    assert not w._cache.claves()
    w.cerrar(); w.close()


def test_cambiar_de_fuente_ajusta_el_zoom_y_las_cargas_pendientes_no_estorban(qapp, mapa):
    FUENTES_MAPA["otra"] = FuenteMapa("otra", "Otra", "http://127.0.0.1:9/{z}/{x}/{y}.png", "", zoom_max=12)
    try:
        mapa.centrar(*LIMA, 16)
        mapa.set_fuente("otra")
        assert mapa.zoom == 12
        mapa.set_fuente("local")
        assert mapa._fuente.clave == "local"
    finally:
        del FUENTES_MAPA["otra"]


def test_cerrar_detiene_el_descargador(qapp, mapa):
    mapa.cerrar()
    assert mapa._descargador._cerrado
    mapa.centrar(*LIMA, 14)
    mapa.update(); qapp.processEvents()                            # repintar tras cerrar no lanza ni pide nada
