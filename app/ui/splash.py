"""Pantalla de bienvenida (splash screen) mostrada durante el arranque.

Siempre usa la paleta oscura, igual que la versión original, sin importar el
tema elegido por el usuario.
"""
from __future__ import annotations

from typing import Callable

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import QFrame, QProgressBar, QVBoxLayout

from app.ui import theme
from app.ui.theme import etiqueta

_PASOS = [
    (20, "Cargando configuración…"),
    (50, "Conectando con Google Earth Engine…"),
    (78, "Preparando interfaz…"),
    (100, "Listo."),
]

_SPLASH_QSS = """
QFrame#splash {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #080d14, stop:1 #0d1a28);
    border: 1px solid #1e2d42;
    border-radius: 16px;
}
QProgressBar {
    background: #1e2d42;
    border: none;
    border-radius: 2px;
    min-height: 4px;
    max-height: 4px;
}
QProgressBar::chunk {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #00c488, stop:1 #00e5a0);
    border-radius: 2px;
}
"""


class SplashScreen(QFrame):
    """Ventana breve sin bordes mostrada mientras arranca la aplicación."""

    def __init__(self, on_listo: Callable[[], None]) -> None:
        super().__init__(None, Qt.WindowType.SplashScreen | Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowStaysOnTopHint)
        self._on_listo = on_listo
        self.setObjectName("splash")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)   # sin esquinas cuadradas detrás del borde redondeado
        self.setStyleSheet(theme.construir_qss(theme.PALETA_OSCURA) + _SPLASH_QSS)
        self.setFixedSize(500, 300)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(40, 36, 40, 36)
        lay.addStretch(1)

        # Icono + título
        lbl_icon = etiqueta("TERRA INTEL", 52, centrado=True)
        lay.addWidget(lbl_icon)

        lbl_titulo = etiqueta("TERRA_INTEL", 30, True, centrado=True)
        lbl_titulo.setStyleSheet("color: #c8dff7; letter-spacing: 4px;")
        lay.addWidget(lbl_titulo)

        lbl_sub = etiqueta(
            "Detección de Cambios Territoriales con Imágenes Satelitales",
            11, tono="secundario", centrado=True, wrap=True,
        )
        lay.addWidget(lbl_sub)

        lay.addSpacing(24)

        self._barra = QProgressBar()
        self._barra.setRange(0, 100)
        self._barra.setTextVisible(False)
        lay.addWidget(self._barra)

        self._estado = etiqueta("Iniciando…", 10, mono=True, tono="secundario", centrado=True)
        lay.addWidget(self._estado)

        lay.addStretch(1)

        # Línea inferior de versión
        lbl_ver = etiqueta("v2.0 · Google Earth Engine · PyQt6", 9, mono=True, tono="secundario", centrado=True)
        lay.addWidget(lbl_ver)

        pantalla = QGuiApplication.primaryScreen().availableGeometry()
        self.move(pantalla.center() - self.rect().center())
        QTimer.singleShot(80, lambda: self._avanzar(0))

    def _avanzar(self, paso: int) -> None:
        if paso < len(_PASOS):
            progreso, mensaje = _PASOS[paso]
            self._barra.setValue(progreso)
            self._estado.setText(mensaje)
            QTimer.singleShot(300, lambda: self._avanzar(paso + 1))
        else:
            QTimer.singleShot(220, self._cerrar)

    def _cerrar(self) -> None:
        self._on_listo()
        self.close()
