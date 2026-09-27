# Plan: LANOT_tools emite Items de STAC

Continuación, del lado de LANOT_tools, de
`~/lanot/hpsatviews/docs/stac/STAC_PLAN.md`. hpsv ya emite un Item con `-j` y
`mapdrawer -m` ya lo lee (fase 4 de ese plan). Lo que faltaba es que las
herramientas de este repositorio **escriban** el suyo.

## Principio

El Item lo emite la herramienta que escribe el producto, en el momento en que
lo conoce todo. En la cadena de mesoescala la imagen publicada la escribe
`mapdrawer`, no `hpsv`; en los polares (VIIRS, Metop, MiRS, OMPS) la escribe
`geotiff2view` y hoy nadie emite Item. Collection, Catalog e índice siguen
siendo de un servicio aparte.

## Decisiones tomadas (2026-09-26)

- **Identidad: Item propio.** La vista es `lanot_…`, no un activo añadido al
  Item de hpsv. Con `-m`, el id es el de hpsv con `lanot_` en lugar de `hpsv_`,
  y lleva `links: [{rel: "derived_from"}]` al de hpsv. No se fusionan archivos,
  por la misma razón que D1 de hpsatviews.
- **Convivencia: aditiva.** `--stac` escribe el Item *además* del JSON plano de
  `mapdrawer --o_crs`, que siguen leyendo los guiones de meso y el visor. El
  plano se retira al final, cuando nadie lo lea.

## Fase A — `stac_item.py` — HECHA 2026-09-26 (commit en `main`)

- `footprint(crs, bounds)`: huella en EPSG:4326, port de
  `hpsatviews/tools/stac_sweep.py` sobre pyproj. Limbo por bisección,
  antimeridiano plegado (W > E).
- `canonical_platform()`: `G19→goes-19`, `j01/n20/NOAA-20→noaa-20`,
  `npp→suomi-npp`, `Metop-C→metop-c`.
- `build_id()`: `lanot_<SAT>[_<SECTOR>]_<YYYYJJJ_hhmm>_<producto>`; si falta
  algo, `lanot_` más el nombre de la salida. Nunca inventa un producto.
- `build_asset()`, `build_item()`, `emit()`. El activo lleva su propia rejilla
  (`proj:transform`, `proj:shape`, `proj:wkt2`, `proj:epsg` si hay) y además
  `proj:bbox`, que es exactamente el `bounds` del JSON plano.
- Sin `eo:bands` ni `raster:bands`: los activos son de 8 bits (misma regla que hpsv).

## Fase B — `--stac` en las herramientas — HECHA 2026-09-26 (commit en `main`, sin desplegar)

- `mapdrawer --stac [RUTA]`, `geotiff2view --stac [RUTA]`. Sin RUTA el Item va
  junto a la imagen como `<id>.json`: nombrado por el id para no chocar con el
  JSON plano, que se llama como la imagen.
- Huella: con `-m` se hereda del Item de hpsv (reproyectar o anotar no cambia
  dónde hay dato; el rectángulo en 3857 de un disco completo reclamaría esquinas
  de nodato). Con `--clip`/`--bounds`, la caja de salida. Sin Item de origen, la
  rejilla de entrada tomada antes de `--lat-south` y `--o_crs`.
- Sin fecha, CRS o huella: exit 1, como `hpsv -j`. La imagen ya quedó escrita.
- Pruebas: `tests/test_stac_item.py`. La huella se compara vértice a vértice
  con los tres Items de hpsv de `tests/data` (tolerancia 2e-4°, sólo alcanzada
  en puntos del limbo). Cada Item se valida contra los esquemas oficiales,
  copiados en `tests/data/stac_schemas/`.

## Fase C — Mesoescala: adoptar el Item y retirar el JSON plano — PENDIENTE

### Quién lee hoy el JSON plano

Verificado el 2026-09-26. Hay tres consumidores, y **ninguno lee el JSON de
cada cuadro directamente para publicar**:

| Consumidor | Dónde corre | Qué lee | Para qué |
|---|---|---|---|
| `meso/crea_animaciones_meso.sh:81-84` | tren2, cron cada 10 min | `find -name '*_G*_m*.json'` en `$datadir`; del nombre saca sector y epoch, del contenido `.bounds` | Segmentar episodios: un cambio de `bounds` cierra el episodio |
| `meso/animameso.sh:150-190` | tren2, llamado por el anterior | JSON del **primer cuadro** como base (`$datadir/$oname.json`), le añade `episodio` y `cuadros` | Escribe `<animación>.json` junto al `.webm` y `latest.json` |
| `LANOT_pagina/visualizador_animaciones/views.py:19-30` | servidor web, por HTTP desde `vistas.lanot.unam.mx/animations/rgb/mesoescala/` | `bounds`, `crs` (busca `'3857'` en la cadena), `satellite`, `band`, `timestamp` del **JSON de la animación** | Coloca el video en Leaflet |

Consecuencia: el visor no ve el Item de los cuadros; ve lo que `animameso.sh`
escribe. Ese JSON es además **lo único que se conserva** (los PNG son
intermedios regenerables; se archiva a `/depot/goes-*/vistas/abi/meso/animaciones/`
con `almacena_meso_tren2.sh`). Así que el Item que más importa en meso es el de
la **animación**, y lo escribe `animameso.sh`, no `mapdrawer`.

### Decisiones que faltan antes del código

**C-D1. ¿Qué pasa con el Item de hpsv?** `crea_rgb_meso.py` corre dentro de un
`TemporaryDirectory`: el Item de hpsv y su PNG se borran al terminar. El
`derived_from` del Item de la vista quedaría apuntando a un archivo que no
existe. Opciones:
- (a) Copiar el Item de hpsv a `$datadir` junto al de la vista. Su activo
  (el PNG sin anotar) no estará: es exactamente el estado «capturado y
  eliminado» que D2 de hpsatviews quiere distinguible.
- (b) No enlazar: pasar `--stac` sin `-m`… no sirve, `-m` es lo que
  georreferencia. Habría que añadir a mapdrawer una opción para omitir el enlace.
- (c) Dejar el enlace colgante y documentarlo.

Recomendación: **(a)**. Es la única que no pierde información, y el coste es
un JSON de ~10 KB por cuadro que se purga con la misma regla que los PNG.
Depende de la decisión de retención que sigue abierta en STAC_PLAN.md.

**C-D2. ¿El JSON de la animación pasa a ser Item de STAC?** Recomendación: sí,
porque es el que se conserva. Un Item por episodio, con:
- `datetime: null`, `start_datetime`/`end_datetime` (inicio y fin del episodio);
- activo `video` (`.webm`, `video/webm`, roles `["visual"]`) con la rejilla
  de los cuadros (`proj:epsg: 3857`, `proj:transform`, `proj:shape`, `proj:bbox`);
- `geometry`/`bbox` heredados del Item del primer cuadro;
- `lanot:episodio` y `lanot:cuadros` con lo que hoy va en `episodio`/`cuadros`;
- `links` `derived_from` a los Items de los cuadros, si C-D1 los conserva.

El id tiene que ser estable al crecer el episodio (hoy `animameso.sh` reescribe
el mismo nombre mientras el episodio sigue vivo): usar el nombre de la
animación, que ya lo es.

**C-D3. ¿Cómo se llama el Item de cada cuadro en `$datadir`?** Hoy el plano es
`YYYYMMDD_hhmm_SAT_SECTOR.json`; el Item, `lanot_<SAT>_<SECTOR>_<YYYYJJJ_hhmm>_<modo>.json`.
Recomendación: dejarlo por id, y que los lectores tomen imagen, instante y
sector **del contenido** (`assets.image.href`, `properties.datetime`,
`properties["lanot:sector"]`) en vez del nombre. Es lo que ya hace
`crea_rgb_meso.py` con el Item de hpsv desde el incidente del 2026-09-08
(86 JSON con el satélite de otra corrida por emparejar por nombre).

### Pasos, en orden

El orden es **lectores tolerantes primero, escritores después, retiro al
final**. Así ningún paso necesita desplegar dos servidores a la vez, y cada uno
se revierte solo.

**C1. Integrar y desplegar las fases A y B.** Rama en LANOT_tools, commit,
merge a `main`, instalar en tren2 (`sudo ./install.sh`). Es aditivo: sin
`--stac` nada cambia. Comprobar `processing:software` en un Item de prueba:
debe decir la versión instalada, no `desconocida`.

**C2. `crea_rgb_meso.py` pasa `--stac`.** Añadir `--stac` a `cmd_mapdrawer`
(y, según C-D1, copiar el Item de hpsv a `outdir`). Aditivo: el JSON plano se
sigue escribiendo.
- **Trampa a cerrar en el mismo cambio:** el `find -name '*_G*_m*.json'` de
  `crea_animaciones_meso.sh:81` y `:97` también encaja con
  `lanot_G19_m1_….json` (y con `hpsv_G19_m1_….json` si se copian). Hoy se
  descartarían porque `.[0:13]` no parsea como fecha y el `awk '$2 != 0'` los
  tira, pero eso es suerte. Estrechar el patrón a `'[0-9]*_G*_m*.json'`.
- Verificar el purgado: la limpieza de cuadros de `$datadir` no está en
  `cron/mesoescala.cron` ni en los guiones versionados. Averiguar en tren2 qué
  la hace y que abarque `lanot_*.json` (y `hpsv_*.json`).

**C3. Lectores tolerantes.** Que cada lector acepte los dos formatos, con el
Item primero:
- `crea_animaciones_meso.sh`: leer los `lanot_*_m*.json`; `bounds` =
  `.assets.image["proj:bbox"]`, epoch = `.properties.datetime`, sector =
  `.properties["lanot:sector"]`, cuadro = `.assets.image.href`. Con respaldo al
  JSON plano mientras exista.
- `views.py` (LANOT_pagina, despliegue aparte): `_bounds_a_leaflet()` acepta un
  Item —`proj:bbox` y `proj:epsg` del activo `video`— o el formato actual.
  Satélite: `properties.platform` (`goes-19` → `G19`, la misma conversión que
  `Metadata.from_stac_item`); hora: `start_datetime` o `datetime`.

**C4. `animameso.sh` escribe el Item del episodio** (según C-D2), tomando como
base el Item del primer cuadro en vez del JSON plano. Mientras C3 no esté
desplegado en el web, conservar además las claves planas en la raíz (`bounds`,
`crs`, `satellite`, `band`, `timestamp`): el esquema del Item no las prohíbe.
Quitarlas en C5.

**C5. Retirar el JSON plano.**
- `mapdrawer --o_crs` deja de escribir `<imagen>.json` (`mapdrawer.py`, bloque
  «Sidecar JSON cuando se usó --o_crs»).
- `geotiff2view --save-metadata`: ningún guion la usa (verificado 2026-09-26;
  sólo `tests/test_geotiff2view.py:106`). Quitarla o hacerla alias de `--stac`.
- `Metadata.from_json_file()`/`save_json()`: borrar si ya nadie los llama.
- Quitar los respaldos al formato plano de C3 y las claves planas de C4.
- Actualizar `CLAUDE.md` («Metadata JSON = STAC Item», «Emitting STAC») y el README.

**C6. Polares (independiente de meso).** `crea_vistas_viirs.sh` y
`crea_vistas_metop.sh` pueden añadir `--stac` a `geotiff2view` en cuanto se
decida la retención: no tienen consumidores de JSON que migrar. Ojo con la copia
sin versionar `~/lanot/polar/crea_vistas_metop.sh` en kawak, que es la que llama
el crontab.

### Verificación de la fase C

- C2: en tren2, tras un ciclo, cada `YYYYMMDD_hhmm_SAT_SECTOR.png` tiene su
  `lanot_…json`; `jq '.assets.image["proj:bbox"]'` es igual a `.bounds` del
  plano del mismo cuadro (ya lo prueba
  `test_reprojected_view_links_to_hpsv_item`, pero hay que verlo con datos reales).
- C3: correr `crea_animaciones_meso.sh` con `MESO_DIR`/`MESO_OUTDIR` apuntando
  a una copia de un día real, leyendo sólo Items, y comparar con `diff` la lista
  de episodios contra la que sale leyendo el plano. Tienen que ser idénticas.
- C4: el Item del episodio valida contra los esquemas oficiales (reusar el
  validador de `tests/test_stac_item.py`), y el visor coloca el video en el
  mismo sitio que antes.
- C5: `grep -rn "\.bounds\|save-metadata\|save_json\|from_json_file"` en
  LANOT_tools, LANOT_procesamiento_goes y LANOT_pagina no encuentra lectores
  vivos.

### Fuera de alcance

- Collection, Catalog e índice.
- La **retención** de Items (quién los purga y cuándo): sigue abierta en
  STAC_PLAN.md, «Estado y lo que queda», punto 2. C-D1 y C6 dependen de ella.

## Pendientes (resumen, 2026-09-26)

Lista única de lo que queda. El detalle de la fase C está arriba.

### Decisiones del usuario, antes de tocar meso

- [ ] **Retención de Items** (STAC_PLAN.md de hpsatviews, «Estado y lo que
  queda», punto 2). Bloquea C-D1 y C6.
- [ ] **C-D1**: qué pasa con el Item de hpsv que hoy se borra con el directorio
  temporal de `crea_rgb_meso.py`. Recomendado: copiarlo junto a la vista.
- [ ] **C-D2**: el JSON de la animación pasa a ser Item de STAC por episodio.
  Recomendado: sí.
- [ ] **C-D3**: los Items de cuadro se nombran por id y los lectores toman
  imagen, instante y sector del contenido. Recomendado: sí.
- [ ] Aprobar el orden C1 → C6 (lectores tolerantes, luego escritores, luego
  retiro del plano).

### Fase C, en orden

- [ ] **C1** Desplegar LANOT_tools en tren2 (`sudo ./install.sh`) y comprobar
  que `processing:software` trae la versión instalada, no `desconocida`.
- [ ] **C2** `crea_rgb_meso.py` pasa `--stac`; en el mismo cambio, estrechar el
  `find` de `crea_animaciones_meso.sh:81` y `:97` a `'[0-9]*_G*_m*.json'`.
- [ ] **C2** Averiguar en tren2 qué purga los cuadros de `$datadir` (no está en
  `cron/mesoescala.cron` ni en los guiones versionados) y que abarque
  `lanot_*.json`.
- [ ] **C3** Lectores tolerantes: `crea_animaciones_meso.sh` y `views.py` de
  LANOT_pagina (despliegue aparte).
- [ ] **C4** `animameso.sh` escribe el Item del episodio, con las claves planas
  en la raíz mientras el visor no tenga C3.
- [ ] **C5** Retirar el JSON plano de `--o_crs`, `--save-metadata`,
  `Metadata.from_json_file()`/`save_json()` y los respaldos de C3/C4; actualizar
  `CLAUDE.md` y README.
- [ ] **C6** Polares: `--stac` en `crea_vistas_viirs.sh` y
  `crea_vistas_metop.sh` (y la copia sin versionar de kawak en `~/lanot/polar/`).

### Deuda menor de las fases A y B

- [ ] **`MapDrawer.crop()` en CRS proyectado**: recorta los píxeles con las dos
  esquinas (`_geo2pixel` de UL y LR) pero `set_bounds()` recalcula
  `proj_bounds` con el perímetro entero de la caja lat/lon. En rejilla fija
  (curva) las dos rejillas difieren, y el Item de `mapdrawer --clip` hereda esa
  discrepancia porque describe `proj_bounds`, que es con lo que se dibujan las
  capas. Existía antes de `--stac`; no se tocó.
- [ ] **`geotiff2view` pasa los bounds del GeoTIFF a `set_bounds()` como
  lat/lon**, lo que sólo es correcto en 4326. Por eso `--stac` toma ahí la
  rejilla del GeoTIFF y sólo usa la de MapDrawer con `--clip`. Con un GeoTIFF
  proyectado, `--clip` en geotiff2view sigue siendo sospechoso.
- [ ] **La huella existe tres veces** (C en hpsv, Python/osr en
  `stac_sweep.py`, Python/pyproj aquí). Lo que las sujeta son las pruebas
  vértice a vértice contra Items de hpsv; si hpsv cambia `src/footprint.c`, hay
  que regenerar `tests/data/hpsv_*.json` y correr `tests/test_stac_item.py`.
- [ ] **Esquemas copiados** de `hpsatviews/docs/stac/schemas/`. Si hpsv sube
  la versión del núcleo o de `projection`/`processing`, copiar de nuevo y
  ajustar `STAC_VERSION`/`EXT_*` en `stac_item.py`.
- [ ] **`jsonschema` no está en `/opt/lanot-tools/venv`**: la suite corre con el
  `python3` del sistema, o hay que instalar `requirements-dev.txt` en el venv.
- [ ] No se hizo `Metadata.to_stac_item()`, que el plan original mencionaba:
  `stac_item.emit()` cumple ese papel para las dos herramientas. Añadirlo sólo
  si otro llamador lo necesita.
- [ ] No hay `--stac-collection` (hpsv sí la tiene). Sin ella el Item es válido
  y el indizador asigna la colección; añadirla cuando exista el catálogo.
