"""AreaEstudioDialog con mapa: sincronización de campos, buscador y selección por clic."""
import time

import pytest

pytest.importorskip("PyQt6.QtWidgets")

from app.core.exceptions import GeocodificacionError  # noqa: E402
from app.models.area_estudio import RADIO_BUFFER_METROS  # noqa: E402
from app.services.geocodificacion_service import Lugar  # noqa: E402
from app.ui.widgets.area_dialog import AreaEstudioDialog  # noqa: E402

pytestmark = pytest.mark.usefixtures("sin_red_de_mapas")

MIRAFLORES = Lugar("Miraflores, Lima, Lima Metropolitana, Perú", -12.1211, -77.0297)
SURCO = Lugar("Santiago de Surco, Lima, Perú", -12.1453, -76.9918)


def esperar(qapp, condicion, timeout=5.0):
    limite = time.monotonic() + timeout
    while not condicion():
        assert time.monotonic() < limite, "Tiempo de espera agotado"
        qapp.processEvents()
        time.sleep(0.01)


@pytest.fixture
def dialogo(qapp):
    d = AreaEstudioDialog()
    d._tabs.setCurrentIndex(1)
    d.show()
    qapp.processEvents()
    yield d
    d.done(0)


def test_clic_en_el_mapa_rellena_los_campos_sin_recentrar(qapp, dialogo):
    centro_antes = (dialogo._mapa.lon, dialogo._mapa.lat)
    dialogo._mapa.punto_elegido.emit(-77.0300, -12.1200)
    assert (dialogo._spin_lon.value(), dialogo._spin_lat.value()) == (-77.03, -12.12)
    assert (dialogo._mapa.lon, dialogo._mapa.lat) == centro_antes          # la vista no salta bajo el cursor
    assert dialogo._mapa._area[:2] == (-77.03, -12.12)                     # pero el cuadrado sí se mueve
    assert "-12.1200" in dialogo._lbl_busqueda.text()


def test_un_clic_fuera_de_peru_se_limita_y_se_avisa(qapp, dialogo):
    dialogo._mapa.punto_elegido.emit(-100.0, 10.0)
    assert dialogo._spin_lon.value() == dialogo._spin_lon.minimum()
    assert dialogo._spin_lat.value() == dialogo._spin_lat.maximum()
    assert "fuera de Perú" in dialogo._lbl_busqueda.text()


def test_escribir_coordenadas_lleva_el_mapa_hasta_ahi(qapp, dialogo):
    dialogo._spin_lat.setValue(-13.5)
    dialogo._spin_lon.setValue(-71.97)
    assert (dialogo._mapa.lon, dialogo._mapa.lat) == pytest.approx((-71.97, -13.5), abs=1e-9)
    assert dialogo._mapa._area[:2] == (-71.97, -13.5)


def test_cambiar_el_radio_actualiza_el_cuadrado_y_vuelve_a_encuadrar(qapp, dialogo):
    dialogo._spin_radio.setValue(30_000)
    zoom_grande = dialogo._mapa.zoom
    dialogo._spin_radio.setValue(3_000)
    assert dialogo._mapa._area[2] == 3_000
    assert dialogo._mapa.zoom > zoom_grande                                  # área menor -> más zoom
    rect = dialogo._mapa.rect_area()
    assert dialogo._mapa.rect().contains(rect.toRect())


def test_busqueda_completa_elige_el_primer_resultado_y_permite_cambiar(qapp, dialogo, monkeypatch):
    consultas = []
    monkeypatch.setattr("app.ui.widgets.area_dialog.buscar_lugar",
                        lambda texto: consultas.append(texto) or [MIRAFLORES, SURCO])
    dialogo._edit_busqueda.setText("  Miraflores ")
    dialogo._btn_buscar.click()
    assert not dialogo._btn_buscar.isEnabled()                               # bloqueado mientras busca
    esperar(qapp, lambda: dialogo._btn_buscar.isEnabled())
    assert consultas == ["Miraflores"]
    assert dialogo._combo_resultados.count() == 2 and not dialogo._combo_resultados.isHidden()
    assert (dialogo._spin_lat.value(), dialogo._spin_lon.value()) == (-12.1211, -77.0297)
    assert dialogo._edit_nombre.text() == "Miraflores"
    assert dialogo._mapa._area[:2] == (-77.0297, -12.1211)

    dialogo._combo_resultados.setCurrentIndex(1)
    dialogo._combo_resultados.activated.emit(1)
    assert (dialogo._spin_lat.value(), dialogo._spin_lon.value()) == (-12.1453, -76.9918)
    assert dialogo._edit_nombre.text() == "Santiago de Surco"


def test_busqueda_sin_resultados_y_con_error_dejan_el_dialogo_usable(qapp, dialogo, monkeypatch):
    monkeypatch.setattr("app.ui.widgets.area_dialog.buscar_lugar", lambda texto: [])
    dialogo._edit_busqueda.setText("zzzzzz")
    dialogo._buscar()
    esperar(qapp, lambda: dialogo._btn_buscar.isEnabled())
    assert "Sin resultados" in dialogo._lbl_busqueda.text() and dialogo._combo_resultados.isHidden()

    def sin_internet(texto):
        raise GeocodificacionError("No se pudo consultar el buscador de lugares: sin internet")

    monkeypatch.setattr("app.ui.widgets.area_dialog.buscar_lugar", sin_internet)
    dialogo._buscar()
    esperar(qapp, lambda: dialogo._btn_buscar.isEnabled())
    assert "sin internet" in dialogo._lbl_busqueda.text()


def test_busqueda_muy_corta_no_consulta(qapp, dialogo, monkeypatch):
    llamadas = []
    monkeypatch.setattr("app.ui.widgets.area_dialog.buscar_lugar", lambda t: llamadas.append(t) or [])
    dialogo._edit_busqueda.setText("ab")
    dialogo._buscar()
    assert llamadas == [] and "al menos 3" in dialogo._lbl_busqueda.text() and dialogo._btn_buscar.isEnabled()


def test_ver_region_en_el_mapa_lleva_a_la_pestana_del_mapa(qapp):
    d = AreaEstudioDialog()
    d._combo_region.setCurrentIndex(
        next(i for i in range(d._combo_region.count()) if d._combo_region.itemData(i).nombre == "Juliaca"))
    d._ver_region_en_mapa()
    assert d._tabs.currentIndex() == 1 and d._edit_nombre.text() == "Juliaca"
    assert (d._spin_lat.value(), d._spin_lon.value()) == (-15.4994, -70.1336)
    d.show(); qapp.processEvents(); qapp.processEvents()
    assert d._mapa_ajustado and d._mapa.rect().contains(d._mapa.rect_area().toRect())
    d.done(0)


def test_aceptar_desde_el_mapa_usa_lo_que_se_ve(qapp, dialogo):
    dialogo._mapa.punto_elegido.emit(-77.03, -12.12)
    dialogo._edit_nombre.setText("Mi barrio")
    dialogo._spin_radio.setValue(4_000)
    dialogo._aceptar()
    area = dialogo.area
    assert (area.nombre, area.latitud, area.longitud, area.radio_metros) == ("Mi barrio", -12.12, -77.03, 4_000)


def test_el_radio_inicial_es_el_configurado_y_se_dibuja(qapp):
    d = AreaEstudioDialog(radio_defecto=RADIO_BUFFER_METROS)
    assert d._mapa._area[2] == RADIO_BUFFER_METROS
    d.done(0)


def test_cerrar_el_dialogo_detiene_las_descargas(qapp):
    d = AreaEstudioDialog()
    d.done(0)
    assert d._mapa._descargador._cerrado
