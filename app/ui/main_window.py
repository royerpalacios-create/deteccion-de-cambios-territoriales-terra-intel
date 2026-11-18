"""Ventana principal de TERRA_INTEL (PyQt6).

Mantiene el flujo de trabajo original (cargar imágenes -> detectar cambios ->
ver resultado -> exportar) y la misma separación en servicios y widgets.

Cambios propios de la migración a Qt:

- Las operaciones lentas (inicializar Earth Engine, cargar mosaicos y
  descargar thumbnails, detectar cambios) corren en un hilo de fondo
  (:class:`~app.ui.trabajo.Trabajo`); la ventana ya no se congela.
- El tema claro/oscuro se aplica en vivo (no hace falta reiniciar).
- Las imágenes descargadas se guardan en memoria y no se vuelven a bajar
  cada vez que se refresca la vista previa.
"""
from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable

from PIL import Image
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import (
    QApplication, QDialog, QFileDialog, QFrame, QHBoxLayout, QMainWindow,
    QMessageBox, QSlider, QStackedWidget, QVBoxLayout, QWidget,
)

from app.core.config import GestorConfiguracion
from app.core.exceptions import TerraIntelError
from app.core.logging_config import obtener_logger
from app.models.area_estudio import AreaDeEstudio, ESCALA_MINIMA_METROS, calcular_escala_metros, crear_area_estudio
from app.models.proyecto import Proyecto
from app.services.adquisicion_service import AdquisicionService, etiqueta_periodo, periodo_desde_etiqueta
from app.services.clasificacion_service import ClasificacionService
from app.services.deteccion_cambios_service import DeteccionCambiosService
from app.services.earth_engine_service import EarthEngineService
from app.services.exportacion_service import ContextoReporte, ExportacionService
from app.services.proyecto_service import ProyectoService
from app.services.teselas_service import ServicioTeselas
from app.ui import theme
from app.ui.theme import boton, etiqueta, linea_horizontal
from app.ui.trabajo import Trabajo
from app.ui.widgets.about_dialog import AboutDialog
from app.ui.widgets.area_dialog import AreaEstudioDialog
from app.ui.widgets.layer_panel import LayerPanel
from app.ui.widgets.map_canvas import MapCanvas, pil_a_qimage_rgba
from app.ui.widgets.map_view import CapaImagen, MapaNavegable
from app.ui.widgets.results_panel import ResultsPanel
from app.ui.widgets.ribbon import ComandosRibbon, QuickAccessBar, construir_menu
from app.ui.widgets.settings_dialog import SettingsDialog
from app.ui.widgets.status_bar import StatusBar
from app.utils.geo import limites_cuadrado
from app.utils.image_utils import abrir_imagen
from app.utils.tiempo import cronometro

logger = obtener_logger("main_window")

RAIZ_PROYECTO = Path(__file__).resolve().parent.parent.parent
FILTRO_IMAGENES = "Imágenes (*.png *.jpg *.jpeg *.tif *.tiff)"


def _con_margen(widget: QWidget, izq: int, arriba: int, der: int, abajo: int) -> QWidget:
    """Envuelve ``widget`` en un contenedor con márgenes."""
    contenedor = QWidget()
    lay = QVBoxLayout(contenedor)
    lay.setContentsMargins(izq, arriba, der, abajo)
    lay.addWidget(widget)
    return contenedor


def _fila(izq: int, arriba: int, der: int, abajo: int, espaciado: int = 0) -> tuple[QWidget, QHBoxLayout]:
    contenedor = QWidget()
    lay = QHBoxLayout(contenedor)
    lay.setContentsMargins(izq, arriba, der, abajo)
    lay.setSpacing(espaciado)
    return contenedor, lay


class MainWindow(QMainWindow):
    def __init__(self, gestor_config: GestorConfiguracion) -> None:
        super().__init__()
        self._gestor_config = gestor_config
        config = gestor_config.config
        self._paleta = theme.obtener_paleta(config.tema)

        self.setWindowTitle("TERRA_INTEL | Change Analysis")
        pantalla = QGuiApplication.primaryScreen().availableGeometry()
        self.setMinimumSize(min(1300, pantalla.width()), min(780, pantalla.height()))
        self.resize(min(1600, pantalla.width()), min(900, pantalla.height()))

        # ------------------------------------------------------------ servicios
        self._ee_service = EarthEngineService(config.proyecto_earth_engine)
        self._adquisicion = AdquisicionService(umbral_nubes=config.umbral_nubes)
        self._clasificacion = ClasificacionService()
        self._deteccion = DeteccionCambiosService()
        self._exportacion = ExportacionService(RAIZ_PROYECTO / "exports")
        self._proyectos = ProyectoService(gestor_config, RAIZ_PROYECTO / "data")
        self._servicio_teselas = ServicioTeselas(RAIZ_PROYECTO / "cache" / "teselas")

        # ------------------------------------------------------------- estado
        self.imagen_anterior: str | None = None       # ruta local o URL del thumbnail
        self.imagen_actual: str | None = None
        self.imagen_anterior_ee = None                # ee.Image (solo si viene de EE)
        self.imagen_actual_ee = None
        self._pil_anterior: Image.Image | None = None  # caché de las imágenes ya abiertas
        self._pil_actual: Image.Image | None = None
        self.modo_vista = "overlay"                   # "overlay" | "swipe"
        self.posicion_slider = 0.5
        self.resultado_deteccion = None
        self.proyecto_actual: Proyecto | None = None
        self._ee_iniciado = False
        # Área de estudio y periodos activos (los elige el usuario en AreaEstudioDialog)
        self._area_estudio: AreaDeEstudio | None = None
        self._periodo_t1: tuple[str, str] = ("2019-01-01", "2019-12-31")
        self._periodo_t2: tuple[str, str] = ("2024-01-01", "2024-12-31")
        self._escala_analisis = ESCALA_MINIMA_METROS  # m/píxel; baja la resolución si el área es grande
        self._area_en_mapa: tuple[float, float, float] | None = None   # área con la que se encuadró el mapa
        self._qimages: dict[int, object] = {}         # caché PIL -> QImage para la vista de mapa

        self._construir_ui()

    # ------------------------------------------------------------------ UI
    def _construir_ui(self) -> None:
        comandos = ComandosRibbon(
            nuevo_proyecto=self.nuevo_proyecto,
            abrir_proyecto=self.abrir_proyecto,
            guardar_proyecto=self.guardar_proyecto,
            exportar_csv=lambda: self.exportar_reporte("csv"),
            exportar_json=lambda: self.exportar_reporte("json"),
            exportar_excel=lambda: self.exportar_reporte("excel"),
            exportar_word=lambda: self.exportar_reporte("word"),
            exportar_pdf=lambda: self.exportar_reporte("pdf"),
            salir=self.close,
            alternar_tema=self.alternar_tema,
            abrir_configuracion=self.abrir_configuracion,
            detectar_cambios=self.detectar_cambios,
            cargar_desde_ee=self.cargar_desde_ee,
            rescan=self.rescan_area,
            alternar_vista=self.alternar_modo_vista,
            capturar_mapa=self.capturar_mapa,
            mostrar_acerca_de=self.mostrar_acerca_de,
        )
        construir_menu(self, comandos)

        central = QWidget()
        self.setCentralWidget(central)
        raiz = QVBoxLayout(central)
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.setSpacing(0)

        self.quick_access = QuickAccessBar(comandos)
        raiz.addWidget(self.quick_access)

        cuerpo = QHBoxLayout()
        cuerpo.setContentsMargins(0, 0, 0, 0)
        cuerpo.setSpacing(0)
        cuerpo.addWidget(self._construir_sidebar())
        cuerpo.addWidget(self._construir_area_principal(), 1)
        raiz.addLayout(cuerpo, 1)

        self.status_bar = StatusBar()
        self.setStatusBar(self.status_bar)

        self.map_canvas.mostrar_bienvenida()

    def _construir_sidebar(self) -> QFrame:
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(340)
        lay = QVBoxLayout(sidebar)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        encabezado = QWidget()
        h = QVBoxLayout(encabezado)
        h.setContentsMargins(20, 20, 20, 10)
        h.setSpacing(3)
        lbl_sup = etiqueta("ANÁLISIS TERRITORIAL", 10, True, mono=True, tono="acento")
        lbl_sup.setStyleSheet("letter-spacing: 2px;")
        h.addWidget(lbl_sup)
        h.addWidget(etiqueta("Leyenda de Cambios", 22, True))
        h.addWidget(etiqueta("% de área afectada por categoría", 11, mono=True, tono="secundario"))
        lay.addWidget(encabezado)

        lay.addWidget(_con_margen(linea_horizontal(), 16, 6, 16, 6))

        self.layer_panel = LayerPanel()
        self.layer_panel.cambiado.connect(self._refrescar_vista_resultado)
        lay.addWidget(self.layer_panel)

        lay.addWidget(_con_margen(linea_horizontal(), 16, 6, 16, 6))

        self.results_panel = ResultsPanel()
        lay.addWidget(self.results_panel, 1)

        self.btn_rescan = boton("⟳  RE-SCAN TARGET AREA", self.rescan_area, "acento",
                                alto=44, px=12, negrita=True, mono=True)
        self.btn_rescan.setStyleSheet(
            "border-radius: 10px; letter-spacing: 1px;"
        )
        lay.addWidget(_con_margen(self.btn_rescan, 16, 12, 16, 16))
        return sidebar

    def _construir_area_principal(self) -> QFrame:
        area = QFrame()
        area.setObjectName("areaPrincipal")
        lay = QVBoxLayout(area)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self.map_canvas = MapCanvas(self._paleta)
        self.mapa_navegable = MapaNavegable(self._servicio_teselas, self._paleta)
        self.mapa_navegable.vista_cambiada.connect(self._al_mover_mapa)
        self._pila_mapas = QStackedWidget()          # 0: visor de imágenes (overlay/swipe) · 1: mapa navegable
        self._pila_mapas.addWidget(self.map_canvas)
        self._pila_mapas.addWidget(self.mapa_navegable)
        lay.addWidget(_con_margen(self._pila_mapas, 6, 6, 6, 6), 1)

        # -- etiquetas de época
        fila, f = _fila(20, 5, 20, 5)
        self.label_anterior = etiqueta("EPOCH A: Sin imagen", 13, True, tono="secundario")
        self.label_actual = etiqueta("EPOCH B: Sin imagen", 13, True, tono="advertencia")
        f.addWidget(self.label_anterior)
        f.addStretch(1)
        f.addWidget(self.label_actual)
        lay.addWidget(fila)

        # -- botones de carga y detección
        fila, f = _fila(20, 5, 20, 5, espaciado=8)
        self.btn_cargar_anterior = boton("Época Anterior", self.cargar_imagen_anterior, "panel", alto=42, px=12)
        self.btn_cargar_actual = boton("Época Actual", self.cargar_imagen_actual, "panel", alto=42, px=12)
        self.btn_ee = boton("Earth Engine", self.cargar_desde_ee, "verde", alto=42, px=12)
        self.btn_detectar = boton("DETECTAR CAMBIOS", self.detectar_cambios, "peligro",
                                  alto=42, px=14, negrita=True)
        for b in (self.btn_cargar_anterior, self.btn_cargar_actual, self.btn_ee, self.btn_detectar):
            f.addWidget(b, 1)
        lay.addWidget(fila)

        # -- vista e informe
        fila, f = _fila(20, 0, 20, 4, espaciado=8)
        self.btn_modo_vista = boton("Vista: Overlay", self.alternar_modo_vista, "panel", alto=34, px=12)
        self.btn_informe = boton("Generar Informe PDF", lambda: self.exportar_reporte("pdf"), "verde", alto=34, px=12)
        self.btn_modo_vista.setEnabled(False)
        self.btn_informe.setEnabled(False)
        f.addWidget(self.btn_modo_vista, 1)
        f.addWidget(self.btn_informe, 1)
        lay.addWidget(fila)

        # -- slider de comparación (swipe)
        fila, f = _fila(50, 5, 50, 6, espaciado=10)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, 100)
        self.slider.setValue(50)
        self.slider.valueChanged.connect(self._actualizar_slider)
        f.addWidget(etiqueta("ANTES", tono="secundario"))
        f.addWidget(self.slider, 1)
        f.addWidget(etiqueta("DESPUÉS", tono="advertencia"))
        lay.addWidget(fila)
        return area

    # -------------------------------------------------------- hilos de fondo
    def _en_segundo_plano(self, funcion: Callable[[], Any], al_terminar: Callable[[Any], None],
                          al_fallar: Callable[[Any], None]) -> None:
        trabajo = Trabajo(funcion, parent=self)
        trabajo.terminado.connect(al_terminar)
        trabajo.fallo.connect(al_fallar)
        trabajo.terminado.connect(trabajo.deleteLater)
        trabajo.fallo.connect(trabajo.deleteLater)
        trabajo.iniciar()

    # ---------------------------------------------------------- Earth Engine
    def showEvent(self, evento) -> None:  # noqa: N802
        super().showEvent(evento)
        if not self._ee_iniciado:          # la ventana ya es visible: arrancamos EE sin bloquearla
            self._ee_iniciado = True
            QTimer.singleShot(200, self._inicializar_earth_engine)

    def _inicializar_earth_engine(self) -> None:
        self._en_segundo_plano(self._ee_service.inicializar, self._al_inicializar_ee, self._al_fallar_ee)

    def _al_inicializar_ee(self, conectado: bool) -> None:
        self.status_bar.set_conexion(bool(conectado))
        if not conectado:
            QMessageBox.warning(
                self, "Autenticación requerida",
                "Earth Engine no está autenticado.\n"
                "Ejecuta: python -c \"import ee; ee.Authenticate()\"\n\n"
                f"Detalle: {self._ee_service.ultimo_error}",
            )

    def _al_fallar_ee(self, error: Exception) -> None:
        self.status_bar.set_conexion(False)
        QMessageBox.warning(self, "Autenticación requerida", f"No se pudo conectar con Earth Engine:\n{error}")

    # --------------------------------------------------------------- carga
    def cargar_imagen_anterior(self) -> None:
        archivo, _ = QFileDialog.getOpenFileName(self, "Seleccionar Imagen Anterior", "", FILTRO_IMAGENES)
        if archivo:
            self.imagen_anterior = archivo
            self.imagen_anterior_ee = None
            self._pil_anterior = None
            self._limpiar_resultado()
            self._mostrar_vista_previa()
            self.label_anterior.setText(f"EPOCH A: {os.path.basename(archivo)}")
            self.status_bar.set_mensaje(f"Imagen anterior cargada: {os.path.basename(archivo)}")

    def cargar_imagen_actual(self) -> None:
        archivo, _ = QFileDialog.getOpenFileName(self, "Seleccionar Imagen Actual", "", FILTRO_IMAGENES)
        if archivo:
            self.imagen_actual = archivo
            self.imagen_actual_ee = None
            self._pil_actual = None
            self._limpiar_resultado()
            self._mostrar_vista_previa()
            self.label_actual.setText(f"EPOCH B: {os.path.basename(archivo)}")
            self.status_bar.set_mensaje(f"Imagen actual cargada: {os.path.basename(archivo)}")

    def cargar_desde_ee(self) -> None:
        try:
            self._ee_service.requerir_conexion()
        except TerraIntelError as error:
            QMessageBox.critical(self, "Earth Engine no conectado", str(error))
            return

        dialogo = AreaEstudioDialog(
            self, area=self._area_estudio, periodo_t1=self._periodo_t1, periodo_t2=self._periodo_t2,
            radio_defecto=self._gestor_config.config.radio_area_estudio_m,
            servicio_teselas=self._servicio_teselas,
        )
        if dialogo.exec() != QDialog.DialogCode.Accepted or dialogo.area is None:
            return
        area, periodo_t1, periodo_t2 = dialogo.area, dialogo.periodo_t1, dialogo.periodo_t2
        self._gestor_config.actualizar(radio_area_estudio_m=int(area.radio_metros))   # se recuerda el radio

        self.status_bar.set_mensaje(f"Cargando «{area.nombre}» desde Earth Engine…", "advertencia")
        self.status_bar.set_coordenadas(area.longitud, area.latitud)
        self.btn_ee.setEnabled(False)
        self._en_segundo_plano(
            lambda: self._tarea_cargar_ee(area, periodo_t1, periodo_t2),
            self._al_cargar_ee, self._al_fallar_carga_ee,
        )

    def _tarea_cargar_ee(self, area: AreaDeEstudio, periodo_t1: tuple[str, str],
                         periodo_t2: tuple[str, str]) -> dict:
        """Corre en el hilo de fondo: consulta EE y descarga las miniaturas.

        Las llamadas a la API de Earth Engine van en serie; solo la descarga de las dos
        miniaturas (HTTP puro con ``requests``) se hace en paralelo.
        """
        roi = area.geometria()
        with cronometro("armar mosaicos (perezoso)", logger):
            mosaico_t1 = self._adquisicion.obtener_mosaico(roi, *periodo_t1)
            mosaico_t2 = self._adquisicion.obtener_mosaico(roi, *periodo_t2)

        with cronometro("comprobar que hay imágenes", logger):
            for nombre, mosaico, periodo in (("la Época A (T1)", mosaico_t1, periodo_t1),
                                             ("la Época B (T2)", mosaico_t2, periodo_t2)):
                if mosaico.bandNames().size().getInfo() == 0:
                    return {"vacio": f"{nombre}, {etiqueta_periodo(*periodo)}"}

        with cronometro("URL de las miniaturas", logger):
            url1 = self._adquisicion.obtener_thumbnail_url(mosaico_t1, roi)
            url2 = self._adquisicion.obtener_thumbnail_url(mosaico_t2, roi)

        with cronometro("descargar miniaturas (2 en paralelo)", logger), ThreadPoolExecutor(max_workers=2) as pool:
            pil1, pil2 = pool.map(lambda url: abrir_imagen(url).convert("RGBA"), (url1, url2))

        return {
            "area": area, "periodo_t1": periodo_t1, "periodo_t2": periodo_t2,
            "mosaico_t1": mosaico_t1, "mosaico_t2": mosaico_t2,
            "url1": url1, "url2": url2, "pil1": pil1, "pil2": pil2,
        }

    def _al_cargar_ee(self, datos: dict) -> None:
        self.btn_ee.setEnabled(True)
        if "vacio" in datos:
            umbral = self._gestor_config.config.umbral_nubes
            QMessageBox.warning(
                self, "Sin imágenes",
                f"No hay imágenes de Sentinel-2 para {datos['vacio']} con menos de {umbral}% de nubes.\n\n"
                "Prueba con un periodo más largo, sube el umbral de nubes en Configuración o elige otra zona.",
            )
            self.status_bar.set_mensaje("Error: no se encontraron imágenes", "alerta")
            return

        self._limpiar_resultado()               # lo anterior ya no corresponde a esta zona
        self.proyecto_actual = None
        self._area_estudio = datos["area"]
        self._periodo_t1, self._periodo_t2 = datos["periodo_t1"], datos["periodo_t2"]
        self._escala_analisis = calcular_escala_metros(self._area_estudio.radio_metros)
        self._clasificacion.escala_metros = self._escala_analisis
        self._deteccion.escala_metros = self._escala_analisis

        self.imagen_anterior, self.imagen_anterior_ee, self._pil_anterior = datos["url1"], datos["mosaico_t1"], datos["pil1"]
        self.imagen_actual, self.imagen_actual_ee, self._pil_actual = datos["url2"], datos["mosaico_t2"], datos["pil2"]

        etiqueta_a = etiqueta_periodo(*self._periodo_t1)
        etiqueta_b = etiqueta_periodo(*self._periodo_t2)
        self.label_anterior.setText(f"EPOCH A: Sentinel-2 {etiqueta_a}")
        self.label_actual.setText(f"EPOCH B: Sentinel-2 {etiqueta_b}")
        self.map_canvas.etiqueta_t1, self.map_canvas.etiqueta_t2 = etiqueta_a, etiqueta_b
        self.status_bar.escala.setText(f"{self._escala_analisis} m/px")
        self._mostrar_vista_previa()
        self.status_bar.set_mensaje(f"«{self._area_estudio.nombre}»: imágenes cargadas desde Earth Engine", "exito")

    def _al_fallar_carga_ee(self, error: Exception) -> None:
        self.btn_ee.setEnabled(True)
        QMessageBox.critical(self, "Error", f"Error al cargar desde Earth Engine:\n{error}")
        self.status_bar.set_mensaje("Error al cargar desde Earth Engine", "alerta")

    def _limpiar_resultado(self) -> None:
        """Descarta una detección anterior (para no mezclarla con imágenes nuevas)."""
        self.resultado_deteccion = None
        self.map_canvas.imagen_t1 = self.map_canvas.imagen_t2 = self.map_canvas.imagen_cambios = None
        self.mapa_navegable.set_capas([])
        self._qimages.clear()
        self._pila_mapas.setCurrentIndex(0)
        self.results_panel.mostrar_mensaje_espera()
        self.btn_modo_vista.setEnabled(False)
        self.btn_informe.setEnabled(False)

    def _mostrar_vista_previa(self) -> None:
        if not self.imagen_anterior or not self.imagen_actual:
            self.map_canvas.mostrar_bienvenida()
            return
        try:
            if self._pil_anterior is None:     # archivo local (las URL de EE ya vienen en caché)
                self._pil_anterior = abrir_imagen(self.imagen_anterior)
            if self._pil_actual is None:
                self._pil_actual = abrir_imagen(self.imagen_actual)
            self.map_canvas.mostrar_comparacion_lado_a_lado(
                self._pil_anterior, self._pil_actual, "ANTES", "DESPUÉS",
            )
        except Exception as error:
            logger.exception("Error al mostrar vista previa")
            self.map_canvas.mostrar_error(str(error))

    # ---------------------------------------------------------- detección
    def detectar_cambios(self) -> None:
        if not self.imagen_anterior or not self.imagen_actual:
            QMessageBox.warning(self, "Advertencia", "Carga ambas imágenes satelitales primero.")
            return
        if self.imagen_anterior_ee is None or self.imagen_actual_ee is None:
            QMessageBox.warning(
                self, "Detección no disponible",
                "La detección real requiere ambas imágenes cargadas desde Earth Engine.\n"
                "Usa 'Cargar desde Earth Engine' para ambas épocas.",
            )
            return

        self.status_bar.set_mensaje("Detectando cambios… puede tardar 1-2 minutos", "advertencia")
        self.btn_detectar.setText("⏳ Procesando…")
        for b in (self.btn_detectar, self.btn_modo_vista, self.btn_informe):
            b.setEnabled(False)
        self._en_segundo_plano(self._tarea_detectar, self._al_detectar, self._al_fallar_deteccion)

    def _tarea_detectar(self):
        """Corre en el hilo de fondo: clasifica, detecta y descarga la capa de cambios.

        Earth Engine es perezoso: construir la clasificación es casi instantáneo y el
        cómputo real (muestreo, entrenamiento, clasificación e histograma) ocurre dentro
        de ``detectar`` al pedir el resultado con ``getInfo()``. Por eso los tiempos se
        registran por fase y no por "función".
        """
        if self._area_estudio is not None:
            roi, centro = self._area_estudio.geometria(), self._area_estudio.centro()
        else:                                    # imágenes de EE cargadas sin pasar por el diálogo
            roi = self.imagen_actual_ee.geometry()
            try:
                centro_geo = roi.centroid(1).coordinates().getInfo()   # EE exige un margen de error > 0
                centro = (centro_geo[0], centro_geo[1])
            except Exception:
                centro = (0.0, 0.0)

        with cronometro("construir clasificación (perezoso)", logger):
            clasificaciones = self._clasificacion.clasificar_mosaicos_temporales(
                self.imagen_anterior_ee, self.imagen_actual_ee, roi=roi,
                anios=(int(self._periodo_t1[0][:4]), int(self._periodo_t2[0][:4])),   # ← NUEVO
            )
        with cronometro(f"cómputo en Earth Engine a {self._escala_analisis} m/px", logger):
            resultado = self._deteccion.detectar(
                clasificaciones["clasificacion_t1"], clasificaciones["clasificacion_t2"], roi, centro,
            )
        with cronometro("descargar capa de cambios", logger):
            imagen_cambios = abrir_imagen(resultado.url_overlay).convert("RGBA")
        return resultado, imagen_cambios

    def _al_detectar(self, datos) -> None:
        resultado, imagen_cambios = datos
        self.map_canvas.imagen_t1 = self._pil_anterior.convert("RGBA")
        self.map_canvas.imagen_t2 = self._pil_actual.convert("RGBA")
        self.map_canvas.imagen_cambios = imagen_cambios
        self.resultado_deteccion = resultado

        self.results_panel.mostrar_estadisticas(resultado.estadisticas)
        self._refrescar_vista_resultado()
        self.status_bar.set_mensaje("Detección completada", "exito")
        self.btn_detectar.setText("DETECTAR CAMBIOS")
        for b in (self.btn_detectar, self.btn_modo_vista, self.btn_informe):
            b.setEnabled(True)

        if self._gestor_config.config.autoguardado:
            self.guardar_proyecto()

    def _al_fallar_deteccion(self, error: Exception) -> None:
        texto = str(error)
        if "No valid training data" in texto:
            mensaje = ("No se pudieron generar muestras de entrenamiento en esta zona.\n\n"
                       "Suele pasar cuando casi todo el área está cubierta de nubes o es muy pequeña. "
                       "Prueba con otro periodo, un radio mayor o un umbral de nubes más alto.")
        elif "Computation timed out" in texto or "memory limit" in texto:
            mensaje = ("Earth Engine no alcanzó a terminar el cálculo.\n\n"
                       "Reduce el radio del área de estudio o elige un periodo más corto.")
        else:
            mensaje = f"Error en la detección:\n{error}"
        QMessageBox.critical(self, "Error en la detección", mensaje)
        self.status_bar.set_mensaje("Error en la detección", "alerta")
        self.btn_detectar.setText("DETECTAR CAMBIOS")
        self.btn_detectar.setEnabled(True)
        hay_resultado = self.resultado_deteccion is not None
        self.btn_modo_vista.setEnabled(hay_resultado)
        self.btn_informe.setEnabled(hay_resultado)

    # -------------------------------------------------------------- vistas
    def _refrescar_vista_resultado(self) -> None:
        if self.resultado_deteccion is None:
            self._pila_mapas.setCurrentIndex(0)
            self._mostrar_vista_previa()
            return
        if self.modo_vista == "mapa":
            self._mostrar_vista_mapa()
            return
        self._pila_mapas.setCurrentIndex(0)
        if self.modo_vista == "overlay":
            self.map_canvas.mostrar_resultado_overlay(
                mostrar_t1=self.layer_panel.mostrar_t1,
                mostrar_t2=self.layer_panel.mostrar_t2,
                mostrar_cambios=self.layer_panel.mostrar_cambios,
                opacidad_cambios=self.layer_panel.opacidad_cambios,
            )
        else:
            self.map_canvas.mostrar_resultado_swipe(
                posicion_relativa=self.posicion_slider,
                mostrar_cambios=self.layer_panel.mostrar_cambios,
                opacidad_cambios=self.layer_panel.opacidad_cambios,
            )

    def alternar_modo_vista(self) -> None:
        """Rota entre las tres vistas: overlay -> swipe -> mapa -> overlay."""
        siguiente = {"overlay": "swipe", "swipe": "mapa", "mapa": "overlay"}[self.modo_vista]
        self._fijar_modo_vista(siguiente)

    def _fijar_modo_vista(self, modo: str) -> None:
        self.modo_vista = modo
        self.btn_modo_vista.setText({"overlay": "Vista: Overlay", "swipe": "Vista: Swipe",
                                     "mapa": "Vista: Mapa"}[modo])
        self._refrescar_vista_resultado()

    def _qimage(self, imagen):
        """QImage con transparencia de una imagen PIL, convertida una sola vez."""
        clave = id(imagen)
        if clave not in self._qimages:
            self._qimages[clave] = pil_a_qimage_rgba(imagen)
        return self._qimages[clave]

    def _mostrar_vista_mapa(self) -> None:
        """Pone la imagen satelital y la capa de cambios sobre un mapa navegable, georreferenciadas."""
        area = self._area_estudio
        if area is None:
            self.status_bar.set_mensaje("La vista de mapa necesita un área elegida con «Earth Engine»", "alerta")
            self._fijar_modo_vista("overlay")
            return
        limites = limites_cuadrado(area.longitud, area.latitud, area.radio_metros)
        capas = []
        base = self.map_canvas.imagen_t2 if self.layer_panel.mostrar_t2 else (
            self.map_canvas.imagen_t1 if self.layer_panel.mostrar_t1 else None)
        if base is not None:
            capas.append(CapaImagen(self._qimage(base), limites, 1.0))
        if self.layer_panel.mostrar_cambios and self.map_canvas.imagen_cambios is not None:
            capas.append(CapaImagen(self._qimage(self.map_canvas.imagen_cambios), limites,
                                    self.layer_panel.opacidad_cambios))

        mapa = self.mapa_navegable
        clave_area = (area.longitud, area.latitud, area.radio_metros)
        mapa.set_area(*clave_area)
        mapa.set_capas(capas)
        self._pila_mapas.setCurrentIndex(1)
        if self._area_en_mapa != clave_area:             # primera vez con esta zona: se encuadra
            self._area_en_mapa = clave_area
            mapa.ajustar_a_area()
            if base is not None:
                self.status_bar.set_mensaje(
                    "Vista de mapa: desmarca «Época B» en Capas para ver los cambios sobre el mapa base")

    def _al_mover_mapa(self) -> None:
        self.status_bar.set_zoom(self.mapa_navegable.zoom)
        self.status_bar.set_coordenadas(self.mapa_navegable.lon, self.mapa_navegable.lat)

    def _actualizar_slider(self, valor: int) -> None:
        self.posicion_slider = valor / 100.0
        if self.resultado_deteccion is not None and self.modo_vista == "swipe":
            self._refrescar_vista_resultado()

    def rescan_area(self) -> None:
        self.status_bar.set_mensaje("Escaneando área…", "advertencia")
        self.btn_rescan.setText("⏳ Escaneando…")
        self.btn_rescan.setEnabled(False)

        def finalizar() -> None:
            estado = "Conectado" if self._ee_service.conectado else "No conectado"
            self.status_bar.set_mensaje(f"SAR-V2 Orbital Stream: Nominal ({estado})")
            self.btn_rescan.setText("↻  RE-SCAN TARGET AREA")
            self.btn_rescan.setEnabled(True)

        QTimer.singleShot(1500, finalizar)

    def capturar_mapa(self) -> None:
        ruta, _ = QFileDialog.getSaveFileName(
            self, "Guardar captura del mapa", str(RAIZ_PROYECTO / "exports"), "Imagen PNG (*.png)",
        )
        if ruta:
            if not ruta.lower().endswith(".png"):
                ruta += ".png"
            self.map_canvas.guardar_captura(ruta)
            self.status_bar.set_mensaje(f"Captura guardada: {os.path.basename(ruta)}", "exito")

    # ------------------------------------------------------------ reportes
    def exportar_reporte(self, formato: str) -> None:
        if self.resultado_deteccion is None:
            QMessageBox.warning(self, "Sin resultados", "Ejecuta primero la detección de cambios.")
            return
        try:
            contexto = ContextoReporte(
                titulo_proyecto=(self.proyecto_actual.nombre if self.proyecto_actual else "Proyecto sin nombre"),
                autor=os.environ.get("USERNAME") or os.environ.get("USER") or "Usuario",
                periodo_t1=etiqueta_periodo(*self._periodo_t1), periodo_t2=etiqueta_periodo(*self._periodo_t2),
                estadisticas=self.resultado_deteccion.estadisticas,
            )
            generador = {
                "csv": self._exportacion.exportar_csv,
                "json": self._exportacion.exportar_json,
                "excel": self._exportacion.exportar_excel,
                "word": self._exportacion.exportar_word,
                "pdf": self._exportacion.exportar_pdf,
            }[formato]
            ruta = generador(contexto)
            self.status_bar.set_mensaje(f"Reporte generado: {ruta.name}", "exito")
            QMessageBox.information(self, "Exportación completada", f"Reporte guardado en:\n{ruta}")
        except TerraIntelError as error:
            QMessageBox.critical(self, "Error al exportar", str(error))

    # ------------------------------------------------------------ proyecto
    def nuevo_proyecto(self) -> None:
        self.imagen_anterior = self.imagen_actual = None
        self.imagen_anterior_ee = self.imagen_actual_ee = None
        self._pil_anterior = self._pil_actual = None
        self._limpiar_resultado()
        self.proyecto_actual = None
        self._area_estudio = None
        self._periodo_t1, self._periodo_t2 = ("2019-01-01", "2019-12-31"), ("2024-01-01", "2024-12-31")
        self.map_canvas.etiqueta_t1 = self.map_canvas.etiqueta_t2 = ""
        self.label_anterior.setText("EPOCH A: Sin imagen")
        self.label_actual.setText("EPOCH B: Sin imagen")
        self.map_canvas.mostrar_bienvenida()
        self.status_bar.set_mensaje("Nuevo proyecto")

    def guardar_proyecto(self) -> None:
        if self.imagen_actual_ee is None:
            QMessageBox.warning(self, "Sin datos", "Carga imágenes desde Earth Engine antes de guardar.")
            return
        try:
            if self._area_estudio is not None:
                longitud, latitud = self._area_estudio.centro()     # ya lo sabemos: no hace falta pedirlo a EE
                nombre_defecto = self._area_estudio.nombre
            else:
                centro = self.imagen_actual_ee.geometry().centroid(1).coordinates().getInfo()
                longitud, latitud = centro[0], centro[1]
                nombre_defecto = "proyecto_terra_intel"
            nombre = self.proyecto_actual.nombre if self.proyecto_actual else nombre_defecto
            proyecto = Proyecto(
                nombre=nombre, longitud=longitud, latitud=latitud,
                periodo_t1=etiqueta_periodo(*self._periodo_t1), periodo_t2=etiqueta_periodo(*self._periodo_t2),
                estadisticas=(self.resultado_deteccion.estadisticas if self.resultado_deteccion else []),
            )
            ruta = self._proyectos.guardar(proyecto)
        except Exception as error:      # un fallo al guardar no debe tumbar la app ni ocultar el resultado
            logger.exception("No se pudo guardar el proyecto")
            QMessageBox.critical(self, "Error al guardar", f"No se pudo guardar el proyecto:\n{error}")
            self.status_bar.set_mensaje("Error al guardar el proyecto", "alerta")
            return
        self.proyecto_actual = proyecto
        self.status_bar.set_mensaje(f"Proyecto guardado: {ruta.name}", "exito")

    def abrir_proyecto(self) -> None:
        ruta, _ = QFileDialog.getOpenFileName(
            self, "Abrir proyecto", str(RAIZ_PROYECTO / "data"), "Proyecto TERRA_INTEL (*.tiproj)",
        )
        if not ruta:
            return
        try:
            proyecto = self._proyectos.abrir(Path(ruta))
        except TerraIntelError as error:
            QMessageBox.critical(self, "Error al abrir proyecto", str(error))
            return
        self.proyecto_actual = proyecto
        self._area_estudio = crear_area_estudio(
            longitud=proyecto.longitud, latitud=proyecto.latitud,
            radio_metros=self._gestor_config.config.radio_area_estudio_m, nombre=proyecto.nombre,
        )
        self._periodo_t1 = periodo_desde_etiqueta(proyecto.periodo_t1) or self._periodo_t1
        self._periodo_t2 = periodo_desde_etiqueta(proyecto.periodo_t2) or self._periodo_t2
        if proyecto.estadisticas:
            self.results_panel.mostrar_estadisticas(proyecto.estadisticas)
        else:
            self.results_panel.mostrar_mensaje_espera()
        self.status_bar.set_mensaje(f"Proyecto abierto: {proyecto.nombre}")
        QMessageBox.information(
            self, "Proyecto abierto",
            f"'{proyecto.nombre}'\nCentro: {proyecto.latitud:.4f}, {proyecto.longitud:.4f}\n"
            "Pulsa «Earth Engine» para reanudar: el área y los periodos ya quedaron preseleccionados.",
        )

    # -------------------------------------------------------------- varios
    def _aplicar_tema(self, nombre_tema: str) -> None:
        self._paleta = theme.aplicar_tema(QApplication.instance(), nombre_tema)
        self.map_canvas.set_paleta(self._paleta)
        self.mapa_navegable.set_paleta(self._paleta)

    def alternar_tema(self) -> None:
        nuevo_tema = "light" if self._gestor_config.config.tema == "dark" else "dark"
        self._gestor_config.actualizar(tema=nuevo_tema)
        self._aplicar_tema(nuevo_tema)
        self.status_bar.set_mensaje(f"Tema cambiado a '{nuevo_tema}'", "exito")

    def abrir_configuracion(self) -> None:
        if SettingsDialog(self, self._gestor_config).exec() == QDialog.DialogCode.Accepted:
            self._al_guardar_configuracion()

    def _al_guardar_configuracion(self) -> None:
        config = self._gestor_config.config
        self._adquisicion.umbral_nubes = config.umbral_nubes
        self._aplicar_tema(config.tema)
        self.status_bar.set_mensaje("Configuración guardada", "exito")

    def mostrar_acerca_de(self) -> None:
        AboutDialog(self).exec()
