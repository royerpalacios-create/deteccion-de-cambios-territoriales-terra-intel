#!/usr/bin/env python3
"""Punto de entrada raíz de TERRA_INTEL.

Uso:

    pip install -r requirements.txt
    python main.py

También soporta un modo de consola sin interfaz gráfica, que ejecuta el
pipeline completo (RS-1 adquisición -> RS-2 clasificación -> RS-3 detección
de cambios) sobre el área de estudio por defecto (Puno) y guarda un mapa
interactivo en ``exports/mapa_cambios.html``:

    python main.py --console
"""
from __future__ import annotations

import sys


def main() -> None:
    if "--console" in sys.argv:
        from scripts.pipeline_consola import ejecutar_pipeline_consola

        ejecutar_pipeline_consola()
        return

    from app.main import run

    run()


if __name__ == "__main__":
    main()
