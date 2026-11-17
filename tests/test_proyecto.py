from pathlib import Path

from app.models.proyecto import EstadisticaCambio, Proyecto


def test_guardar_y_cargar_proyecto_sin_estadisticas(tmp_path: Path):
    proyecto = Proyecto(nombre="Puno 2019-2024", longitud=-70.01, latitud=-15.84)
    ruta = proyecto.guardar(tmp_path / "puno")

    assert ruta.suffix == ".tiproj"
    cargado = Proyecto.cargar(ruta)
    assert cargado.nombre == "Puno 2019-2024"
    assert cargado.longitud == -70.01
    assert cargado.estadisticas == []


def test_guardar_y_cargar_proyecto_con_estadisticas(tmp_path: Path):
    fila = EstadisticaCambio(
        titulo="Urbanización", coords="-15.84, -70.01", porcentaje="12.3%",
        nivel="MEDIO", color="#ffb95f", detalle="1234 px afectados",
    )
    proyecto = Proyecto(nombre="Test", longitud=1.0, latitud=2.0, estadisticas=[fila])
    ruta = proyecto.guardar(tmp_path / "test.tiproj")

    cargado = Proyecto.cargar(ruta)
    assert len(cargado.estadisticas) == 1
    assert cargado.estadisticas[0].titulo == "Urbanización"
