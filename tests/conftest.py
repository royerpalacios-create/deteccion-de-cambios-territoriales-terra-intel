"""Configuración común de las pruebas."""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).parent))

import pytest  # noqa: E402


@pytest.fixture(scope="session")
def qapp():
    pytest.importorskip("PyQt6.QtWidgets")
    from PyQt6.QtWidgets import QApplication

    from app.ui import theme

    app = QApplication.instance() or QApplication([])
    theme.aplicar_tema(app, "dark")
    return app


@pytest.fixture
def sin_red_de_mapas(monkeypatch):
    """Las pruebas de interfaz nunca descargan mapas de internet: devuelven teselas generadas."""
    from servidor_teselas import png_tesela

    from app.services.teselas_service import ServicioTeselas

    monkeypatch.setattr(ServicioTeselas, "obtener_bytes", lambda self, fuente, z, x, y: png_tesela(z, x, y))
