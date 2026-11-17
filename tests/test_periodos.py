"""Validación de periodos de análisis y utilidades de nombres/etiquetas."""
from datetime import date

import pytest

from app.core.exceptions import ValidacionError
from app.services.adquisicion_service import etiqueta_periodo, periodo_desde_etiqueta, validar_periodos
from app.services.proyecto_service import nombre_archivo_seguro

HOY = date(2026, 10, 26)
T1 = ("2019-01-01", "2019-12-31")
T2 = ("2024-01-01", "2024-12-31")


def test_periodos_validos_no_lanzan():
    validar_periodos(T1, T2, hoy=HOY)


@pytest.mark.parametrize("t1, t2, fragmento", [
    (("2019-13-01", "2019-12-31"), T2, "Época A"),                 # mes imposible
    (T1, ("2024-12-31", "2024-01-01"), "Época B"),                  # inicio posterior al fin
    (("2016-01-01", "2016-12-31"), T2, "antes del 2017-03-28"),     # anterior a Sentinel-2
    (T1, ("2026-01-01", "2027-06-30"), "futuro"),                   # termina en el futuro
    (("2024-01-01", "2024-12-31"), ("2019-01-01", "2019-12-31"), "terminar antes"),  # T1 después de T2
    (("2019-01-01", "2020-01-01"), ("2020-01-01", "2020-12-31"), "terminar antes"),  # se tocan
])
def test_periodos_invalidos_explican_que_falla(t1, t2, fragmento):
    with pytest.raises(ValidacionError, match=fragmento):
        validar_periodos(t1, t2, hoy=HOY)


def test_etiqueta_periodo_y_su_inverso():
    assert etiqueta_periodo(*T1) == "2019"
    rango = etiqueta_periodo("2021-03-01", "2021-08-31")
    assert rango == "2021-03-01 → 2021-08-31"
    assert periodo_desde_etiqueta("2019") == T1
    assert periodo_desde_etiqueta(rango) == ("2021-03-01", "2021-08-31")
    assert periodo_desde_etiqueta("texto libre") is None


@pytest.mark.parametrize("nombre, esperado", [
    ("proyecto_terra_intel", "proyecto_terra_intel"),
    ("Lima – Centro", "Lima_Centro"),
    ("Puno (Lago Titicaca)", "Puno_Lago_Titicaca"),
    ("../../etc/passwd", "etc_passwd"),
    ("a/b:c*d", "a_b_c_d"),
    ("   ", "proyecto"),
])
def test_nombre_de_archivo_seguro(nombre, esperado):
    assert nombre_archivo_seguro(nombre) == esperado
