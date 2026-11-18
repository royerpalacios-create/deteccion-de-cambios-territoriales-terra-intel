"""Pruebas de RS-1 (adquisición) con Earth Engine simulado: sin red ni credenciales."""
import sys
import types

import pytest

from app.core.exceptions import DatosInsuficientesError, ValidacionError
from app.models.cobertura import BANDAS_CLASIFICACION
from app.services import adquisicion_service as adq
from app.services.adquisicion_service import AdquisicionService


class _Num:
    def __init__(self, valor):
        self._v = valor

    def getInfo(self):
        return self._v


class _Imagen:
    def __init__(self, llamadas, nombre="img"):
        self.llamadas, self.nombre = llamadas, nombre

    def _reg(self, *args):
        self.llamadas.append(args)
        return _Imagen(self.llamadas, self.nombre)

    def select(self, arg):
        return self._reg("select", arg)

    def gte(self, valor):
        return self._reg("gte", valor)

    def updateMask(self, mascara):
        return self._reg("updateMask", mascara)

    def clip(self, roi):
        return self._reg("clip", roi)


class _Coleccion:
    def __init__(self, llamadas, nombre, n=5, n_con_cs=None):
        self.llamadas, self.nombre, self.n = llamadas, nombre, n
        self.n_con_cs = n if n_con_cs is None else n_con_cs

    def _enc(self, *args):
        self.llamadas.append(args)
        return self

    def filterBounds(self, roi):
        return self._enc("filterBounds", self.nombre, roi)

    def filterDate(self, ini, fin):
        return self._enc("filterDate", self.nombre, ini, fin)

    def filter(self, filtro):
        return self._enc("filter", self.nombre, filtro)

    def size(self):
        return _Num(self.n_con_cs if self.nombre == "con_cs" else self.n)

    def linkCollection(self, otra, bandas):
        self.llamadas.append(("linkCollection", otra.nombre, tuple(bandas)))
        return _Coleccion(self.llamadas, "con_cs", self.n, self.n_con_cs)

    def map(self, funcion):
        self.llamadas.append(("map",))
        funcion(_Imagen(self.llamadas))  # ejecuta la máscara para registrar sus llamadas
        return self

    def select(self, bandas):
        return self._enc("select_bandas", tuple(bandas))

    def median(self):
        self.llamadas.append(("median",))
        return _Imagen(self.llamadas, "mosaico")


@pytest.fixture
def ee_falso(monkeypatch):
    estado = {"llamadas": [], "n": 5, "n_con_cs": None}
    modulo = types.ModuleType("ee")

    def image_collection(nombre):
        estado["llamadas"].append(("ImageCollection", nombre))
        return _Coleccion(estado["llamadas"], nombre, estado["n"], estado["n_con_cs"])

    class Filter:
        @staticmethod
        def calendarRange(a, b, campo):
            return ("calendarRange", a, b, campo)

        @staticmethod
        def lt(campo, valor):
            return ("lt", campo, valor)

        @staticmethod
        def listContains(campo, valor):
            return ("listContains", campo, valor)

    modulo.ImageCollection = image_collection
    modulo.Filter = Filter
    monkeypatch.setitem(sys.modules, "ee", modulo)
    return estado


def _nombres(llamadas):
    return [c[0] for c in llamadas]


def test_bandas_del_informe_coinciden_con_clasificacion():
    assert list(adq.BANDAS_INFORME) == BANDAS_CLASIFICACION


def test_defaults_explicitos():
    s = AdquisicionService()
    assert s.coleccion == "COPERNICUS/S2_SR_HARMONIZED"
    assert s.umbral_nubes == 20
    assert s.meses_temporada == (5, 9)
    assert s.umbral_cloud_score == 0.6
    assert s.escala_metros == 10


def test_flujo_y_orden_de_llamadas(ee_falso):
    roi = object()
    AdquisicionService().obtener_mosaico(roi, "2019-01-01", "2019-12-31")
    ll = ee_falso["llamadas"]
    assert ("ImageCollection", "COPERNICUS/S2_SR_HARMONIZED") in ll
    assert ("filterBounds", "COPERNICUS/S2_SR_HARMONIZED", roi) in ll
    assert ("filterDate", "COPERNICUS/S2_SR_HARMONIZED", "2019-01-01", "2019-12-31") in ll
    orden = [c[0] for c in ll if c[0] in {"filterBounds", "filterDate", "filter", "linkCollection",
                                          "map", "select_bandas", "median", "clip"}
             and (len(c) < 2 or c[0] == "linkCollection" or c[1] != adq.COLECCION_CLOUD_SCORE_PLUS)]
    # 2 filtros de escena (meses, nubes) → unión → filtro de verificación de cs_cdf → máscara → bandas
    assert orden == ["filterBounds", "filterDate", "filter", "filter", "linkCollection", "filter",
                     "map", "select_bandas", "median", "clip"]
    assert ll[-1] == ("clip", roi)


def test_filtro_de_meses_y_nubosidad_de_escena(ee_falso):
    AdquisicionService().obtener_mosaico(object(), "2024-01-01", "2024-12-31")
    filtros = [c[2] for c in ee_falso["llamadas"]
               if c[0] == "filter" and c[1] == "COPERNICUS/S2_SR_HARMONIZED"]
    assert ("calendarRange", 5, 9, "month") in filtros
    assert ("lt", "CLOUDY_PIXEL_PERCENTAGE", 20) in filtros


def test_union_con_cloud_score_plus(ee_falso):
    roi = object()
    AdquisicionService().obtener_mosaico(roi, "2019-01-01", "2019-12-31")
    ll = ee_falso["llamadas"]
    assert ("ImageCollection", "GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED") in ll
    assert ("linkCollection", "GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED", ("cs_cdf",)) in ll
    assert ("filterBounds", "GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED", roi) in ll


def test_mascara_de_pixel_cs_cdf_mayor_o_igual_06(ee_falso):
    AdquisicionService().obtener_mosaico(object(), "2019-01-01", "2019-12-31")
    ll = ee_falso["llamadas"]
    assert ("select", "cs_cdf") in ll
    assert ("gte", 0.6) in ll
    assert "updateMask" in _nombres(ll)
    assert not any(c[0] == "lt" for c in ll if len(c) == 2)  # no se usa lt(0.6) sobre píxeles


def test_umbral_cloud_score_configurable(ee_falso):
    AdquisicionService(umbral_cloud_score=0.7).obtener_mosaico(object(), "2019-01-01", "2019-12-31")
    assert ("gte", 0.7) in ee_falso["llamadas"]


def test_seis_bandas_antes_de_la_mediana(ee_falso):
    AdquisicionService().obtener_mosaico(object(), "2019-01-01", "2019-12-31")
    ll = ee_falso["llamadas"]
    assert ("select_bandas", ("B2", "B3", "B4", "B8", "B11", "B12")) in ll
    assert _nombres(ll).index("select_bandas") < _nombres(ll).index("median")


def test_sin_escenas_en_la_temporada_falla(ee_falso):
    ee_falso["n"] = 0
    with pytest.raises(DatosInsuficientesError, match="meses 5–9"):
        AdquisicionService().obtener_mosaico(object(), "2019-01-01", "2019-12-31")


def test_union_vacia_falla_sin_degradar_al_filtro_de_escena(ee_falso):
    ee_falso["n_con_cs"] = 0
    with pytest.raises(DatosInsuficientesError, match="Cloud Score\\+.*0 de 5"):
        AdquisicionService().obtener_mosaico(object(), "2019-01-01", "2019-12-31")
    assert "median" not in _nombres(ee_falso["llamadas"])


def test_union_parcial_tambien_falla(ee_falso):
    ee_falso["n_con_cs"] = 3
    with pytest.raises(DatosInsuficientesError, match="3 de 5"):
        AdquisicionService().obtener_mosaico(object(), "2019-01-01", "2019-12-31")


def test_t1_y_t2_usan_identico_flujo_y_exponen_metadata(ee_falso):
    roi = object()
    s = AdquisicionService()
    res = s.adquirir_mosaicos_temporales(roi, ("2019-01-01", "2019-12-31"), ("2024-01-01", "2024-12-31"))
    assert {"mosaico_t1", "mosaico_t2", "metadata"} <= set(res)
    m1, m2 = res["metadata"]["t1"], res["metadata"]["t2"]
    comunes = {k: v for k, v in m1.items() if k not in {"fecha_inicio", "fecha_fin"}}
    assert comunes == {k: v for k, v in m2.items() if k not in {"fecha_inicio", "fecha_fin"}}
    assert (m1["fecha_inicio"], m2["fecha_inicio"]) == ("2019-01-01", "2024-01-01")
    assert m1["coleccion"] == "COPERNICUS/S2_SR_HARMONIZED"
    assert m1["meses_temporada"] == [5, 9]
    assert m1["umbral_nubes_escena"] == 20
    assert (m1["banda_cloud_score"], m1["umbral_cloud_score"]) == ("cs_cdf", 0.6)
    assert m1["bandas"] == ["B2", "B3", "B4", "B8", "B11", "B12"]
    assert m1["escala_m"] == 10
    assert m1["n_escenas"] == 5 and m1["n_escenas_con_cloud_score"] == 5


def test_fechas_invalidas_fallan_antes_de_llamar_a_ee(ee_falso):
    with pytest.raises(ValidacionError):
        AdquisicionService().obtener_mosaico(object(), "2019-12-31", "2019-01-01")
    assert ee_falso["llamadas"] == []


@pytest.mark.parametrize("meses", [(0, 9), (5, 13), (9, 5), ("a", 9), (5,)])
def test_meses_invalidos(meses):
    with pytest.raises(ValidacionError):
        AdquisicionService(meses_temporada=meses)


@pytest.mark.parametrize("umbral", [0, -0.1, 1.5, "0.6", True])
def test_umbral_cloud_score_invalido(umbral):
    with pytest.raises(ValidacionError):
        AdquisicionService(umbral_cloud_score=umbral)


def test_import_de_ee_es_diferido():
    """Importar el módulo no debe requerir earthengine-api."""
    assert "ee" not in vars(adq)
