import pytest

from app.models.area_estudio import (
    AreaDeEstudio, PIXELES_MAXIMOS_ANALISIS, RADIO_BUFFER_METROS, calcular_escala_metros,
    crear_area_estudio, crear_area_estudio_puno, estimar_pixeles,
)


def test_crear_area_estudio_puno_valores_por_defecto():
    area = crear_area_estudio_puno()
    assert area.nombre == "Puno"
    assert area.radio_metros == RADIO_BUFFER_METROS == 10_000


def test_area_de_estudio_rechaza_radio_invalido():
    with pytest.raises(ValueError):
        AreaDeEstudio(longitud=-70.0, latitud=-15.8, radio_metros=0)


def test_area_de_estudio_rechaza_coordenadas_fuera_de_rango():
    with pytest.raises(ValueError):
        AreaDeEstudio(longitud=200.0, latitud=-15.8, radio_metros=1000)
    with pytest.raises(ValueError):
        AreaDeEstudio(longitud=-70.0, latitud=95.0, radio_metros=1000)


def test_centro_devuelve_tupla_lon_lat():
    area = AreaDeEstudio(longitud=-70.01, latitud=-15.84, radio_metros=5000)
    assert area.centro() == (-70.01, -15.84)


def test_crear_area_estudio_acepta_cualquier_lugar():
    area = crear_area_estudio(longitud=-77.04, latitud=-12.05, nombre="Lima")
    assert (area.nombre, area.radio_metros) == ("Lima", RADIO_BUFFER_METROS)


def test_estimar_pixeles_crece_con_el_cuadrado_del_radio():
    assert estimar_pixeles(10_000, 10) == 4_000_000          # (20 km / 10 m)^2
    assert estimar_pixeles(20_000, 10) == 4 * estimar_pixeles(10_000, 10)


@pytest.mark.parametrize("radio, escala", [
    (1_000, 10), (5_000, 10), (10_000, 10),   # dentro del presupuesto: resolución nativa
    (25_000, 30), (50_000, 50), (100_000, 100),  # fuera: se baja la resolución
])
def test_escala_adaptativa_respeta_el_presupuesto_de_pixeles(radio, escala):
    assert calcular_escala_metros(radio) == escala
    assert estimar_pixeles(radio, escala) <= PIXELES_MAXIMOS_ANALISIS


def test_escala_es_multiplo_de_10_y_nunca_baja_de_10():
    for radio in (500, 3_333, 12_345, 77_777):
        escala = calcular_escala_metros(radio)
        assert escala >= 10 and escala % 10 == 0
