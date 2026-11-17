"""Panel de resultados: tarjetas con las categorías de cambio detectadas."""
from __future__ import annotations

from typing import Sequence

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QScrollArea, QVBoxLayout, QWidget

from app.models.proyecto import EstadisticaCambio
from app.ui.theme import etiqueta, rgba


class ResultsPanel(QScrollArea):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        contenido = QWidget()
        self._lay = QVBoxLayout(contenido)
        self._lay.setContentsMargins(8, 8, 8, 8)
        self._lay.setSpacing(8)
        self.setWidget(contenido)
        self.mostrar_mensaje_espera()

    def limpiar(self) -> None:
        while (item := self._lay.takeAt(0)) is not None:
            viejo = item.widget()
            if viejo is not None:
                viejo.hide()             # deleteLater() no actúa hasta el próximo ciclo de eventos
                viejo.setParent(None)
                viejo.deleteLater()

    def mostrar_mensaje_espera(self) -> None:
        self.limpiar()
        tarjeta = QFrame()
        tarjeta.setObjectName("tarjetaEspera")
        lay = QVBoxLayout(tarjeta)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(6)
        lbl_icono = etiqueta("🛰️", 28, centrado=True)
        lay.addWidget(lbl_icono)
        lay.addWidget(etiqueta("Esperando análisis", 13, True, tono="secundario", centrado=True))
        lay.addWidget(etiqueta(
            "Carga dos imágenes desde Earth Engine\n"
            "y presiona 'DETECTAR CAMBIOS'.\n\n"
            "Aquí aparecerá la leyenda de colores\n"
            "y el % de área por categoría.",
            10, tono="secundario", centrado=True,
        ))
        self._lay.addWidget(tarjeta)
        self._lay.addStretch(1)

    def mostrar_estadisticas(self, estadisticas: Sequence[EstadisticaCambio]) -> None:
        self.limpiar()
        for fila in estadisticas:
            self._lay.addWidget(self._crear_tarjeta(fila))
        self._lay.addStretch(1)

    @staticmethod
    def _crear_tarjeta(fila: EstadisticaCambio) -> QFrame:
        tarjeta = QFrame()
        tarjeta.setObjectName("tarjetaCambio")
        # Borde izquierdo de color de la categoría + fondo ligeramente elevado
        tarjeta.setStyleSheet(
            f"QFrame#tarjetaCambio {{"
            f"  border: 1px solid {rgba(fila.color, 0.15)};"
            f"  border-left: 3px solid {fila.color};"
            f"  border-radius: 10px;"
            f"}}"
        )
        lay = QVBoxLayout(tarjeta)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(3)

        encabezado = QHBoxLayout()
        insignia = etiqueta(fila.nivel, 9, True, mono=True)
        insignia.setProperty("rol", "insignia")
        insignia.setStyleSheet(
            f"background: {rgba(fila.color, 0.15)}; color: {fila.color};"
            f" border: 1px solid {rgba(fila.color, 0.35)}; border-radius: 4px;"
        )
        porcentaje = etiqueta(fila.porcentaje, 13, True, mono=True)
        porcentaje.setStyleSheet(f"color: {fila.color};")
        encabezado.addWidget(insignia)
        encabezado.addStretch(1)
        encabezado.addWidget(porcentaje)
        lay.addLayout(encabezado)

        lay.addWidget(etiqueta(fila.titulo, 13, True))
        lay.addWidget(etiqueta(fila.coords, 10, mono=True, tono="secundario"))
        detalle = etiqueta(fila.detalle, 10)
        detalle.setStyleSheet(f"color: {rgba(fila.color, 0.8)};")
        lay.addWidget(detalle)
        return tarjeta
