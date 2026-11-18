"""Barra de estado inferior: conexión EE, coordenadas, zoom y mensajes.

Zonas separadas (mensaje / coordenadas / escala / zoom / conexión) como en
QGIS o ArcGIS Pro, así un mensaje temporal no borra el estado de conexión.
Los colores se eligen por *tono* (``exito``, ``alerta``, ``advertencia``) y
los resuelve la hoja de estilos, por eso siguen al tema claro/oscuro.
"""
from __future__ import annotations

from PyQt6.QtWidgets import QFrame, QLabel, QStatusBar

from app.ui.theme import cambiar_tono, etiqueta


class StatusBar(QStatusBar):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setSizeGripEnabled(False)
        self.setFixedHeight(26)

        self.mensaje = self._zona("Sistema listo")
        self.coordenadas = self._zona("Lon: —  ·  Lat: —")
        self.escala = self._zona("1:50 000")
        self.zoom = self._zona("Zoom: 11")
        self.conexion = self._zona("Earth Engine: verificando…", tono="advertencia")

        self.addWidget(self.mensaje, 1)
        for zona in (self.coordenadas, self.escala, self.zoom, self.conexion):
            sep = self._separador()
            self.addPermanentWidget(sep)
            self.addPermanentWidget(zona)

    @staticmethod
    def _zona(texto: str, tono: str = "secundario") -> QLabel:
        zona = etiqueta(texto, 10, mono=True, tono=tono)
        zona.setContentsMargins(8, 0, 8, 0)
        return zona

    @staticmethod
    def _separador() -> QFrame:
        sep = QFrame()
        sep.setObjectName("separadorVertical")
        sep.setFixedWidth(1)
        sep.setFixedHeight(14)
        return sep

    def set_mensaje(self, texto: str, tono: str | None = None) -> None:
        self.mensaje.setText(texto)
        cambiar_tono(self.mensaje, tono or "secundario")

    def set_conexion(self, conectado: bool) -> None:
        if conectado:
            self.conexion.setText("Earth Engine: Conectado")
            cambiar_tono(self.conexion, "exito")
        else:
            self.conexion.setText("Earth Engine: No conectado")
            cambiar_tono(self.conexion, "alerta")

    def set_coordenadas(self, lon: float, lat: float) -> None:
        self.coordenadas.setText(f"Lon: {lon:.4f}  ·  Lat: {lat:.4f}")

    def set_zoom(self, nivel: int) -> None:
        self.zoom.setText(f"Zoom: {nivel}")
