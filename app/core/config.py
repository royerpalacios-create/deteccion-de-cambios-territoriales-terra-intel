"""Configuración persistente de la aplicación (preferencias del usuario).

Sustituye a los valores fijos ("dark", "dark-blue", proyecto EE hardcodeado
como ``"dctiis"``) que estaban repetidos dentro de ``interfaz.py`` y
``Proyecto.py``. Ahora viven en un único archivo JSON editable,
``config/settings.json``, que se crea automáticamente a partir de
``config/default_settings.json`` la primera vez que se ejecuta la app.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

RAIZ_PROYECTO = Path(__file__).resolve().parent.parent.parent
DIR_CONFIG = RAIZ_PROYECTO / "config"
ARCHIVO_CONFIG_DEFECTO = DIR_CONFIG / "default_settings.json"
ARCHIVO_CONFIG_USUARIO = DIR_CONFIG / "settings.json"

MAX_PROYECTOS_RECIENTES = 8


@dataclass
class AppConfig:
    """Preferencias de usuario persistidas entre sesiones."""

    tema: str = "dark"                      # "dark" | "light"
    color_acento: str = "dark-blue"
    mapa_base_defecto: str = "sentinel2"
    idioma: str = "es"
    proyecto_earth_engine: str = "dctiis"
    umbral_nubes: int = 20
    radio_area_estudio_m: int = 10_000   # = RADIO_BUFFER_METROS
    autoguardado: bool = True
    proyectos_recientes: list[str] = field(default_factory=list)

    def a_diccionario(self) -> dict[str, Any]:
        return asdict(self)

    def agregar_proyecto_reciente(self, ruta: str) -> None:
        """Inserta ``ruta`` al inicio de la lista de recientes (sin duplicar)."""
        recientes = [r for r in self.proyectos_recientes if r != ruta]
        recientes.insert(0, ruta)
        self.proyectos_recientes = recientes[:MAX_PROYECTOS_RECIENTES]


class GestorConfiguracion:
    """Carga y guarda :class:`AppConfig` en ``config/settings.json``."""

    def __init__(self, ruta_usuario: Path = ARCHIVO_CONFIG_USUARIO,
                 ruta_defecto: Path = ARCHIVO_CONFIG_DEFECTO) -> None:
        self._ruta_usuario = ruta_usuario
        self._ruta_defecto = ruta_defecto
        self.config = self._cargar()

    def _cargar(self) -> AppConfig:
        ruta = self._ruta_usuario if self._ruta_usuario.exists() else self._ruta_defecto
        try:
            datos = json.loads(ruta.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            datos = {}
        campos_validos = AppConfig.__dataclass_fields__.keys()
        datos_filtrados = {k: v for k, v in datos.items() if k in campos_validos}
        return AppConfig(**datos_filtrados)

    def guardar(self) -> None:
        self._ruta_usuario.parent.mkdir(parents=True, exist_ok=True)
        self._ruta_usuario.write_text(
            json.dumps(self.config.a_diccionario(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def actualizar(self, **cambios: Any) -> None:
        for clave, valor in cambios.items():
            if hasattr(self.config, clave):
                setattr(self.config, clave, valor)
        self.guardar()
