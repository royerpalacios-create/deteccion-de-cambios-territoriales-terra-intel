"""Punto de entrada de la aplicación TERRA_INTEL (PyQt6).

Flujo de arranque:

1. Configura logging (``logs/terra_intel.log``).
2. Carga la configuración persistida del usuario (``config/settings.json``).
3. Crea la ``QApplication`` y aplica el tema guardado.
4. Muestra el splash screen y, al terminar, la ventana principal.
"""
from __future__ import annotations

import sys

from app.core.config import GestorConfiguracion
from app.core.logging_config import configurar_logging, obtener_logger

logger = obtener_logger("main")


def _instalar_manejador_de_errores() -> None:
    """Evita que una excepción no controlada cierre la aplicación.

    A diferencia de Tkinter, PyQt6 termina el proceso si una excepción se
    escapa de un slot. Aquí se registra en el log y se avisa al usuario.
    """
    def manejar(tipo, valor, traza) -> None:
        if issubclass(tipo, KeyboardInterrupt):
            sys.__excepthook__(tipo, valor, traza)
            return
        logger.error("Error no controlado", exc_info=(tipo, valor, traza))
        try:
            from PyQt6.QtWidgets import QApplication, QMessageBox

            if QApplication.instance() is not None:
                QMessageBox.critical(
                    None, "Error inesperado",
                    f"Ocurrió un error inesperado:\n{valor}\n\nEl detalle quedó en logs/terra_intel.log.",
                )
        except Exception:
            pass

    sys.excepthook = manejar


def run() -> None:
    configurar_logging()
    logger.info("Iniciando TERRA_INTEL…")

    gestor_config = GestorConfiguracion()

    from PyQt6.QtWidgets import QApplication

    from app.ui import theme
    from app.ui.main_window import MainWindow
    from app.ui.splash import SplashScreen

    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("TERRA_INTEL")
    _instalar_manejador_de_errores()
    theme.aplicar_tema(app, gestor_config.config.tema)

    ventana = MainWindow(gestor_config)           # se muestra recién cuando el splash termina
    splash = SplashScreen(on_listo=ventana.show)
    splash.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    run()
