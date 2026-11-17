"""Ventana de configuración: tema, mapa base, proyecto EE, nubosidad.

Se usa con ``exec()``: devuelve ``Accepted`` si el usuario guardó los cambios
(ya persistidos en :class:`~app.core.config.GestorConfiguracion`).
"""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QCheckBox, QComboBox, QDialog, QHBoxLayout, QLineEdit, QSlider, QVBoxLayout

from app.core.config import GestorConfiguracion
from app.ui.theme import boton, etiqueta, fuente


class SettingsDialog(QDialog):
    def __init__(self, parent, gestor_config: GestorConfiguracion) -> None:
        super().__init__(parent)
        self.setWindowTitle("Configuración")
        self.setFixedSize(420, 480)
        self.setModal(True)
        self._gestor = gestor_config
        config = gestor_config.config

        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 20, 20, 20)
        lay.setSpacing(2)
        lay.addWidget(etiqueta("Configuración", 20, True))
        lay.addSpacing(14)

        lay.addWidget(etiqueta("Tema", tono="secundario"))
        self.combo_tema = self._combo(["dark", "light"], config.tema)
        lay.addWidget(self.combo_tema)
        lay.addSpacing(10)

        lay.addWidget(etiqueta("Mapa base por defecto", tono="secundario"))
        self.combo_mapa_base = self._combo(
            ["sentinel2", "osm", "google_satellite", "hybrid", "terrain"], config.mapa_base_defecto
        )
        lay.addWidget(self.combo_mapa_base)
        lay.addSpacing(10)

        lay.addWidget(etiqueta("ID de proyecto de Google Earth Engine", tono="secundario"))
        self.entrada_proyecto_ee = QLineEdit(config.proyecto_earth_engine)
        self.entrada_proyecto_ee.setFont(fuente(12))
        lay.addWidget(self.entrada_proyecto_ee)
        lay.addSpacing(10)

        self._etiqueta_nubes = etiqueta(f"Umbral de nubes: {config.umbral_nubes}%", tono="secundario")
        lay.addWidget(self._etiqueta_nubes)
        self.slider_nubes = QSlider(Qt.Orientation.Horizontal)
        self.slider_nubes.setRange(0, 100)
        self.slider_nubes.setValue(int(config.umbral_nubes))
        self.slider_nubes.valueChanged.connect(self._actualizar_etiqueta_nubes)
        lay.addWidget(self.slider_nubes)
        lay.addSpacing(10)

        self.chk_autoguardado = QCheckBox("Autoguardar proyecto al detectar cambios")
        self.chk_autoguardado.setFont(fuente(12))
        self.chk_autoguardado.setChecked(bool(config.autoguardado))
        lay.addWidget(self.chk_autoguardado)

        lay.addStretch(1)
        botones = QHBoxLayout()
        botones.setSpacing(12)
        botones.addWidget(boton("Cancelar", self.reject), 1)
        guardar = boton("Guardar", self._guardar, "acento")
        guardar.setDefault(True)
        botones.addWidget(guardar, 1)
        lay.addLayout(botones)

    @staticmethod
    def _combo(valores: list[str], actual: str) -> QComboBox:
        combo = QComboBox()
        combo.setFont(fuente(12))
        combo.addItems(valores)
        combo.setCurrentText(actual)
        return combo

    def _actualizar_etiqueta_nubes(self, valor: int) -> None:
        self._etiqueta_nubes.setText(f"Umbral de nubes: {valor}%")

    def _guardar(self) -> None:
        self._gestor.actualizar(
            tema=self.combo_tema.currentText(),
            mapa_base_defecto=self.combo_mapa_base.currentText(),
            proyecto_earth_engine=self.entrada_proyecto_ee.text().strip() or "dctiis",
            umbral_nubes=self.slider_nubes.value(),
            autoguardado=self.chk_autoguardado.isChecked(),
        )
        self.accept()
