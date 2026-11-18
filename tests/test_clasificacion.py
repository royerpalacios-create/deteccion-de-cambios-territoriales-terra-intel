"""RS-2: etiquetas Dynamic World, muestreo por época, split y validación (EE simulado)."""
import sys
from unittest.mock import MagicMock

import pytest

from app.core.exceptions import ValidacionError
from app.services import clasificacion_service as cs
from app.services.clasificacion_service import (
    ClasificacionService,
    dividir_train_holdout,
    etiquetas_dynamic_world,
    muestrear_epoca,
)


@pytest.fixture
def ee(monkeypatch):
    falso = MagicMock()
    monkeypatch.setitem(sys.modules, "ee", falso)
    return falso


def test_mapeo_dw_agrupa_vegetacion_y_excluye_nieve():
    assert cs.MAPEO_DW_A_APP[0] == 1                                    # agua
    assert {cs.MAPEO_DW_A_APP[c] for c in (1, 2, 3, 4, 5)} == {2}       # vegetación
    assert cs.MAPEO_DW_A_APP[6] == 3                                    # urbano
    assert cs.MAPEO_DW_A_APP[7] == 4                                    # suelo desnudo
    assert 8 not in cs.MAPEO_DW_A_APP                                   # nieve/hielo fuera


def test_etiquetas_usan_moda_anual_y_remap(ee):
    etiquetas_dynamic_world("roi", 2019)

    ee.ImageCollection.assert_called_once_with("GOOGLE/DYNAMICWORLD/V1")
    coleccion = ee.ImageCollection.return_value.filterBounds.return_value
    coleccion.filterDate.assert_called_once_with("2019-01-01", "2020-01-01")
    moda = coleccion.filterDate.return_value.select.return_value.mode.return_value
    moda.remap.assert_called_once_with([0, 1, 2, 3, 4, 5, 6, 7], [1, 2, 2, 2, 2, 2, 3, 4])


def test_muestreo_por_epoca_usa_150_10m_semilla_42_y_conserva_epoca(ee):
    mosaico = MagicMock()
    pila = mosaico.select.return_value.addBands.return_value

    muestrear_epoca(mosaico, MagicMock(), "roi", "2019", ["B2", "B3"])

    kw = pila.stratifiedSample.call_args.kwargs
    assert kw["numPoints"] == 150
    assert kw["scale"] == 10
    assert kw["seed"] == 42
    assert kw["classBand"] == "clase"
    asignar_epoca = pila.stratifiedSample.return_value.map.call_args.args[0]
    punto = MagicMock()
    asignar_epoca(punto)
    punto.set.assert_called_once_with("epoca", "2019")


def test_split_es_determinista_70_30(ee):
    muestras = MagicMock()
    dividir_train_holdout(muestras)

    muestras.randomColumn.assert_called_once_with("azar", 42)
    ee.Filter.lt.assert_called_once_with("azar", 0.7)
    ee.Filter.gte.assert_called_once_with("azar", 0.7)


def test_con_roi_sin_anios_falla_en_vez_de_degradar_a_umbrales(ee):
    with pytest.raises(ValidacionError, match="anios"):
        ClasificacionService().clasificar_mosaicos_temporales(MagicMock(), MagicMock(), roi="roi")


def test_flujo_completo_entrena_una_vez_con_t1_t2_y_valida_en_holdout(ee):
    ee.Dictionary.return_value.getInfo.return_value = {
        "n_total": 300, "n_entrenamiento": 210, "n_holdout": 90,
        "global": {"n": 90, "concordancia": 0.8, "kappa": 0.7, "matriz_error": []},
        "por_epoca": {}, "muestras_por_epoca_clase": {},
    }
    servicio = ClasificacionService()
    t1, t2 = MagicMock(), MagicMock()

    r = servicio.clasificar_mosaicos_temporales(t1, t2, roi="roi", anios=(2019, 2024))

    # un solo RF, entrenado con la tabla de entrenamiento (no con T2 solo)
    assert ee.Classifier.smileRandomForest.call_count == 1
    assert ee.Classifier.smileRandomForest.call_args.kwargs["numberOfTrees"] == 100
    # se mezclan las dos épocas antes de partir
    assert ee.ImageCollection.call_count == 2
    # contrato de salida
    assert set(r) == {"clasificacion_t1", "clasificacion_t2", "validacion"}
    assert r["validacion"]["fuente"] == "Dynamic World"
    assert r["validacion"]["semilla"] == 42
    assert r["validacion"]["n_total"] == 300
    assert "no exactitud" in r["validacion"]["advertencia"]


def test_metricas_se_calculan_sobre_predicciones_del_holdout(ee):
    ee.Dictionary.return_value.getInfo.return_value = {"n_total": 1}
    holdout, muestras, entren = MagicMock(), MagicMock(), MagicMock()

    ClasificacionService().calcular_validacion("rf", muestras, entren, holdout, ("2019", "2024"))

    holdout.classify.assert_called_once_with("rf")           # predice SOLO el holdout
    predichos = holdout.classify.return_value
    assert predichos.errorMatrix.call_args.args == ("clase", "classification", [1, 2, 3, 4])
    assert predichos.filter.call_count == 2                  # una matriz por época


def test_error_de_ee_en_validacion_se_reporta_accionable(ee):
    ee.Dictionary.return_value.getInfo.side_effect = RuntimeError("sin datos")
    with pytest.raises(ValidacionError, match="validación"):
        ClasificacionService().clasificar_mosaicos_temporales(
            MagicMock(), MagicMock(), roi="roi", anios=(2019, 2024))


def test_muestras_explicitas_no_usan_dynamic_world(ee):
    r = ClasificacionService().clasificar_mosaicos_temporales(
        MagicMock(), MagicMock(), muestras="puntos-campo")
    assert not ee.ImageCollection.called
    assert r["validacion"] is None