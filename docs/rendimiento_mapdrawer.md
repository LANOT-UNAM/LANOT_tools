# Rendimiento de mapdrawer y recursos compartidos (2026-10-04)

Registro de lo que se midió, lo que se cambió y lo que se decidió no hacer. Todos los
cambios dan la **misma imagen píxel por píxel** salvo el gpkg simplificado (≤ 1 px).

## Dónde se iba el tiempo

Perfil (`cProfile`) de `mapdrawer` sobre CONUS C02 de 10000×6000 con tres capas,
retícula, logo y fecha: **22 s**.

| | antes | qué era |
|---|---|---|
| codificar el PNG | 13.4 s | zlib nivel 6 (el de Pillow), un hilo |
| `draw_shapefile` | 6.7 s | 1.1 M llamadas a `pyproj.transform`, una por punto |
| dibujo de Pillow (`draw_lines`) | 0.08 s | — |

Conclusión: **Pillow no es el problema.** Se evaluó reemplazarlo con una biblioteca crecida
desde `hpsatviews/include/image.h` y se descartó: a `image.h` le falta casi todo lo que usa
LANOT_tools (texto TrueType con halo, líneas con grosor, polígonos, remuestreo a razón
arbitraria, lectura PNG/JPEG), obligaría a compilar un puente C en el venv y en el `.sif`
(Python 3.9), hpsatviews es GPL-3.0, y numpy/rasterio/pyproj seguirían. Si se quiere un
motor gráfico en C, tiene sentido dentro de hpsv, para hpsv.

## Cambios (todos en `main`)

| commit | cambio | efecto |
|---|---|---|
| `59b3777` | `draw_shapefile` proyecta cada trazo con una llamada (`_geo2pixel_array`, `_draw_path`); PNG con `compress_level=1` en mapdrawer y geotiff2view | CONUS: 22 s → 7.5 s; geotiff2view: 15 s → 6 s |
| `4ea0072` | `compress_level=1` en glm_renderer y ash_view_generator | ~3× al codificar, ~12 % más grande |
| `9c16871` | leer del gpkg solo las geometrías del recuadro (`fiona.filter(bbox=)`) | recorte 1453×1512: 2.8 s → 2.1 s |
| `2f8b16f` | con `--clip`, `LazyGeoTIFF` lee del GeoTIFF solo la ventana | 9 recortes de `crea_rgbs.sh` (`xargs -P4`): 10.7 s → 5.1 s |
| `5b165a4` | geotiff2view: banda uint8 con offset 0 sin pasar por int64 | 0.27 s → 0.01 s en 60 Mpx (solo CPT con offset 0) |
| `ac38ea2` | `LANOT_DIR` sustituye a `/usr/local/share/lanot` | para probar recursos sin instalarlos |
| `248aa61`, `fa99373` | `recursos.sha256`, `install.sh --verifica` / `--solo-recursos`; comparación con sha256sum (la base del `.sif` no trae `cmp`) | ver abajo |

Fuera del repo: `mexico_estados.gpkg` se simplificó a 0.001° (1,014,750 → 63,094
vértices, 16.4 → 1.1 MB; a 0.5 km/px la línea se mueve ≤ 1 px). Con eso las 9 vistas de
`crea_rgbs.sh` bajan otro 25 % (4.4 s → 3.4 s). Receta:

```bash
ogr2ogr -f GPKG -simplify 0.001 -nlt MULTILINESTRING -nln estados_lineas \
        mexico_estados.gpkg mexico_estados_original.gpkg estados_lineas
```

## Lo que se evaluó y no se hizo

- **Varios recortes en una sola corrida de mapdrawer**: con la lectura por ventana, lo
  compartible entre recortes es ~0.7 s (arranque de Python y lectura de capas). En un solo
  proceso sin paralelismo saldría más lento que `xargs -P 4`; con paralelismo interno se
  ganaría ~1–1.5 s a cambio de partir `main()` (~650 líneas). Con el gpkg simplificado lo
  compartible baja a ~0.4 s.
- **Recortar desde hpsv** (`hpsv rgb -c <recorte> -G`): ~6 s por recorte en CPU porque
  recalcula el RGB, y la malla no coincide (mexico 2071×1279 contra 2068×1278).
- **geotiff2view en float32** para el caso general: 2.5× más rápido, pero con offsets no
  enteros (173.15) podría cambiar el truncamiento de algún píxel.
- **Vectorizar la retícula**: 0.02–0.17 s.

Lo que queda caro en una vista: codificar el PNG (0.1–1.6 s según tamaño; JPEG tarda
~0.2 s), el arranque de Python (~0.4 s) y dibujar las capas.

## Recursos compartidos

Las CPT, los logos (`.svg`/`.pdf` y los `.png` que leen las herramientas) y
`recortes_coordenadas.csv` salen del repo; `recursos.sha256` dice qué va en qué ruta de
`/usr/local/share/lanot`. En cada servidor:

```bash
./install.sh --verifica            # solo reporta: FALTA / DIFIERE / SOBRA
sudo ./install.sh --solo-recursos  # actualiza recursos sin recrear el venv
```

Tras cambiar una CPT, un logo, los recortes o un gpkg: `./genera_manifiesto.sh` (si no,
`tests/test_recursos.py` falla). Las 16 CPT que hay instaladas y no están en el repo
(`irterm`, `SVGA*_TEMP`, `terascan`, `cenapred`…) no las usa ningún script de `~/lanot`;
`install.sh` no las toca y `--verifica` las lista como `SOBRA`.

**Pendiente de decidir: si los gpkg entran al repo** (~20 MB; `.git` pasaría de ~4 a ~24 MB
y cada cambio de gpkg suma su tamaño). Alternativas descartadas en la propuesta: Git LFS
(git-lfs en cada servidor) y release de GitHub (salida a internet al instalar). Mientras
tanto se copian a mano y el manifiesto los lista solo para que `--verifica` avise.

## Estado del despliegue (2026-10-04)

| dónde | estado |
|---|---|
| kawak (cadena GOES, `/opt/lanot-tools`) | instalado `fa99373`; `--verifica`: 37/37 |
| tahan (`/opt/lanot-tools`) | instalado `fa99373`; `--verifica`: 37/37 |
| tahan, `.sif` de polar2grid | pin `fa99373`, instalado 18:18; **falta verificar la primera pasada**: ver `LANOT_procesamiento_polar/docs/estado_y_pendientes.md` |
| laptop | `--verifica`: 37/37 |

`mexico_estados.gpkg` simplificado (sha256 `6222c73a…e8e1d`) en las tres máquinas. El
original de INEGI (sha256 `78189817…`) está en kawak y tahan como `mexico_estados2023.gpkg`
y en la laptop como `mexico_estados_original.gpkg`.
