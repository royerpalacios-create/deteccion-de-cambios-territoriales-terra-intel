"""Diálogo para seleccionar el área de estudio y el periodo de análisis.

Permite al usuario elegir entre:
  1. Una región predefinida del Perú (combo con 33+ zonas).
  2. Coordenadas manuales (lat/lon) con radio configurable.

También permite configurar los dos periodos temporales (T1 y T2) con
sus fechas de inicio y fin. Las fechas se validan antes de cerrar el
diálogo, y los valores usados la última vez se recuerdan al reabrirlo.
"""
from __future__ import annotations

from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout,
    QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QSpinBox,
    QTabWidget, QVBoxLayout, QWidget,
)

from app.core.exceptions import ValidacionError
from app.models.area_estudio import (
    AreaDeEstudio, ESCALA_MINIMA_METROS, RADIO_BUFFER_METROS, calcular_escala_metros, estimar_pixeles,
)
from app.models.regiones_peru import REGIONES_PERU, RegionPeru
from app.core.exceptions import GeocodificacionError
from app.services.adquisicion_service import validar_periodos
from app.services.geocodificacion_service import Lugar, buscar_lugar
from app.services.teselas_service import ServicioTeselas
from app.ui.theme import boton, etiqueta, fuente, paleta_activa
from app.ui.trabajo import Trabajo
from app.ui.widgets.map_view import MapaNavegable

PERIODO_T1_DEFECTO = ("2019-01-01", "2019-12-31")
PERIODO_T2_DEFECTO = ("2024-01-01", "2024-12-31")


class AreaEstudioDialog(QDialog):
    """Diálogo modal para configurar el área de estudio y los periodos."""

    def __init__(self, parent=None, area: AreaDeEstudio | None = None,
                 periodo_t1: tuple[str, str] | None = None,
                 periodo_t2: tuple[str, str] | None = None,
                 radio_defecto: float = RADIO_BUFFER_METROS,
                 servicio_teselas: ServicioTeselas | None = None) -> None:
        """``area`` y los periodos son la selección anterior (para recordarla al reabrir).

        ``servicio_teselas`` descarga (y cachea en disco) los mapas; si no se da, usa uno sin caché.
        """
        super().__init__(parent)
        self.setWindowTitle("Seleccionar Área de Estudio")
        self.setModal(True)
        pantalla = QGuiApplication.primaryScreen().availableGeometry()
        self.setMinimumSize(min(920, pantalla.width() - 40), min(600, pantalla.height() - 60))
        self._servicio_teselas = servicio_teselas or ServicioTeselas()
        self._mapa_ajustado = False
        self._desde_mapa = False

        self._area: AreaDeEstudio | None = None
        self._fecha_inicio_t1, self._fecha_fin_t1 = periodo_t1 or PERIODO_T1_DEFECTO
        self._fecha_inicio_t2, self._fecha_fin_t2 = periodo_t2 or PERIODO_T2_DEFECTO
        self._radio_inicial = int(area.radio_metros if area else radio_defecto)

        self._construir_ui()
        if area is not None:
            self._preseleccionar(area)

    # ────────────────────────────────────────────── construcción de la UI ──
    def _construir_ui(self) -> None:
        raiz = QVBoxLayout(self)
        raiz.setSpacing(10)
        raiz.setContentsMargins(16, 14, 16, 14)

        raiz.addWidget(etiqueta("Área de Estudio", 16, True))
        raiz.addWidget(etiqueta(
            "Elige una región, busca un lugar o haz clic en el mapa. El área analizada es el cuadrado verde.",
            11, tono="secundario", wrap=True))

        cuerpo = QHBoxLayout()
        cuerpo.setSpacing(14)
        raiz.addLayout(cuerpo, 1)

        # ── Columna izquierda: regiones / mapa ──
        tabs = QTabWidget()
        tabs.setFont(fuente(11))
        tabs.addTab(self._tab_region(), "Regiones del Perú")
        tabs.addTab(self._tab_manual(), "Mapa y coordenadas")
        tabs.currentChanged.connect(self._on_tab_cambiado)
        self._tabs = tabs
        cuerpo.addWidget(tabs, 1)

        # ── Columna derecha: periodos, radio y botones ──
        derecha = QWidget()
        derecha.setFixedWidth(400)
        der = QVBoxLayout(derecha)
        der.setContentsMargins(0, 0, 0, 0)
        der.setSpacing(10)
        der.addWidget(self._grupo_periodos())

        grp_radio = QGroupBox("Radio del área de estudio")
        grp_radio.setFont(fuente(11))
        f = QFormLayout(grp_radio)
        self._spin_radio = QSpinBox()
        self._spin_radio.setRange(1_000, 100_000)
        self._spin_radio.setSingleStep(1_000)
        self._spin_radio.setValue(max(1_000, min(100_000, self._radio_inicial)))
        self._spin_radio.setSuffix(" m")
        self._spin_radio.setFont(fuente(11))
        f.addRow("Radio (metros):", self._spin_radio)
        self._lbl_resolucion = etiqueta("", 10, mono=True, tono="secundario", wrap=True)
        f.addRow(self._lbl_resolucion)
        self._spin_radio.valueChanged.connect(self._actualizar_resolucion)
        self._spin_radio.valueChanged.connect(self._al_cambiar_radio)
        self._actualizar_resolucion(self._spin_radio.value())
        der.addWidget(grp_radio)
        der.addStretch(1)

        botones = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        botones.setFont(fuente(11))
        botones.button(QDialogButtonBox.StandardButton.Ok).setText("Cargar imágenes")
        botones.button(QDialogButtonBox.StandardButton.Cancel).setText("Cancelar")
        botones.accepted.connect(self._aceptar)
        botones.rejected.connect(self.reject)
        der.addWidget(botones)
        cuerpo.addWidget(derecha)

        self._sincronizar_mapa()
        self._mapa.centrar(self._spin_lon.value(), self._spin_lat.value(), 9)

    def _tab_region(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 12, 8, 8)
        lay.setSpacing(10)

        lay.addWidget(etiqueta("Departamento / zona:", 11, tono="secundario"))

        # Combo de búsqueda rápida por departamento
        self._combo_depto = QComboBox()
        self._combo_depto.setFont(fuente(11))
        deptos = sorted({r.departamento for r in REGIONES_PERU})
        self._combo_depto.addItem("Todos los departamentos")
        self._combo_depto.addItems(deptos)
        self._combo_depto.currentTextChanged.connect(self._filtrar_regiones)
        lay.addWidget(self._combo_depto)

        lay.addWidget(etiqueta("Región / localidad:", 11, tono="secundario"))
        self._combo_region = QComboBox()
        self._combo_region.setFont(fuente(11))
        self._poblar_combo_regiones(REGIONES_PERU)
        self._combo_region.currentIndexChanged.connect(self._on_region_cambiada)
        lay.addWidget(self._combo_region)

        # Preview de coordenadas
        self._lbl_coords_region = etiqueta("", 10, mono=True, tono="acento")
        lay.addWidget(self._lbl_coords_region)
        self._on_region_cambiada(0)   # inicializar preview

        lay.addWidget(boton("Ver en el mapa y ajustar", self._ver_region_en_mapa, alto=32))
        lay.addStretch(1)
        return w

    def _tab_manual(self) -> QWidget:
        """Mapa navegable + buscador + coordenadas (los campos y el mapa se mantienen sincronizados)."""
        contenedor = QWidget()
        lay = QVBoxLayout(contenedor)            # el contenedor es dueño del layout y de todos sus hijos
        lay.setContentsMargins(8, 10, 8, 8)
        lay.setSpacing(8)

        # -- buscador de lugares
        fila = QHBoxLayout()
        self._edit_busqueda = QLineEdit()
        self._edit_busqueda.setFont(fuente(11))
        self._edit_busqueda.setPlaceholderText("Buscar un lugar: distrito, ciudad, comunidad…")
        self._edit_busqueda.returnPressed.connect(self._buscar)
        self._btn_buscar = boton("Buscar", self._buscar, alto=32)
        fila.addWidget(self._edit_busqueda, 1)
        fila.addWidget(self._btn_buscar)
        lay.addLayout(fila)
        self._combo_resultados = QComboBox()
        self._combo_resultados.setFont(fuente(10))
        self._combo_resultados.hide()
        self._combo_resultados.activated.connect(self._elegir_resultado)
        lay.addWidget(self._combo_resultados)
        self._lbl_busqueda = etiqueta("Haz clic en el mapa para colocar el centro del área.", 10, tono="secundario")
        lay.addWidget(self._lbl_busqueda)

        # -- mapa
        self._mapa = MapaNavegable(self._servicio_teselas, paleta_activa())
        self._mapa.habilitar_seleccion(True)
        self._mapa.punto_elegido.connect(self._al_clic_mapa)
        lay.addWidget(self._mapa, 1)

        # -- coordenadas
        self._spin_lat = QDoubleSpinBox()
        self._spin_lat.setRange(-18.5, -0.0)
        self._spin_lat.setDecimals(4)
        self._spin_lat.setSingleStep(0.1)
        self._spin_lat.setValue(-15.84)
        self._spin_lat.setFont(fuente(11))

        self._spin_lon = QDoubleSpinBox()
        self._spin_lon.setRange(-82.0, -68.0)
        self._spin_lon.setDecimals(4)
        self._spin_lon.setSingleStep(0.1)
        self._spin_lon.setValue(-70.01)
        self._spin_lon.setFont(fuente(11))

        self._edit_nombre = QLineEdit("Área personalizada")
        self._edit_nombre.setFont(fuente(11))

        self._spin_lat.valueChanged.connect(self._al_cambiar_coordenadas)
        self._spin_lon.valueChanged.connect(self._al_cambiar_coordenadas)

        coordenadas = QHBoxLayout()
        coordenadas.setSpacing(8)
        for texto, campo in (("Lat (°S):", self._spin_lat), ("Lon (°W):", self._spin_lon)):
            coordenadas.addWidget(etiqueta(texto, 11, tono="secundario"))
            coordenadas.addWidget(campo)
        coordenadas.addWidget(etiqueta("Nombre:", 11, tono="secundario"))
        coordenadas.addWidget(self._edit_nombre, 1)
        lay.addLayout(coordenadas)
        return contenedor

    def _grupo_periodos(self) -> QGroupBox:
        grp = QGroupBox("Periodos de análisis (Sentinel-2)")
        grp.setFont(fuente(11))
        lay = QVBoxLayout(grp)
        lay.setSpacing(8)

        # T1
        fila_t1 = QWidget()
        h1 = QHBoxLayout(fila_t1)
        h1.setContentsMargins(0, 0, 0, 0)
        lbl_t1 = QLabel("Época A (T1):")
        lbl_t1.setFont(fuente(11))
        lbl_t1.setFixedWidth(100)
        self._edit_t1_ini = self._campo_fecha(self._fecha_inicio_t1)
        self._edit_t1_fin = self._campo_fecha(self._fecha_fin_t1)
        h1.addWidget(lbl_t1)
        h1.addWidget(QLabel("Inicio:")); h1.addWidget(self._edit_t1_ini)
        h1.addWidget(QLabel("  Fin:")); h1.addWidget(self._edit_t1_fin)
        lay.addWidget(fila_t1)

        # T2
        fila_t2 = QWidget()
        h2 = QHBoxLayout(fila_t2)
        h2.setContentsMargins(0, 0, 0, 0)
        lbl_t2 = QLabel("Época B (T2):")
        lbl_t2.setFont(fuente(11))
        lbl_t2.setFixedWidth(100)
        self._edit_t2_ini = self._campo_fecha(self._fecha_inicio_t2)
        self._edit_t2_fin = self._campo_fecha(self._fecha_fin_t2)
        h2.addWidget(lbl_t2)
        h2.addWidget(QLabel("Inicio:")); h2.addWidget(self._edit_t2_ini)
        h2.addWidget(QLabel("  Fin:")); h2.addWidget(self._edit_t2_fin)
        lay.addWidget(fila_t2)

        nota = etiqueta("Formato: AAAA-MM-DD  (Sentinel-2 disponible desde 2017)", 10,
                        tono="secundario")
        lay.addWidget(nota)
        return grp

    @staticmethod
    def _campo_fecha(valor: str) -> QLineEdit:
        e = QLineEdit(valor)
        e.setFont(fuente(11, mono=True))
        e.setFixedWidth(96)
        e.setInputMask("9999-99-99")
        return e

    # ──────────────────────────────────────────────────────── lógica interna
    def _poblar_combo_regiones(self, regiones: list[RegionPeru]) -> None:
        self._combo_region.clear()
        for r in regiones:
            self._combo_region.addItem(f"{r.nombre}  ({r.departamento})", userData=r)

    def _filtrar_regiones(self, depto: str) -> None:
        if depto == "Todos los departamentos":
            filtradas = REGIONES_PERU
        else:
            filtradas = [r for r in REGIONES_PERU if r.departamento == depto]
        self._poblar_combo_regiones(filtradas)

    def _on_region_cambiada(self, _idx: int) -> None:
        region: RegionPeru | None = self._combo_region.currentData()
        if region:
            self._lbl_coords_region.setText(
                f"Lat: {region.latitud:.4f}   Lon: {region.longitud:.4f}"
            )

    def _on_tab_cambiado(self, idx: int) -> None:
        if idx == 1 and not self._mapa_ajustado:       # el mapa ya tiene su tamaño real: se encuadra el área
            QTimer.singleShot(0, self._ajustar_mapa)

    def showEvent(self, evento) -> None:  # noqa: N802
        super().showEvent(evento)
        if self._tabs.currentIndex() == 1 and not self._mapa_ajustado:
            QTimer.singleShot(0, self._ajustar_mapa)

    def done(self, resultado: int) -> None:
        self._mapa.cerrar()                            # detiene las descargas de teselas en segundo plano
        super().done(resultado)

    # ───────────────────────────────────── mapa, coordenadas y buscador
    def _ajustar_mapa(self) -> None:
        self._mapa_ajustado = True
        self._mapa.ajustar_a_area()

    def _sincronizar_mapa(self) -> None:
        """Dibuja en el mapa el área que describen los campos."""
        self._mapa.set_area(self._spin_lon.value(), self._spin_lat.value(), self._spin_radio.value())

    def _fijar_coordenadas(self, latitud: float, longitud: float, desde_mapa: bool = False) -> None:
        """Escribe lat/lon en los campos. ``desde_mapa`` evita que el mapa se re-centre al hacer clic."""
        self._desde_mapa = desde_mapa
        try:
            self._spin_lat.setValue(latitud)
            self._spin_lon.setValue(longitud)
        finally:
            self._desde_mapa = False
        self._sincronizar_mapa()

    def _al_cambiar_coordenadas(self, _valor: float) -> None:
        self._sincronizar_mapa()
        if not self._desde_mapa:                       # el usuario escribió: se lleva el mapa hasta ahí
            self._mapa.centrar(self._spin_lon.value(), self._spin_lat.value())

    def _al_cambiar_radio(self, _valor: int) -> None:
        self._sincronizar_mapa()
        self._mapa.ajustar_a_area()

    def _al_clic_mapa(self, lon: float, lat: float) -> None:
        self._fijar_coordenadas(lat, lon, desde_mapa=True)
        fuera = abs(self._spin_lat.value() - lat) > 1e-3 or abs(self._spin_lon.value() - lon) > 1e-3
        self._lbl_busqueda.setText(
            "Ese punto está fuera de Perú: se ajustó al límite permitido." if fuera
            else f"Centro del área: {self._spin_lat.value():.4f}, {self._spin_lon.value():.4f}")

    def _ver_region_en_mapa(self) -> None:
        region: RegionPeru | None = self._combo_region.currentData()
        if region is None:
            return
        self._fijar_coordenadas(region.latitud, region.longitud)
        self._edit_nombre.setText(region.nombre)
        self._mapa_ajustado = False
        self._tabs.setCurrentIndex(1)

    def _buscar(self) -> None:
        texto = self._edit_busqueda.text().strip()
        if len(texto) < 3:
            self._lbl_busqueda.setText("Escribe al menos 3 caracteres para buscar.")
            return
        self._btn_buscar.setEnabled(False)
        self._lbl_busqueda.setText(f"Buscando «{texto}»…")
        trabajo = Trabajo(lambda: buscar_lugar(texto), parent=self)
        trabajo.terminado.connect(self._al_buscar)
        trabajo.fallo.connect(self._al_fallar_busqueda)
        trabajo.terminado.connect(trabajo.deleteLater)
        trabajo.fallo.connect(trabajo.deleteLater)
        trabajo.iniciar()

    def _al_buscar(self, lugares: list[Lugar]) -> None:
        self._btn_buscar.setEnabled(True)
        self._combo_resultados.clear()
        if not lugares:
            self._combo_resultados.hide()
            self._lbl_busqueda.setText("Sin resultados. Prueba con otro nombre o haz clic en el mapa.")
            return
        for lugar in lugares:
            self._combo_resultados.addItem(lugar.nombre, userData=lugar)
        self._combo_resultados.show()
        self._lbl_busqueda.setText(f"{len(lugares)} resultado(s): elige uno de la lista.")
        self._elegir_resultado(0)

    def _al_fallar_busqueda(self, error: Exception) -> None:
        self._btn_buscar.setEnabled(True)
        self._lbl_busqueda.setText(str(error) if isinstance(error, (GeocodificacionError, ValidacionError))
                                   else f"Error al buscar: {error}")

    def _elegir_resultado(self, indice: int) -> None:
        lugar = self._combo_resultados.itemData(indice)
        if not isinstance(lugar, Lugar):
            return
        self._fijar_coordenadas(lugar.latitud, lugar.longitud)
        self._edit_nombre.setText(lugar.nombre_corto)
        self._mapa.ajustar_a_area()

    def _actualizar_resolucion(self, radio: int) -> None:
        escala = calcular_escala_metros(radio)
        millones = estimar_pixeles(radio, escala) / 1_000_000
        texto = f"Resolución de análisis: {escala} m/píxel  ·  ≈ {millones:.1f} M de píxeles por época"
        if escala > ESCALA_MINIMA_METROS:
            texto += "\nEl área es grande: se reduce la resolución para que Earth Engine pueda procesarla."
        self._lbl_resolucion.setText(texto)

    def _preseleccionar(self, area: AreaDeEstudio) -> None:
        """Deja marcada la selección anterior: la región si coincide, o las coordenadas manuales."""
        for i in range(self._combo_region.count()):
            region = self._combo_region.itemData(i)
            if region is not None and region.nombre == area.nombre:
                self._combo_region.setCurrentIndex(i)
                self._fijar_coordenadas(area.latitud, area.longitud)   # el mapa queda ya en esta región
                self._edit_nombre.setText(area.nombre)
                self._tabs.setCurrentIndex(0)
                return
        self._fijar_coordenadas(area.latitud, area.longitud)
        self._edit_nombre.setText(area.nombre)
        self._tabs.setCurrentIndex(1)

    # ─────────────────────────────────────────────── propiedades de resultado
    def _aceptar(self) -> None:
        periodo_t1 = (self._edit_t1_ini.text(), self._edit_t1_fin.text())
        periodo_t2 = (self._edit_t2_ini.text(), self._edit_t2_fin.text())
        try:
            validar_periodos(periodo_t1, periodo_t2)
        except ValidacionError as error:
            QMessageBox.warning(self, "Periodos no válidos", str(error))
            return                      # el diálogo sigue abierto para corregir

        radio = self._spin_radio.value()
        if self._tabs.currentIndex() == 0:
            # Región predefinida
            region: RegionPeru | None = self._combo_region.currentData()
            if region is None:
                return
            self._area = AreaDeEstudio(
                longitud=region.longitud,
                latitud=region.latitud,
                radio_metros=radio,
                nombre=region.nombre,
            )
        else:
            # Coordenadas manuales
            self._area = AreaDeEstudio(
                longitud=self._spin_lon.value(),
                latitud=self._spin_lat.value(),
                radio_metros=radio,
                nombre=self._edit_nombre.text().strip() or "Área personalizada",
            )

        self._fecha_inicio_t1, self._fecha_fin_t1 = periodo_t1
        self._fecha_inicio_t2, self._fecha_fin_t2 = periodo_t2
        self.accept()

    @property
    def area(self) -> AreaDeEstudio | None:
        return self._area

    @property
    def periodo_t1(self) -> tuple[str, str]:
        return (self._fecha_inicio_t1, self._fecha_fin_t1)

    @property
    def periodo_t2(self) -> tuple[str, str]:
        return (self._fecha_inicio_t2, self._fecha_fin_t2)

