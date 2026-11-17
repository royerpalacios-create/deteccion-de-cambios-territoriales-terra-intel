# Arquitectura de TERRA_INTEL

## Visión general

TERRA_INTEL sigue una arquitectura en capas inspirada en Clean Architecture,
adaptada al tamaño real del proyecto (una aplicación de escritorio con
PyQt6, no un backend distribuido). El objetivo es que cada
carpeta tenga una única responsabilidad y que las capas superiores no
conozcan detalles de las inferiores.

```
main.py                    # entry point raíz (GUI o --console)
scripts/
  pipeline_consola.py       # pipeline RS-1→RS-2→RS-3 sin interfaz gráfica

app/
  main.py                   # arranque de la app (config + splash + ventana)
  core/                      # infraestructura transversal
    config.py                #   AppConfig + GestorConfiguracion (JSON persistido)
    logging_config.py        #   logger único de la app (logs/terra_intel.log)
    exceptions.py             #   jerarquía de excepciones propias
  models/                    # entidades de dominio (dataclasses, sin lógica de negocio)
    area_estudio.py           #   AreaDeEstudio (ROI)
    cobertura.py               #   ClaseCobertura, CategoriaCambio
    proyecto.py                #   Proyecto, EstadisticaCambio (guardar/cargar .tiproj)
  services/                  # lógica de negocio / casos de uso
    earth_engine_service.py   #   ciclo de vida de la conexión EE
    adquisicion_service.py     #   RS-1: adquisición Sentinel-2
    clasificacion_service.py   #   RS-2: clasificación Random Forest
    deteccion_cambios_service.py # RS-3: matriz de transición y capa de cambios
    exportacion_service.py     #   CSV / JSON / Excel / Word / PDF
    teselas_service.py          #   descarga de teselas de mapa + caché LRU (memoria) y en disco
    geocodificacion_service.py   #   búsqueda de lugares por nombre (Nominatim)
    proyecto_service.py         #   guardar/abrir proyecto + recientes
  ui/                         # capa de presentación (PyQt6)
    theme.py                   #   paletas + hoja de estilos QSS (tema en vivo)
    trabajo.py                 #   hilos de fondo para tareas lentas (EE, descargas)
    splash.py                   #   pantalla de bienvenida
    main_window.py               #   orquesta ribbon + sidebar + mapa + status bar
    widgets/
      ribbon.py                   #   menú desplegable + accesos rápidos
      layer_panel.py               #   checkboxes de capas + opacidad
      results_panel.py             #   tarjetas de estadísticas de cambio
      map_canvas.py                 #   composición real overlay/swipe
      map_view.py                    #   mapa navegable (teselas, zoom, capas georreferenciadas)
      area_dialog.py                  #   selector de área: regiones, mapa, buscador, periodos
      status_bar.py                 #   barra de estado inferior
      settings_dialog.py             #   panel de configuración
      about_dialog.py                 #   acerca de
  utils/                       # funciones puras, reutilizables, sin estado
    image_utils.py               #   carga/composición de imágenes (PIL)
    geo.py                        #   Web Mercator, teselas, escala (funciones puras)
    tiempo.py                      #   cronómetro por fase para el log
    stats.py                      #   construcción de filas de estadísticas

config/
  default_settings.json        # valores por defecto (versionado)
  settings.json                 # preferencias del usuario (generado, ignorado por git)

data/       # proyectos guardados (.tiproj)
exports/    # reportes generados (csv/json/xlsx/docx/pdf/png/html)
logs/       # logs de ejecución
tests/      # pruebas (modelos, config, utils y UI en modo offscreen — sin Earth Engine)
```

## Principios aplicados

- **Separación de responsabilidades**: la UI (`app/ui`) nunca llama
  directamente a `ee.*`; siempre pasa por un servicio (`app/services`). Los
  servicios nunca crean widgets. Los modelos (`app/models`) son datos, no
  comportamiento de UI.
- **Inyección de dependencias simple**: `MainWindow` recibe un
  `GestorConfiguracion` ya construido y crea sus propios servicios a partir
  de la configuración, en vez de leer variables globales.
- **Import perezoso de Earth Engine**: módulos como `area_estudio.py` o los
  servicios importan `ee` dentro de los métodos que lo necesitan, no en la
  cabecera del archivo. Esto permite testear modelos y utilidades puras sin
  tener credenciales de Earth Engine configuradas.
- **Un solo lugar de verdad por concepto**: colores de categorías de cambio,
  clases de cobertura, y parámetros de visualización viven una sola vez en
  `app/models/cobertura.py`, en vez de estar repetidos en varios archivos
  como en el proyecto original.

## Flujo de trabajo típico

1. `app/main.py` crea `GestorConfiguracion`, muestra el splash y construye
   `MainWindow`.
2. `MainWindow` inicializa `EarthEngineService` en segundo plano.
3. El usuario carga imágenes (`cargar_desde_ee` → `AdquisicionService`) o
   archivos locales.
4. `detectar_cambios()` lanza un hilo (`threading.Thread`) que llama a
   `ClasificacionService` y luego a `DeteccionCambiosService`, evitando
   congelar la interfaz mientras Earth Engine procesa.
5. El resultado se compone visualmente en `MapCanvas` (overlay o swipe) y se
   resume en `ResultsPanel`.
6. El usuario exporta con `ExportacionService` (CSV/JSON/Excel/Word/PDF) o
   guarda el proyecto con `ProyectoService`.

## Qué se simplificó a propósito

Esta reconstrucción prioriza una base de código real, correcta y
mantenible por sobre una réplica pixel-perfect de ArcGIS Pro. En concreto:

- El "Ribbon" es un menú clásico de Qt + una barra de accesos rápidos, no un
  framework de ribbon con pestañas contextuales (Qt no ofrece esto de
  forma nativa y construir uno desde cero no aportaría robustez real).
- No hay un motor de mapas con teselas (OSM/Google/Hybrid) embebido de
  forma interactiva dentro de la ventana Qt: se sigue el enfoque del
  proyecto original (thumbnails/composición con PIL, pintados con
  `QPainter`) en vez de incrustar un navegador (`QtWebEngine`). El modo
  `--console` sí genera un mapa interactivo real (Leaflet, vía `geemap`) en
  `exports/mapa_cambios.html`.
- Los reportes PDF/Word no incluyen gráficos estadísticos generados
  dinámicamente (histogramas); incluyen tablas y, si hay una captura
  guardada, la imagen del resultado.
