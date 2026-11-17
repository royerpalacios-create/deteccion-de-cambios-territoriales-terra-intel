"""El generador de muestras arma una consulta estratificada (sin Earth Engine real)."""
import sys
from unittest.mock import MagicMock

from app.services.clasificacion_service import ClasificacionService, generar_muestras_sobre_roi


def test_muestras_usan_stratified_sample_con_n_puntos_por_clase(monkeypatch):
    ee = MagicMock()
    monkeypatch.setitem(sys.modules, "ee", ee)

    generar_muestras_sobre_roi(MagicMock(), "roi-falso", puntos_por_clase=25)

    llamadas = [c for c in ee.mock_calls if c[0].endswith("stratifiedSample")]
    assert len(llamadas) == 1
    assert llamadas[0].kwargs["numPoints"] == 25
    assert llamadas[0].kwargs["classBand"] == "clase"
    assert llamadas[0].kwargs["region"] == "roi-falso"
    # las cuatro clases se etiquetan con where(): suelo, urbano, vegetación y agua
    assert sum(1 for c in ee.mock_calls if c[0].endswith(".where")) == 4


def test_con_roi_no_se_usan_los_puntos_fijos_de_puno(monkeypatch):
    ee = MagicMock()
    monkeypatch.setitem(sys.modules, "ee", ee)
    servicio = ClasificacionService()
    servicio.clasificar_mosaicos_temporales(MagicMock(), MagicMock(), roi="roi-falso")
    nombres = [c[0] for c in ee.mock_calls]
    assert any(n.endswith("stratifiedSample") for n in nombres)
    assert not any("Geometry.Point" in n for n in nombres)   # los puntos legacy de Puno usan Geometry.Point
