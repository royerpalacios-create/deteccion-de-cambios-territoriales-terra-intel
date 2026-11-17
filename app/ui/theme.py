"""Paleta de colores, fuentes y hoja de estilos (QSS) de TERRA_INTEL.

Los colores viven en dos paletas (oscura y clara). :func:`construir_qss` las
convierte en una hoja de estilos Qt que se aplica a toda la aplicación, de
modo que el cambio de tema se aplica **en vivo** (en la versión CustomTkinter
había que reiniciar la app).

Convenciones usadas por los widgets:

- ``variante`` (propiedad de ``QPushButton``): ``panel``, ``peligro``,
  ``verde`` o ``acento``. Sin propiedad = botón de superficie por defecto.
- ``tono`` (propiedad de ``QLabel``): ``secundario``, ``exito``, ``alerta``,
  ``advertencia``, ``info`` o ``acento``. Sin propiedad = texto primario.

Las fuentes se fijan por código (:func:`fuente`) y los colores por QSS.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from string import Template
from typing import Callable

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont, QPalette
from PyQt6.QtWidgets import QApplication, QFrame, QLabel, QPushButton, QWidget

RAIZ_PROYECTO = Path(__file__).resolve().parent.parent.parent
DIR_ICONOS = RAIZ_PROYECTO / "assets" / "icons"


@dataclass(frozen=True)
class Paleta:
    fondo_principal: str
    fondo_panel: str
    fondo_superficie: str
    borde: str
    texto_primario: str
    texto_secundario: str
    acento: str
    acento_hover: str
    alerta: str
    advertencia: str
    exito: str
    info: str


PALETA_OSCURA = Paleta(
    fondo_principal="#080d14",
    fondo_panel="#0d1520",
    fondo_superficie="#131c2b",
    borde="#1e2d42",
    texto_primario="#c8dff7",
    texto_secundario="#5a7494",
    acento="#00e5a0",
    acento_hover="#00c488",
    alerta="#ff5252",
    advertencia="#ffab40",
    exito="#00e5a0",
    info="#40c4ff",
)

PALETA_CLARA = Paleta(
    fondo_principal="#f0f4f8",
    fondo_panel="#ffffff",
    fondo_superficie="#e8edf5",
    borde="#cdd6e4",
    texto_primario="#111827",
    texto_secundario="#4b5a6e",
    acento="#00a876",
    acento_hover="#00875e",
    alerta="#e03434",
    advertencia="#d97706",
    exito="#00a876",
    info="#0369a1",
)


def obtener_paleta(nombre_tema: str) -> Paleta:
    return PALETA_CLARA if nombre_tema == "light" else PALETA_OSCURA


_paleta_activa: Paleta = PALETA_OSCURA


def paleta_activa() -> Paleta:
    """Paleta aplicada por la última llamada a :func:`aplicar_tema`."""
    return _paleta_activa


# ------------------------------------------------------------------ fuentes
FAMILIAS_UI = ["Segoe UI", "Inter"]
FAMILIAS_MONO = ["JetBrains Mono", "Consolas"]


def fuente(px: int = 12, negrita: bool = False, mono: bool = False) -> QFont:
    """Fuente de la app (tamaño en píxeles, como en CustomTkinter)."""
    f = QFont()
    f.setFamilies(FAMILIAS_MONO if mono else FAMILIAS_UI)
    f.setStyleHint(QFont.StyleHint.Monospace if mono else QFont.StyleHint.SansSerif)
    f.setPixelSize(px)
    f.setBold(negrita)
    return f


# --------------------------------------------------------------------- QSS
_PLANTILLA_QSS = Template("""
/* ─── Base ─── */
QMainWindow, QDialog  { background: $fondo_principal; }
QWidget               { color: $texto_primario; }   /* sin regla de fuente aquí: pisaría las monoespaciadas */
QToolTip {
    background: $fondo_panel;
    color: $texto_primario;
    border: 1px solid $acento;
    border-radius: 6px;
    padding: 6px 10px;
}

/* ─── Paneles estructurales ─── */
QFrame#sidebar {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 $fondo_panel, stop:1 $fondo_principal);
    border-right: 1px solid $borde;
}
QFrame#barraRapida {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 $fondo_panel, stop:1 $fondo_principal);
    border-bottom: 1px solid $borde;
}
QFrame#areaPrincipal { background: $fondo_principal; }
QFrame#splash        { background: $fondo_principal; border: 1px solid $borde; }
QFrame#linea         { background: $borde; border: none; }
QFrame#separadorVertical { background: $borde; border: none; }
QFrame#tarjetaCambio {
    background: $fondo_panel;   /* el color del borde (por categoría) se fija en la tarjeta */
}
QFrame#tarjetaEspera {
    background: $fondo_superficie;
    border: 1px solid $borde;
    border-radius: 14px;
}

/* ─── Etiquetas ─── */
QLabel                        { background: transparent; }
QLabel[tono="secundario"]     { color: $texto_secundario; }
QLabel[tono="acento"]         { color: $acento; }
QLabel[tono="exito"]          { color: $exito; }
QLabel[tono="alerta"]         { color: $alerta; }
QLabel[tono="advertencia"]    { color: $advertencia; }
QLabel[tono="info"]           { color: $info; }
QLabel[rol="insignia"]        { color: #ffffff; border-radius: 5px; padding: 2px 9px; }

/* ─── Botones base ─── */
QPushButton {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 $fondo_superficie, stop:1 $fondo_panel);
    color: $texto_primario;
    border: 1px solid $borde;
    border-radius: 8px;
    padding: 0 16px;
}
QPushButton:hover {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 $borde, stop:1 $fondo_superficie);
    border-color: $texto_secundario;
}
QPushButton:pressed { background: $fondo_panel; border-color: $acento; }

/* ─── Variante panel ─── */
QPushButton[variante="panel"] {
    background: $fondo_panel;
    border: 1px solid $borde;
}
QPushButton[variante="panel"]:hover { background: $fondo_superficie; border-color: $texto_secundario; }

/* ─── Variante peligro (alerta) ─── */
QPushButton[variante="peligro"] {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 $alerta, stop:1 #cc3030);
    color: #ffffff;
    border: 1px solid #ff7070;
    font-weight: bold;
}
QPushButton[variante="peligro"]:hover {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #ff7070, stop:1 $alerta);
    border-color: #ffffff;
}
QPushButton[variante="peligro"]:pressed { background: #cc3030; }

/* ─── Variante verde ─── */
QPushButton[variante="verde"] {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #1e4a38, stop:1 #122e22);
    color: $texto_verde;   /* el fondo es verde oscuro en ambos temas: el texto debe ser claro */
    border: 1px solid #2a5a42;
}
QPushButton[variante="verde"]:hover {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #2a5a42, stop:1 #1e4a38);
    border-color: $acento;
    color: #ffffff;
}

/* ─── Variante acento (primario) ─── */
QPushButton[variante="acento"] {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 $acento, stop:1 $acento_hover);
    color: $fondo_principal;
    border: 1px solid $acento;
    font-weight: bold;
}
QPushButton[variante="acento"]:hover {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #22ffbe, stop:1 $acento);
    border-color: #ffffff;
}
QPushButton[variante="acento"]:pressed { background: $acento_hover; }

/* ─── Deshabilitados ─── */
QPushButton:disabled,
QPushButton[variante]:disabled { background: $fondo_panel; color: $texto_secundario; border-color: $borde; }

/* ─── Inputs ─── */
QLineEdit, QComboBox {
    background: $fondo_superficie;
    border: 1px solid $borde;
    border-radius: 7px;
    padding: 6px 12px;
    selection-background-color: $acento;
    selection-color: $fondo_principal;
}
QLineEdit:focus, QComboBox:focus { border: 1px solid $acento; }
QComboBox::drop-down { border: none; width: 22px; }
QComboBox QAbstractItemView {
    background: $fondo_panel;
    border: 1px solid $borde;
    border-radius: 6px;
    outline: 0;
    selection-background-color: $acento;
    selection-color: $fondo_principal;
}

/* ─── CheckBox ─── */
QCheckBox                  { spacing: 8px; background: transparent; }
QCheckBox::indicator       { width: 17px; height: 17px; border: 2px solid $texto_secundario; border-radius: 5px; background: transparent; }
QCheckBox::indicator:hover { border-color: $acento; background: rgba(0,229,160,0.08); }
QCheckBox::indicator:checked { background: $acento; border-color: $acento; image: url("$icono_check"); }

/* ─── Slider ─── */
QSlider::groove:horizontal { height: 5px; background: $borde; border-radius: 3px; }
QSlider::sub-page:horizontal {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 $acento_hover, stop:1 $acento);
    border-radius: 3px;
}
QSlider::handle:horizontal {
    background: $acento;
    width: 16px;
    height: 16px;
    margin: -6px 0;
    border-radius: 8px;
    border: 2px solid $fondo_principal;
}
QSlider::handle:horizontal:hover { background: #22ffbe; }

/* ─── ProgressBar ─── */
QProgressBar {
    background: $borde;
    border: none;
    border-radius: 3px;
    min-height: 5px;
    max-height: 5px;
}
QProgressBar::chunk {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 $acento_hover, stop:1 $acento);
    border-radius: 3px;
}

/* ─── Menú ─── */
QMenuBar { background: $fondo_panel; border-bottom: 1px solid $borde; }
QMenuBar::item { padding: 7px 14px; background: transparent; border-radius: 4px; }
QMenuBar::item:selected { background: $fondo_superficie; color: $acento; }
QMenu {
    background: $fondo_panel;
    border: 1px solid $borde;
    border-radius: 8px;
    padding: 5px;
}
QMenu::item             { padding: 7px 30px 7px 20px; border-radius: 5px; }
QMenu::item:selected    { background: $acento; color: $fondo_principal; }
QMenu::item:disabled    { color: $texto_secundario; }
QMenu::separator        { height: 1px; background: $borde; margin: 4px 10px; }

/* ─── Status bar ─── */
QStatusBar              { background: $fondo_panel; border-top: 1px solid $borde; }
QStatusBar::item        { border: none; }

/* ─── Scroll ─── */
QScrollArea { border: none; background: transparent; }
QScrollArea > QWidget > QWidget { background: transparent; }
QScrollBar:vertical          { background: transparent; width: 8px; margin: 0; }
QScrollBar::handle:vertical  { background: $borde; border-radius: 4px; min-height: 24px; }
QScrollBar::handle:vertical:hover { background: $texto_secundario; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; }

/* ─── Diálogos ─── */
QMessageBox QPushButton { min-width: 90px; min-height: 30px; }
""")


def construir_qss(paleta: Paleta) -> str:
    """Genera la hoja de estilos Qt completa para ``paleta``."""
    oscuro = paleta is PALETA_OSCURA or paleta == PALETA_OSCURA
    icono = DIR_ICONOS / ("check_dark.svg" if oscuro else "check_light.svg")
    texto_verde = paleta.acento if oscuro else "#8af5cf"
    return _PLANTILLA_QSS.substitute(asdict(paleta), icono_check=icono.as_posix(), texto_verde=texto_verde)


def _paleta_qt(p: Paleta) -> QPalette:
    """QPalette equivalente, para widgets que el QSS no cubre (diálogos nativos de Qt)."""
    q = QPalette()
    roles = {
        QPalette.ColorRole.Window: p.fondo_principal, QPalette.ColorRole.WindowText: p.texto_primario,
        QPalette.ColorRole.Base: p.fondo_superficie, QPalette.ColorRole.AlternateBase: p.fondo_panel,
        QPalette.ColorRole.Text: p.texto_primario, QPalette.ColorRole.Button: p.fondo_superficie,
        QPalette.ColorRole.ButtonText: p.texto_primario, QPalette.ColorRole.ToolTipBase: p.fondo_panel,
        QPalette.ColorRole.ToolTipText: p.texto_primario, QPalette.ColorRole.Highlight: p.acento,
        QPalette.ColorRole.HighlightedText: p.fondo_principal, QPalette.ColorRole.PlaceholderText: p.texto_secundario,
        QPalette.ColorRole.Link: p.info,
    }
    for rol, color in roles.items():
        q.setColor(rol, QColor(color))
    for rol in (QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText, QPalette.ColorRole.WindowText):
        q.setColor(QPalette.ColorGroup.Disabled, rol, QColor(p.texto_secundario))
    return q


def aplicar_tema(app: QApplication, nombre_tema: str) -> Paleta:
    """Aplica el tema ``"dark"`` / ``"light"`` a toda la aplicación (en vivo)."""
    global _paleta_activa
    paleta = _paleta_activa = obtener_paleta(nombre_tema)
    app.setStyle("Fusion")
    app.setFont(fuente(12))
    app.setPalette(_paleta_qt(paleta))
    app.setStyleSheet(construir_qss(paleta))
    return paleta


# ---------------------------------------------------------- helpers de widgets
def rgba(color_hex: str, alfa: float) -> str:
    """Color CSS ``rgba()`` a partir de ``#RRGGBB`` y un alfa 0-1.

    Qt interpreta ``#RRGGBBAA`` como ``#AARRGGBB`` (alfa al inicio), así que
    añadir un sufijo al hexadecimal cambia el color en vez de hacerlo translúcido.
    """
    h = color_hex.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r}, {g}, {b}, {alfa:g})"


def repulir(widget: QWidget) -> None:
    """Fuerza a Qt a reevaluar el QSS tras cambiar una propiedad dinámica."""
    estilo = widget.style()
    estilo.unpolish(widget)
    estilo.polish(widget)
    widget.update()


def cambiar_tono(etiqueta_: QLabel, tono: str | None) -> None:
    etiqueta_.setProperty("tono", tono)
    repulir(etiqueta_)


def etiqueta(texto: str = "", px: int = 12, negrita: bool = False, mono: bool = False,
             tono: str | None = None, centrado: bool = False, wrap: bool = False) -> QLabel:
    lbl = QLabel(texto)
    lbl.setFont(fuente(px, negrita, mono))
    if tono:
        lbl.setProperty("tono", tono)
    if centrado:
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    lbl.setWordWrap(wrap)
    return lbl


def boton(texto: str, comando: Callable[[], None], variante: str | None = None, alto: int = 36,
          px: int = 12, negrita: bool = False, mono: bool = False, ancho_min: int = 0) -> QPushButton:
    b = QPushButton(texto)
    b.setFont(fuente(px, negrita, mono))
    b.setFixedHeight(alto)
    if ancho_min:
        b.setMinimumWidth(ancho_min)
    if variante:
        b.setProperty("variante", variante)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    b.clicked.connect(lambda _marcado=False: comando())
    return b


def linea_horizontal() -> QFrame:
    f = QFrame()
    f.setObjectName("linea")
    f.setFixedHeight(1)
    return f
