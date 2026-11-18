"""Pruebas de humo de la interfaz PyQt6.

No necesitan monitor ni credenciales de Earth Engine: Qt corre en modo
``offscreen`` y los servicios de EE se reemplazan por dobles de prueba. Se
omiten solas si PyQt6 no está instalado.
"""
from __future__ import annotations

import os
import time
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PyQt6.QtWidgets")

from PIL import Image  # noqa: E402
from PyQt6.QtWidgets import QApplication, QDialog, QMessageBox, QTableWidget, QWidget  # noqa: E402

from app.core.config import GestorConfiguracion  # noqa: E402
from app.models.area_estudio import AreaDeEstudio  # noqa: E402
from app.models.proyecto import EstadisticaCambio  # noqa: E402
from app.services.deteccion_cambios_service import ResultadoDeteccion  # noqa: E402
from app.services.exportacion_service import ExportacionService  # noqa: E402
from app.services.proyecto_service import ProyectoService  # noqa: E402
from app.ui import theme  # noqa: E402
from app.ui.main_window import MainWindow  # noqa: E402
from app.ui.widgets.area_dialog import AreaEstudioDialog  # noqa: E402
from app.ui.widgets.layer_panel import LayerPanel  # noqa: E402
from app.ui.widgets.map_canvas import MapCanvas  # noqa: E402
from app.ui.widgets.results_panel import ResultsPanel  # noqa: E402
from app.utils.stats import (  # noqa: E402
    construir_estadisticas_cambios,
    construir_histograma_categorias,
    construir_resumen_transicion,
)

pytestmark = pytest.mark.usefixtures("sin_red_de_mapas")

ESTADISTICAS = [
    EstadisticaCambio("Urbanización", "-15.84, -70.01", "12.4%", "ALTO", "#ff6b6b", "Vegetación → Suelo"),
    EstadisticaCambio("Agua", "-15.85, -70.02", "2.3%", "BAJO", "#4ea8de", "Agua → Suelo"),
]


# ------------------------------------------------------------------ utilidades
@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    theme.aplicar_tema(app, "dark")
    return app


def esperar(qapp, condicion, timeout: float = 5.0) -> None:
    """Procesa eventos de Qt hasta que ``condicion()`` sea verdadera."""
    limite = time.monotonic() + timeout
    while not condicion():
        assert time.monotonic() < limite, "Tiempo de espera agotado"
        qapp.processEvents()
        time.sleep(0.01)


def png(ruta, color, tam=(64, 48)):
    Image.new("RGBA", tam, color).save(ruta)
    return str(ruta)


class _Dato:
    def __init__(self, valor):
        self._valor = valor

    def getInfo(self):  # noqa: N802 (API de Earth Engine)
        return self._valor


class _ImagenEE:
    """Doble mínimo de ``ee.Image`` con lo que usa la UI."""

    def __init__(self, bandas: int = 3):
        self._bandas = bandas

    def bandNames(self):  # noqa: N802
        return SimpleNamespace(size=lambda: _Dato(self._bandas))

    def geometry(self):
        return SimpleNamespace(centroid=lambda *_a, **_k: SimpleNamespace(coordinates=lambda: _Dato([-70.01, -15.84])))


class _AreaSinEE(AreaDeEstudio):
    """Área real, pero con una geometría de mentira (en el entorno de pruebas no hay ``ee``)."""

    def geometria(self):
        return "roi-falso"


class _DialogoFalso:
    """Reemplaza a AreaEstudioDialog: «acepta» la selección configurada en ``seleccion``."""

    seleccion = {
        "area": _AreaSinEE(longitud=-77.0428, latitud=-12.0464, radio_metros=10_000, nombre="Lima – Centro"),
        "periodo_t1": ("2019-01-01", "2019-12-31"),
        "periodo_t2": ("2024-01-01", "2024-12-31"),
    }
    recibido: dict = {}

    def __init__(self, parent=None, **kwargs):
        type(self).recibido = kwargs
        self.area = self.seleccion["area"]
        self.periodo_t1 = self.seleccion["periodo_t1"]
        self.periodo_t2 = self.seleccion["periodo_t2"]

    def exec(self):
        return QDialog.DialogCode.Accepted


@pytest.fixture
def ventana(qapp, tmp_path, monkeypatch):
    mensajes: list[tuple[str, str]] = []
    for nombre in ("warning", "information", "critical"):
        monkeypatch.setattr(
            QMessageBox, nombre,
            staticmethod(lambda *a, _n=nombre, **k: mensajes.append((_n, a[1])) or QMessageBox.StandardButton.Ok),
        )
    monkeypatch.setattr("app.ui.main_window.AreaEstudioDialog", _DialogoFalso)

    gestor = GestorConfiguracion(ruta_usuario=tmp_path / "settings.json")
    w = MainWindow(gestor)
    w._ee_iniciado = True                                  # no intentar conectar con EE real
    w._proyectos = ProyectoService(gestor, tmp_path / "data")
    w._exportacion = ExportacionService(tmp_path / "exports")

    # Dobles de Earth Engine
    capturas: dict = {"mosaicos": [], "clasificar": {}}
    w._ee_service.requerir_conexion = lambda: None
    w._adquisicion.obtener_mosaico = lambda roi, ini, fin: capturas["mosaicos"].append((roi, ini, fin)) or _ImagenEE()
    w._adquisicion.obtener_thumbnail_url = lambda mosaico, roi: png(tmp_path / "t.png", (60, 90, 50, 255))
    w._clasificacion.clasificar_mosaicos_temporales = (
        lambda a, b, **k: capturas["clasificar"].update(k) or {"clasificacion_t1": 1, "clasificacion_t2": 2}
    )
    w._deteccion.detectar = lambda *a: ResultadoDeteccion(
        mapa_t1=None, mapa_t2=None, categoria=None,
        url_overlay=png(tmp_path / "c.png", (255, 107, 107, 255)), estadisticas=ESTADISTICAS,
    )
    w.mensajes = mensajes
    w.capturas = capturas
    w.tmp = tmp_path
    w.show()
    yield w
    w.close()


# ----------------------------------------------------------------------- flujo
def test_flujo_completo_cargar_detectar_exportar(qapp, ventana):
    w = ventana
    w.cargar_desde_ee()
    assert not w.btn_ee.isEnabled()                        # bloqueado mientras corre el hilo
    esperar(qapp, lambda: w.btn_ee.isEnabled())
    assert w.imagen_actual_ee is not None and w._pil_actual is not None
    assert w.label_anterior.text() == "EPOCH A: Sentinel-2 2019"
    assert w.capturas["mosaicos"][0] == ("roi-falso", "2019-01-01", "2019-12-31")

    w.detectar_cambios()
    assert w.btn_detectar.text() == "⏳ Procesando…" and not w.btn_detectar.isEnabled()
    esperar(qapp, lambda: w.resultado_deteccion is not None)
    assert w.btn_detectar.isEnabled() and w.btn_informe.isEnabled() and w.btn_modo_vista.isEnabled()
    assert w.map_canvas.imagen_cambios is not None
    assert w.results_panel._lay.count() == len(ESTADISTICAS) + 1
    assert w.capturas["clasificar"]["roi"] == "roi-falso", "el ROI debe llegar al clasificador (si no, usa puntos de Puno)"
    assert (w.tmp / "data" / "Lima_Centro.tiproj").exists(), "el proyecto se guarda con el nombre del área"

    w.exportar_reporte("csv")
    assert list((w.tmp / "exports").glob("*.csv"))
    assert ("information", "Exportación completada") in w.mensajes

    w.nuevo_proyecto()
    assert w.resultado_deteccion is None and w.imagen_actual is None and w.map_canvas.imagen_t2 is None


def test_sin_imagenes_en_ee_avisa_y_rehabilita_boton(qapp, ventana):
    w = ventana
    w._adquisicion.obtener_mosaico = lambda roi, ini, fin: _ImagenEE(bandas=0)
    w.cargar_desde_ee()
    esperar(qapp, lambda: w.btn_ee.isEnabled())
    assert ("warning", "Sin imágenes") in w.mensajes and w.imagen_actual_ee is None


def test_error_en_hilo_se_muestra_y_no_bloquea_la_ui(qapp, ventana):
    w = ventana

    def falla(*_a):
        raise RuntimeError("sin red")

    w._adquisicion.obtener_mosaico = falla
    w.cargar_desde_ee()
    esperar(qapp, lambda: w.btn_ee.isEnabled())
    assert any(t == "critical" and "Error" in titulo for t, titulo in w.mensajes)

    # Error durante la detección: el botón vuelve a quedar usable
    w.imagen_anterior = w.imagen_actual = "x"
    w.imagen_anterior_ee = w.imagen_actual_ee = _ImagenEE()
    w._pil_anterior = w._pil_actual = Image.new("RGBA", (8, 8))
    w._clasificacion.clasificar_mosaicos_temporales = falla
    w.detectar_cambios()
    esperar(qapp, lambda: w.btn_detectar.isEnabled())
    assert w.btn_detectar.text() == "DETECTAR CAMBIOS" and w.resultado_deteccion is None


def test_detectar_exige_imagenes_de_earth_engine(qapp, ventana):
    w = ventana
    w.detectar_cambios()
    assert w.mensajes[-1] == ("warning", "Advertencia")
    w.imagen_anterior = w.imagen_actual = "local.png"
    w.detectar_cambios()
    assert w.mensajes[-1] == ("warning", "Detección no disponible")


# ----------------------------------------------------------------------- tema
def test_cambio_de_tema_en_vivo(qapp, ventana):
    w = ventana
    w.alternar_tema()
    assert w._gestor_config.config.tema == "light"
    assert w._paleta == theme.PALETA_CLARA and w.map_canvas._paleta == theme.PALETA_CLARA
    assert theme.PALETA_CLARA.fondo_principal in qapp.styleSheet()
    w.alternar_tema()
    assert w._paleta == theme.PALETA_OSCURA


def test_qss_se_genera_para_ambas_paletas():
    for paleta in (theme.PALETA_OSCURA, theme.PALETA_CLARA):
        qss = theme.construir_qss(paleta)
        assert "$" not in qss and paleta.acento in qss


# -------------------------------------------------------------------- widgets
def test_panel_de_capas_emite_senal_y_expone_estado(qapp):
    panel = LayerPanel()
    avisos = []
    panel.cambiado.connect(lambda: avisos.append(1))
    panel.chk_t1.setChecked(False)
    panel.slider_opacidad.setValue(40)
    assert len(avisos) == 2
    assert panel.mostrar_t1 is False and panel.mostrar_t2 is True and panel.opacidad_cambios == 0.4


def test_panel_de_resultados_reemplaza_contenido(qapp):
    panel = ResultsPanel()
    panel.mostrar_estadisticas(ESTADISTICAS)
    assert panel._lay.count() == len(ESTADISTICAS) + 1     # tarjetas + stretch
    panel.mostrar_mensaje_espera()
    assert panel._lay.count() == 2


def test_panel_muestra_matriz_y_balance_con_cambios_menores_al_umbral(qapp):
    transiciones = {11: (999, 9.99), 13: (1, 0.01)}
    resumen = construir_resumen_transicion(transiciones)
    estadisticas = construir_estadisticas_cambios(
        construir_histograma_categorias(transiciones),
        resumen.total_pixeles,
        (0.0, 0.0),
    )
    panel = ResultsPanel()
    panel.mostrar_estadisticas(estadisticas, resumen)

    matriz = panel.findChild(QTableWidget, "matrizTransicion")
    balance = panel.findChild(QTableWidget, "balanceTransicion")
    assert matriz is not None and balance is not None
    assert matriz.item(0, 2).text() == "0.01 ha (0.1%)\n1 px"
    assert "0.10%" in matriz.item(0, 2).toolTip()
    assert balance.item(0, 1).text() == "10.00"

    sin_datos = construir_resumen_transicion({})
    panel.mostrar_estadisticas([], sin_datos)
    matriz_sin_datos = panel.findChild(QTableWidget, "matrizTransicion")
    balance_sin_datos = panel.findChild(QTableWidget, "balanceTransicion")
    assert matriz_sin_datos.item(0, 0).text() == "—"
    assert balance_sin_datos.item(0, 1).text() == "—"


def test_mapa_se_recompone_al_redimensionar_y_guarda_captura(qapp, tmp_path):
    canvas = MapCanvas(theme.PALETA_OSCURA)
    canvas.resize(500, 300)
    canvas.show()
    canvas.imagen_t1 = Image.new("RGBA", (100, 100), (0, 128, 0, 255))
    canvas.imagen_t2 = Image.new("RGBA", (100, 100), (128, 0, 0, 255))
    canvas.imagen_cambios = Image.new("RGBA", (100, 100), (255, 255, 0, 120))

    canvas.mostrar_resultado_swipe(0.5, True, 1.0)
    assert (canvas._fondo.width(), canvas._fondo.height()) == (500, 300)
    canvas.resize(640, 360)
    qapp.processEvents()
    assert (canvas._fondo.width(), canvas._fondo.height()) == (640, 360)

    salida = tmp_path / "captura.png"
    canvas.guardar_captura(salida)
    assert salida.exists() and Image.open(salida).size == (640, 360)


def test_mapa_overlay_respeta_capas_visibles(qapp):
    canvas = MapCanvas(theme.PALETA_OSCURA)
    canvas.resize(200, 200)
    canvas.show()
    canvas.mostrar_resultado_overlay(True, True, True, 1.0)   # sin imágenes: no hace nada
    assert canvas._fondo is None
    canvas.imagen_t1 = Image.new("RGBA", (50, 50), (0, 255, 0, 255))
    canvas.imagen_t2 = Image.new("RGBA", (50, 50), (255, 0, 0, 255))
    canvas.mostrar_resultado_overlay(mostrar_t1=True, mostrar_t2=False, mostrar_cambios=False, opacidad_cambios=1.0)
    centro = canvas._fondo.pixelColor(100, 100)
    assert (centro.red(), centro.green()) == (0, 255)         # solo se ve la Época A


# ------------------------------------------------------------ regresión: autoguardado
def test_centroide_se_pide_con_margen_de_error(qapp, ventana):
    """Earth Engine rechaza ``centroid()`` sin margen de error (fallo real en Puno)."""
    w = ventana
    llamadas = []

    def centroid(*args, **kwargs):
        llamadas.append((args, kwargs))
        if not args and not kwargs:
            raise RuntimeError("Please specify a non-zero error margin")
        return SimpleNamespace(coordinates=lambda: _Dato([-70.01, -15.84]))

    w.imagen_actual_ee = SimpleNamespace(geometry=lambda: SimpleNamespace(centroid=centroid))
    w.guardar_proyecto()
    assert llamadas and (llamadas[0][0] or llamadas[0][1]), "centroid() debe recibir un margen de error"
    assert list((w.tmp / "data").glob("*.tiproj"))


def test_fallo_al_guardar_no_tumba_la_app(qapp, ventana):
    w = ventana

    def centroid(*_a, **_k):
        raise RuntimeError("fallo de EE")

    w.imagen_actual_ee = SimpleNamespace(geometry=lambda: SimpleNamespace(centroid=centroid))
    w.guardar_proyecto()                                    # no debe lanzar
    assert ("critical", "Error al guardar") in w.mensajes


def test_manejador_global_registra_y_avisa(qapp, monkeypatch):
    import sys

    from app import main as app_main

    avisos = []
    monkeypatch.setattr(QMessageBox, "critical", staticmethod(lambda *a, **k: avisos.append(a[1])))
    anterior = sys.excepthook
    try:
        app_main._instalar_manejador_de_errores()
        sys.excepthook(RuntimeError, RuntimeError("boom"), None)
    finally:
        sys.excepthook = anterior
    assert avisos == ["Error inesperado"]


# --------------------------------------------- área de estudio y periodos en el flujo
def test_el_dialogo_recibe_la_seleccion_anterior(qapp, ventana):
    w = ventana
    w.cargar_desde_ee()
    esperar(qapp, lambda: w.btn_ee.isEnabled())
    w.cargar_desde_ee()                                    # segunda vez: debe recordar la primera
    esperar(qapp, lambda: w.btn_ee.isEnabled())
    previo = _DialogoFalso.recibido
    assert previo["area"].nombre == "Lima – Centro" and previo["periodo_t2"] == ("2024-01-01", "2024-12-31")


def test_periodos_elegidos_se_usan_y_se_muestran(qapp, ventana, monkeypatch):
    w = ventana
    monkeypatch.setattr(_DialogoFalso, "seleccion", {
        **_DialogoFalso.seleccion, "periodo_t1": ("2021-03-01", "2021-08-31"),
    })
    w.cargar_desde_ee()
    esperar(qapp, lambda: w.btn_ee.isEnabled())
    assert w.capturas["mosaicos"][0][1:] == ("2021-03-01", "2021-08-31")
    assert w.label_anterior.text() == "EPOCH A: Sentinel-2 2021-03-01 → 2021-08-31"
    assert w.map_canvas.etiqueta_t1 == "2021-03-01 → 2021-08-31" and w.map_canvas.etiqueta_t2 == "2024"


def test_area_grande_baja_la_resolucion_de_analisis(qapp, ventana, monkeypatch):
    w = ventana
    monkeypatch.setattr(_DialogoFalso, "seleccion", {
        **_DialogoFalso.seleccion,
        "area": _AreaSinEE(longitud=-77.04, latitud=-12.05, radio_metros=50_000, nombre="Grande"),
    })
    w.cargar_desde_ee()
    esperar(qapp, lambda: w.btn_ee.isEnabled())
    assert w._escala_analisis == 50
    assert w._clasificacion.escala_metros == w._deteccion.escala_metros == 50
    assert w.status_bar.escala.text() == "50 m/px"


def test_epoca_sin_imagenes_se_nombra_en_el_aviso(qapp, ventana):
    w = ventana
    vacias = iter([_ImagenEE(3), _ImagenEE(0)])           # T1 con datos, T2 vacía
    w._adquisicion.obtener_mosaico = lambda roi, ini, fin: next(vacias)
    w.cargar_desde_ee()
    esperar(qapp, lambda: w.btn_ee.isEnabled())
    assert ("warning", "Sin imágenes") in w.mensajes and w.imagen_actual_ee is None


def test_cargar_otra_zona_descarta_el_resultado_anterior(qapp, ventana):
    w = ventana
    w.cargar_desde_ee()
    esperar(qapp, lambda: w.btn_ee.isEnabled())
    w.detectar_cambios()
    esperar(qapp, lambda: w.resultado_deteccion is not None)
    assert w.btn_informe.isEnabled()

    w.cargar_desde_ee()
    esperar(qapp, lambda: w.btn_ee.isEnabled())
    assert w.resultado_deteccion is None and w.map_canvas.imagen_cambios is None
    assert not w.btn_informe.isEnabled() and not w.btn_modo_vista.isEnabled()


def test_error_de_muestras_se_explica_en_castellano(qapp, ventana):
    w = ventana
    w.cargar_desde_ee()
    esperar(qapp, lambda: w.btn_ee.isEnabled())

    def falla(*_a):
        raise RuntimeError("No valid training data were found.")

    w._deteccion.detectar = falla
    w.detectar_cambios()
    esperar(qapp, lambda: w.btn_detectar.isEnabled())
    assert ("critical", "Error en la detección") in w.mensajes


def test_abrir_proyecto_deja_el_area_preseleccionada(qapp, ventana, monkeypatch):
    from app.models.proyecto import Proyecto

    w = ventana
    ruta = w._proyectos.guardar(Proyecto(nombre="Lima – Centro", longitud=-77.04, latitud=-12.05,
                                         periodo_t1="2021", periodo_t2="2023"))
    monkeypatch.setattr("app.ui.main_window.QFileDialog.getOpenFileName", staticmethod(lambda *a, **k: (str(ruta), "")))
    w.abrir_proyecto()
    assert w._area_estudio.nombre == "Lima – Centro" and w._area_estudio.centro() == (-77.04, -12.05)
    assert w._periodo_t1 == ("2021-01-01", "2021-12-31") and w._periodo_t2 == ("2023-01-01", "2023-12-31")


# ------------------------------------------------------------ AreaEstudioDialog real
def test_dialogo_rechaza_fechas_invalidas_y_sigue_abierto(qapp, monkeypatch):
    avisos = []
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: avisos.append(a[2])))
    d = AreaEstudioDialog()
    d._edit_t2_ini.setText("2019-05-01")                   # empieza antes de que termine la Época A
    d._aceptar()
    assert d.area is None and avisos and "terminar antes" in avisos[0]
    assert d.result() != QDialog.DialogCode.Accepted


def test_dialogo_region_y_coordenadas_manuales(qapp):
    d = AreaEstudioDialog()
    d._combo_region.setCurrentIndex(
        next(i for i in range(d._combo_region.count()) if d._combo_region.itemData(i).nombre == "Juliaca"))
    d._aceptar()
    assert (d.area.nombre, d.area.latitud) == ("Juliaca", -15.4994)
    assert d.periodo_t1 == ("2019-01-01", "2019-12-31")

    d = AreaEstudioDialog()
    d._tabs.setCurrentIndex(1)
    d._spin_lat.setValue(-12.05)
    d._spin_lon.setValue(-77.04)
    d._edit_nombre.setText("Mi zona")
    d._spin_radio.setValue(7_000)
    d._aceptar()
    assert (d.area.nombre, d.area.radio_metros) == ("Mi zona", 7_000)


def test_dialogo_recuerda_la_seleccion_anterior(qapp):
    previa = AreaDeEstudio(longitud=-77.04, latitud=-12.05, radio_metros=7_000, nombre="Mi zona")
    d = AreaEstudioDialog(area=previa, periodo_t1=("2021-03-01", "2021-08-31"), periodo_t2=("2023-01-01", "2023-12-31"))
    assert d._tabs.currentIndex() == 1 and d._edit_nombre.text() == "Mi zona" and d._spin_radio.value() == 7_000
    assert d._edit_t1_ini.text() == "2021-03-01"
    d._aceptar()
    assert d.periodo_t1 == ("2021-03-01", "2021-08-31") and d.area.latitud == -12.05

    region = AreaDeEstudio(longitud=-70.1336, latitud=-15.4994, radio_metros=10_000, nombre="Juliaca")
    assert AreaEstudioDialog(area=region)._combo_region.currentData().nombre == "Juliaca"


def test_dialogo_avisa_cuando_el_area_obliga_a_bajar_la_resolucion(qapp):
    d = AreaEstudioDialog()
    d._spin_radio.setValue(10_000)
    assert "10 m/píxel" in d._lbl_resolucion.text() and "reduce" not in d._lbl_resolucion.text()
    d._spin_radio.setValue(50_000)
    assert "50 m/píxel" in d._lbl_resolucion.text() and "reduce la resolución" in d._lbl_resolucion.text()


# ----------------------------------------------------------------- tema y tarjetas
def test_tarjetas_usan_rgba_y_siguen_al_tema(qapp):
    """Qt lee #RRGGBBAA como #AARRGGBB: un sufijo de alfa cambia el color en vez de aclararlo."""
    panel = ResultsPanel()
    panel.mostrar_estadisticas(ESTADISTICAS)
    estilos = "".join(w.styleSheet() for w in panel.widget().findChildren(QWidget))
    assert "rgba(" in estilos
    assert not any(f"{c.color}{sufijo}" in estilos for c in ESTADISTICAS for sufijo in ("22", "55", "cc"))
    for paleta in (theme.PALETA_OSCURA, theme.PALETA_CLARA):
        qss = theme.construir_qss(paleta)
        assert "font-family" not in qss, "una regla global de fuente pisa las fuentes monoespaciadas"
        assert f"QFrame#tarjetaCambio {{\n    background: {paleta.fondo_panel};" in qss


def test_rgba_convierte_hex_a_color_css():
    assert theme.rgba("#ff6b6b", 0.15) == "rgba(255, 107, 107, 0.15)"


# ------------------------------------------------------------- vista de mapa
def _con_resultado(qapp, w):
    w.cargar_desde_ee()
    esperar(qapp, lambda: w.btn_ee.isEnabled())
    w.detectar_cambios()
    esperar(qapp, lambda: w.resultado_deteccion is not None)


def test_las_tres_vistas_rotan_y_vuelven_al_inicio(qapp, ventana):
    w = ventana
    _con_resultado(qapp, w)
    esperado = [("swipe", 0, "Swipe"), ("mapa", 1, "Mapa"), ("overlay", 0, "Overlay")]
    for modo, pagina, texto in esperado:
        w.alternar_modo_vista()
        assert w.modo_vista == modo and w._pila_mapas.currentIndex() == pagina
        assert w.btn_modo_vista.text().endswith(texto)


def test_la_vista_de_mapa_georreferencia_las_capas_y_respeta_el_panel(qapp, ventana):
    from app.utils.geo import limites_cuadrado

    w = ventana
    _con_resultado(qapp, w)
    w._fijar_modo_vista("mapa")
    area = w._area_estudio
    limites = limites_cuadrado(area.longitud, area.latitud, area.radio_metros)
    capas = w.mapa_navegable._capas
    assert len(capas) == 2 and all(c.limites == limites for c in capas)       # Época B + cambios
    assert w.mapa_navegable._area == (area.longitud, area.latitud, area.radio_metros)
    assert w.mapa_navegable.rect().contains(w.mapa_navegable.rect_area().toRect())   # ya encuadrado

    w.layer_panel.chk_t2.setChecked(False)                                    # la señal del panel refresca el mapa
    w.layer_panel.chk_t1.setChecked(False)
    assert len(w.mapa_navegable._capas) == 1                                  # solo los cambios sobre el mapa base
    w.layer_panel.slider_opacidad.setValue(40)
    assert w.mapa_navegable._capas[0].opacidad == pytest.approx(0.4)
    w.layer_panel.chk_cambios.setChecked(False)
    assert w.mapa_navegable._capas == []


def test_la_vista_de_mapa_no_vuelve_a_encuadrar_si_el_usuario_navego(qapp, ventana):
    w = ventana
    _con_resultado(qapp, w)
    w._fijar_modo_vista("mapa")
    w.mapa_navegable.centrar(-70.0, -15.0, 6)                                 # el usuario se fue a otro sitio
    w.layer_panel.slider_opacidad.setValue(70)                                # un cambio de capa no debe moverlo
    assert (w.mapa_navegable.lon, w.mapa_navegable.zoom) == (-70.0, 6)


def test_vista_de_mapa_sin_area_vuelve_al_overlay(qapp, ventana):
    w = ventana
    _con_resultado(qapp, w)
    w._area_estudio = None
    w._fijar_modo_vista("mapa")
    assert w.modo_vista == "overlay" and w._pila_mapas.currentIndex() == 0
    assert "área" in w.status_bar.mensaje.text()


def test_cargar_otra_zona_regresa_al_visor_y_vacia_el_mapa(qapp, ventana):
    w = ventana
    _con_resultado(qapp, w)
    w._fijar_modo_vista("mapa")
    w.cargar_desde_ee()
    esperar(qapp, lambda: w.btn_ee.isEnabled())
    assert w._pila_mapas.currentIndex() == 0 and w.mapa_navegable._capas == []
    assert w.resultado_deteccion is None


def test_el_dialogo_recibe_el_servicio_de_teselas_con_cache_en_disco(qapp, ventana):
    w = ventana
    w.cargar_desde_ee()
    esperar(qapp, lambda: w.btn_ee.isEnabled())
    servicio = _DialogoFalso.recibido["servicio_teselas"]
    assert servicio is w._servicio_teselas
    assert servicio.directorio_cache.parts[-2:] == ("cache", "teselas")


def test_el_mapa_sigue_al_tema_y_actualiza_la_barra_de_estado(qapp, ventana):
    w = ventana
    w.alternar_tema()
    assert w.mapa_navegable._paleta == theme.PALETA_CLARA
    w.mapa_navegable.centrar(-71.5, -16.4, 12)
    assert w.status_bar.zoom.text() == "Zoom: 12" and "-16.4000" in w.status_bar.coordenadas.text()
    w.alternar_tema()
