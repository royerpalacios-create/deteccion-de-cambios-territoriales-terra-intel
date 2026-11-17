from app.utils.stats import construir_estadisticas_cambios


def test_sin_cambios_devuelve_fila_unica():
    histograma = {"0": 1000}
    filas = construir_estadisticas_cambios(histograma, total_pixeles=1000, centro=(-70.0, -15.8))
    assert len(filas) == 1
    assert filas[0].titulo == "Sin cambios significativos"


def test_ignora_diferencias_menores_al_uno_por_ciento():
    histograma = {"0": 990, "1": 5, "2": 5}  # 0.5% cada una
    filas = construir_estadisticas_cambios(histograma, total_pixeles=1000, centro=(-70.0, -15.8))
    assert len(filas) == 1  # todas quedan por debajo del umbral, solo la fila "sin cambios"


def test_clasifica_niveles_correctamente():
    histograma = {"0": 700, "1": 200, "2": 80, "3": 20}  # 20%, 8%, 2%
    filas = construir_estadisticas_cambios(histograma, total_pixeles=1000, centro=(-70.0, -15.8))
    niveles = {f.detalle: f.nivel for f in filas}
    assert filas[0].nivel == "ALTO"       # 20% (diferencia=1)
    assert filas[0].titulo == "Urbanización"
    assert any(f.nivel == "MEDIO" for f in filas)  # 8% (diferencia=2)
    assert any(f.nivel == "BAJO" for f in filas)   # 2% (diferencia=3)


def test_orden_de_mayor_a_menor_porcentaje():
    histograma = {"0": 500, "1": 100, "2": 300, "3": 100}
    filas = construir_estadisticas_cambios(histograma, total_pixeles=1000, centro=(0.0, 0.0))
    porcentajes = [float(f.porcentaje.strip("%")) for f in filas]
    assert porcentajes == sorted(porcentajes, reverse=True)


def test_sin_pixeles_validos_no_se_presenta_como_cero_cambios():
    filas = construir_estadisticas_cambios({}, total_pixeles=None, centro=(0.0, 0.0))
    assert filas[0].titulo == "Sin datos válidos"
    assert filas[0].porcentaje == "—"
    assert filas[0].nivel == "SIN DATOS"


def test_usa_nombres_legibles_de_todas_las_categorias():
    nombres = {
        "1": "Urbanización",
        "2": "Pérdida de vegetación",
        "3": "Ganancia de vegetación",
        "4": "Cambio en cuerpo de agua",
        "5": "Otro cambio",
    }
    for categoria, nombre in nombres.items():
        filas = construir_estadisticas_cambios(
            {categoria: 20},
            total_pixeles=100,
            centro=(0.0, 0.0),
        )
        assert filas[0].titulo == nombre
