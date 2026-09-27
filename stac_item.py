#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
stac_item - Emite un Item de STAC para las imágenes que escriben mapdrawer y
geotiff2view.

Es el inverso de Metadata.from_stac_item(): aquél lee el Item de 'hpsv -j',
éste escribe el de la vista que sale de LANOT_tools. La frontera es la misma que
fija ~/lanot/hpsatviews/docs/stac/STAC_PLAN.md: el Item lo emite la herramienta
que escribe el producto; Collection, Catalog e índice son de otro servicio.

Identidad: la vista es un Item propio, con su id, y cuando parte de un Item de
hpsv lo enlaza con rel=derived_from. No se fusionan archivos.

Autor: Alejandro Aguilar Sierra
LANOT - Laboratorio Nacional de Observación de la Tierra
"""

import json
import math
import os
import re
from datetime import datetime, timezone

STAC_VERSION = "1.0.0"
EXT_PROJ = "https://stac-extensions.github.io/projection/v1.1.0/schema.json"
EXT_PROCESSING = "https://stac-extensions.github.io/processing/v1.1.0/schema.json"

EDGE_SAMPLES = 32          # igual que FOOTPRINT_EDGE_SAMPLES de hpsv
LIMB_BISECTIONS = 40

MEDIA_TYPES = {
    '.png': 'image/png',
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.tif': 'image/tiff; application=geotiff',
    '.tiff': 'image/tiff; application=geotiff',
}


# --------------------------------------------------------------------------
# Huella en EPSG:4326. Port de ~/lanot/hpsatviews/tools/stac_sweep.py, que a su
# vez es port de src/footprint.c: se camina el borde del ráster y, donde una
# muestra cae fuera del disco visible, se lleva por bisección hacia el centro;
# donde un borde cruza el limbo se biseca además a lo largo del borde para
# clavar esa esquina. Aquí con pyproj, que ya es dependencia de LANOT_tools,
# en vez de osr. Mismo orden de vértices que el original, para que
# tests/test_stac_item.py pueda comparar contra los Items de hpsv vértice a
# vértice: es lo único que impide que las tres copias se separen.
# --------------------------------------------------------------------------
def _wrap(lon):
    while lon < -180.0:
        lon += 360.0
    while lon > 180.0:
        lon -= 360.0
    return lon


def _delta(lon, ref):
    d = lon - ref
    while d < -180.0:
        d += 360.0
    while d >= 180.0:
        d -= 360.0
    return d


def _project(tr, x, y):
    lon, lat = tr.transform(x, y)
    if not (math.isfinite(lon) and math.isfinite(lat)):
        return None
    if abs(lat) > 90.0 or abs(lon) > 180.0:
        return None
    return _wrap(lon), lat


def _bisect(tr, ax, ay, bx, by):
    """Último punto sobre la Tierra en el segmento de a (válido) hacia b."""
    lo, hi = 0.0, 1.0
    for _ in range(LIMB_BISECTIONS):
        mid = 0.5 * (lo + hi)
        if _project(tr, ax + (bx - ax) * mid, ay + (by - ay) * mid):
            lo = mid
        else:
            hi = mid
    return _project(tr, ax + (bx - ax) * lo, ay + (by - ay) * lo)


def footprint(crs, bounds):
    """
    Huella en EPSG:4326 de un ráster.

    Args:
        crs: CRS del ráster (EPSG, Proj4, WKT o pyproj.CRS).
        bounds: (left, bottom, right, top) en unidades de crs.

    Returns:
        (geometry, bbox) o None si el centro del ráster no cae en la Tierra.
        geometry es un Polygon de GeoJSON cerrado; bbox es [W, S, E, N] y, si
        la huella cruza el antimeridiano, W > E (convención de STAC).
    """
    from pyproj import CRS, Transformer

    tr = Transformer.from_crs(CRS.from_user_input(crs), "EPSG:4326",
                              always_xy=True)
    x0, x1 = sorted((bounds[0], bounds[2]))
    y0, y1 = sorted((bounds[1], bounds[3]))
    cx, cy = 0.5 * (x0 + x1), 0.5 * (y0 + y1)
    centre = _project(tr, cx, cy)
    if not centre:
        return None
    # Las longitudes se acumulan como diferencias respecto al centro, no en
    # crudo: un disco de GOES-West va de -218° a -56°, y el mínimo y máximo
    # ingenuos serían el planeta entero. En geos el centro es lon_0.
    lon_ref = centre[0]

    corners = [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]
    samples = []
    for i in range(4):
        ax, ay = corners[i]
        bx, by = corners[i + 1]
        for k in range(EDGE_SAMPLES):
            t = k / EDGE_SAMPLES
            samples.append((ax + (bx - ax) * t, ay + (by - ay) * t))

    ring = []
    for i, (px, py) in enumerate(samples):
        qx, qy = samples[i - 1]
        here = _project(tr, px, py)
        prev = _project(tr, qx, qy)
        if (here is None) != (prev is None):
            cut = (_bisect(tr, px, py, qx, qy) if here
                   else _bisect(tr, qx, qy, px, py))
            if cut:
                ring.append(cut)
        ring.append(here if here else _bisect(tr, cx, cy, px, py))
    ring = [p for p in ring if p]
    if len(ring) < 4:
        return None

    dmin = min(_delta(p[0], lon_ref) for p in ring)
    dmax = max(_delta(p[0], lon_ref) for p in ring)
    bbox = [_wrap(lon_ref + dmin), min(p[1] for p in ring),
            _wrap(lon_ref + dmax), max(p[1] for p in ring)]
    geometry = {"type": "Polygon",
                "coordinates": [[list(p) for p in ring] + [list(ring[0])]]}
    return geometry, bbox


# --------------------------------------------------------------------------
# Plataforma. Metadata guarda la forma de display ('G19', 'NOAA-20',
# 'Suomi NPP', 'Metop-C'); STAC pide un nombre canónico en minúsculas.
# --------------------------------------------------------------------------
_PLATFORMS = [
    # (regex sobre el nombre normalizado, platform, constellation, corto)
    (r'g(?:oes)?-?(\d{2})', 'goes-{0}', 'goes', 'G{0}'),
    (r'(?:suomi-?)?s?npp', 'suomi-npp', 'jpss', 'npp'),
    (r'(?:noaa-?(2\d)|j0([1-3]))', None, 'jpss', None),
    (r'metop-?([abc])', 'metop-{0}', 'metop', 'metop{0}'),
]


def canonical_platform(satellite):
    """
    Nombre de plataforma de STAC a partir del que guarda Metadata.

    Returns:
        (platform, constellation, short) o (None, None, None) si no se
        reconoce. short es la forma de los nombres de archivo (G19, n20, npp).
    """
    if not satellite:
        return None, None, None
    s = re.sub(r'[\s_]+', '-', str(satellite).strip().lower())
    for pattern, platform, constellation, short in _PLATFORMS:
        m = re.fullmatch(pattern, s)
        if not m:
            continue
        if constellation == 'jpss' and platform is None:
            # noaa-20 ↔ j01: los JPSS se numeran desde NOAA-20.
            n = int(m.group(1)) if m.group(1) else 19 + int(m.group(2))
            return f'noaa-{n}', 'jpss', f'n{n}'
        g = m.groups()
        return platform.format(*g), constellation, short.format(*g)
    return None, None, None


def instruments_for(constellation, sensor=None):
    if sensor:
        return [str(sensor).strip().lower()]
    return {'goes': ['abi']}.get(constellation)


# --------------------------------------------------------------------------
# Tiempo e identidad
# --------------------------------------------------------------------------
_TS_FORMATS = ("%Y:%m:%d %H:%M:%S", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S.%fZ",
               "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%MZ")


def parse_timestamp(ts):
    """datetime UTC desde las formas que guarda Metadata, o None."""
    if isinstance(ts, datetime):
        return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
    if not ts:
        return None
    for fmt in _TS_FORMATS:
        try:
            return datetime.strptime(str(ts).strip(), fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _slug(text):
    return re.sub(r'[^A-Za-z0-9]+', '-', str(text)).strip('-')


def build_id(meta, fallback):
    """
    lanot_<SAT>[_<SECTOR>]_<YYYYJJJ_hhmm>_<producto>, el mismo tronco que
    hpsv con otro prefijo y sin realces. Si falta algo de eso, 'lanot_' más el
    nombre de la salida: nunca un id inventado.
    """
    _, _, short = canonical_platform(meta.get('satellite'))
    when = parse_timestamp(meta.get('timestamp'))
    product = meta.get('product') or meta.get('band')
    if short and when and product:
        parts = ['lanot', short]
        if meta.get('sector'):
            parts.append(_slug(meta['sector']))
        parts += [when.strftime('%Y%j_%H%M'), _slug(product)]
        return '_'.join(parts)
    return 'lanot_' + _slug(fallback)


def derived_id(source_item):
    """id de la vista de un Item de hpsv: el mismo, con prefijo lanot_."""
    iid = source_item.get('id', '')
    return 'lanot_' + iid[len('hpsv_'):] if iid.startswith('hpsv_') else 'lanot_' + iid


def software_version():
    try:
        from importlib.metadata import version
        return version('lanot-tools')
    except Exception:
        return 'desconocida'


# --------------------------------------------------------------------------
# Rejilla y activo
# --------------------------------------------------------------------------
def grid_transform(bounds, width, height):
    """proj:transform (orden de STAC, no el de GDAL) de un ráster norte arriba."""
    left, bottom, right, top = bounds
    return [(right - left) / width, 0.0, left, 0.0, -(top - bottom) / height, top]


def crs_fields(crs):
    """proj:wkt2 y, si tiene código de autoridad, proj:epsg."""
    from pyproj import CRS
    c = CRS.from_user_input(crs)
    fields = {'proj:wkt2': c.to_wkt()}
    epsg = c.to_epsg()
    if epsg:
        fields['proj:epsg'] = epsg
    return fields


def build_asset(path, crs, bounds, width, height, item_dir=None):
    """Activo de la imagen escrita, con su propia rejilla (lección de hpsv -B)."""
    href = os.path.relpath(path, item_dir) if item_dir else os.path.basename(path)
    left, bottom, right, top = bounds
    asset = {
        'href': href,
        'type': MEDIA_TYPES.get(os.path.splitext(path)[1].lower(), 'application/octet-stream'),
        'roles': ['visual'],
        'proj:shape': [height, width],
        'proj:transform': grid_transform(bounds, width, height),
        # proj:bbox por activo: es lo que un guion con jq necesita, sin
        # tener que reconstruirlo de transform y shape.
        'proj:bbox': [left, bottom, right, top],
    }
    asset.update(crs_fields(crs))
    return asset


# --------------------------------------------------------------------------
# Item
# --------------------------------------------------------------------------
def build_item(meta, asset, *, item_id, tool, footprint_crs=None,
               footprint_bounds=None, source_item=None, source_href=None,
               collection=None):
    """
    Item de STAC de una vista.

    Args:
        meta: Metadata (o dict) con timestamp, satellite, sensor, product,
            units, cpt.
        asset (dict): De build_asset().
        item_id (str): De build_id() o derived_id().
        tool (str): 'mapdrawer' o 'geotiff2view', va a lanot:tool.
        footprint_crs, footprint_bounds: Rejilla de la que sale la huella si no
            se hereda. Conviene la de ANTES de reproyectar: el rectángulo
            reproyectado de un disco completo tiene esquinas de nodato, y
            declararlas haría que una búsqueda coincidiera con mar abierto.
        source_item (dict): Item de hpsv del que parte la vista. Si se da y
            footprint_bounds es None, geometry y bbox se heredan de él.
        source_href (str): Ruta al Item de origen, relativa al nuevo.
        collection (str): Opcional; sin ella el indizador la asigna.

    Raises:
        ValueError: Sin fecha o sin huella no hay Item: STAC exige datetime y
            geometry, y un Item sin ellas es un huérfano que nadie encuentra.
    """
    props_src = (source_item or {}).get('properties', {})

    when = parse_timestamp(props_src.get('datetime') or meta.get('timestamp'))
    if when is None:
        raise ValueError("sin fecha de observación no hay Item de STAC "
                         f"(timestamp={meta.get('timestamp')!r})")

    if footprint_bounds is None and source_item and source_item.get('geometry'):
        geometry, bbox = source_item['geometry'], source_item['bbox']
    else:
        fp = None
        if footprint_crs and footprint_bounds:
            fp = footprint(footprint_crs, footprint_bounds)
        if fp is None:
            raise ValueError("no se pudo calcular la huella en EPSG:4326: "
                             "hace falta un CRS y límites que caigan en la Tierra")
        geometry, bbox = fp

    props = {'datetime': when.strftime('%Y-%m-%dT%H:%M:%SZ')}
    if props_src.get('platform'):
        for key in ('platform', 'constellation', 'instruments'):
            if props_src.get(key):
                props[key] = props_src[key]
    else:
        platform, constellation, _ = canonical_platform(meta.get('satellite'))
        if platform:
            props['platform'] = platform
            props['constellation'] = constellation
        instruments = instruments_for(constellation, meta.get('sensor'))
        if instruments:
            props['instruments'] = instruments
    props['processing:software'] = {'lanot-tools': software_version()}
    props['lanot:tool'] = tool
    for key in ('sector', 'product', 'band', 'units', 'cpt'):
        if meta.get(key):
            props[f'lanot:{key}'] = str(meta[key])
    if 'sector' not in meta and props_src.get('hpsv:sector'):
        props['lanot:sector'] = props_src['hpsv:sector']

    links = []
    if source_href:
        links.append({'rel': 'derived_from', 'href': source_href,
                      'type': 'application/geo+json'})

    item = {
        'type': 'Feature',
        'stac_version': STAC_VERSION,
        'stac_extensions': [EXT_PROJ, EXT_PROCESSING],
        'id': item_id,
        'geometry': geometry,
        'bbox': bbox,
        'properties': props,
        'links': links,
        'assets': {'image': asset},
    }
    if collection:
        item['collection'] = collection
    return item


def write_item(item, path):
    with open(path, 'w') as f:
        json.dump(item, f, indent=2, ensure_ascii=False)
        f.write('\n')


def emit(stac_arg, output_path, crs, bounds, size, meta, tool,
         footprint_grid=None, source_item=None, source_path=None):
    """
    Arma y escribe el Item de una imagen ya guardada. Es lo que llaman
    mapdrawer --stac y geotiff2view --stac.

    Args:
        stac_arg: Valor de --stac (True o una ruta).
        output_path (str): Imagen escrita.
        crs, bounds: Rejilla de la imagen escrita (bounds en unidades de crs,
            (left, bottom, right, top)).
        size: (ancho, alto) de la imagen escrita.
        meta: Metadata o dict.
        tool (str): Herramienta que escribió la imagen.
        footprint_grid: (crs, bounds) de donde calcular la huella, o None para
            heredarla de source_item.
        source_item (dict), source_path (str): Item de hpsv de origen.

    Returns:
        str: Ruta del Item escrito.

    Raises:
        ValueError: Sin CRS, fecha o huella.
    """
    if not crs or bounds is None:
        raise ValueError("la imagen de salida no tiene CRS y límites conocidos "
                         "(¿falta --metadata o georreferencia en la entrada?)")
    if source_item:
        iid = derived_id(source_item)
    else:
        iid = build_id(meta, os.path.splitext(os.path.basename(output_path))[0])
    path = item_path(stac_arg, iid, output_path)
    item_dir = os.path.dirname(os.path.abspath(path))
    asset = build_asset(os.path.abspath(output_path), crs, bounds,
                        size[0], size[1], item_dir=item_dir)
    source_href = (os.path.relpath(os.path.abspath(source_path), item_dir)
                   if source_item and source_path else None)
    fp_crs, fp_bounds = footprint_grid if footprint_grid else (None, None)
    item = build_item(meta, asset, item_id=iid, tool=tool,
                      footprint_crs=fp_crs, footprint_bounds=fp_bounds,
                      source_item=source_item, source_href=source_href)
    write_item(item, path)
    return path


def item_path(stac_arg, item_id, output_path):
    """
    Dónde va el Item: la ruta dada, o <id>.json junto a la imagen. Se nombra
    por el id y no por la imagen, como hpsv: así no choca con el sidecar plano
    de --o_crs, que se llama como la imagen.
    """
    if stac_arg and stac_arg is not True:
        if os.path.isdir(stac_arg) or stac_arg.endswith(os.sep):
            return os.path.join(stac_arg, f'{item_id}.json')
        return stac_arg
    return os.path.join(os.path.dirname(output_path) or '.', f'{item_id}.json')
