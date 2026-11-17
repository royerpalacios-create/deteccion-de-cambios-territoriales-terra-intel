"""Utilidades puras para estadísticas de cambio y transiciones de cobertura."""
from __future__ import annotations

from typing import Dict, List, Mapping

from app.models.cobertura import CATEGORIAS_CAMBIO, CLASES_COBERTURA
from app.models.proyecto import (
    BalanceCobertura,
    CeldaTransicion,
    EstadisticaCambio,
    ResumenTransicion,
)

_UMBRAL_ALTO = 15.0
_UMBRAL_MEDIO = 5.0
_PORCENTAJE_MINIMO_RELEVANTE = 1.0


def categorizar_transicion(clase_t1: int, clase_t2: int) -> int:
    """Aplica en orden las reglas de categoría de cambio para una pareja T1→T2."""
    ids_validos = {clase.id for clase in CLASES_COBERTURA.values()}
    if clase_t1 not in ids_validos or clase_t2 not in ids_validos:
        raise ValueError(f"Clases de cobertura no válidas: {clase_t1} → {clase_t2}")

    id_agua = CLASES_COBERTURA["agua"].id
    id_vegetacion = CLASES_COBERTURA["vegetacion"].id
    id_urbano = CLASES_COBERTURA["urbano"].id

    if clase_t1 == clase_t2:
        return 0
    if clase_t2 == id_urbano:
        return 1
    if clase_t1 == id_vegetacion:
        return 2
    if clase_t2 == id_vegetacion:
        return 3
    if (clase_t1 == id_agua) != (clase_t2 == id_agua):
        return 4
    return 5


def construir_histograma_categorias(
    transiciones: Mapping[int, tuple[int, float]],
) -> Dict[str, int]:
    """Agrupa conteos de pares de clases por categoría de cambio."""
    histograma: Dict[str, int] = {}
    for codigo, (pixeles, _) in transiciones.items():
        clase_t1, clase_t2 = divmod(int(codigo), 10)
        categoria = categorizar_transicion(clase_t1, clase_t2)
        clave = str(categoria)
        histograma[clave] = histograma.get(clave, 0) + int(pixeles)
    return histograma


def construir_resumen_transicion(
    transiciones: Mapping[int, tuple[int, float]],
) -> ResumenTransicion:
    """Construye la matriz T1→T2 y el balance por clase.

    ``transiciones`` asigna a ``T1 * 10 + T2`` el conteo de píxeles y el área
    en hectáreas. Un resultado vacío se representa con ``None`` (no-data);
    una celda cero dentro de una matriz válida sí representa cero observado.
    """
    clases_ordenadas = sorted(CLASES_COBERTURA.values(), key=lambda clase: clase.id)
    ids = [clase.id for clase in clases_ordenadas]
    nombres = tuple(clase.nombre for clase in clases_ordenadas)
    indices = {clase_id: indice for indice, clase_id in enumerate(ids)}

    def sin_datos() -> ResumenTransicion:
        matriz_vacia = tuple(tuple(None for _ in ids) for _ in ids)
        balance_vacio = tuple(
            BalanceCobertura(nombre, None, None, None, None, None, None, None)
            for nombre in nombres
        )
        return ResumenTransicion(nombres, matriz_vacia, balance_vacio, None, None)

    if not transiciones:
        return sin_datos()

    pixeles = [[0 for _ in ids] for _ in ids]
    areas = [[0.0 for _ in ids] for _ in ids]
    for codigo, (cantidad, area_ha) in transiciones.items():
        clase_t1, clase_t2 = divmod(int(codigo), 10)
        if clase_t1 not in indices or clase_t2 not in indices:
            raise ValueError(f"Código de transición no válido: {codigo}")
        if cantidad < 0 or area_ha < 0:
            raise ValueError(f"Conteo o área negativos para la transición {codigo}")
        fila, columna = indices[clase_t1], indices[clase_t2]
        pixeles[fila][columna] += int(cantidad)
        areas[fila][columna] += float(area_ha)

    total_pixeles = sum(sum(fila) for fila in pixeles)
    area_total_ha = sum(sum(fila) for fila in areas)
    if total_pixeles == 0:
        return sin_datos()
    if area_total_ha <= 0:
        raise ValueError("El área total debe ser positiva cuando hay píxeles válidos")

    matriz = tuple(
        tuple(
            CeldaTransicion(
                pixeles=pixeles[fila][columna],
                area_ha=areas[fila][columna],
                porcentaje=areas[fila][columna] / area_total_ha * 100,
            )
            for columna in range(len(ids))
        )
        for fila in range(len(ids))
    )
    balances = []
    for indice, nombre in enumerate(nombres):
        persistencia = areas[indice][indice]
        area_t1 = sum(areas[indice])
        area_t2 = sum(fila[indice] for fila in areas)
        balances.append(BalanceCobertura(
            clase=nombre,
            area_t1_ha=area_t1,
            area_t2_ha=area_t2,
            entradas_ha=area_t2 - persistencia,
            salidas_ha=area_t1 - persistencia,
            neto_ha=area_t2 - area_t1,
            persistencia_ha=persistencia,
            persistencia_pct=(persistencia / area_t1 * 100) if area_t1 else None,
        ))

    return ResumenTransicion(
        clases=nombres,
        matriz=matriz,
        balance=tuple(balances),
        total_pixeles=total_pixeles,
        area_total_ha=area_total_ha,
    )


def construir_estadisticas_cambios(
    histograma: Dict[str, float],
    total_pixeles: float | None,
    centro: tuple[float, float],
) -> List[EstadisticaCambio]:
    """Convierte un histograma de categorías en tarjetas ordenadas por porcentaje.

    Categorías menores al umbral se omiten de las tarjetas, pero permanecen
    en la matriz de transición. ``None`` o cero píxeles significa no-data.
    """
    lon, lat = centro
    if not total_pixeles:
        return [EstadisticaCambio(
            titulo="Sin datos válidos",
            coords=f"{lat:.3f}, {lon:.3f}",
            porcentaje="—",
            nivel="SIN DATOS",
            color="#909097",
            detalle="No hay píxeles válidos para comparar",
        )]

    filas: List[EstadisticaCambio] = []
    items_ordenados = sorted(histograma.items(), key=lambda item: item[1], reverse=True)

    for categoria_str, conteo in items_ordenados:
        categoria_id = int(float(categoria_str))
        if categoria_id == 0:
            continue

        porcentaje = (conteo / total_pixeles) * 100
        if porcentaje < _PORCENTAJE_MINIMO_RELEVANTE:
            continue

        categoria = CATEGORIAS_CAMBIO[categoria_id]
        if porcentaje > _UMBRAL_ALTO:
            nivel, color = "ALTO", "#ff6b6b"
        elif porcentaje > _UMBRAL_MEDIO:
            nivel, color = "MEDIO", "#ffb95f"
        else:
            nivel, color = "BAJO", categoria.color

        filas.append(EstadisticaCambio(
            titulo=categoria.nombre,
            coords=f"{lat:.3f}, {lon:.3f}",
            porcentaje=f"{porcentaje:.1f}%",
            nivel=nivel,
            color=color,
            detalle=f"{int(conteo)} px afectados",
        ))

    if not filas:
        filas = [EstadisticaCambio(
            titulo="Sin cambios significativos",
            coords=f"{lat:.3f}, {lon:.3f}",
            porcentaje="0.0%",
            nivel="BAJO",
            color=CATEGORIAS_CAMBIO[0].color,
            detalle="No se detectaron variaciones relevantes",
        )]

    return filas
