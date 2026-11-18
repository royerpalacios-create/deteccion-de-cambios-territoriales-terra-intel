"""Panel de resultados: tarjetas con las categorías de cambio detectadas."""
from __future__ import annotations

from typing import Sequence

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.models.proyecto import EstadisticaCambio, ResumenTransicion
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
        lbl_icono = etiqueta("TERRA INTEL", 28, centrado=True)
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

    def mostrar_estadisticas(
        self,
        estadisticas: Sequence[EstadisticaCambio],
        resumen_transicion: ResumenTransicion | None = None,
    ) -> None:
        self.limpiar()
        if resumen_transicion is not None:
            self._lay.addWidget(etiqueta("Matriz de transición T1 → T2", 13, True))
            if resumen_transicion.total_pixeles is None:
                self._lay.addWidget(etiqueta(
                    "Sin datos válidos; las celdas muestran no-data, no ceros.",
                    10,
                    tono="secundario",
                ))
            self._lay.addWidget(self._crear_matriz(resumen_transicion))
            self._lay.addWidget(etiqueta("Balance por cobertura (ha)", 13, True))
            self._lay.addWidget(self._crear_balance(resumen_transicion))
        for fila in estadisticas:
            self._lay.addWidget(self._crear_tarjeta(fila))
        self._lay.addStretch(1)

    @staticmethod
    def _crear_matriz(resumen: ResumenTransicion) -> QTableWidget:
        tabla = QTableWidget(len(resumen.clases), len(resumen.clases))
        tabla.setObjectName("matrizTransicion")
        tabla.setHorizontalHeaderLabels(resumen.clases)
        tabla.setVerticalHeaderLabels(resumen.clases)
        tabla.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        tabla.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        tabla.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        tabla.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        tabla.setMinimumHeight(190)
        tabla.setMaximumHeight(230)
        for fila, valores in enumerate(resumen.matriz):
            for columna, celda in enumerate(valores):
                texto = "—" if celda is None else (
                    f"{celda.area_ha:.2f} ha ({celda.porcentaje:.1f}%)\n"
                    f"{celda.pixeles} px"
                )
                item = QTableWidgetItem(texto)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if celda is None:
                    item.setToolTip("No hay datos válidos para esta matriz")
                else:
                    item.setToolTip(f"{celda.porcentaje:.2f}% del área válida")
                tabla.setItem(fila, columna, item)
        return tabla

    @staticmethod
    def _crear_balance(resumen: ResumenTransicion) -> QTableWidget:
        encabezados = (
            "Cobertura", "T1 (ha)", "T2 (ha)", "Entradas (ha)",
            "Salidas (ha)", "Neto (ha)", "Persistencia (ha / %)",
        )
        tabla = QTableWidget(len(resumen.balance), len(encabezados))
        tabla.setObjectName("balanceTransicion")
        tabla.setHorizontalHeaderLabels(encabezados)
        tabla.verticalHeader().hide()
        tabla.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        tabla.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        tabla.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        tabla.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        tabla.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        tabla.setMinimumHeight(150)
        tabla.setMaximumHeight(190)
        for fila, balance in enumerate(resumen.balance):
            persistencia = "—"
            if balance.persistencia_ha is not None:
                porcentaje = (
                    "—" if balance.persistencia_pct is None
                    else f"{balance.persistencia_pct:.1f}%"
                )
                persistencia = f"{balance.persistencia_ha:.2f} / {porcentaje}"
            valores = (
                balance.clase,
                balance.area_t1_ha,
                balance.area_t2_ha,
                balance.entradas_ha,
                balance.salidas_ha,
                balance.neto_ha,
                persistencia,
            )
            for columna, valor in enumerate(valores):
                if columna == 0 or isinstance(valor, str):
                    texto = str(valor)
                else:
                    texto = "—" if valor is None else f"{valor:.2f}"
                item = QTableWidgetItem(texto)
                if columna:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                tabla.setItem(fila, columna, item)
        return tabla

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
