"""Catálogo de regiones del Perú para el selector de área de estudio.

Cubre los 25 departamentos con coordenadas representativas de su capital
o zona más relevante para análisis de cambio de cobertura. El radio por
defecto es 10 km (10 000 m), ajustable desde la UI.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List


@dataclass(frozen=True)
class RegionPeru:
    nombre: str          # nombre visible en la UI
    departamento: str    # departamento oficial
    latitud: float
    longitud: float
    radio_metros: int = 10_000   # radio buffer alrededor del centro


# ── Catálogo ────────────────────────────────────────────────────────────────
REGIONES_PERU: List[RegionPeru] = [
    # Amazonas
    RegionPeru("Chachapoyas",         "Amazonas",       -6.2287, -77.8692),
    # Áncash
    RegionPeru("Huaraz",              "Áncash",         -9.5269, -77.5278),
    # Apurímac
    RegionPeru("Abancay",             "Apurímac",       -13.6354, -72.8815),
    # Arequipa
    RegionPeru("Arequipa",            "Arequipa",       -16.4090, -71.5375),
    RegionPeru("Majes – Siguas",      "Arequipa",       -16.3500, -72.2500),
    # Ayacucho
    RegionPeru("Ayacucho",            "Ayacucho",       -13.1588, -74.2236),
    # Cajamarca
    RegionPeru("Cajamarca",           "Cajamarca",      -7.1638,  -78.5001),
    # Callao
    RegionPeru("Callao",              "Callao",         -12.0566, -77.1181),
    # Cusco
    RegionPeru("Cusco",               "Cusco",          -13.5320, -71.9675),
    RegionPeru("Machu Picchu",        "Cusco",          -13.1631, -72.5450),
    # Huancavelica
    RegionPeru("Huancavelica",        "Huancavelica",   -12.7869, -74.9729),
    # Huánuco
    RegionPeru("Huánuco",             "Huánuco",        -9.9306,  -76.2401),
    # Ica
    RegionPeru("Ica",                 "Ica",            -14.0678, -75.7286),
    RegionPeru("Paracas",             "Ica",            -13.8329, -76.2484),
    # Junín
    RegionPeru("Huancayo",            "Junín",          -12.0651, -75.2049),
    # La Libertad
    RegionPeru("Trujillo",            "La Libertad",    -8.1116,  -79.0288),
    # Lambayeque
    RegionPeru("Chiclayo",            "Lambayeque",     -6.7714,  -79.8409),
    # Lima
    RegionPeru("Lima – Centro",       "Lima",           -12.0464, -77.0428),
    RegionPeru("Lima – Cono Norte",   "Lima",           -11.8500, -77.0500),
    RegionPeru("Lima – Cono Sur",     "Lima",           -12.2500, -76.9500),
    # Loreto
    RegionPeru("Iquitos",             "Loreto",         -3.7491,  -73.2538),
    RegionPeru("Datem del Marañón",   "Loreto",         -4.5000,  -76.8000),
    # Madre de Dios
    RegionPeru("Puerto Maldonado",    "Madre de Dios",  -12.5932, -69.1892),
    RegionPeru("Tambopata",           "Madre de Dios",  -12.8300, -69.2800),
    # Moquegua
    RegionPeru("Moquegua",            "Moquegua",       -17.1942, -70.9347),
    # Pasco
    RegionPeru("Cerro de Pasco",      "Pasco",          -10.6861, -76.2601),
    # Piura
    RegionPeru("Piura",               "Piura",          -5.1945,  -80.6328),
    RegionPeru("Sechura",             "Piura",          -5.5578,  -80.8228),
    # Puno
    RegionPeru("Puno (Lago Titicaca)","Puno",           -15.8402, -70.0219),
    RegionPeru("Juliaca",             "Puno",           -15.4994, -70.1336),
    # San Martín
    RegionPeru("Tarapoto",            "San Martín",     -6.4851,  -76.3580),
    # Tacna
    RegionPeru("Tacna",               "Tacna",          -18.0066, -70.2463),
    # Tumbes
    RegionPeru("Tumbes",              "Tumbes",         -3.5669,  -80.4515),
    # Ucayali
    RegionPeru("Pucallpa",            "Ucayali",        -8.3791,  -74.5539),
]

# Índice por nombre para búsqueda rápida
REGIONES_POR_NOMBRE: Dict[str, RegionPeru] = {r.nombre: r for r in REGIONES_PERU}


def region_por_nombre(nombre: str) -> RegionPeru | None:
    return REGIONES_POR_NOMBRE.get(nombre)


def nombres_regiones() -> List[str]:
    return [r.nombre for r in REGIONES_PERU]

