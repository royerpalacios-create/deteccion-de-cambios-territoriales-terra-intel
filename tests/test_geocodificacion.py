"""Búsqueda de lugares (con respuestas simuladas: no se consulta Nominatim)."""
import pytest
import requests

from app.core.exceptions import GeocodificacionError, ValidacionError
from app.services import geocodificacion_service as geo
from app.services.geocodificacion_service import Lugar, buscar_lugar


class _Respuesta:
    def __init__(self, datos, error=None):
        self._datos, self._error = datos, error

    def raise_for_status(self):
        if self._error:
            raise self._error

    def json(self):
        return self._datos


def simular(monkeypatch, respuesta, capturar=None):
    def falso(url, params=None, headers=None, timeout=None):
        if capturar is not None:
            capturar.update(url=url, params=params, headers=headers)
        if isinstance(respuesta, Exception):
            raise respuesta
        return respuesta
    monkeypatch.setattr(geo.requests, "get", falso)


def test_busqueda_devuelve_lugares_y_envia_user_agent(monkeypatch):
    enviado = {}
    simular(monkeypatch, _Respuesta([
        {"display_name": "Miraflores, Lima, Perú", "lat": "-12.1211", "lon": "-77.0297"},
        {"display_name": "Miraflores, Arequipa, Perú", "lat": "-16.39", "lon": "-71.52"},
    ]), enviado)
    lugares = buscar_lugar("  Miraflores ")
    assert lugares[0] == Lugar("Miraflores, Lima, Perú", -12.1211, -77.0297)
    assert lugares[0].nombre_corto == "Miraflores" and len(lugares) == 2
    assert enviado["params"]["q"] == "Miraflores" and enviado["params"]["countrycodes"] == "pe"
    assert "TERRA_INTEL" in enviado["headers"]["User-Agent"]


def test_sin_resultados_devuelve_lista_vacia(monkeypatch):
    simular(monkeypatch, _Respuesta([]))
    assert buscar_lugar("zzzzzz") == []


def test_texto_muy_corto_se_rechaza_sin_consultar(monkeypatch):
    simular(monkeypatch, AssertionError("no debe consultar"))
    with pytest.raises(ValidacionError):
        buscar_lugar("ab")


@pytest.mark.parametrize("fallo", [
    requests.ConnectionError("sin internet"),
    _Respuesta(None, error=requests.HTTPError("429")),
    _Respuesta([{"sin": "campos"}]),
    _Respuesta("no es una lista"),
])
def test_los_fallos_se_traducen_a_un_error_claro(monkeypatch, fallo):
    simular(monkeypatch, fallo)
    with pytest.raises(GeocodificacionError, match="buscador"):
        buscar_lugar("Lima")
