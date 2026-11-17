import sys
from types import SimpleNamespace

import pytest

from app.services.deteccion_cambios_service import DeteccionCambiosService
from app.utils.stats import categorizar_transicion, construir_resumen_transicion


class _Computed:
    def getInfo(self):
        return {
            "groups": [
                {"transicion": 11, "count": 90, "sum": 0.9},
                {"transicion": 13, "count": 10, "sum": 0.1},
            ],
        }


class _Image:
    def add(self, _other):
        return self

    def addBands(self, _other):
        return self

    def divide(self, _divisor):
        return self

    def getThumbURL(self, _params):
        return "overlay.png"

    def multiply(self, _factor):
        return self

    def neq(self, _value):
        return self

    def reduceRegion(self, **_kwargs):
        return _Computed()

    def remap(self, _from, _to, **_kwargs):
        return self

    def rename(self, _name):
        return self

    def toInt(self):
        return self

    def updateMask(self, _mask):
        return self


class _Reducer:
    def combine(self, *_args, **_kwargs):
        return self

    def group(self, **_kwargs):
        return self

    @staticmethod
    def count():
        return _Reducer()

    @staticmethod
    def sum():
        return _Reducer()


class _EarthEngineImage(_Image):
    @staticmethod
    def pixelArea():
        return _EarthEngineImage()


@pytest.mark.parametrize(
    ("clase_t1", "clase_t2", "categoria"),
    [
        (1, 1, 0), (1, 2, 3), (1, 3, 1), (1, 4, 4),
        (2, 1, 2), (2, 2, 0), (2, 3, 1), (2, 4, 2),
        (3, 1, 4), (3, 2, 3), (3, 3, 0), (3, 4, 5),
        (4, 1, 4), (4, 2, 3), (4, 3, 1), (4, 4, 0),
    ],
)
def test_categoriza_las_16_transiciones_en_orden(clase_t1, clase_t2, categoria):
    assert categorizar_transicion(clase_t1, clase_t2) == categoria


def test_matriz_area_por_epoca_y_balance():
    resumen = construir_resumen_transicion({
        11: (10, 1.0),
        12: (2, 0.2),
        21: (1, 0.1),
        22: (5, 0.5),
    })

    agua, vegetacion = resumen.balance[:2]
    assert resumen.clases == ("Agua", "Vegetación", "Urbano", "Suelo desnudo")
    assert resumen.total_pixeles == 18
    assert resumen.area_total_ha == pytest.approx(1.8)
    assert resumen.matriz[0][0].pixeles == 10
    assert resumen.matriz[0][1].porcentaje == pytest.approx(100 / 9)
    assert resumen.matriz[0][2].pixeles == 0
    assert resumen.matriz[0][2].area_ha == 0
    assert agua.area_t1_ha == pytest.approx(1.2)
    assert agua.area_t2_ha == pytest.approx(1.1)
    assert agua.entradas_ha == pytest.approx(0.1)
    assert agua.salidas_ha == pytest.approx(0.2)
    assert agua.neto_ha == pytest.approx(-0.1)
    assert agua.persistencia_ha == pytest.approx(1.0)
    assert vegetacion.persistencia_pct == pytest.approx(5 / 6 * 100)


def test_matriz_vacia_distingue_no_data_de_cero_observado():
    sin_datos = construir_resumen_transicion({})
    con_datos = construir_resumen_transicion({11: (1, 0.01)})

    assert sin_datos.total_pixeles is None
    assert sin_datos.matriz[0][0] is None
    assert con_datos.total_pixeles == 1
    assert con_datos.matriz[0][0].pixeles == 1
    assert con_datos.matriz[0][1].pixeles == 0


def test_servicio_devuelve_matriz_y_estadisticas_de_las_mismas_transiciones(monkeypatch):
    monkeypatch.setitem(
        sys.modules,
        "ee",
        SimpleNamespace(Image=_EarthEngineImage, Reducer=_Reducer),
    )

    resultado = DeteccionCambiosService().detectar(
        _Image(), _Image(), roi=object(), centro=(0.0, 0.0),
    )

    assert resultado.resumen_transicion.total_pixeles == 100
    assert resultado.resumen_transicion.matriz[0][2].pixeles == 10
    assert any(fila.titulo == "Urbanización" for fila in resultado.estadisticas)
