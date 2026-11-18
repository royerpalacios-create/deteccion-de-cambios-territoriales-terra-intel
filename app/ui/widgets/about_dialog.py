"""Diálogo "Acerca de"."""
from __future__ import annotations

from PyQt6.QtWidgets import QDialog, QVBoxLayout

from app.ui.theme import boton, etiqueta

VERSION = "2.0.0"


class AboutDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Acerca de TERRA_INTEL")
        self.setFixedSize(420, 320)
        self.setModal(True)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 24, 24, 24)
        lay.addWidget(etiqueta("TERRA INTEL", 40, centrado=True))
        lay.addWidget(etiqueta("TERRA_INTEL", 22, True, centrado=True))
        lay.addWidget(etiqueta(f"Versión {VERSION}", 11, mono=True, tono="secundario", centrado=True))
        lay.addSpacing(10)
        lay.addWidget(etiqueta(
            "Sistema de Detección de Cambios Territoriales con\n"
            "Imágenes Satelitales (Sentinel-2 / Google Earth Engine).\n\n"
            "Proyecto académico — Programación Orientada a Objetos II\n"
            "Escuela Profesional de Ingeniería de Sistemas, UNA-PUNO.",
            12, tono="secundario", centrado=True,
        ))
        lay.addStretch(1)
        cerrar = boton("Cerrar", self.accept, "acento", alto=36)
        cerrar.setDefault(True)
        lay.addWidget(cerrar)
