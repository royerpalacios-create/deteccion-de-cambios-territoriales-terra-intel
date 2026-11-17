"""Panel de capas: activar/desactivar T1, T2 y la capa de cambios, y opacidad.

Emite :attr:`cambiado` cada vez que el usuario toca un control; la ventana
principal responde redibujando el :class:`~app.ui.widgets.map_canvas.MapCanvas`.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QCheckBox, QSlider, QVBoxLayout, QWidget

from app.ui.theme import etiqueta, fuente


class LayerPanel(QWidget):
    cambiado = pyqtSignal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 6, 20, 10)
        lay.setSpacing(6)

        lbl_capas = etiqueta("CAPAS VISIBLES", 10, True, mono=True, tono="acento")
        lbl_capas.setStyleSheet("letter-spacing: 2px;")
        lay.addWidget(lbl_capas)

        self.chk_t1 = self._checkbox("Época A (T1 — Antes)", lay)
        self.chk_t2 = self._checkbox("Época B (T2 — Después)", lay)
        self.chk_cambios = self._checkbox("Capa de cambios detectados", lay)

        lay.addSpacing(6)
        lbl_op = etiqueta("Opacidad de cambios", 10, tono="secundario")
        lbl_op.setStyleSheet("letter-spacing: 1px;")
        lay.addWidget(lbl_op)
        self.slider_opacidad = QSlider(Qt.Orientation.Horizontal)
        self.slider_opacidad.setRange(0, 100)
        self.slider_opacidad.setValue(100)
        self.slider_opacidad.valueChanged.connect(lambda _valor: self.cambiado.emit())
        lay.addWidget(self.slider_opacidad)

    def _checkbox(self, texto: str, lay: QVBoxLayout) -> QCheckBox:
        chk = QCheckBox(texto)
        chk.setFont(fuente(12))
        chk.setChecked(True)
        chk.toggled.connect(lambda _marcado: self.cambiado.emit())
        lay.addWidget(chk)
        return chk

    @property
    def opacidad_cambios(self) -> float:
        return self.slider_opacidad.value() / 100.0

    @property
    def mostrar_t1(self) -> bool:
        return self.chk_t1.isChecked()

    @property
    def mostrar_t2(self) -> bool:
        return self.chk_t2.isChecked()

    @property
    def mostrar_cambios(self) -> bool:
        return self.chk_cambios.isChecked()
