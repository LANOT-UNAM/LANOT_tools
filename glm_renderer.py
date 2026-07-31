#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
glm_renderer - Renderizador de datos GLM (Geostationary Lightning Mapper).

Ofrece dos modos independientes:

1. Eventos del L2 LCFA (`render_glm_layer`): capa RGBA con un "glow" de la
   densidad de eventos de rayo, cualitativa, sin unidades.
2. Productos grillados GLMF (`render_glm_grid_layer`): capa RGBA cuantitativa
   de FED / MFA / TOE acumulados sobre una ventana de varios minutos y
   coloreados por valor físico con una paleta CPT.

Uso como módulo:
    from glm_renderer import render_glm_layer
    glm_layer = render_glm_layer(glm_files, metadata)
    base_img = Image.alpha_composite(base_img.convert('RGBA'), glm_layer)

Uso standalone:
    glm_renderer.py base.tif archivo1.nc archivo2.nc ... -o salida.png

Autor: Alejandro Aguilar Sierra
LANOT - Laboratorio Nacional de Observación de la Tierra
"""

import sys
import argparse
from datetime import datetime, timezone

import numpy as np
from PIL import Image
from netCDF4 import Dataset

try:
    from pyproj import Transformer
    HAS_PYPROJ = True
except ImportError:
    HAS_PYPROJ = False

try:
    from scipy.ndimage import gaussian_filter
    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False

try:
    import rasterio
    from rasterio.transform import from_bounds as transform_from_bounds
    from rasterio.warp import reproject, Resampling
    HAS_RASTERIO = True
except ImportError:
    HAS_RASTERIO = False

# Proyecciones GOES predefinidas (mismas que mapdrawer)
GOES_PROJECTIONS = {
    'goes16': '+proj=geos +h=35786023.0 +lon_0=-75.0 +sweep=x +a=6378137.0 +b=6356752.31414 +units=m +no_defs',
    'goes17': '+proj=geos +h=35786023.0 +lon_0=-137.0 +sweep=x +a=6378137.0 +b=6356752.31414 +units=m +no_defs',
    'goes18': '+proj=geos +h=35786023.0 +lon_0=-137.0 +sweep=x +a=6378137.0 +b=6356752.31414 +units=m +no_defs',
    'goes19': '+proj=geos +h=35786023.0 +lon_0=-75.0 +sweep=x +a=6378137.0 +b=6356752.31414 +units=m +no_defs',
}


def _resolve_crs(crs_name):
    if crs_name is None:
        return None
    return GOES_PROJECTIONS.get(crs_name.lower(), crs_name)


def render_glm_layer(glm_files, metadata, base_color=(255, 255, 0)):
    """
    Genera una capa RGBA con la densidad de eventos GLM lista para composición.

    Usa el CRS y los bounds del objeto Metadata para proyectar los eventos de
    rayo al espacio de imagen. Almacena el rango temporal de los archivos GLM
    como 'glm_time_start' y 'glm_time_end' en el objeto metadata recibido.

    Args:
        glm_files (list[str]): Lista de rutas a archivos NetCDF GLM.
        metadata: Instancia de Metadata con 'crs' y 'bounds' ya presentes.
        base_color (tuple): Color RGB base de los rayos. Default amarillo (255,255,0).

    Returns:
        PIL.Image or None: Imagen RGBA con la capa de rayos, o None si no hay datos.
    """
    if not HAS_PYPROJ:
        print("Error: pyproj es necesario para render_glm_layer.", file=sys.stderr)
        return None

    # Resolver CRS desde metadata
    crs_str = _resolve_crs(metadata.get('crs'))
    if crs_str is None:
        print("Error: metadata no contiene 'crs'.", file=sys.stderr)
        return None

    bounds = metadata.get('bounds')
    if bounds is None:
        print("Error: metadata no contiene 'bounds'.", file=sys.stderr)
        return None
    # bounds en formato rasterio: (left, bottom, right, top)
    xmin, ymin, xmax, ymax = bounds[0], bounds[1], bounds[2], bounds[3]

    # Tamaño de imagen desde metadata si está disponible, o desde 'image_size'
    img_size = metadata.get('image_size')
    if img_size:
        img_width, img_height = img_size
    else:
        img_width, img_height = 2500, 1500

    # 1. Recolectar eventos y tiempos de todos los archivos GLM
    lons_list, lats_list = [], []
    time_starts, time_ends = [], []

    for f in glm_files:
        try:
            with Dataset(f, 'r') as nc:
                event_lon = nc.variables['event_lon'][:]
                event_lat = nc.variables['event_lat'][:]
                lons_list.append(np.ma.filled(event_lon, np.nan))
                lats_list.append(np.ma.filled(event_lat, np.nan))

                # Extraer rango temporal del archivo
                for time_var in ('product_time', 'time_coverage_start',
                                 'event_time_offset'):
                    if time_var in nc.variables or hasattr(nc, time_var):
                        try:
                            if hasattr(nc, time_var):
                                t_str = getattr(nc, time_var)
                                dt = datetime.strptime(
                                    t_str[:19], "%Y-%m-%dT%H:%M:%S"
                                ).replace(tzinfo=timezone.utc)
                            else:
                                from netCDF4 import num2date
                                t_var = nc.variables[time_var]
                                dt_nc = num2date(t_var[0], units=t_var.units)
                                dt = datetime(dt_nc.year, dt_nc.month, dt_nc.day,
                                              dt_nc.hour, dt_nc.minute, dt_nc.second,
                                              tzinfo=timezone.utc)
                            time_starts.append(dt)
                            time_ends.append(dt)
                            break
                        except Exception:
                            pass
        except Exception as e:
            print(f"Advertencia: no se pudo leer {f}: {e}", file=sys.stderr)

    if not lons_list:
        print("Advertencia: no hay datos GLM en los archivos proporcionados.",
              file=sys.stderr)
        return None

    # Almacenar rango temporal en metadata
    if time_starts:
        t0 = min(time_starts)
        t1 = max(time_ends)
        metadata['glm_time_start'] = t0.strftime("%Y:%m:%d %H:%M:%S")
        metadata['glm_time_end'] = t1.strftime("%Y:%m:%d %H:%M:%S")

    all_lons = np.concatenate(lons_list)
    all_lats = np.concatenate(lats_list)

    # Filtrar NaN
    valid = np.isfinite(all_lons) & np.isfinite(all_lats)
    all_lons = all_lons[valid]
    all_lats = all_lats[valid]

    if all_lons.size == 0:
        return None

    # 2. Proyectar al CRS de la imagen
    transformer = Transformer.from_crs("epsg:4326", crs_str, always_xy=True)
    x_proj, y_proj = transformer.transform(all_lons, all_lats)

    # Filtrar puntos fuera de los límites proyectados
    in_bounds = (
        (x_proj >= xmin) & (x_proj <= xmax) &
        (y_proj >= ymin) & (y_proj <= ymax)
    )
    x_proj = x_proj[in_bounds]
    y_proj = y_proj[in_bounds]

    if x_proj.size == 0:
        return None

    # 3. Histograma 2D: densidad de eventos por píxel
    # numpy.histogram2d requiere bins monotónicamente crecientes
    x_bins = np.linspace(xmin, xmax, img_width + 1)
    y_bins = np.linspace(ymin, ymax, img_height + 1)

    density, _, _ = np.histogram2d(x_proj, y_proj, bins=[x_bins, y_bins])
    density = density.T      # Transponer: filas=Y, columnas=X
    density = np.flipud(density)  # Invertir Y: ymax queda en fila 0 (top de imagen)

    # 4. Construir capa RGBA con efecto "glow" (estilo CIRA)
    rgba_array = np.zeros((img_height, img_width, 4), dtype=np.uint8)

    if HAS_SCIPY:
        # Aplicar filtro Gaussiano para expandir puntos a manchas de luz.
        # sigma controla el radio de la mancha (en píxeles).
        smooth_density = gaussian_filter(density, sigma=2.0)
        # Umbral para no pintar ruido de píxeles casi vacíos
        mask = smooth_density > 0.15
        r, g, b = base_color
        rgba_array[mask, 0] = r
        rgba_array[mask, 1] = g
        rgba_array[mask, 2] = b
        # Alpha logarítmico estilo CIRA: comprime picos extremos y topa en 200
        # para que la textura de nubes sea siempre visible bajo el glow.
        alpha = np.clip(np.log1p(smooth_density[mask]) * 60, 0, 200).astype(np.uint8)
        rgba_array[mask, 3] = alpha
    else:
        # Fallback sin scipy: puntos simples con alpha mínimo visible
        mask = density > 0
        r, g, b = base_color
        rgba_array[mask, 0] = r
        rgba_array[mask, 1] = g
        rgba_array[mask, 2] = b
        alpha = np.clip(density[mask] * 40, 30, 250).astype(np.uint8)
        rgba_array[mask, 3] = alpha

    return Image.fromarray(rgba_array, 'RGBA')


# ---------------------------------------------------------------------------
# Modo grilla: productos GLMF (FED / MFA / TOE)
# ---------------------------------------------------------------------------

# Variable NetCDF que corresponde a cada producto grillado.
GRID_VARS = {
    'FED': 'flash_extent_density',
    'MFA': 'minimum_flash_area',
    'TOE': 'total_energy',
}

# Cómo se agrega cada producto sobre la ventana de acumulación. Los archivos
# GLMF son de 1 minuto, así que la ventana de 5 min la armamos nosotros.
GRID_AGG = {
    'FED': 'sum',   # glmtools asigna cada flash a un solo bin de 1 min
    'TOE': 'sum',   # la energía es aditiva
    'MFA': 'min',   # el flash más pequeño de la ventana
}

# Factor para pasar de las unidades del NetCDF a las unidades del CPT.
# Única conversión de unidades del módulo: el producto entrega TOE en nJ, pero
# los valores son ilegibles en esa unidad (p50 ≈ 1.2e-06 nJ), así que las
# paletas y la barra de color se rotulan en femtojoules, como en la literatura
# del GLM. FED (conteo) y MFA (km²) se usan tal cual.
GRID_SCALE = {
    'FED': 1.0,
    'MFA': 1.0,
    'TOE': 1e6,     # nJ -> fJ
}

GRID_UNITS = {
    'FED': 'conteo',
    'MFA': 'km2',
    'TOE': 'fJ',
}


def _grid_subdataset(path, product):
    """Ruta de subdataset de GDAL para la variable de un producto grillado."""
    return f'NETCDF:"{path}":{GRID_VARS[product]}'


def _read_grid_times(tags):
    """Extrae (inicio, fin) de los tags globales de un NetCDF GLMF."""
    out = []
    for key in ('NC_GLOBAL#time_coverage_start', 'NC_GLOBAL#time_coverage_end'):
        val = tags.get(key)
        if not val:
            out.append(None)
            continue
        try:
            out.append(datetime.strptime(val[:19], "%Y-%m-%dT%H:%M:%S")
                       .replace(tzinfo=timezone.utc))
        except ValueError:
            out.append(None)
    return out[0], out[1]


def accumulate_glm_grids(files, product):
    """
    Acumula un producto GLM grillado sobre una ventana de varios archivos.

    Cada archivo GLMF cubre 1 minuto; esta función construye la ventana
    completa (típicamente 5 archivos = 5 min) aplicando la agregación que
    corresponde al producto: suma para FED y TOE, mínimo para MFA.

    Todos los archivos deben compartir CRS, transform y shape; sumar mallas
    distintas produciría basura, así que se aborta con error explícito.

    El `_FillValue` del producto es 0 en las tres variables, o sea "sin dato"
    y "cero flashes" son el mismo valor. Se tratan como 0 al acumular.

    Args:
        files (list[str]): Rutas a los NetCDF GLMF a acumular.
        product (str): 'FED', 'MFA' o 'TOE'.

    Returns:
        tuple or None: (data, fed, crs, transform, (t_ini, t_fin)) donde `data`
        es el producto acumulado en las unidades del NetCDF (float32) y `fed`
        es el FED acumulado de la misma ventana, que el llamador usa para
        construir la máscara de pintado. Para product='FED' ambos son el mismo
        arreglo. Devuelve None si no se pudo leer ningún archivo.

    Raises:
        ValueError: si `product` no es válido, o si los archivos no comparten
            la misma malla.
    """
    if product not in GRID_VARS:
        raise ValueError(f"Producto GLM desconocido: {product!r}. "
                         f"Válidos: {sorted(GRID_VARS)}")
    if not HAS_RASTERIO:
        print("Error: rasterio es necesario para accumulate_glm_grids.",
              file=sys.stderr)
        return None

    need_fed = product != 'FED'
    agg = GRID_AGG[product]

    data = None       # acumulador del producto pedido
    fed = None        # acumulador de FED (máscara de pintado)
    crs = transform = shape = None
    starts, ends = [], []
    n_read = 0

    for f in files:
        try:
            with rasterio.open(_grid_subdataset(f, product)) as src:
                if crs is None:
                    crs, transform, shape = src.crs, src.transform, src.shape
                elif (src.crs != crs or src.transform != transform
                        or src.shape != shape):
                    raise ValueError(
                        f"Malla incompatible en {f}: se esperaba shape={shape}, "
                        f"transform={transform}, crs={crs}; se encontró "
                        f"shape={src.shape}, transform={src.transform}, crs={src.crs}. "
                        "No se pueden acumular mallas distintas.")
                values = src.read(1, masked=True)
                t0, t1 = _read_grid_times(src.tags())

            values = np.ma.filled(values.astype(np.float32), 0.0)
            values[~np.isfinite(values)] = 0.0

            if need_fed:
                with rasterio.open(_grid_subdataset(f, 'FED')) as src_fed:
                    fed_values = np.ma.filled(
                        src_fed.read(1, masked=True).astype(np.float32), 0.0)
                fed_values[~np.isfinite(fed_values)] = 0.0
            else:
                fed_values = values

            if data is None:
                # MFA se agrega por mínimo: se arranca en +inf y sólo se
                # considera donde ese archivo tuvo flashes.
                data = np.full(shape, np.inf, np.float32) if agg == 'min' \
                    else np.zeros(shape, np.float32)
                fed = data if not need_fed else np.zeros(shape, np.float32)

            if agg == 'sum':
                data += values
            else:
                np.minimum(data,
                           np.where(fed_values > 0, values, np.float32(np.inf)),
                           out=data)

            if need_fed:
                fed += fed_values

            if t0 is not None:
                starts.append(t0)
            if t1 is not None:
                ends.append(t1)
            n_read += 1

        except ValueError:
            raise
        except Exception as e:
            print(f"Advertencia: no se pudo leer {f}: {e}", file=sys.stderr)

    if not n_read:
        print("Advertencia: no se pudo leer ningún archivo GLM grillado.",
              file=sys.stderr)
        return None

    if agg == 'min':
        # Celdas sin flashes en toda la ventana: de vuelta a 0 (= sin dato).
        data[~np.isfinite(data)] = 0.0

    times = (min(starts) if starts else None, max(ends) if ends else None)
    return data, fed, crs, transform, times


def cpt_grid_breaks(cpt_obj):
    """
    Devuelve los quiebres físicos de un CPT discreto de escala logarítmica.

    Las paletas glm_*.cpt indexan por número de intervalo (0, 1, 2, ...) y
    llevan el valor físico del borde inferior de cada intervalo en la etiqueta:

        0   0  40 120  ; 0.2
        1   0  90 200  ; 0.5

    Esta indirección es deliberada. ColorPaletteTable construye su LUT de 256
    entradas lineal en el valor, de modo que una paleta con quiebres
    logarítmicos en unidades físicas colapsaría las décadas bajas en un puñado
    de índices; e indexada por valor, el parser discreto trunca los quiebres a
    entero y 0.2 y 0.5 colisionarían en 0. Al indexar por intervalo, la escala
    logarítmica vive en el CPT (no en el código) y la barra de color de
    mapdrawer sale rotulada en unidades físicas sin lógica duplicada.

    Args:
        cpt_obj (ColorPaletteTable): paleta ya cargada.

    Returns:
        list[float] or None: bordes inferiores en orden creciente, o None si el
        CPT no tiene el formato esperado.
    """
    if cpt_obj is None or not getattr(cpt_obj, 'labels', None):
        return None

    idxs = sorted(cpt_obj.labels)
    if idxs != list(range(len(idxs))):
        print("Advertencia: el CPT de grilla GLM debe indexar los intervalos "
              "desde 0 sin huecos.", file=sys.stderr)
        return None

    breaks = []
    for i in idxs:
        try:
            breaks.append(float(str(cpt_obj.labels[i]).split()[0]))
        except (ValueError, IndexError):
            print(f"Advertencia: la etiqueta del intervalo {i} del CPT no es "
                  "un valor numérico.", file=sys.stderr)
            return None

    if any(b <= a for a, b in zip(breaks, breaks[1:])):
        print("Advertencia: los quiebres del CPT de grilla GLM no son "
              "estrictamente crecientes.", file=sys.stderr)
        return None

    return breaks


def render_glm_grid_layer(files, metadata, product='FED', cpt_obj=None,
                          min_fed=0.1, alpha=220):
    """
    Genera una capa RGBA cuantitativa de un producto GLM grillado.

    Acumula la ventana con `accumulate_glm_grids`, la reproyecta a la malla de
    la imagen base y colorea por valor físico con `cpt_obj`. Almacena el rango
    temporal real de la ventana en el objeto metadata recibido como
    'glm_time_start' y 'glm_time_end', igual que `render_glm_layer`.

    Sólo se pintan las celdas con FED >= min_fed en la ventana; las demás
    quedan totalmente transparentes. Esto vale también para MFA y TOE, que se
    enmascaran con el FED de la misma ventana: sin esa máscara el color más
    bajo de la paleta se pintaría sobre todo el dominio y taparía el IR (menos
    del 1 % de las celdas tienen actividad en una ventana típica).

    El remuestreo es siempre `nearest`. Interpolar suavizaría el conteo e
    inventaría flashes donde no los hubo; es la diferencia deliberada con el
    glow decorativo de `render_glm_layer`. Como la malla GLMF es la misma malla
    fija ABI de 2 km, si la base está en proyección nativa la reproyección es
    prácticamente la identidad.

    Args:
        files (list[str]): Rutas a los NetCDF GLMF de la ventana.
        metadata: Instancia de Metadata con 'crs', 'bounds' e 'image_size'.
        product (str): 'FED', 'MFA' o 'TOE'.
        cpt_obj (ColorPaletteTable): paleta indexada por intervalo; ver
            `cpt_grid_breaks`.
        min_fed (float): FED acumulado mínimo para pintar una celda. El default
            0.1 es intencionalmente bajo: el FED del producto es fraccionario
            (mínimo observado 4.6e-06, p50 = 2.0) y un umbral de 1 descartaría
            cerca de la mitad de las celdas con actividad.
        alpha (int): opacidad constante de las celdas pintadas. El color ya
            codifica la magnitud; modular además el alpha falsearía la lectura
            del CPT.

    Returns:
        PIL.Image or None: capa RGBA del tamaño de metadata['image_size'], o
        None si no hay datos o falta información para proyectar.
    """
    if not HAS_RASTERIO:
        print("Error: rasterio es necesario para render_glm_grid_layer.",
              file=sys.stderr)
        return None

    crs_str = _resolve_crs(metadata.get('crs'))
    if crs_str is None:
        print("Error: metadata no contiene 'crs'.", file=sys.stderr)
        return None

    bounds = metadata.get('bounds')
    if bounds is None:
        print("Error: metadata no contiene 'bounds'.", file=sys.stderr)
        return None
    xmin, ymin, xmax, ymax = bounds[0], bounds[1], bounds[2], bounds[3]

    breaks = cpt_grid_breaks(cpt_obj)
    if not breaks:
        print(f"Error: se requiere un CPT de intervalos para --glm-product "
              f"{product} (ej. glm_{product.lower()}.cpt).", file=sys.stderr)
        return None

    img_size = metadata.get('image_size')
    img_width, img_height = img_size if img_size else (2500, 1500)

    acc = accumulate_glm_grids(files, product)
    if acc is None:
        return None
    data, fed, src_crs, src_transform, (t0, t1) = acc

    metadata['glm_product'] = product

    if t0 is not None and t1 is not None:
        metadata['glm_time_start'] = t0.strftime("%Y:%m:%d %H:%M:%S")
        metadata['glm_time_end'] = t1.strftime("%Y:%m:%d %H:%M:%S")

    # Reproyectar al grid de la imagen base.
    dst_transform = transform_from_bounds(xmin, ymin, xmax, ymax,
                                          img_width, img_height)

    def _warp(source):
        dst = np.zeros((img_height, img_width), np.float32)
        reproject(source=source, destination=dst,
                  src_transform=src_transform, src_crs=src_crs,
                  dst_transform=dst_transform, dst_crs=crs_str,
                  src_nodata=0, dst_nodata=0,
                  resampling=Resampling.nearest)
        return dst

    try:
        data_dst = _warp(data)
        fed_dst = data_dst if fed is data else _warp(fed)
    except Exception as e:
        print(f"Error reproyectando la malla GLM: {e}", file=sys.stderr)
        return None

    mask = fed_dst >= min_fed
    if not mask.any():
        print(f"Advertencia: ninguna celda GLM supera min_fed={min_fed} "
              "dentro de los límites de la imagen.", file=sys.stderr)
        return None

    # Índice de intervalo por valor físico. Los valores por debajo del primer
    # quiebre caen en el intervalo 0 (el color más bajo de la paleta).
    values = data_dst[mask] * GRID_SCALE[product]
    idx = np.clip(np.searchsorted(breaks, values, side='right') - 1,
                  0, len(breaks) - 1)

    palette = np.array(cpt_obj.palette[:len(breaks) * 3],
                       dtype=np.uint8).reshape(-1, 3)

    rgba = np.zeros((img_height, img_width, 4), dtype=np.uint8)
    rgba[mask, :3] = palette[idx]
    rgba[mask, 3] = np.uint8(np.clip(alpha, 0, 255))

    return Image.fromarray(rgba, 'RGBA')


# ---------------------------------------------------------------------------
# Uso standalone
# ---------------------------------------------------------------------------
if __name__ == '__main__':
    import rasterio
    from metadata import Metadata

    parser = argparse.ArgumentParser(
        description="Sobrepone datos GLM sobre una imagen base ABI.")
    parser.add_argument("base", help="Imagen base GeoTIFF o PNG.")
    parser.add_argument("glm_files", nargs='+', help="Archivos NetCDF GLM.")
    parser.add_argument("-o", "--output", default="glm_out.png",
                        help="Archivo de salida PNG (default: glm_out.png).")
    parser.add_argument("--color", default="yellow",
                        choices=["yellow", "magenta", "white"],
                        help="Color base de los rayos (default: yellow).")
    args = parser.parse_args()

    COLOR_MAP = {
        'yellow':  (255, 255, 0),
        'magenta': (255, 0, 255),
        'white':   (255, 255, 255),
    }

    # Cargar metadata desde GeoTIFF base
    try:
        with rasterio.open(args.base) as src:
            metadata = Metadata.from_rasterio(src)
            img_w, img_h = src.width, src.height
        metadata['image_size'] = (img_w, img_h)
        base_img = Image.open(args.base).convert('RGBA')
    except Exception as e:
        print(f"Error abriendo imagen base: {e}", file=sys.stderr)
        sys.exit(1)

    glm_layer = render_glm_layer(args.glm_files, metadata,
                                 base_color=COLOR_MAP[args.color])
    if glm_layer is None:
        print("No se generó capa GLM. Guardando imagen base sin cambios.")
        base_img.save(args.output)
    else:
        result = Image.alpha_composite(base_img, glm_layer)
        result.save(args.output)
        print(f"Guardado: {args.output}")
        if 'glm_time_start' in metadata:
            print(f"Rango GLM: {metadata['glm_time_start']} – {metadata['glm_time_end']}")
