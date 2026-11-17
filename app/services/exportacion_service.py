"""Servicio de exportación de resultados a distintos formatos.

En el proyecto original, ``generar_reporte_pdf`` era un placeholder:

    def generar_reporte_pdf(self):
        messagebox.showinfo("Informe PDF", "Funcionalidad en desarrollo")

Este servicio implementa exportación real a CSV, JSON, Excel (.xlsx) y
Word (.docx) siempre, y a PDF si la librería ``reportlab`` está disponible
(se declara en ``requirements.txt``).
"""
from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, Sequence

from app.core.exceptions import ExportacionError
from app.core.logging_config import obtener_logger
from app.models.proyecto import EstadisticaCambio

logger = obtener_logger("exportacion_service")


@dataclass
class ContextoReporte:
    """Datos necesarios para armar cualquiera de los reportes."""

    titulo_proyecto: str
    autor: str
    periodo_t1: str
    periodo_t2: str
    estadisticas: Sequence[EstadisticaCambio]
    imagen_resultado: Path | None = None  # captura del mapa/comparación, opcional

    @property
    def fecha_texto(self) -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M")


class ExportacionService:
    """Genera archivos de exportación en ``exports/`` a partir de un contexto."""

    def __init__(self, directorio_salida: Path) -> None:
        self.directorio_salida = directorio_salida
        self.directorio_salida.mkdir(parents=True, exist_ok=True)

    def _ruta(self, nombre_base: str, extension: str) -> Path:
        marca_tiempo = datetime.now().strftime("%Y%m%d_%H%M%S")
        return self.directorio_salida / f"{nombre_base}_{marca_tiempo}.{extension}"

    # ---------------------------------------------------------------- CSV
    def exportar_csv(self, contexto: ContextoReporte, nombre_base: str = "reporte_cambios") -> Path:
        ruta = self._ruta(nombre_base, "csv")
        try:
            with ruta.open("w", newline="", encoding="utf-8") as archivo:
                escritor = csv.writer(archivo)
                escritor.writerow(["Categoría", "Coordenadas", "Porcentaje", "Nivel", "Detalle"])
                for fila in contexto.estadisticas:
                    escritor.writerow([fila.titulo, fila.coords, fila.porcentaje, fila.nivel, fila.detalle])
        except OSError as error:
            raise ExportacionError(f"No se pudo exportar CSV: {error}") from error
        logger.info("Reporte CSV generado en %s", ruta)
        return ruta

    # --------------------------------------------------------------- JSON
    def exportar_json(self, contexto: ContextoReporte, nombre_base: str = "reporte_cambios") -> Path:
        ruta = self._ruta(nombre_base, "json")
        datos = {
            "proyecto": contexto.titulo_proyecto,
            "autor": contexto.autor,
            "fecha": contexto.fecha_texto,
            "periodo_t1": contexto.periodo_t1,
            "periodo_t2": contexto.periodo_t2,
            "estadisticas": [fila.a_diccionario() for fila in contexto.estadisticas],
        }
        try:
            ruta.write_text(json.dumps(datos, indent=2, ensure_ascii=False), encoding="utf-8")
        except OSError as error:
            raise ExportacionError(f"No se pudo exportar JSON: {error}") from error
        logger.info("Reporte JSON generado en %s", ruta)
        return ruta

    # -------------------------------------------------------------- Excel
    def exportar_excel(self, contexto: ContextoReporte, nombre_base: str = "reporte_cambios") -> Path:
        try:
            from openpyxl import Workbook
            from openpyxl.styles import Font, PatternFill
        except ImportError as error:
            raise ExportacionError("openpyxl no está instalado (ver requirements.txt).") from error

        ruta = self._ruta(nombre_base, "xlsx")
        libro = Workbook()
        hoja = libro.active
        hoja.title = "Cambios detectados"

        hoja.append(["Reporte de detección de cambios territoriales"])
        hoja.append([f"Proyecto: {contexto.titulo_proyecto}"])
        hoja.append([f"Autor: {contexto.autor}   Fecha: {contexto.fecha_texto}"])
        hoja.append([f"Periodo comparado: {contexto.periodo_t1} vs {contexto.periodo_t2}"])
        hoja.append([])

        encabezado = ["Categoría", "Coordenadas", "Porcentaje", "Nivel", "Detalle"]
        hoja.append(encabezado)
        fila_encabezado = hoja.max_row
        for celda in hoja[fila_encabezado]:
            celda.font = Font(bold=True, color="FFFFFF")
            celda.fill = PatternFill("solid", fgColor="1A2A3E")

        for fila in contexto.estadisticas:
            hoja.append([fila.titulo, fila.coords, fila.porcentaje, fila.nivel, fila.detalle])

        for columna in hoja.columns:
            ancho = max((len(str(celda.value)) for celda in columna if celda.value is not None), default=10)
            hoja.column_dimensions[columna[0].column_letter].width = min(ancho + 4, 50)

        try:
            libro.save(ruta)
        except OSError as error:
            raise ExportacionError(f"No se pudo exportar Excel: {error}") from error
        logger.info("Reporte Excel generado en %s", ruta)
        return ruta

    # --------------------------------------------------------------- Word
    def exportar_word(self, contexto: ContextoReporte, nombre_base: str = "reporte_cambios") -> Path:
        try:
            from docx import Document
            from docx.shared import Pt
        except ImportError as error:
            raise ExportacionError("python-docx no está instalado (ver requirements.txt).") from error

        ruta = self._ruta(nombre_base, "docx")
        documento = Document()

        documento.add_heading("TERRA_INTEL — Reporte de Cambios Territoriales", level=0)
        parrafo = documento.add_paragraph()
        parrafo.add_run(f"Proyecto: {contexto.titulo_proyecto}\n").bold = True
        parrafo.add_run(f"Autor: {contexto.autor}\n")
        parrafo.add_run(f"Fecha de generación: {contexto.fecha_texto}\n")
        parrafo.add_run(f"Periodo comparado: {contexto.periodo_t1} vs {contexto.periodo_t2}")

        documento.add_heading("Resumen ejecutivo", level=1)
        total = len(contexto.estadisticas)
        documento.add_paragraph(
            f"Se identificaron {total} categoría(s) de cambio con área relevante entre "
            f"ambas épocas analizadas. El detalle por categoría se muestra a continuación."
        )

        documento.add_heading("Tabla de cambios detectados", level=1)
        tabla = documento.add_table(rows=1, cols=5)
        tabla.style = "Light Grid Accent 1"
        encabezados = ["Categoría", "Coordenadas", "Porcentaje", "Nivel", "Detalle"]
        for i, texto in enumerate(encabezados):
            celda = tabla.rows[0].cells[i]
            celda.text = texto
            celda.paragraphs[0].runs[0].font.bold = True

        for fila in contexto.estadisticas:
            celdas = tabla.add_row().cells
            celdas[0].text = fila.titulo
            celdas[1].text = fila.coords
            celdas[2].text = fila.porcentaje
            celdas[3].text = fila.nivel
            celdas[4].text = fila.detalle

        if contexto.imagen_resultado and Path(contexto.imagen_resultado).exists():
            documento.add_heading("Comparación visual", level=1)
            documento.add_picture(str(contexto.imagen_resultado), width=Pt(400))

        documento.add_heading("Conclusiones", level=1)
        documento.add_paragraph(
            "Este reporte fue generado automáticamente por TERRA_INTEL a partir de la "
            "clasificación de cobertura terrestre (Random Forest) sobre imágenes Sentinel-2 "
            "y la comparación de las dos épocas seleccionadas."
        )

        try:
            documento.save(ruta)
        except OSError as error:
            raise ExportacionError(f"No se pudo exportar Word: {error}") from error
        logger.info("Reporte Word generado en %s", ruta)
        return ruta

    # ---------------------------------------------------------------- PDF
    def exportar_pdf(self, contexto: ContextoReporte, nombre_base: str = "reporte_cambios") -> Path:
        try:
            from reportlab.lib import colors
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.styles import getSampleStyleSheet
            from reportlab.lib.units import cm
            from reportlab.platypus import (
                Image as RLImage,
                Paragraph,
                SimpleDocTemplate,
                Spacer,
                Table,
                TableStyle,
            )
        except ImportError as error:
            raise ExportacionError("reportlab no está instalado (ver requirements.txt).") from error

        ruta = self._ruta(nombre_base, "pdf")
        estilos = getSampleStyleSheet()
        documento = SimpleDocTemplate(str(ruta), pagesize=A4)
        elementos = []

        elementos.append(Paragraph("TERRA_INTEL — Reporte de Cambios Territoriales", estilos["Title"]))
        elementos.append(Spacer(1, 0.3 * cm))
        elementos.append(Paragraph(f"<b>Proyecto:</b> {contexto.titulo_proyecto}", estilos["Normal"]))
        elementos.append(Paragraph(f"<b>Autor:</b> {contexto.autor}", estilos["Normal"]))
        elementos.append(Paragraph(f"<b>Fecha:</b> {contexto.fecha_texto}", estilos["Normal"]))
        elementos.append(Paragraph(
            f"<b>Periodo comparado:</b> {contexto.periodo_t1} vs {contexto.periodo_t2}", estilos["Normal"]
        ))
        elementos.append(Spacer(1, 0.6 * cm))

        if contexto.imagen_resultado and Path(contexto.imagen_resultado).exists():
            elementos.append(RLImage(str(contexto.imagen_resultado), width=15 * cm, height=9 * cm))
            elementos.append(Spacer(1, 0.6 * cm))

        elementos.append(Paragraph("Tabla de cambios detectados", estilos["Heading2"]))
        datos_tabla = [["Categoría", "Coordenadas", "%", "Nivel", "Detalle"]]
        for fila in contexto.estadisticas:
            datos_tabla.append([fila.titulo, fila.coords, fila.porcentaje, fila.nivel, fila.detalle])

        tabla = Table(datos_tabla, hAlign="LEFT", repeatRows=1)
        tabla.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1A2A3E")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F0F2F5")]),
        ]))
        elementos.append(tabla)

        elementos.append(Spacer(1, 0.6 * cm))
        elementos.append(Paragraph("Conclusiones", estilos["Heading2"]))
        elementos.append(Paragraph(
            "Reporte generado automáticamente a partir de la clasificación de cobertura "
            "terrestre y la matriz de transición entre las dos épocas seleccionadas.",
            estilos["Normal"],
        ))

        try:
            documento.build(elementos)
        except Exception as error:
            raise ExportacionError(f"No se pudo exportar PDF: {error}") from error
        logger.info("Reporte PDF generado en %s", ruta)
        return ruta

    def exportar_todos(self, contexto: ContextoReporte, formatos: Iterable[str]) -> list[Path]:
        """Exporta en varios formatos a la vez. ``formatos`` p.ej. {"csv","pdf"}."""
        generadores = {
            "csv": self.exportar_csv,
            "json": self.exportar_json,
            "excel": self.exportar_excel,
            "word": self.exportar_word,
            "pdf": self.exportar_pdf,
        }
        rutas = []
        for formato in formatos:
            generador = generadores.get(formato)
            if generador is None:
                raise ExportacionError(f"Formato de exportación desconocido: {formato}")
            rutas.append(generador(contexto))
        return rutas
