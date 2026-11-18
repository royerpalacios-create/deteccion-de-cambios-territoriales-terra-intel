"""Barra superior tipo "Ribbon": menú desplegable + accesos rápidos.

Qt no trae un Ribbon nativo, así que se combinan, como en el software de
escritorio profesional:

1. La barra de menús clásica (``Archivo / Ver / Capas / Análisis /
   Herramientas / Ayuda``) con atajos de teclado.
2. Una barra de accesos rápidos (:class:`QuickAccessBar`) con botones grandes
   para las acciones más usadas (Detectar cambios, Guardar, Exportar, Tema).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from PyQt6.QtGui import QAction, QKeySequence
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QMainWindow, QMenu, QMenuBar

from app.ui.theme import boton


@dataclass
class ComandosRibbon:
    """Callbacks que la ventana principal conecta a cada acción del menú."""

    nuevo_proyecto: Callable[[], None]
    abrir_proyecto: Callable[[], None]
    guardar_proyecto: Callable[[], None]
    exportar_csv: Callable[[], None]
    exportar_json: Callable[[], None]
    exportar_excel: Callable[[], None]
    exportar_word: Callable[[], None]
    exportar_pdf: Callable[[], None]
    salir: Callable[[], None]
    alternar_tema: Callable[[], None]
    abrir_configuracion: Callable[[], None]
    detectar_cambios: Callable[[], None]
    cargar_desde_ee: Callable[[], None]
    rescan: Callable[[], None]
    alternar_vista: Callable[[], None]
    capturar_mapa: Callable[[], None]
    mostrar_acerca_de: Callable[[], None]


def _accion(menu: QMenu, texto: str, comando: Callable[[], None] | None,
            atajo: str | None = None) -> QAction:
    accion = QAction(texto, menu)
    if comando is None:
        accion.setEnabled(False)
    else:
        accion.triggered.connect(lambda _marcado=False: comando())
    if atajo:
        accion.setShortcut(QKeySequence(atajo))
    menu.addAction(accion)
    return accion


def construir_menu(ventana: QMainWindow, c: ComandosRibbon) -> QMenuBar:
    """Construye la barra de menús clásica en ``ventana``."""
    barra = ventana.menuBar()

    archivo = barra.addMenu("Archivo")
    _accion(archivo, "Nuevo proyecto", c.nuevo_proyecto, "Ctrl+N")
    _accion(archivo, "Abrir proyecto…", c.abrir_proyecto, "Ctrl+O")
    _accion(archivo, "Guardar proyecto", c.guardar_proyecto, "Ctrl+S")
    archivo.addSeparator()
    exportar = archivo.addMenu("Exportar reporte")
    _accion(exportar, "CSV", c.exportar_csv)
    _accion(exportar, "JSON", c.exportar_json)
    _accion(exportar, "Excel (.xlsx)", c.exportar_excel)
    _accion(exportar, "Word (.docx)", c.exportar_word)
    _accion(exportar, "PDF", c.exportar_pdf)
    archivo.addSeparator()
    _accion(archivo, "Salir", c.salir, "Ctrl+Q")

    ver = barra.addMenu("Ver")
    _accion(ver, "Alternar tema claro/oscuro", c.alternar_tema)
    _accion(ver, "Alternar vista overlay/swipe", c.alternar_vista)
    _accion(ver, "Capturar mapa como imagen…", c.capturar_mapa)

    capas = barra.addMenu("Capas")
    _accion(capas, "Ver panel de capas", None)

    analisis = barra.addMenu("Análisis")
    _accion(analisis, "Seleccionar área y cargar imágenes…", c.cargar_desde_ee, "Ctrl+E")
    _accion(analisis, "Detectar cambios (RS-1 → RS-2 → RS-3)", c.detectar_cambios, "Ctrl+D")
    _accion(analisis, "Re-scan área objetivo", c.rescan)

    herramientas = barra.addMenu("Herramientas")
    _accion(herramientas, "Configuración…", c.abrir_configuracion, "Ctrl+,")

    ayuda = barra.addMenu("Ayuda")
    _accion(ayuda, "Acerca de TERRA_INTEL", c.mostrar_acerca_de)
    return barra


class QuickAccessBar(QFrame):
    """Barra de accesos rápidos con los botones de acción más usados."""

    def __init__(self, c: ComandosRibbon, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("barraRapida")
        self.setFixedHeight(58)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 8, 14, 8)
        lay.setSpacing(6)

        # Botón principal — acción crítica con énfasis visual
        lay.addWidget(boton("Detectar Cambios", c.detectar_cambios, "peligro",
                            alto=40, px=13, negrita=True, ancho_min=190))

        sep1 = QFrame(); sep1.setObjectName("separadorVertical"); sep1.setFixedWidth(1)
        lay.addWidget(sep1)

        lay.addWidget(boton("Guardar", c.guardar_proyecto, "panel", alto=38, ancho_min=130))
        lay.addWidget(boton("PDF", c.exportar_pdf, "panel", alto=38, ancho_min=110))
        lay.addWidget(boton("Vista", c.alternar_vista, "panel", alto=38, ancho_min=110))
        lay.addWidget(boton("Capturar", c.capturar_mapa, "panel", alto=38, ancho_min=120))

        lay.addStretch(1)

        sep2 = QFrame(); sep2.setObjectName("separadorVertical"); sep2.setFixedWidth(1)
        lay.addWidget(sep2)

        lay.addWidget(boton("Tema", c.alternar_tema, "panel", alto=38, ancho_min=100))
        lay.addWidget(boton("Config", c.abrir_configuracion, "panel", alto=38, ancho_min=100))
