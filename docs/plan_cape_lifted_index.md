# Plan: CAPE y Lifted Index de los sondeos NUCAPS

Escrito el 2026-08-29. Lo que falta **en LANOT_tools** para que los dos
parámetros de estabilidad de NUCAPS salgan como vistas, y lo que ya está hecho
fuera para que se entienda el cuadro completo.

Queda pendiente **una sola decisión tuya: los rangos de las dos paletas.** Todo
lo demás está especificado abajo.

---

## De dónde salen

Los `NUCAPS-EDR` que produce CSPP HEAP traen una variable `Stability` con **16
parámetros por campo de regard**. No hay variables `CAPE` ni `Lifted_Index`
propias: son columnas de ese array.

| Producto | Dónde | Unidades reales | Lo que declara el archivo |
|---|---|---|---|
| CAPE | `Stability[:, 0]` | J/kg | `units = "1"` |
| Lifted Index | `Stability[:, 9]` | K | `units = "1"` |

Los índices salen del código de CSPP Sounder QL
(`/data/cspp/cspp-sounder-ql-1.4/scripts/sounder_packages/nucaps.py`, métodos
`stability_cape` y `stability_lifted_index`). Las unidades declaradas en el
archivo son inservibles, de ahí que las fije el YAML del lector.

**Trampa heredada de NUCAPS**, avisada por el propio código de CIMSS: los
no-recuperados quedan como **`-999.0`**, que no es el `_FillValue` declarado
(`-9999.0`). El lector ya los enmascara; se menciona aquí porque si algún día
alguien lee estos productos por otra vía, esos `-999` se pintarían como dato.

## Lo que ya está hecho, fuera de este repositorio

En `LANOT_procesamiento_polar`, `contenedores/parches/aplicar_parches_satpy.py`
parchea el Satpy del bundle de Polar2Grid para exponer los dos productos:
indexado de la última dimensión (`column_index`), enmascarado del `-999`
(`extra_fill_values`) y precedencia de `units` desde el YAML. Probado con la
suite de `nucaps` del propio bundle, 23/23.

**Pendiente allí:** recompilar `polar2grid_v3.2-mapdrawer.sif`, y añadir los dos
productos a la lista `-p` del bloque de sondeos de `run_polar2grid_edr.sh` junto
con su sección de decoración. Eso lo hago yo cuando existan las CPT, porque sin
ellas la vista saldría en escala de grises o sin nombre.

---

## 1. Dos paletas nuevas

`colortables/nucaps_cape.cpt` y `colortables/nucaps_lifted_index.cpt`, con el
formato de las que ya hay (ver `nucaps_temp_500.cpt`): cabecera con `# UNIT =`
y `# COLOR_MODEL = RGB`, y filas `Value R G B   Value R G B`.

**Rango fijo, no percentiles.** Es la misma razón que en las de temperatura y
está escrita en su cabecera: con rango fijo, dos pasadas del mismo producto se
comparan; con percentiles, cada imagen se estira a lo suyo y deja de significar
lo mismo. En estos dos importa aún más, porque lo que se lee no es el patrón
sino el **umbral**.

### `nucaps_cape.cpt` — secuencial

CAPE es una magnitud positiva sin cero significativo: paleta secuencial, oscura
o fría abajo y caliente arriba. Los umbrales con los que se habla de CAPE:

| J/kg | Lectura habitual |
|---|---|
| < 300 | prácticamente nada |
| 300 – 1000 | inestabilidad débil |
| 1000 – 2500 | moderada |
| 2500 – 4000 | fuerte |
| > 4000 | extrema |

Dos cosas a decidir, y por eso está sin hacer:

- **El máximo.** 4000 J/kg cubre casi todo, pero en verano sobre el Golfo se ven
  valores altos y saturar el tope pierde la señal. Una alternativa es 3000 con
  el último color abierto.
- **La linealidad.** Con escala lineal de 0 a 4000, todo el rango "interesante"
  de 0–1000 se come una cuarta parte de la paleta. Como el `.cpt` es una tabla
  de tramos, se puede dar más resolución abajo sin cambiar nada del código:
  tramos estrechos hasta 1500 y anchos arriba.

**Ojo con el sesgo:** el CAPE de NUCAPS es de sondeo satelital infrarrojo y no
es comparable sin más con el de un radiosondeo; tiende a subestimar en
situaciones de capa límite húmeda. Si la vista se va a publicar, conviene que la
etiqueta no invite a leerlo como un CAPE de radiosondeo.

### `nucaps_lifted_index.cpt` — divergente

El Lifted Index sí tiene un cero con significado: **negativo es inestable**. Eso
pide paleta divergente y, sobre todo, que **el cero caiga en un límite de color
y no en mitad de un tramo**, o la vista mentirá justo donde se la mira.

| K | Lectura habitual |
|---|---|
| > +2 | estable |
| 0 a −2 | marginal |
| −3 a −5 | moderadamente inestable |
| −6 a −9 | muy inestable |
| < −10 | extremo |

Un rango de **−10 a +10** cubre lo operativo. Sugerencia: fríos o neutros para
los positivos, cálidos para los negativos —al revés de lo intuitivo, porque
"negativo" aquí es "peligroso"—, y un color neutro claro justo en el cero.

Conviene decidirlo a la vez que el CAPE: las dos vistas se van a mirar juntas, y
si una dice "rojo = mucho" y la otra "rojo = poco", se leen mal.

## 2. Dos entradas en `product_map`

En `metadata.py`, dentro de la lista `product_map`. El match es por **subcadena
sobre el nombre en minúsculas**, y gana la primera que aparezca, así que el
orden importa.

```python
('cape',         'CAPE',          'J/kg'),
('lifted_index', 'Lifted Index',  'K'),
```

**Dónde ponerlas:** en el bloque de sondeos NUCAPS, junto a
`skin_temperature` y los `temperature_*mb`, y **antes** del respaldo genérico
`('temperature', 'Temperature', 'K')` que cierra ese bloque. Ninguna de las
entradas anteriores casa con estos nombres, así que no hay colisión — pero
conviene dejarlas dentro del bloque para que se lean juntas.

**El token tiene que ser el nombre con el que Polar2Grid bautiza el archivo**,
que aquí es el del dataset en el YAML del lector. Los archivos saldrán como:

```
noaa20_atms-cris_CAPE_20260829_191434_wgs84_geo_5km.tif
noaa20_atms-cris_Lifted_Index_20260829_191434_wgs84_geo_5km.tif
```

Sin estas entradas la vista sale **bien coloreada y sin decir de qué es**: la
etiqueta cae al nombre del sensor y queda "NOAA-20 CrIS+ATMS" a secas. Degrada
en silencio, que es el modo de fallo que más veces nos ha mordido.

## 3. Cómo probarlo sin esperar a una pasada

Las CPT van montadas desde el host, así que **no hacen falta recompilaciones
para iterar sobre los colores**: `git pull` + `install.sh` en tahan y volver a
vestir el GeoTIFF. `product_map`, en cambio, viaja dentro del `.sif`, así que un
cambio ahí sí obliga a recompilar y a mover el pin `LANOT_TOOLS_COMMIT`.

Por eso conviene este orden: **primero `product_map`** (entra en la siguiente
recompilación, que ya hace falta por los parches de Satpy), y **después las CPT**,
que se pueden ajustar tantas veces como quieras sin tocar la imagen.

Para probar `metadata.py` sin nada más:

```python
from metadata import Metadata
m = Metadata()
m.enrich_from_filename('noaa20_atms-cris_CAPE_20260829_191434_wgs84_geo_5km.tif')
assert m['product'] == 'CAPE' and m['units'] == 'J/kg' and m['sensor'] == 'CrIS+ATMS'
```

Ese mismo assert conviene añadirlo al `%post` y al `%test` del `.def`, como ya
está el de `Temp 500 hPa`: es lo único de la vista de sondeos que viaja dentro
de la imagen y que un pin viejo puede dejar atrás sin que nada falle.

## 4. Y una posibilidad que no es para ahora

Estos dos productos son campos 2D y encajan en la cadena tal cual. El **Skew-T**
no: es un perfil vertical en un punto, no una rejilla, y necesitaría leer el
`.nc` directamente y una lista de sitios. Se habló el mismo día; queda anotado
aquí para que no se pierda el hilo, pero es otro plan.
