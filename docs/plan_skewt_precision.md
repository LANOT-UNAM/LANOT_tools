# Skew-T: precisión por eje e isotermas de 2 puntos

Escrito el 2026-10-01. **Hecho el 2026-10-01** (ver "Resultado" al final). Sale de una sesión en el
repo de MetaGráfica: al meter `examples/skewt_golfo.mg` (una instantánea de lo que
emite `skewt.py`) al corpus hubo que decimarlo a mano con
`tools/simplifica_mg.py --escala` (commit 8a281f9 de MetaGráfica, ver las NOTAS de
ese ejemplo). Si el generador hace bien estas dos cosas, eso sobra.

Antecedentes del módulo: `docs/plan_skewt.md`.

## Línea base (medida el 2026-10-01, `main` en 028686d)

Con el sondeo sintético de `tests/test_skewt.py` y el papel por omisión (16x20):

| | valor |
|---|---|
| `.mg` emitido | 35 999 bytes |
| isotermas | 18 polilíneas, **508 puntos** (deberían ser 36) |
| escala x | 0.1625 cm/°C → un milésimo = **0.0016 mm** |
| escala y | 6.73 cm por unidad de ln p → un milésimo = **0.067 mm** |

Para repetir la medida:

```bash
python3 - <<'EOF'
import sys; sys.path[:0] = ['tests', '.']
from test_skewt import _sondeo_sintetico
import skewt
d = skewt.SkewT(); src = d.render(_sondeo_sintetico(), "x")
sec = src.split("% isotermas")[1].split("% adiab")[0]
pl = [l for l in sec.splitlines() if 'polyline' in l]
print(len(src), "bytes;", len(pl), "isotermas,",
      sum(len(l.split('{')[1].split('}')[0].split()) // 2 for l in pl), "puntos")
EOF
```

## 1. Precisión por eje, derivada del papel (la importante)

**El problema.** `_fmt(v, dec=3)` emite 3 decimales en x y en y, pero el plot es
anisótropo (~41x entre ejes). En x sobra precisión; en y falta: el escalón de
0.067 mm hacía zigzaguear las isotermas hasta **0.044 mm** (medido en MG).

**La regla.** El error de redondeo es medio escalón por la escala del eje. Pedir
que no pase de una tolerancia en papel, `TOL_CM = 0.001` (0.01 mm):

```
dec = ceil(log10(0.5 · escala_cm_por_unidad / TOL_CM))     # y mínimo 0
```

Con el papel por omisión da **x: 2, y: 4** (error 0.008 mm y 0.003 mm). Hay que
**derivarlo de `self.box`** en `__init__`, no fijarlo, para que valga con
cualquier `--size`, `--tmin/--tmax` o `--pmin`.

**Dónde tocar `skewt.py`:**

- `SkewT.__init__`: calcular `self.dec_x`, `self.dec_y` a partir de `bw/(tmax-tmin)`
  y `bh/ymax`. Una constante de módulo `TOL_CM` junto a `STYLE`.
- Un helper `self._xy(x, y)` → `f"{x:.{dec_x}f} {y:.{dec_y}f}"`, y usarlo en
  `_polys`, el `marker` de `_surface` y la `polyline`/`text` de `_parcel`.
- Los `_fmt(…, 4)` fijos de y (`_isobars`, `_surface`, `_parcel`, el `y=(0,…)` del
  `plot`) pasan a `self.dec_y`.
- **No** tocar lo que va en cm de página (`_header`, `_logo`, `display_size`,
  `world_window`, `box=`): ahí 2–3 decimales de cm ya son de sobra.
- **Trampa — tramos degenerados tras redondear.** `_has_extent` mira la extensión
  en datos sin redondear (tol 1e-6). Con 2 decimales en x un tramo de extensión
  real 0.003 °C y Δy = 0 sale como dos puntos idénticos: es el mismo bug de la
  esquina (`polyline { -40.000 0.000  -40.000 0.000 }`) que ya se arregló una vez.
  Comprobar la extensión **sobre las cadenas ya formateadas** (o quitar puntos
  consecutivos que redondean igual) y actualizar el docstring de `_has_extent`,
  que dice "tres decimales".

## 2. Isotermas de 2 puntos (la mayor reducción)

Son rectas exactas, `x = T + m·y` (`test_isoterma_es_recta` ya lo afirma), pero
salen muestreadas con los 61 puntos de `p_grid`.

**El cambio**, en `_background`: generar cada isoterma con dos presiones,
`self.curve([t, t], [self.pmax, self.pmin])`, y dejar que `clip` la recorte. El
recorte por bisección es exacto en un segmento recto en el espacio (x, y), y la
esquina tocada ya la filtra `_has_extent`. Alternativa analítica si se prefiere:
`y ∈ [max(0, (tmin−t)/m), min(ymax, (tmax−t)/m)]`; se emite si el intervalo no es
vacío. La primera es una línea y reutiliza código ya probado — preferirla.

Esperado: 508 → 36 puntos en isotermas; mismas 18 polilíneas.

> **Corrección al implementar:** la opción "preferida" de arriba pierde
> isotermas. `clip` solo mira transiciones dentro↔fuera de cada tramo, y con el
> sesgo (m·ymax ≈ 95 °C > 80 °C de ancho) una isoterma como −50 °C entra por la
> izquierda y sale por la derecha con **los dos extremos fuera**: el tramo único
> se descarta. Se implementó la analítica, `SkewT.isotherm(t)`, que no pasa por
> `clip`.

## Pruebas nuevas (`tests/test_skewt.py`)

- **`test_ninguna_isoterma_tiene_mas_de_2_puntos`**: partir el `render` entre
  `% isotermas` y `% adiabáticas` y contar pares por `polyline`.
- **`test_las_isotermas_no_cambian_de_numero`**: siguen saliendo 18 (o las que
  toquen) — que el recorte no tire ninguna.
- **`test_error_de_redondeo_en_papel`**, parametrizada con varios `--size`
  (16x20, 10x12, 30x40) y un `--pmin` distinto: `0.5·10^-dec · escala ≤ TOL_CM`
  en ambos ejes.
- **`test_ningun_punto_repetido_tras_redondear`**: en ninguna `polyline` hay dos
  pares consecutivos idénticos como cadena.
- Las que ya existen deben seguir verdes, sobre todo `test_el_mg_emitido_compila`
  (sin `Warning` ni `Error` en stderr) y `test_ningun_tramo_tiene_longitud_cero`.

## Lo que NO se hace

- **Douglas-Peucker sobre adiabáticas y razón de mezcla: no.** Medido en MG: a
  tolerancia invisible (0.01 mm) solo quita el 26 %; 61 niveles en log p ya es
  una densidad sensata. A 0.05 mm sí se nota (peor píxel 106/255). Si algún día
  se hace, medir en cm de papel (el plot es anisótropo) y **nunca** decimar el
  perfil ni la parcela: son datos, no dibujo.
- **No regenerar `examples/skewt_golfo.mg` en MetaGráfica.** Es una instantánea
  anterior a `_has_extent`, la superficie y el logo; regenerarlo metería el logo
  al corpus, y allá se decidió dejar el ejemplo como está (es interno).

## Cómo retomarlo (p.ej. desde pegaso)

```bash
cd ~/lanot/LANOT_tools && git pull
which mg                               # sin mg se saltan las pruebas de compilar
python3 -m pytest tests/ -q            # base: 323 passed, 0 skipped
python3 -m pytest tests/test_skewt.py -v
```

Orden sugerido: (2) primero, que es una línea y su prueba; luego (1) con la
trampa de los tramos degenerados; volver a medir con el bloque de arriba y anotar
aquí bytes y puntos después. De punta a punta, si hay gránulos NUCAPS a mano (ver
"Los datos de prueba" en `plan_skewt.md`):

```bash
skewt NUCAPS-EDR_*.nc --lat 20.6 --lon -90.5 -o golfo.svg --keep-mg
mg golfo.mg golfo.pdf                  # comparar a ojo con la de antes, con zoom
```

Al terminar: actualizar el conteo de pruebas en `CLAUDE.md` y marcar este plan
como hecho.

## Resultado (2026-10-01)

Con el bloque de medida de arriba, papel por omisión:

| | antes | después |
|---|---|---|
| `.mg` emitido | 35 999 bytes | **29 264 bytes** (−19 %) |
| isotermas | 18 polilíneas, 508 puntos | 18 polilíneas, **36 puntos** |
| decimales x / y | 3 / 3 | **2 / 4** (de `TOL_CM`) |

Mismo número de isotermas y mismos extremos (±1 en el último decimal) que la
versión anterior con 16x20, 10x12, `--pmin 200` y `--skew 0`. Comparado en PDF
rasterizado a 300 dpi: solo cambia el antialiasing subpíxel a lo largo de las
líneas.

Implementado como: `TOL_CM` y `_decimals()` de módulo; `self.dec_x`/`dec_y` en
`__init__`; `SkewT.isotherm()` (recorte analítico, acotado a la caja);
`SkewT._xy()`; `_polys(..., clip=True)` quita los puntos consecutivos que
redondean igual y descarta la polilínea si queda de uno. 14 pruebas nuevas en
`tests/test_skewt.py` (sección "precisión de lo emitido").

## Confirmado en operación (2026-10-04, tahan)

El `.sif` con `094db73` entró el 2026-10-01 a las 15:50. En
`/data/output/jpss/vistas/sounder/skewt` (sin `--keep-mg`, así que se compara
el SVG que produce `mg`, no el `.mg`):

| | antes | después |
|---|---|---|
| SVG, promedio de los 14 sitios | ~79.1 KB (n=275) | **~70.7 KB** (n=74, −11 %) |
| CDMX, NOAA-21 (01-oct 19:40 vs 03-oct 19:03) | 78 708 bytes | 70 331 bytes |
| isotermas (`#4682B4`) en ese par | 18 trazos, 508 puntos | 18 trazos, **36 puntos** |
| resto de los trazos | — | idénticos en número y puntos |

La reducción del SVG es menor que la del `.mg` (−19 %) porque el SVG también
lleva texto y estilos, y `mg` reescribe las coordenadas en unidades de página
con su propia precisión: los 2/4 decimales no se ven ahí. En las curvas de
fondo (iguales en los dos), la desviación mediana de cada punto respecto a sus
vecinos en el 40 % superior bajó de ~0.10 a 0.02–0.05 pt; a 8× las dos versiones
se ven lisas.
