import json
from pathlib import Path

from app.core.config import AppConfig, GestorConfiguracion


def test_carga_config_por_defecto_si_no_existe_settings(tmp_path: Path):
    defecto = tmp_path / "default_settings.json"
    defecto.write_text(json.dumps({"tema": "dark", "umbral_nubes": 20}), encoding="utf-8")
    usuario = tmp_path / "settings.json"

    gestor = GestorConfiguracion(ruta_usuario=usuario, ruta_defecto=defecto)
    assert gestor.config.tema == "dark"
    assert gestor.config.umbral_nubes == 20


def test_guardar_y_recargar_config(tmp_path: Path):
    defecto = tmp_path / "default_settings.json"
    defecto.write_text(json.dumps(AppConfig().a_diccionario()), encoding="utf-8")
    usuario = tmp_path / "settings.json"

    gestor = GestorConfiguracion(ruta_usuario=usuario, ruta_defecto=defecto)
    gestor.actualizar(tema="light", umbral_nubes=35)

    assert usuario.exists()
    gestor2 = GestorConfiguracion(ruta_usuario=usuario, ruta_defecto=defecto)
    assert gestor2.config.tema == "light"
    assert gestor2.config.umbral_nubes == 35


def test_agregar_proyecto_reciente_no_duplica_y_limita_tamano():
    config = AppConfig()
    for i in range(10):
        config.agregar_proyecto_reciente(f"proyecto_{i}.tiproj")
    assert len(config.proyectos_recientes) == 8
    assert config.proyectos_recientes[0] == "proyecto_9.tiproj"

    config.agregar_proyecto_reciente("proyecto_9.tiproj")
    assert config.proyectos_recientes.count("proyecto_9.tiproj") == 1
    assert config.proyectos_recientes[0] == "proyecto_9.tiproj"
