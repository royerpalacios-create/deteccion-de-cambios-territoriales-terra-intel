"""Matemáticas de mapas web (Web Mercator, teselas, escalas)."""
import math

import pytest

from app.utils.geo import (
    LATITUD_MAXIMA, barra_escala, formatear_distancia, limites_cuadrado, lonlat_a_mundo,
    metros_por_pixel, mundo_a_lonlat, tesela_de, zoom_para_ajustar,
)


def test_tesela_de_valores_de_referencia():
    assert tesela_de(-0.1278, 51.5074, 10) == (511, 340)     # Londres (referencia de la wiki de OSM)
    assert tesela_de(0, 0, 0) == (0, 0)
    assert tesela_de(-179.99, 85.0, 1) == (0, 0)
    assert tesela_de(179.99, -85.0, 1) == (1, 1)


def test_el_mundo_a_zoom_cero_es_una_tesela():
    assert lonlat_a_mundo(-180, LATITUD_MAXIMA, 0) == pytest.approx((0, 0), abs=1e-6)
    assert lonlat_a_mundo(180, -LATITUD_MAXIMA, 0) == pytest.approx((256, 256), abs=1e-6)
    assert lonlat_a_mundo(0, 0, 0) == pytest.approx((128, 128))


@pytest.mark.parametrize("lon, lat, zoom", [(-77.0428, -12.0464, 12), (-70.01, -15.84, 5), (0, 0, 18), (170, 60, 3)])
def test_ida_y_vuelta_lonlat_mundo(lon, lat, zoom):
    x, y = lonlat_a_mundo(lon, lat, zoom)
    assert mundo_a_lonlat(x, y, zoom) == pytest.approx((lon, lat), abs=1e-9)


def test_latitud_fuera_de_mercator_se_recorta():
    assert lonlat_a_mundo(0, 90, 3)[1] == pytest.approx(lonlat_a_mundo(0, LATITUD_MAXIMA, 3)[1])


def test_metros_por_pixel():
    assert metros_por_pixel(0, 0) == pytest.approx(156_543.03, rel=1e-6)           # valor clásico en el ecuador
    assert metros_por_pixel(0, 10) == pytest.approx(metros_por_pixel(0, 9) / 2)    # cada zoom divide a la mitad
    assert metros_por_pixel(60, 8) == pytest.approx(metros_por_pixel(0, 8) / 2, rel=1e-3)   # cos 60° = 0.5


def test_limites_del_cuadrado_miden_dos_veces_el_radio():
    lon_min, lat_min, lon_max, lat_max = limites_cuadrado(-77.0428, -12.0464, 10_000)
    alto_m = (lat_max - lat_min) * math.pi / 180 * 6_378_137
    ancho_m = (lon_max - lon_min) * math.pi / 180 * 6_378_137 * math.cos(math.radians(-12.0464))
    assert alto_m == pytest.approx(20_000, rel=1e-6)
    assert ancho_m == pytest.approx(20_000, rel=2e-3)
    assert (lon_min + lon_max) / 2 == pytest.approx(-77.0428) and (lat_min + lat_max) / 2 == pytest.approx(-12.0464)


def test_el_cuadrado_se_ve_cuadrado_en_pantalla():
    """En Mercator los píxeles de ancho y alto de un cuadrado de 2r metros deben coincidir."""
    for lat in (-0.5, -12.0464, -17.5):
        lon_min, lat_min, lon_max, lat_max = limites_cuadrado(-70.0, lat, 8_000)
        x1, y1 = lonlat_a_mundo(lon_min, lat_max, 12)
        x2, y2 = lonlat_a_mundo(lon_max, lat_min, 12)
        assert (x2 - x1) == pytest.approx(y2 - y1, rel=2e-3)


def test_zoom_para_ajustar_baja_al_crecer_el_radio_y_respeta_limites():
    zooms = [zoom_para_ajustar(-12.0, r, 700, 500) for r in (1_000, 5_000, 20_000, 100_000)]
    assert zooms == sorted(zooms, reverse=True) and len(set(zooms)) > 1
    assert zoom_para_ajustar(-12.0, 1, 700, 500) == 18                  # radio ínfimo: tope del mapa
    assert zoom_para_ajustar(-12.0, 5_000_000, 700, 500) == 3           # radio enorme: mínimo
    assert zoom_para_ajustar(-12.0, 10, 700, 500, zoom_max=15) == 15
    z = zoom_para_ajustar(-12.0, 10_000, 700, 500)
    assert 2 * 10_000 / metros_por_pixel(-12.0, z) <= 0.6 * 500          # el área cabe en la vista


@pytest.mark.parametrize("zoom", range(3, 19))
def test_barra_de_escala_es_redonda_y_cabe(zoom):
    metros, px = barra_escala(-12.0, zoom)
    assert px <= 110
    mantisa = metros / 10 ** math.floor(math.log10(metros))
    assert round(mantisa) in (1, 2, 5) and abs(mantisa - round(mantisa)) < 1e-9
    assert px == round(metros / metros_por_pixel(-12.0, zoom))


def test_formatear_distancia():
    assert formatear_distancia(500) == "500 m"
    assert formatear_distancia(1000) == "1 km"
    assert formatear_distancia(2500) == "2.5 km"
    assert formatear_distancia(20_000) == "20 km"
