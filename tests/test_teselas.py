"""Caché LRU y descarga de teselas (contra un servidor HTTP local, sin internet)."""
import sys
from pathlib import Path

import pytest
import requests

sys.path.insert(0, str(Path(__file__).parent))
from servidor_teselas import ServidorTeselas  # noqa: E402

from app.services.teselas_service import CacheLRU, FUENTES_MAPA, FuenteMapa, ServicioTeselas  # noqa: E402


# --------------------------------------------------------------------------- LRU
def test_lru_descarta_el_menos_recientemente_usado():
    c = CacheLRU(3)
    for k in "abc":
        c.put(k, k.upper())
    c.get("a")                       # "a" pasa a ser el más reciente; el más antiguo ahora es "b"
    c.put("d", "D")
    assert c.claves() == ["c", "a", "d"] and "b" not in c and len(c) == 3


def test_lru_peek_no_altera_el_orden_y_put_actualiza():
    c = CacheLRU(2)
    c.put("a", 1)
    c.put("b", 2)
    assert c.peek("a") == 1 and c.claves() == ["a", "b"]
    c.put("a", 10)                   # reescribir también cuenta como uso
    c.put("c", 3)
    assert c.get("a") == 10 and "b" not in c
    assert c.get("zzz") is None


def test_lru_exige_capacidad_positiva():
    with pytest.raises(ValueError):
        CacheLRU(0)


# ---------------------------------------------------------------------- fuentes
def test_el_orden_de_la_url_depende_del_proveedor():
    assert FUENTES_MAPA["osm"].url_tesela(5, 10, 20).endswith("/5/10/20.png")          # z/x/y
    assert FUENTES_MAPA["esri"].url_tesela(5, 10, 20).endswith("/tile/5/20/10")        # z/y/x


# ------------------------------------------------------------------------- red
@pytest.fixture
def servidor():
    with ServidorTeselas() as s:
        yield s


def fuente_local(servidor):
    return FuenteMapa("local", "Local", servidor.url, "test")


def test_descarga_y_cache_en_disco(servidor, tmp_path):
    servicio = ServicioTeselas(tmp_path, timeout=3)
    f = fuente_local(servidor)
    datos = servicio.obtener_bytes(f, 5, 10, 20)
    assert datos.startswith(b"\x89PNG") and len(servidor.peticiones) == 1
    assert (tmp_path / "local" / "5" / "10" / "20.tile").read_bytes() == datos

    assert servicio.obtener_bytes(f, 5, 10, 20) == datos       # segunda vez: sale del disco
    assert len(servidor.peticiones) == 1


def test_sin_cache_en_disco_siempre_pide(servidor):
    servicio = ServicioTeselas(None, timeout=3)
    f = fuente_local(servidor)
    servicio.obtener_bytes(f, 5, 1, 1)
    servicio.obtener_bytes(f, 5, 1, 1)
    assert len(servidor.peticiones) == 2


def test_error_http_se_propaga_y_no_se_cachea(servidor, tmp_path):
    servicio = ServicioTeselas(tmp_path, timeout=3)
    with pytest.raises(requests.HTTPError):
        servicio.obtener_bytes(fuente_local(servidor), 0, 0, 0)          # el servidor responde 404 para z = 0
    assert not list(tmp_path.rglob("*.tile"))


def test_una_pagina_de_error_con_codigo_200_no_se_toma_por_tesela(servidor, tmp_path):
    servicio = ServicioTeselas(tmp_path, timeout=3)
    with pytest.raises(ValueError):
        servicio.obtener_bytes(fuente_local(servidor), 5, 3, 7)          # y == 7 devuelve HTML
    assert not list(tmp_path.rglob("*.tile")) and not list(tmp_path.rglob("*.tmp"))


def test_una_tesela_corrupta_en_disco_se_vuelve_a_descargar(servidor, tmp_path):
    servicio = ServicioTeselas(tmp_path, timeout=3)
    f = fuente_local(servidor)
    ruta = servicio.ruta_cache(f, 5, 2, 2)
    ruta.parent.mkdir(parents=True)
    ruta.write_bytes(b"basura")
    assert servicio.obtener_bytes(f, 5, 2, 2).startswith(b"\x89PNG")
    assert ruta.read_bytes().startswith(b"\x89PNG")


def test_servidor_inalcanzable_lanza_error_de_requests(tmp_path):
    f = FuenteMapa("x", "x", "http://127.0.0.1:9/{z}/{x}/{y}.png", "")
    with pytest.raises(requests.RequestException):
        ServicioTeselas(tmp_path, timeout=1).obtener_bytes(f, 5, 1, 1)
