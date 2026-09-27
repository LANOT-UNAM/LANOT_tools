"""
Tests para stac_item.py y las banderas --stac de mapdrawer y geotiff2view.

Cubre:
- footprint(): reproduce vértice a vértice la huella que emitió hpsv en los
  tres Items de tests/data (CONUS y disco completo), y el antimeridiano de
  GOES-West. Es lo único que sujeta esta copia a src/footprint.c de hpsv.
- canonical_platform(), build_id(), derived_id()
- Ida y vuelta: Metadata.from_stac_item() lee lo que build_item() escribe
- CLI: mapdrawer --stac con -m y --o_crs; geotiff2view --stac con y sin --clip;
  ambos salen con 1 si no hay CRS o fecha
- Todo Item escrito valida contra los esquemas oficiales de STAC, versionados
  en tests/data/stac_schemas/ (copia de ~/lanot/hpsatviews/docs/stac/schemas/,
  sin eo). jsonschema es dependencia dura de la suite: un salto silencioso
  contaría como aprobado un Item que nadie validó.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import stac_item
from metadata import Metadata

import jsonschema
import rasterio
from rasterio.transform import from_bounds

DATA = Path(__file__).parent / 'data'
SCHEMAS = DATA / 'stac_schemas'
ROOT = Path(__file__).parent.parent
MAPDRAWER = str(ROOT / 'mapdrawer.py')
GEOTIFF2VIEW = str(ROOT / 'geotiff2view.py')

ITEM_CONUS = DATA / 'hpsv_G16_conus_2024220_1302_ash.json'
ITEM_CONUS_B = DATA / 'hpsv_G16_conus_2024220_1302_gray_C13.json'
ITEM_FD = DATA / 'hpsv_G19_fd_2026172_1805_gray_C02.json'

# La huella de hpsv sale de la forma cerrada en C y ésta de PROJ. Fuera del
# limbo coinciden a 1e-6°; en los puntos que se llevan por bisección al borde
# del disco, donde la latitud cambia muy rápido con x, la frontera de validez
# de las dos difiere un poco y el vértice se mueve hasta 1.2e-4° (~13 m, contra
# píxeles de 500 m o más). Medido el 2026-09-26.
FOOTPRINT_TOL = 2e-4


def _load(path):
    with open(path) as f:
        return json.load(f)


def _asset_bounds(asset):
    a, _, c, _, e, f = asset['proj:transform']
    h, w = asset['proj:shape']
    return (c, f + e * h, c + a * w, f)


# ---------------------------------------------------------------------------
# Validación contra los esquemas oficiales (mismo método que
# hpsatviews/tests/stac_validators.sh, sin red)
# ---------------------------------------------------------------------------

def _schema_docs():
    docs = {}
    for path in SCHEMAS.rglob('*.json'):
        doc = json.loads(path.read_text())
        rel = path.relative_to(SCHEMAS).as_posix()
        for scheme in ('https', 'http'):
            docs[f'{scheme}://{rel}'] = doc
    return docs


def assert_valid_stac(item):
    from referencing import Registry, Resource
    from referencing.jsonschema import DRAFT7
    docs = _schema_docs()
    registry = Registry().with_resources(
        (uri, Resource.from_contents(doc, default_specification=DRAFT7))
        for uri, doc in docs.items())
    urls = [f"https://schemas.stacspec.org/v{item['stac_version']}"
            "/item-spec/json-schema/item.json"] + item['stac_extensions']
    for url in urls:
        assert url in docs, f"esquema no versionado: {url}"
        errors = list(jsonschema.Draft7Validator(docs[url], registry=registry)
                      .iter_errors(item))
        assert not errors, f"{url}: {jsonschema.exceptions.best_match(iter(errors)).message}"


# ---------------------------------------------------------------------------
# footprint
# ---------------------------------------------------------------------------

class TestFootprint:
    @pytest.mark.parametrize('item_path', [ITEM_CONUS, ITEM_CONUS_B, ITEM_FD])
    def test_matches_hpsv_vertex_by_vertex(self, item_path):
        item = _load(item_path)
        asset = item['assets']['image']      # la rejilla fija, de donde sale
        geometry, bbox = stac_item.footprint(asset['proj:wkt2'],
                                             _asset_bounds(asset))
        ref = item['geometry']['coordinates'][0]
        mine = geometry['coordinates'][0]
        assert len(mine) == len(ref)
        for p, q in zip(mine, ref):
            assert p == pytest.approx(q, abs=FOOTPRINT_TOL)
        assert bbox == pytest.approx(item['bbox'], abs=FOOTPRINT_TOL)
        assert mine[0] == mine[-1]

    def test_goes_west_crosses_antimeridian(self):
        # El disco de G19 movido a lon_0 = -137: va de 141.7°E a 55.7°W por
        # el Pacífico. Sin plegar, el mínimo y máximo serían el planeta entero.
        fd = _load(ITEM_FD)['assets']['image']
        crs = ('+proj=geos +h=35786023 +lon_0=-137 +sweep=x +ellps=GRS80 '
               '+units=m +no_defs')
        _, bbox = stac_item.footprint(crs, _asset_bounds(fd))
        west, south, east, north = bbox
        assert west > east
        assert west == pytest.approx(141.7005, abs=1e-3)
        assert east == pytest.approx(-55.7006, abs=1e-3)
        assert (south, north) == pytest.approx((-81.3282, 81.3282), abs=1e-3)

    def test_geographic_box_is_its_own_footprint(self):
        _, bbox = stac_item.footprint('EPSG:4326', (-118, 14, -86, 33))
        assert bbox == pytest.approx([-118, 14, -86, 33])

    def test_off_earth_returns_none(self):
        # Una rejilla fija enteramente fuera del disco: su centro no es Tierra.
        crs = '+proj=geos +h=35786023 +lon_0=-75 +sweep=x +ellps=GRS80'
        assert stac_item.footprint(crs, (6.0e6, 6.0e6, 7.0e6, 7.0e6)) is None


# ---------------------------------------------------------------------------
# Nombres e identidad
# ---------------------------------------------------------------------------

class TestNames:
    @pytest.mark.parametrize('sat, expected', [
        ('G19', ('goes-19', 'goes', 'G19')),
        ('goes-16', ('goes-16', 'goes', 'G16')),
        ('Suomi NPP', ('suomi-npp', 'jpss', 'npp')),
        ('NOAA-20', ('noaa-20', 'jpss', 'n20')),
        ('j02', ('noaa-21', 'jpss', 'n21')),
        ('Metop-C', ('metop-c', 'metop', 'metopc')),
        ('Landsat-9', (None, None, None)),
        (None, (None, None, None)),
    ])
    def test_canonical_platform(self, sat, expected):
        assert stac_item.canonical_platform(sat) == expected

    def test_build_id_follows_hpsv_stem(self):
        meta = Metadata(satellite='NOAA-20', timestamp='2026:09:25 19:51:49',
                        product='SST')
        assert stac_item.build_id(meta, 'x') == 'lanot_n20_2026268_1951_SST'

    def test_build_id_falls_back_to_output_name(self):
        # Sin producto no se inventa uno: se usa el nombre de la salida.
        meta = Metadata(satellite='NOAA-20', timestamp='2026:09:25 19:51:49')
        assert stac_item.build_id(meta, 'vista final') == 'lanot_vista-final'

    def test_derived_id_keeps_scene_identity(self):
        assert (stac_item.derived_id(_load(ITEM_CONUS))
                == 'lanot_G16_conus_2024220_1302_ash')


# ---------------------------------------------------------------------------
# build_item
# ---------------------------------------------------------------------------

def _viirs_item(tmp_path):
    meta = Metadata(satellite='NOAA-20', sensor='VIIRS', product='SST',
                    timestamp='2026:09:25 19:51:49', units='K')
    img = tmp_path / 'sst.png'
    bounds = (-118.0, 14.0, -86.0, 33.0)
    asset = stac_item.build_asset(str(img), 'EPSG:4326', bounds, 300, 200)
    return stac_item.build_item(
        meta, asset, item_id=stac_item.build_id(meta, 'sst'), tool='geotiff2view',
        footprint_crs='EPSG:4326', footprint_bounds=bounds), bounds


class TestBuildItem:
    def test_valid_stac(self, tmp_path):
        item, _ = _viirs_item(tmp_path)
        assert_valid_stac(item)
        props = item['properties']
        assert props['datetime'] == '2026-09-25T19:51:49Z'
        assert props['platform'] == 'noaa-20'
        assert props['instruments'] == ['viirs']
        assert props['lanot:units'] == 'K'

    def test_round_trip_through_reader(self, tmp_path):
        item, bounds = _viirs_item(tmp_path)
        meta = Metadata.from_stac_item(item, image_path='sst.png')
        # El lector prefiere proj:wkt2 a proj:epsg, así que vuelve el WKT.
        from pyproj import CRS
        assert CRS.from_user_input(meta['crs']).to_epsg() == 4326
        assert meta['bounds'] == pytest.approx(bounds)
        assert meta['satellite'] == 'NOAA-20'

    def test_no_eo_or_raster_stats_on_8bit_asset(self, tmp_path):
        item, _ = _viirs_item(tmp_path)
        asset = item['assets']['image']
        assert 'eo:bands' not in asset and 'raster:bands' not in asset

    def test_inherits_footprint_from_source(self):
        src = _load(ITEM_CONUS)
        asset = stac_item.build_asset('v.png', 'EPSG:3857', (0, 0, 1, 1), 1, 1)
        item = stac_item.build_item(Metadata(), asset, item_id='lanot_x',
                                    tool='mapdrawer', source_item=src,
                                    source_href=ITEM_CONUS.name)
        assert item['geometry'] == src['geometry']
        assert item['bbox'] == src['bbox']
        assert item['properties']['platform'] == 'goes-16'
        assert item['properties']['lanot:sector'] == 'conus'
        assert item['links'] == [{'rel': 'derived_from', 'href': ITEM_CONUS.name,
                                  'type': 'application/geo+json'}]
        assert_valid_stac(item)

    def test_no_timestamp_is_an_error(self):
        asset = stac_item.build_asset('v.png', 'EPSG:4326', (0, 0, 1, 1), 1, 1)
        with pytest.raises(ValueError, match='sin fecha'):
            stac_item.build_item(Metadata(satellite='G19'), asset, item_id='x',
                                 tool='t', footprint_crs='EPSG:4326',
                                 footprint_bounds=(0, 0, 1, 1))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _run(*args):
    return subprocess.run([sys.executable, *args], capture_output=True,
                          text=True, timeout=180)


class TestMapdrawerCli:
    def _scene(self, tmp_path):
        src = _load(ITEM_CONUS)
        h, w = src['assets']['image']['proj:shape']
        Image.new('RGB', (w, h), (40, 40, 40)).save(tmp_path / 'rgb_json_out.png')
        item_src = tmp_path / ITEM_CONUS.name
        item_src.write_text(json.dumps(src))
        return tmp_path / 'rgb_json_out.png', item_src

    def test_reprojected_view_links_to_hpsv_item(self, tmp_path):
        img, src = self._scene(tmp_path)
        (tmp_path / 'pub').mkdir()
        r = _run(MAPDRAWER, str(img), '-m', str(src), '--o_crs', 'epsg:3857',
                 '-o', str(tmp_path / 'pub' / 'vista.png'), '--stac')
        assert r.returncode == 0, r.stderr
        item = _load(tmp_path / 'pub' / 'lanot_G16_conus_2024220_1302_ash.json')
        assert_valid_stac(item)
        asset = item['assets']['image']
        assert asset['href'] == 'vista.png'
        assert asset['proj:epsg'] == 3857
        # El Item y el sidecar plano describen la misma rejilla: es lo que
        # permite migrar a los consumidores de meso sin cambiar resultados.
        flat = _load(tmp_path / 'pub' / 'vista.json')
        assert asset['proj:bbox'] == pytest.approx(flat['bounds'])
        with Image.open(tmp_path / 'pub' / 'vista.png') as out:
            assert asset['proj:shape'] == [out.height, out.width]
        # La huella es la del dato, no el rectángulo reproyectado.
        assert item['geometry'] == _load(ITEM_CONUS)['geometry']
        assert item['links'][0]['href'] == f'../{ITEM_CONUS.name}'

    def test_fixed_grid_view_keeps_source_grid(self, tmp_path):
        img, src = self._scene(tmp_path)
        r = _run(MAPDRAWER, str(img), '-m', str(src),
                 '-o', str(tmp_path / 'out.png'), '--stac', str(tmp_path / 'i.json'))
        assert r.returncode == 0, r.stderr
        asset = _load(tmp_path / 'i.json')['assets']['image']
        src_asset = _load(ITEM_CONUS)['assets']['image']
        assert asset['proj:transform'] == pytest.approx(src_asset['proj:transform'])
        assert 'proj:epsg' not in asset

    def test_without_crs_exits_1(self, tmp_path):
        Image.new('RGB', (50, 50)).save(tmp_path / 'img.png')
        r = _run(MAPDRAWER, str(tmp_path / 'img.png'), '-o',
                 str(tmp_path / 'out.png'), '--stac')
        assert r.returncode == 1
        assert 'Item de STAC' in r.stderr


class TestGeotiff2viewCli:
    def _tif(self, tmp_path, name):
        path = tmp_path / name
        import numpy as np
        data = (np.arange(300 * 200) % 251).reshape(200, 300).astype('uint8')
        with rasterio.open(path, 'w', driver='GTiff', height=200, width=300,
                           count=1, dtype='uint8', crs='EPSG:4326',
                           transform=from_bounds(-118, 14, -86, 33, 300, 200)) as d:
            d.write(data, 1)
        return path

    def test_item_from_filename_metadata(self, tmp_path):
        tif = self._tif(tmp_path, 'npp_viirs_sst_20260925_195149.tif')
        r = _run(GEOTIFF2VIEW, str(tif), '-o', str(tmp_path / 'a.png'), '--stac')
        assert r.returncode == 0, r.stderr
        item = _load(tmp_path / 'lanot_npp_2026268_1951_SST.json')
        assert_valid_stac(item)
        assert item['properties']['platform'] == 'suomi-npp'
        assert item['bbox'] == pytest.approx([-118, 14, -86, 33])
        assert item['assets']['image']['proj:bbox'] == pytest.approx([-118, 14, -86, 33])

    def test_clip_is_the_footprint(self, tmp_path):
        tif = self._tif(tmp_path, 'npp_viirs_sst_20260925_195149.tif')
        r = _run(GEOTIFF2VIEW, str(tif), '-o', str(tmp_path / 'b.png'),
                 '--clip=-110,30,-95,20', '--stac', str(tmp_path / 'b.json'))
        assert r.returncode == 0, r.stderr
        item = _load(tmp_path / 'b.json')
        assert item['bbox'] == pytest.approx([-110, 20, -95, 30])
        with Image.open(tmp_path / 'b.png') as out:
            assert item['assets']['image']['proj:shape'] == [out.height, out.width]

    def test_without_timestamp_exits_1(self, tmp_path):
        tif = self._tif(tmp_path, 'sinfecha.tif')
        r = _run(GEOTIFF2VIEW, str(tif), '-o', str(tmp_path / 'c.png'), '--stac')
        assert r.returncode == 1
        assert 'sin fecha' in r.stderr
