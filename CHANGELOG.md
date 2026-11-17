# Changelog

Todas las mejoras notables de este proyecto se documentan en este archivo.

## [Sin publicar] — Mapa interactivo

### Añadido
- **Mapa navegable** hecho con Qt puro (`app/ui/widgets/map_view.py`), sin añadir
  dependencias: arrastrar, zoom con rueda/doble clic/teclado, capas base de
  calles (OpenStreetMap) y satélite (Esri), barra de escala, coordenadas y atribución.
- **Selector de área con mapa**: el diálogo tiene ahora la pestaña «Mapa y
  coordenadas» con buscador de lugares (Nominatim), clic para elegir el centro,
  y el cuadrado del área dibujado y sincronizado con el radio y los campos.
- **Vista «Mapa»** en la ventana principal (overlay → swipe → mapa): la imagen
  satelital y la capa de cambios georreferenciadas sobre el mapa base.
- `app/services/teselas_service.py`: descarga de teselas con caché LRU en memoria
  y caché en disco (`cache/teselas/`); `app/utils/geo.py`: proyección Web
  Mercator, índices de teselas y escala, con pruebas contra valores de referencia.
- 78 pruebas nuevas (matemáticas del mapa, descarga contra un servidor HTTP local,
  widget, diálogo y vista de mapa).

## [Sin publicar] — Selector de área, periodos y correcciones

### Añadido
- **Selector de área de estudio** (`AreaEstudioDialog`) conectado al flujo:
  regiones del Perú o coordenadas manuales, radio y periodos T1/T2 a elección.
  Valida las fechas (formato, orden, Sentinel-2 desde 2017-03-28, sin futuro) y
  recuerda la última selección. Se abre con el botón «Earth Engine» o `Ctrl+E`.
- Escala de análisis adaptativa (`calcular_escala_metros`): mantiene el cálculo
  por debajo de 4 M de píxeles por época bajando la resolución en áreas grandes.
- Tiempos por fase en el log (`app/utils/tiempo.py`) y descarga de las dos
  miniaturas en paralelo.

### Corregido
- La detección fuera de Puno fallaba con «No valid training data were found»:
  el área no se pasaba al clasificador y caía a los 8 puntos fijos de Puno.
- `generar_muestras_sobre_roi` usaba `sample(numPixels=…)`, que reparte los
  puntos sobre toda la región y descarta los enmascarados (una clase poco
  frecuente quedaba casi sin muestras). Ahora usa `stratifiedSample`.
- Pestaña «Coordenadas manuales» vacía: los campos se destruían al construir el
  diálogo (el widget contenedor quedaba sin referencia).
- Colores de las tarjetas de resultados: Qt lee `#RRGGBBAA` como `#AARRGGBB`, así
  que los sufijos `22`/`55`/`cc` cambiaban el color en vez de hacerlo translúcido
  (ahora `rgba()`). Los fondos fijos oscuros rompían el tema claro.
- Una regla `font-family` global en el QSS pisaba las fuentes monoespaciadas.
- Resultados de una zona anterior seguían visibles tras cargar otra.
- Etiquetas de épocas, informes y proyectos usaban 2019/2024 fijos; ahora los
  periodos reales. Nombres de archivo de proyecto saneados (`Lima – Centro` →
  `Lima_Centro.tiproj`). Mensajes de error claros para muestras y tiempo agotado.
- Radio por defecto unificado en 10 km (`config.py`, `default_settings.json`).

## Migración de la interfaz a PyQt6

### Cambiado
- La capa `app/ui` pasó de CustomTkinter a **PyQt6**. Servicios, modelos,
  utilidades y el modo `--console` no se tocaron (ya no dependían de Tk).
- `requirements.txt`: se reemplaza `customtkinter` por `PyQt6`.
- El tema claro/oscuro ahora vive en una hoja de estilos Qt (QSS) generada
  desde las paletas de `theme.py`.

### Mejorado
- Las operaciones lentas (conectar con Earth Engine, cargar mosaicos y
  descargar thumbnails, detectar cambios) corren en hilos de fondo
  (`app/ui/trabajo.py`): la ventana ya no se congela. Antes, cargar desde EE
  y la vista previa bloqueaban la interfaz.
- El cambio de tema se aplica **al instante**, sin reiniciar.
- El mapa se recompone al redimensionar la ventana, y "Capturar" guarda lo
  que se ve (incluidas las etiquetas ANTES/DESPUÉS).
- Las imágenes descargadas se guardan en memoria; ya no se vuelven a bajar
  al refrescar la vista previa.
- Atajos de teclado: Ctrl+N / O / S / D / Q y Ctrl+, (configuración).
- Pruebas de humo de la UI (`tests/test_ui_smoke.py`), en modo offscreen.

## [2.0.0] — Reingeniería completa

### Arquitectura
- Se reestructuró el proyecto de 4 archivos sueltos (`Proyecto.py`,
  `adquisicion_datos.py`, `clasificacion_cobertura.py`, `interfaz.py`, este
  último de 993 líneas) a un paquete `app/` en capas
  (`core/models/services/ui/utils`), ver `docs/ARCHITECTURE.md`.
- Se eliminó el acoplamiento entre lógica de Earth Engine y widgets de
  Tkinter: ahora la UI solo llama a servicios (`AdquisicionService`,
  `ClasificacionService`, `DeteccionCambiosService`, `ExportacionService`).
- Se añadió inyección de configuración (`GestorConfiguracion`) en vez de
  constantes fijas repartidas por el código (`project="dctiis"`, `20`% de
  nubes, tema oscuro fijo, etc.).

### Corrección de errores
- **Bug crítico corregido**: `mostrar_resultado_deteccion()` en el
  `interfaz.py` original ignoraba las imágenes reales descargadas y
  dibujaba círculos de relleno con `ImageDraw` a modo de maqueta — el
  resultado real de la detección nunca se veía en pantalla. Ahora
  `MapCanvas` compone de verdad las imágenes T1/T2/capa de cambios
  (`componer_overlay`, `componer_swipe`).
- Se reemplazó el reporte PDF, que era un `messagebox.showinfo("... en
  desarrollo")`, por exportación real a PDF (reportlab), además de CSV,
  JSON, Excel (openpyxl) y Word (python-docx).
- Se reemplazaron los `print()` de estado por logging real
  (`logs/terra_intel.log`) con niveles y timestamps.
- Se añadió manejo de errores tipado (`app/core/exceptions.py`) en vez de
  `except Exception` genéricos silenciosos.

### Funcionalidades nuevas
- Panel de capas con visibilidad y opacidad independientes por capa
  (Época A, Época B, capa de cambios).
- Barra de estado con indicador de conexión a Earth Engine, coordenadas,
  escala y zoom.
- Guardar/abrir proyecto (`.tiproj`) con lista de proyectos recientes.
- Panel de configuración persistente (tema, mapa base, proyecto de Earth
  Engine, umbral de nubes, autoguardado).
- Splash screen de arranque.
- Menú Archivo/Ver/Capas/Análisis/Herramientas/Ayuda + barra de accesos
  rápidos, además de los botones ya existentes.
- Diálogo "Acerca de".
- Captura del área de visualización a PNG.
- Modo consola (`python main.py --console`) que ejecuta el pipeline
  RS-1→RS-2→RS-3 y genera un mapa interactivo real en HTML (Leaflet, vía
  `geemap`), reemplazando al antiguo `Proyecto.py`.

### Calidad de código
- Type hints y docstrings en todos los módulos nuevos.
- Suite de pruebas unitarias (`tests/`) para modelos, configuración y
  utilidades puras (sin dependencia de Earth Engine ni de Tkinter),
  ejecutable con `pytest`.
- `requirements.txt` actualizado con las librerías de exportación.

## [1.0.0] — Versión original

- Proyecto académico base: adquisición Sentinel-2 (RS-1), clasificación de
  cobertura con Random Forest (RS-2) y comparación temporal (RS-3), con una
  interfaz de escritorio en CustomTkinter.
