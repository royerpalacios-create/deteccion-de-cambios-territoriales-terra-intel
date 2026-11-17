# TERRA_INTEL — Detección de Cambios Territoriales con Imágenes Satelitales

Aplicación de escritorio para detectar y analizar cambios territoriales
(urbanización, pérdida/ganancia de vegetación, variación de cuerpos de
agua) comparando dos épocas de imágenes Sentinel-2 mediante clasificación
de cobertura terrestre (Random Forest) sobre Google Earth Engine.

Reingeniería completa del proyecto académico original (POO II), reescrito
con arquitectura en capas, corrección de errores reales y exportación de
reportes funcional. Ver `CHANGELOG.md` para el detalle de lo que cambió y
`docs/ARCHITECTURE.md` para el diseño técnico.

## Requisitos previos

- Python 3.10 o superior.
- Una cuenta de Google Earth Engine (gratuita) con un proyecto de Google
  Cloud registrado. Si no tienes una, créala en
  https://code.earthengine.google.com/register.

## Instalación

```bash
pip install -r requirements.txt
```

La interfaz usa **PyQt6**, que se instala por `pip` y no requiere Tkinter.
En Linux, si la app no abre y menciona `xcb-cursor`, instala `sudo apt install libxcb-cursor0`.

### Autenticar Earth Engine (solo la primera vez)

```bash
python -c "import ee; ee.Authenticate()"
```

Esto abrirá el navegador para iniciar sesión con tu cuenta de Google. Las
credenciales quedan guardadas localmente; no hace falta repetir este paso
en ejecuciones futuras.

Por defecto la app usa el proyecto de Earth Engine `dctiis`. Si tu proyecto
de Google Cloud se llama distinto, cámbialo en **Herramientas → Configuración**
dentro de la app, o edita `config/default_settings.json` antes del primer
arranque.

## Ejecución

```bash
python main.py
```

Esto abre la interfaz gráfica (splash screen → ventana principal). El modo oscuro/claro se cambia al instante desde **Ver → Alternar tema** o el botón 🌗 Tema.

### Modo consola (sin interfaz gráfica)

```bash
python main.py --console
```

Ejecuta el pipeline completo (adquisición → clasificación → detección de
cambios) sobre el área de estudio por defecto y genera un mapa interactivo
en `exports/mapa_cambios.html`.

## Uso básico de la interfaz

1. **Archivo → Nuevo proyecto** (o simplemente abre la app).
2. **🛰️ Earth Engine** (o **Análisis → Seleccionar área y cargar imágenes…**,
   `Ctrl+E`): elige una región del Perú o escribe coordenadas, el radio del
   área y los dos periodos (por defecto 2019 y 2024). La app valida las
   fechas y descarga los mosaicos Sentinel-2. Si el radio es grande baja la
   resolución sola (se indica en el diálogo) para que Earth Engine pueda
   procesarlo. El diálogo recuerda tu última selección. En la pestaña
   **Mapa y coordenadas** puedes navegar por un mapa (ver más abajo),
   buscar un lugar por nombre o hacer clic para colocar el centro del área.
3. **🔍 Detectar cambios**: genera muestras de entrenamiento sobre tu área
   (índices NDVI/NDWI/NDBI), clasifica ambas épocas (Random Forest) y calcula
   la matriz de transición entre clases de cobertura. Funciona en cualquier
   zona, no solo en Puno. En `logs/terra_intel.log` queda el tiempo de cada fase.
   El panel presenta la matriz T1→T2 en hectáreas y porcentaje, además del
   balance por clase (área inicial/final, entradas, salidas, cambio neto y
   persistencia). Las celdas sin observaciones válidas se indican como no-data,
   separadas de las transiciones cuyo valor medido es cero.
4. Usa el panel de capas (izquierda) para mostrar/ocultar la Época A, la
   Época B o la capa de cambios, y ajustar su opacidad.
5. **🔀 Vista**: alterna entre superposición de colores (overlay),
   comparación deslizante (swipe, con el control inferior) y **mapa**: la
   imagen y la capa de cambios georreferenciadas sobre un mapa navegable.
   Para ver los cambios sobre el mapa base, desmarca «Época B» (y «Época A») en
   el panel de capas.
6. **Archivo → Exportar reporte**: genera CSV, JSON, Excel, Word o PDF con
   la tabla de cambios detectados.
7. **Archivo → Guardar proyecto**: guarda las coordenadas y resultados
   actuales en `data/*.tiproj` para reabrirlos después.

### Mapa interactivo

El mapa se dibuja con Qt (no usa un navegador embebido): arrastra para mover,
rueda o doble clic para acercar, `+`/`−` y flechas del teclado, botón **⌖**
para encuadrar el área de estudio. Arriba a la derecha eliges la capa base:
**Calles (OpenStreetMap)** o **Satélite (Esri)**. Incluye barra de escala,
coordenadas del cursor y la atribución que exigen esos proveedores.

- Necesita **internet** para descargar los mapas y para el buscador de
  lugares (Nominatim de OpenStreetMap, con una consulta por cada clic en
  «Buscar»). Si no hay conexión el mapa lo avisa y el resto de la app sigue
  funcionando.
- Los mapas descargados se guardan en `cache/teselas/` (se puede borrar sin
  problema), así que repetir una zona no vuelve a descargar nada.
- Uso de los servidores: OpenStreetMap y Esri son servicios gratuitos con
  condiciones de uso (identificación de la aplicación, atribución, sin
  descargas masivas). Es adecuado para uso académico y personal; si algún día
  distribuyes la aplicación, revisa sus términos.

## Ejecutar las pruebas

```bash
pip install pytest   # ya incluido en requirements.txt
pytest tests/ -v
```

Las pruebas cubren modelos de dominio, configuración persistente, las
utilidades de cálculo de estadísticas y la interfaz (`tests/test_ui_smoke.py`,
que corre Qt en modo *offscreen* con Earth Engine simulado). No requieren
credenciales de Earth Engine ni monitor; si PyQt6 no está instalado, las
pruebas de UI se omiten solas.

## Estructura del proyecto

Ver `docs/ARCHITECTURE.md` para el detalle completo de cada carpeta.

```
main.py            # punto de entrada (GUI o --console)
app/                # código de la aplicación (core/models/services/ui/utils)
scripts/            # pipeline de consola
config/             # configuración por defecto y del usuario
data/               # proyectos guardados (.tiproj)
exports/            # reportes e imágenes exportadas
logs/               # logs de ejecución
tests/              # pruebas unitarias
docs/               # documentación técnica
```

## Solución de problemas

**"Earth Engine no está conectado" / la app muestra una advertencia al
iniciar** — Ejecuta `python -c "import ee; ee.Authenticate()"` y reinicia
la aplicación. Revisa también que el ID de proyecto en **Herramientas →
Configuración** corresponda a un proyecto de Google Cloud real con la API
de Earth Engine habilitada.

**"No se encontraron imágenes para esta ubicación"** — Sentinel-2 no
siempre tiene cobertura sin nubes en todas las fechas/lugares. Prueba con
otra coordenada o sube el umbral de nubes en Configuración.

**El mapa se ve en gris / dice "Sin conexión"** — No se pudieron descargar los
mapas (sin internet, un cortafuegos o el servidor ocupado). Prueba otra capa
base con el selector del mapa; se reintenta solo cada pocos segundos.

**La detección de cambios está deshabilitada** — La detección requiere que
ambas imágenes se hayan cargado desde Earth Engine (no desde archivo
local), porque necesita las bandas espectrales originales para clasificar.

## Licencia

MIT — ver `LICENSE`.
