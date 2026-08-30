# Skew-T: lo que se decidió y lo que la especificación no sabía

Escrito el 2026-08-30, al implementar `docs/especificacion_modulo_skewt_v1.md`.
Este documento es el registro de las decisiones y de los cinco puntos en los que
el dato real desmintió a la especificación. La especificación sigue siendo la
lista de requisitos; esto es lo que costó cumplirlos.

## El motor: MetaGráfica, no una biblioteca de Python

La §1 pedía "una biblioteca en python equivalente a PIL" para vectorial. Se
midieron cuatro candidatas y ganó la que no es una biblioteca de Python:

| | veredicto |
|---|---|
| **MetaGráfica** (`mg`) | **elegida.** Cero dependencias de pip; `install.sh` sin tocar. Única con texto matemático y con `plot`/`axis`/`rule`/`legend`/`table` ya hechos. |
| `pycairo` | se publica **solo como sdist**: `pip download pycairo` falla sin `libcairo2-dev`, y `install.sh` crea un venv limpio sin paso de `apt`. Rompería la instalación en tahan. |
| `cairocffi` | funcionaría (wheel pura sobre `libcairo.so.2`), pero cuesta una dependencia nueva para reimplementar lo que `mg` ya trae. |
| `svgwrite` | solo SVG: sin PDF, sin texto matemático, sin ejes ni métricas de texto. Más código nuestro por menos salida. |
| `aggdraw` | es **raster**, un acelerador de PIL. No responde a la §1. |

**Costo aceptado:** `mg` es un binario C++ fuera de pip. Hay que instalarlo y
fijarle versión en tahan, con el precedente del pin `LANOT_TOOLS_COMMIT`. Si
falta, el `.mg` se escribe igual y se avisa — como degradan `rasterio` y `pyproj`.

**Se descartó** escribir el diagrama como un `.mg` parametrizado al estilo de
`lib/polar_map.mg`: la adiabática saturada es una integración numérica y partir
la física entre dos lenguajes la vuelve improbable de probar. La física vive en
Python; `mg` dibuja y compone.

## Los cinco puntos donde el dato desmintió a la especificación

**1. NUCAPS no trae punto de rocío.** La §2 lo pedía como si se leyera del
archivo. Trae `H2O_MR` en kg/kg y hay que derivarlo: `e = w·p/(ε+w)` e inversión
de Magnus, sobre agua también bajo cero, que es la convención de los Skew-T.

**2. El eje log no puede ser el de `mg`.** Con `yscale="log"` mg remapea
coordenada por coordenada y las matrices no componen (§11 de su referencia), así
que el shear del sesgo no se puede expresar ahí. Se hace `y = log(p_max/p)` y
`x = T + m·y` en Python sobre un `plot` **lineal**. Sale mejor: toda la física
queda del lado que se puede probar.

**3. `-d DPI` se cayó con el raster.** `mg` da EPS, SVG y PDF, no PNG ni JPEG. Se
decidió entregar la v1 solo vectorial; lo sustituye `--size ANCHOxALTO` en cm,
que es el `display_size` de `mg`. Si algún día hace falta raster, `pdftocairo`
sobre el PDF es el camino más ligero.

**4. Los `Quality_Flag` son diez, no dos.** El archivo trae `flag_values` y
`flag_meanings`: `accepted`, `reject_physical`, `reject_MIT`, `reject_NOAA_reg`…
Solo el 0 es aceptado. En la pasada del 2026-08-29 hay FOR con 1 y con 9. La
etiqueta se lee **del propio archivo**, no de una tabla nuestra, para que si
NUCAPS cambia el catálogo la vista no mienta. Por omisión un retrieval rechazado
no se dibuja; `--quality-any` lo dibuja y lo rotula.

**5. El `-999.0` existe, y solo en `Stability`.** Confirmado sobre los 14
gránulos: `Pressure`, `Temperature` y `H2O_MR` usan el `_FillValue` declarado
(`-9999.0`) y netCDF4 los enmascara solo; `Stability` mete además `-999.0`, que
no está declarado y pasaría como dato. Es la trampa que ya avisaba
`plan_cape_lifted_index.md`, y aquí se midió dónde vive.

Un sexto, menor: los niveles bajo `Surface_Pressure` **ya vienen recortados** en
estos archivos. El filtro se quedó igual, porque el mismo lector tiene que servir
para un NUCAPS que no los recorte.

## Lo que quedó fuera de la v1

- **Barbas de viento.** NUCAPS no trae viento. Entran con WRF, y con ellas la
  columna derecha del lienzo.
- **CAPE y LI calculados por nosotros.** Se leen de `Stability[0]` y
  `Stability[9]` para que el número del Skew-T sea el mismo que el de la vista 2D
  del mismo archivo. La **parcela dibujada sí la calculamos**, así que la tabla
  los rotula como de NUCAPS: si algún día discrepan a la vista, la figura dice de
  quién es cada cosa.
- **Raster.** Ver punto 3.

## Dos arreglos que se hicieron en MetaGráfica

Los destapó este trabajo, y los dos eran piezas que ninguna figura del corpus
ejercitaba (`rule(` no aparecía en ningún `.mg` del repo de mg):

- Un símbolo desconocido dentro de `$…$` no avanzaba el índice: `$^\circ$C`
  salía como `irc C`, con código de salida 0. Ahora avisa y descarta, como
  documenta su §6.
- `rule` no heredaba el estado de estilo del bloque `plot` —lo tomaba de fuera
  del plot—, contra lo que promete su §9. Ahora obedece al bloque, y sus propios
  argumentos siguen ganando.

## Los datos de prueba, y cómo volver a tenerlos

**No están en el repo ni pueden estarlo**: son 14 gránulos de 3.7 MB cada uno. En
la máquina donde se desarrolló viven en `~/lanot/datos_nucaps/`. Para rehacerlos
en otra máquina, de la pasada `j01_d20260829_b45492` (2026-08-29, 19:14–19:22Z,
1680 FOR entre lat 6.3–35.2 y lon −104.4 a −78.0, que cubre México entero):

```bash
rsync -av tahan:/data/output/jpss/level2/sounder/NUCAPS-EDR_v3r2_j01_*20260829*.nc \
      ~/lanot/datos_nucaps/
```

**Los 14, no uno**: cada gránulo es una rebanada corta del swath y el punto pedido
puede caer entre dos, así que con uno solo queda sin ejercitar el camino de "FOR
más cercano entre varios archivos".

Dos puntos con los que se comprobó, y que sirven de referencia porque contrastan:

| | FOR | superficie | CAPE | LCL / LFC / EL |
|---|---|---|---|---|
| CDMX (19.4, −99.1) | 19.47N 98.72W, a 40 km | 750 hPa (2240 m) | 43 J/kg | 626 / 559 / 518 |
| Golfo (20.6, −90.5) | 20.63N 90.48W, a 4 km | nivel del mar | 4772 J/kg | 950 / 868 / 139 |

La suite **no** los necesita: `tests/data/nucaps_perfil_cdmx.npz` son 3.7 kB con el
perfil real del primero, y el lector se prueba contra un NUCAPS-EDR miniatura
construido en `tmp_path`.

## Tres arreglos que salieron de llevar la figura al corpus de MG

Al añadir el sondeo del Golfo a `examples/skewt_golfo.mg` de MetaGráfica, sus
comentarios curados destaparon un defecto y la verificación otros dos:

1. **El ancho del cromo no llegaba.** `line_width` dentro del `plot` no hace nada:
   el marco, los ejes y la leyenda **no heredan el estado del cuerpo** —solo los
   `rule`—, así que salían al ancho por omisión de mg. Medido: 18 elementos a
   `stroke-width="1"` donde debían ir a 0.4. Ahora la sentencia va antes del `plot`.
2. **`clip()` emitía polilíneas de longitud cero.** `len(s) > 1` no basta: una
   curva que toca una esquina exacta da dos puntos idénticos.
3. **La cabecera del `.mg` no se explicaba sola.** Ahora lleva gránulo, FOR,
   satélite, hora, coordenadas y calidad, porque el `.mg` es un artefacto
   versionable y puede acabar lejos de su `.nc`.

## Pendientes

Al 2026-08-30, en orden de lo que bloquea a lo que no:

- **`mg` en tahan**: instalarlo y fijarle versión, con el precedente del pin
  `LANOT_TOOLS_COMMIT`. Es lo único que `install.sh` no puede traer, y sin él la
  cadena produce `.mg` pero ninguna figura. Necesita el binario del **2026-08-30 o
  posterior**: antes de esa fecha los `rule` no heredaban el estilo del bloque y
  las isobaras saldrían negras de 1 pt.
- **Recopiar el `.mg` al corpus de MG y re-bendecir.** El de `examples/skewt_golfo.mg`
  es anterior a los tres arreglos de arriba; hay que regenerarlo y correr
  `./test/run.sh capture`. La golden **debe** cambiar (el marco adelgaza de 1 pt a
  0.4); si no cambiara, el arreglo no llegó. Ojo: el encabezado de comentarios
  curado de ese archivo no lo emite el generador, así que la copia lo borra.
- **El script operativo de la cadena.** Hoy `skewt` se invoca a mano. Falta el
  equivalente de `crea_vistas_viirs.sh` o `GLMconus_png.sh`, y para eso hace falta
  antes **la lista de sitios fijos**, que es lo que quedó apuntado al final de
  `plan_cape_lifted_index.md`.
- **El logo** (`logos/lanot_logo.mg`): queda para una discusión aparte. Hoy es una
  figura suelta con su propio `display_size`/`world_window`, así que para ponerlo
  en el diagrama habría que envolverlo en un `struct` —como ya lo está
  `lanot_sat.mg`— y decidir cómo resuelve su `include` fuera de su directorio.

## Cómo se verifica

```bash
# la suite: 224 passed
python3 -m pytest tests/

# de punta a punta con un gránulo real
skewt NUCAPS-EDR_*.nc --lat 19.4 --lon -99.1 -o cdmx.svg --keep-mg
mg cdmx.mg cdmx.pdf          # el .mg tiene que compilar limpio a los tres formatos
```

Lo que hay que mirar en la figura, y por qué:

- **T a la derecha de T_d** en toda la columna, o el punto de rocío está mal
  derivado.
- **El perfil arranca en la presión del suelo**, no en 1000 hPa. Sobre la CDMX
  arranca en 750: son los 2240 m de altitud, y la banda vacía de abajo es el
  terreno.
- **LFC y EL coherentes con el CAPE de la tabla.** En la CDMX (CAPE 43 J/kg) casi
  se tocan; sobre el Golfo (CAPE 4772) el EL sube a 139 hPa.

La suite completa corre sin gránulo y sin `netCDF4` en el caso de `thermo.py`; de
dónde salen los datos para el extremo a extremo, arriba.
