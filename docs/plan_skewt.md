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

Los tests de `thermo.py` corren sin `netCDF4` y sin gránulo: el fixture
`tests/data/nucaps_perfil_cdmx.npz` son 3.7 kB con un perfil **real** extraído de
la pasada del 2026-08-29. Los del lector construyen un NUCAPS-EDR miniatura en
`tmp_path` con la estructura exacta del producto, en vez de versionar los 3.7 MB
del gránulo.
