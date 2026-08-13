# Modo grilla de glm_renderer.py — productos GLMF (FED / MFA / TOE)

## Estado: IMPLEMENTADO ✓

Funciones `accumulate_glm_grids()`, `cpt_grid_breaks()` y `render_glm_grid_layer()`
en `glm_renderer.py`, más `MapDrawer.overlay_glm_grid()` y las opciones
`--glm-grid` / `--glm-product` / `--glm-min-fed` en `mapdrawer.py`.
Paletas nuevas: `colortables/glm_fed.cpt`, `glm_mfa.cpt`, `glm_toe.cpt`.

Complementa a `plan_glm.md`, que documenta el modo de eventos (`--glm`). Los dos
modos son independientes y mutuamente excluyentes en la CLI: el primero sobrepone
*eventos* del L2 LCFA como un glow cualitativo, este renderiza un producto
*grillado* cuantitativo con unidades físicas y barra de color.

---

## El producto de entrada

`CG_GLM-L2-GLMF-M3_G19_sYYYYJJJHHMMSSm_e..._c....nc` (CSPP-Geo, disco completo,
cadencia de **1 minuto**).

- Malla **5424 × 5424 sobre la malla fija ABI de 2 km**, `+proj=geos +lon_0=-75
  +sweep=x`, o sea idéntica a la del ABI de disco completo: GLM y ABI coinciden
  píxel a píxel en proyección nativa. (La literatura del GLM habla de píxeles de
  8 km; el producto grillado de CSPP no es eso.)
- `_FillValue = 0` en las tres variables → "sin dato" y "cero flashes" son el
  mismo valor.
- La capa es **muy dispersa**: en una ventana típica de 5 min sólo ~0.29 % de las
  celdas tienen FED > 0. Pintar los ceros taparía el IR por completo.

### Unidades reales, verificadas contra los archivos

| Producto | Variable NetCDF | Unidad del archivo | Unidad de la paleta |
|---|---|---|---|
| FED | `flash_extent_density` | conteo por píxel de 2 km por minuto | conteo acumulado (sin conversión) |
| MFA | `minimum_flash_area` | km² | km² (sin conversión) |
| TOE | `total_energy` | **nJ** | **fJ** (× 1e6) |

El FED **no es entero**: el producto reparte el conteo de forma fraccionaria
(mínimo observado 4.6e-06). De ahí que `--glm-min-fed` valga 0.1 por defecto y no
1.0; un umbral de 1 descartaría cerca de la mitad de las celdas con actividad.

TOE se rotula en femtojoules porque en nJ los valores son ilegibles
(p50 = 1.2e-06 nJ). Es la única conversión de unidades del módulo, en
`GRID_SCALE`; hay precedente en el repo con la conversión K→C de la colorbar.

---

## Arquitectura implementada

### 1. Acumulación de la ventana — `accumulate_glm_grids(files, product)`

Los archivos son de 1 minuto, así que la ventana de 5 min la arma la herramienta.
Cada archivo se abre con `rasterio.open(f'NETCDF:"{f}":{var}')`, que resuelve la
georreferencia sin hardcodear la proyección y entrega `crs`, `transform` y los
tags globales (`NC_GLOBAL#time_coverage_start` / `_end`) en una sola lectura.

Se verifica que todos los archivos compartan `crs`, `transform` y `shape`; si no,
aborta con `ValueError`. **Nunca sumar mallas distintas.**

Agregación por producto — esto es lo que el script viejo nunca hizo:

| Producto | Agregación | Por qué |
|---|---|---|
| FED | suma | glmtools asigna cada flash a un solo bin de 1 min |
| TOE | suma | la energía es aditiva |
| MFA | **mínimo**, sólo donde hubo flashes | el flash más pequeño de la ventana |

Devuelve `(data, fed, crs, transform, (t_ini, t_fin))`. El segundo elemento es el
FED acumulado de la misma ventana, con el que el llamador construye la máscara de
pintado también para MFA y TOE. Para `product='FED'` ambos son el mismo arreglo.

### 2. Reproyección — `Resampling.nearest`, siempre

`rasterio.warp.reproject` hacia `(metadata['crs'], bounds, image_size)`.
**Nunca interpolar**: suavizar el conteo inventaría flashes donde no los hubo. Es
la diferencia deliberada con el `gaussian_filter` de `render_glm_layer()`, cuyo
glow es decorativo y no cuantitativo.

Como la malla GLMF es la misma malla fija de 2 km del ABI, con la base en
proyección nativa el `reproject` es prácticamente la identidad; con la base
reproyectada a geográficas (`hpsv -G`) sí hay remuestreo real.

### 3. Máscara de cero

`fed_acumulado >= min_fed`. Todo lo demás queda con **alpha = 0** y el IR debajo
permanece visible. La misma máscara de FED se aplica a MFA y TOE, lo que además
suprime celdas de MFA/TOE sin flashes asociados.

### 4. Color por valor físico, escala logarítmica en el CPT

La escala logarítmica vive en los quiebres del CPT, no en el código, para que la
barra de color de `mapdrawer --colorbar` salga consistente sin lógica duplicada.

**Pero las paletas no se indexan por valor**, sino por **número de intervalo**,
con el valor físico del borde inferior en la etiqueta:

```
# Intervalo  R    G    B    ; Valor
0     20   30  140   ; 0.2
1     20   70  200   ; 0.5
2     20  120  240   ; 1
```

Esta indirección es necesaria por cómo funciona `ColorPaletteTable`:

- En el **formato discreto**, el parser hace `val = int(vals[0])`, así que
  quiebres de 0.2 y 0.5 colisionarían ambos en el índice 0.
- En el **formato continuo**, `_build_palette_from_segments()` construye una LUT
  de 256 entradas **lineal en el valor**. Con quiebres de 0.2 a 120 el paso es
  ~0.47, o sea que los cuatro primeros quiebres (0.2, 0.5, 1, 2) caerían dentro
  de los primeros 5 de 256 índices: las décadas bajas quedarían aplastadas y la
  barra de color saldría casi de un solo color en su mitad izquierda.

Indexando por intervalo, `_draw_colorbar()` pinta N bloques de color uniformes y
`_draw_label_row()` los rotula con los valores físicos repartidos por igual — que
es exactamente la lectura correcta de una escala logarítmica. `colorpalettetable.py`
no requirió ningún cambio.

`cpt_grid_breaks()` recupera los quiebres desde las etiquetas y valida que los
índices arranquen en 0 sin huecos y que los quiebres sean estrictamente
crecientes. El lookup es `np.searchsorted(breaks, valor, side='right') - 1`,
recortado al rango; los valores por debajo del primer quiebre caen en el
intervalo 0.

### 5. Alpha constante

Default 220. El color ya codifica la magnitud; modular además el alpha falsearía
la lectura del CPT. (De nuevo, lo contrario a `render_glm_layer()`, donde el
alpha logarítmico *es* la señal.)

### 6. Rango temporal

Efecto lateral idéntico a `render_glm_layer()`: escribe `metadata['glm_time_start']`
y `['glm_time_end']` con el rango real de la ventana, para que `mapdrawer` arme el
timestamp unificado ABI/GLM vía `Metadata.format_timestamp_glm()`.

---

## Calibración de las paletas

Percentiles reales de la ventana **01:40–01:44 UTC del DOY 212 de 2026**
(5 archivos, 84 336 celdas con FED > 0 de 29.4 M):

| Campo | min | p50 | p90 | p95 | p99 | max |
|---|---|---|---|---|---|---|
| FED (conteo / px 2 km / 5 min) | 4.6e-06 | 2.0 | 12.7 | 22.8 | 55.4 | 281 |
| TOE (nJ) | 3.6e-12 | 1.2e-06 | 2.5e-05 | 4.9e-05 | 1.9e-04 | 1.5e-02 |
| MFA (km²) | 64.9 | 523 | 2175 | 2578 | 4033 | 5739 |

- **`glm_fed.cpt`** — quiebres 0.2, 0.5, 1, 2, 4, 8, 15, 25, 40, 60, 120.
  Frío→cálido: pocos flashes en azul, muchos en rojo.
- **`glm_mfa.cpt`** — quiebres 100, 200, 400, 700, 1100, 1600, 2200, 3000, 4000,
  5500. **Invertida a propósito**: área pequeña = amarillo/verde (convección
  fortaleciéndose), área grande = azul/púrpura (debilitándose). Ese orden es el
  punto entero del producto; si la imagen sale al revés, la paleta no quedó
  invertida.
- **`glm_toe.cpt`** — quiebres en fJ: 0.1, 0.3, 1, 3, 10, 30, 100, 300, 1000,
  3000. Escala de brillo púrpura oscuro → naranja → blanco.

Si al ver las imágenes los quiebres quedan cortos, recalcular percentiles sobre
otra ventana antes de tocarlos a ojo.

---

## Uso

```bash
mapdrawer base_a1.tif \
    --glm-grid /data1/output/glm/CG_GLM-L2-GLMF-M3_G19_s2026212014[0-4]*.nc \
    --glm-product FED \
    --cpt glm_fed.cpt --colorbar --colorbar-text-pos below \
    --layer COASTLINE:white:0.0005 \
    --layer MEXSTATES:white:0.0005 \
    --layer grid05:gray:0.0005 \
    --logo-pos 0 --timestamp-pos 2 \
    -o salida-fed_a1.png
```

`--cpt` y `--colorbar` son los que ya existían: la Prioridad 2 del bloque de
colorbar toma el CPT externo y rotula la barra en unidades físicas.
`--glm` y `--glm-grid` son mutuamente excluyentes.

---

## Artefactos conocidos del GLM

El glint solar y los "bar artifacts" producen flashes falsos *anormalmente
pequeños y tenues en área y energía*, o sea que contaminan justamente MFA y TOE.
`--glm-min-fed` sólo mitiga ruido de conteo bajo; el filtrado real corresponde a
los filtros de flash de glmtools, aguas arriba. No se inventa un filtro en la
capa de visualización.

---

## Tests

`tests/test_glm_renderer.py`, clases `TestAccumulateGlmGrids`,
`TestCptGridBreaks` y `TestRenderGlmGridLayer`. Mockean `rasterio.open` con
objetos `crs`/`transform` reales, de modo que la reproyección que se ejercita es
la de verdad. Los tests del modo eventos siguen sin cambios como regresión.
