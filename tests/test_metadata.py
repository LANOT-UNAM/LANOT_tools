"""
Tests para metadata.py

Cubre:
- Acceso dict-like
- get_mapdrawer_bounds()
- from_dict / from_json_file / save_json
- from_stac_item / from_stac_item_file (Item de STAC de hpsv -j)
- enrich_from_filename()
- format_timestamp()
- format_timestamp_glm()   ← nueva funcionalidad GLM
"""

import json
import os
import sys
import tempfile

import pytest

# Asegurar que el directorio raíz del proyecto esté en el path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from metadata import Metadata


# ---------------------------------------------------------------------------
# Acceso dict-like
# ---------------------------------------------------------------------------

class TestDictInterface:
    def test_set_and_get_item(self):
        m = Metadata()
        m['crs'] = 'goes18'
        assert m['crs'] == 'goes18'

    def test_contains(self):
        m = Metadata(satellite='GOES-18')
        assert 'satellite' in m
        assert 'bounds' not in m

    def test_get_with_default(self):
        m = Metadata()
        assert m.get('missing', 42) == 42
        assert m.get('missing') is None

    def test_keys_and_items(self):
        m = Metadata(a=1, b=2)
        assert set(m.keys()) == {'a', 'b'}
        assert dict(m.items()) == {'a': 1, 'b': 2}

    def test_pop(self):
        m = Metadata(x=10)
        val = m.pop('x')
        assert val == 10
        assert 'x' not in m

    def test_pop_missing_with_default(self):
        m = Metadata()
        assert m.pop('nope', 0) == 0

    def test_repr(self):
        m = Metadata(crs='goes16')
        assert 'goes16' in repr(m)


# ---------------------------------------------------------------------------
# Bounds
# ---------------------------------------------------------------------------

class TestBounds:
    def test_get_mapdrawer_bounds_from_rasterio_tuple(self):
        # rasterio: (left, bottom, right, top)
        m = Metadata(bounds=(-130.0, 20.0, -60.0, 50.0))
        ulx, uly, lrx, lry = m.get_mapdrawer_bounds()
        assert ulx == -130.0  # minx
        assert uly == 50.0    # maxy
        assert lrx == -60.0   # maxx
        assert lry == 20.0    # miny

    def test_get_mapdrawer_bounds_none_when_missing(self):
        m = Metadata()
        assert m.get_mapdrawer_bounds() is None


# ---------------------------------------------------------------------------
# Serialización
# ---------------------------------------------------------------------------

class TestSerialization:
    def test_to_dict_returns_copy(self):
        m = Metadata(crs='goes18', satellite='GOES-18')
        d = m.to_dict()
        assert d == {'crs': 'goes18', 'satellite': 'GOES-18'}
        d['extra'] = 'val'
        assert 'extra' not in m  # no afecta el original

    def test_from_dict(self):
        m = Metadata.from_dict({'crs': 'goes16', 'satellite': 'GOES-16'})
        assert m['crs'] == 'goes16'
        assert m['satellite'] == 'GOES-16'

    def test_save_and_load_json(self, tmp_path):
        m = Metadata(crs='goes18', bounds=[-130, 20, -60, 50])
        path = str(tmp_path / 'meta.json')
        m.save_json(path)
        m2 = Metadata.from_json_file(path)
        assert m2['crs'] == 'goes18'
        assert m2['bounds'] == [-130, 20, -60, 50]

    def test_from_json_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            Metadata.from_json_file('/no/existe/meta.json')


# ---------------------------------------------------------------------------
# enrich_from_filename
# ---------------------------------------------------------------------------

class TestEnrichFromFilename:
    def test_goes_abi_filename(self):
        """Detecta sensor ABI desde nombre de archivo GOES estándar."""
        m = Metadata()
        m.enrich_from_filename('OR_ABI-L1b-RadC-M6C13_G18_s20261001800000_e20261001809000_c20261001809088.nc')
        # El sensor ABI siempre se detecta
        assert m.get('sensor') == 'ABI'

    def test_abi_channel_from_simple_filename(self):
        """Detecta banda C13 cuando aparece delimitada por _ en el nombre."""
        m = Metadata()
        m.enrich_from_filename('goes18_abi_C13_20260428_192700.tif')
        assert m.get('band') == 'C13'
        assert m.get('sensor') == 'ABI'

    def test_viirs_filename_timestamp(self):
        m = Metadata()
        m.enrich_from_filename('npp_viirs_cld_temp_acha_20260127_074806_wgs84_geo_750m.tif')
        assert m.get('timestamp') == '2026:01:27 07:48:06'
        assert m.get('satellite') == 'Suomi NPP'
        assert m.get('sensor') == 'VIIRS'

    def test_viirs_product_sst(self):
        m = Metadata()
        m.enrich_from_filename('npp_viirs_sst_20260127_185932_wgs84_geo_750m.tif')
        assert m.get('product') == 'SST'

    def test_viirs_product_cloud_type(self):
        m = Metadata()
        m.enrich_from_filename('npp_viirs_cloud_type_20260203_200738_wgs84_geo_750m.tif')
        assert m.get('product') == 'Cloud Type'

    def test_noaa20_satellite(self):
        m = Metadata()
        m.enrich_from_filename('noaa20_viirs_sst_20260101_120000.tif')
        assert m.get('satellite') == 'NOAA-20'

    def test_does_not_overwrite_existing(self):
        m = Metadata(satellite='Custom')
        m.enrich_from_filename('npp_viirs_sst_20260127_185932.tif')
        assert m['satellite'] == 'Custom'  # no sobreescrito

    def test_cldtoptemp_product_and_units(self):
        m = Metadata()
        m.enrich_from_filename('noaa20_viirs_CldTopTemp_20260508_192713_wgs84_fit.tif')
        assert m.get('product') == 'Cloud Top Temp'
        assert m.get('units') == 'K'

    def test_cldtophght_product_and_units(self):
        m = Metadata()
        m.enrich_from_filename('noaa20_viirs_CldTopHght_20260508_192713_wgs84_fit.tif')
        assert m.get('product') == 'Cloud Top Height'
        assert m.get('units') == 'm'

    def test_cloudphase_product_no_units(self):
        m = Metadata()
        m.enrich_from_filename('noaa20_viirs_CloudPhase_20260508_192713_wgs84_fit.tif')
        assert m.get('product') == 'Cloud Phase'
        assert m.get('units') is None

    def test_cld_temp_acha_product_and_units(self):
        m = Metadata()
        m.enrich_from_filename('npp_viirs_cld_temp_acha_20260127_074806_wgs84_geo_750m.tif')
        assert m.get('product') == 'Cloud Top Temp'
        assert m.get('units') == 'K'

    # --- Sondeos NUCAPS (CSPP HEAP): los nombres que escribe Polar2Grid con el
    # lector `nucaps`. La vista salia rotulada solo "NOAA-21 <fecha>", sin
    # producto NI sensor, porque faltaban las dos entradas.

    def test_nucaps_temperature_level(self):
        m = Metadata()
        m.enrich_from_filename(
            'noaa21_atms-cris_Temperature_497mb_20260630_184728_wgs84_geo_5km.tif')
        assert m.get('satellite') == 'NOAA-21'
        assert m.get('sensor') == 'CrIS+ATMS'
        assert m.get('product') == 'Temp 500 hPa'
        assert m.get('units') == 'K'

    def test_nucaps_edr_de_heap_n21(self):
        # HEAP nombra 'n21' a NOAA-21 (los SDR dicen 'j02').
        m = Metadata()
        m.enrich_from_filename('NUCAPS-EDR_v3r2_n21_s202609221909449_e202609221910147_c202609221942500.nc')
        assert m.get('satellite') == 'NOAA-21'

    def test_nucaps_skin_temperature(self):
        m = Metadata()
        m.enrich_from_filename(
            'noaa20_atms-cris_Skin_Temperature_20260630_184728_wgs84_geo_5km.tif')
        assert m.get('sensor') == 'CrIS+ATMS'
        assert m.get('product') == 'Skin Temperature'

    def test_nucaps_level_sin_entrada_propia_cae_al_generico(self):
        """Los 96 niveles que no se rinden hoy salen como 'Temperature' a secas,
        no sin nombre de producto."""
        m = Metadata()
        m.enrich_from_filename(
            'noaa21_atms-cris_Temperature_110mb_20260630_184728_wgs84_geo_5km.tif')
        assert m.get('product') == 'Temperature'

    def test_generico_no_le_gana_a_los_de_nube(self):
        """El respaldo va al final de product_map a proposito."""
        m = Metadata()
        m.enrich_from_filename('noaa20_viirs_CldTopTemp_20260508_192713_wgs84_fit.tif')
        assert m.get('product') == 'Cloud Top Temp'


# format_timestamp
# ---------------------------------------------------------------------------

class TestFormatTimestamp:
    def test_tiff_format(self):
        m = Metadata(timestamp='2026:04:10 19:27:00')
        result = m.format_timestamp()
        assert '2026/04/10' in result
        assert '19:27' in result

    def test_iso_format(self):
        m = Metadata(timestamp='2026-04-10T19:27:00Z')
        result = m.format_timestamp()
        assert '2026/04/10' in result

    def test_with_satellite(self):
        m = Metadata(satellite='GOES-18', timestamp='2026:04:10 19:27:00')
        result = m.format_timestamp(include_satellite=True)
        assert 'GOES-18' in result

    def test_without_satellite(self):
        m = Metadata(satellite='GOES-18', timestamp='2026:04:10 19:27:00')
        result = m.format_timestamp(include_satellite=False)
        assert 'GOES-18' not in result

    def test_with_band(self):
        m = Metadata(satellite='GOES-18', timestamp='2026:04:10 19:27:00', band='C13')
        result = m.format_timestamp(include_product=True)
        assert 'C13' in result

    def test_no_timestamp_returns_satellite_only(self):
        m = Metadata(satellite='GOES-18')
        result = m.format_timestamp(include_satellite=True)
        assert result == 'GOES-18'

    def test_empty_returns_none(self):
        m = Metadata()
        assert m.format_timestamp() is None


# ---------------------------------------------------------------------------
# format_timestamp_glm  (nueva funcionalidad)
# ---------------------------------------------------------------------------

class TestFormatTimestampGlm:
    def _meta_with_glm(self):
        return Metadata(
            satellite='GOES-18',
            band='C13',
            timestamp='2026:04:28 19:15:00',
            glm_time_start='2026:04:28 19:15:00',
            glm_time_end='2026:04:28 19:30:00',
        )

    def test_contains_satellite(self):
        m = self._meta_with_glm()
        result = m.format_timestamp_glm()
        assert 'GOES-18' in result

    def test_contains_abi_and_glm_label(self):
        m = self._meta_with_glm()
        result = m.format_timestamp_glm()
        assert 'ABI' in result
        assert 'GLM' in result

    def test_contains_band(self):
        m = self._meta_with_glm()
        result = m.format_timestamp_glm()
        assert 'C13' in result

    def test_contains_abi_date(self):
        m = self._meta_with_glm()
        result = m.format_timestamp_glm()
        assert '2026/04/28' in result

    def test_contains_glm_time_range(self):
        m = self._meta_with_glm()
        result = m.format_timestamp_glm()
        assert '19:15' in result
        assert '19:30' in result

    def test_contains_glm_product(self):
        m = self._meta_with_glm()
        m['glm_product'] = 'TOE'
        result = m.format_timestamp_glm()
        assert 'GLM TOE' in result

    def test_no_glm_product_plain_glm_label(self):
        m = self._meta_with_glm()
        result = m.format_timestamp_glm()
        # Sin glm_product la etiqueta es sólo "GLM", sin sufijo de producto
        assert '/ GLM' in result
        for prod in ('FED', 'MFA', 'TOE'):
            assert prod not in result

    def test_same_start_end_no_dash(self):
        m = Metadata(
            satellite='GOES-18',
            timestamp='2026:04:28 19:15:00',
            glm_time_start='2026:04:28 19:15:00',
            glm_time_end='2026:04:28 19:15:00',
        )
        result = m.format_timestamp_glm()
        assert '–' not in result

    def test_fallback_to_format_timestamp_without_glm(self):
        m = Metadata(satellite='GOES-18', timestamp='2026:04:28 19:15:00')
        result = m.format_timestamp_glm()
        # Sin datos GLM debe comportarse igual que format_timestamp
        expected = m.format_timestamp(include_satellite=True, include_product=True)
        assert result == expected


# ---------------------------------------------------------------------------
# from_stac_item: el Item de STAC que escribe hpsv -j
# ---------------------------------------------------------------------------

DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')
# Rejilla fija, un solo activo: hpsv rgb -m ash -s -4 -j (G16 CONUS)
ITEM_FIXED = os.path.join(DATA_DIR, 'hpsv_G16_conus_2024220_1302_ash.json')
# -B: activos 'image' (rejilla fija) e 'image_geographic' (EPSG:4326)
ITEM_BOTH = os.path.join(DATA_DIR, 'hpsv_G16_conus_2024220_1302_gray_C13.json')
ITEM_BOTH_FD = os.path.join(DATA_DIR, 'hpsv_G19_fd_2026172_1805_gray_C02.json')


def _load(path):
    with open(path) as f:
        return json.load(f)


class TestFromStacItem:
    def test_fixed_grid_single_asset(self):
        item = _load(ITEM_FIXED)
        m = Metadata.from_stac_item_file(ITEM_FIXED, image_path='rgb_json_out.png')
        assert m['crs'] == item['assets']['image']['proj:wkt2']
        # Rejilla fija: metros, lo mismo que proj:bbox del Item
        assert m['bounds'] == pytest.approx(item['properties']['proj:bbox'], abs=1e-3)
        assert m['timestamp'] == '2024-08-07T13:02:36Z'
        assert m['satellite'] == 'G16'
        assert m['product'] == 'Volcanic Ash'

    def test_bounds_are_not_root_bbox(self):
        """El bbox de la raíz es la huella en 4326, no la extensión del ráster."""
        item = _load(ITEM_FIXED)
        m = Metadata.from_stac_item(item)
        assert abs(m['bounds'][0]) > 360
        assert abs(item['bbox'][0]) <= 180

    def test_single_asset_does_not_require_matching_name(self):
        m = Metadata.from_stac_item_file(ITEM_FIXED, image_path='/otro/dir/renombrada.png')
        assert 'bounds' in m and 'crs' in m

    def test_timestamp_formats_for_display(self):
        m = Metadata.from_stac_item_file(ITEM_FIXED)
        assert m.format_timestamp() == 'G16 2024/08/07 13:02Z'

    @pytest.mark.parametrize('path', [ITEM_BOTH, ITEM_BOTH_FD])
    def test_B_picks_geographic_asset_by_href(self, path):
        item = _load(path)
        asset = item['assets']['image_geographic']
        m = Metadata.from_stac_item(
            item, image_path=os.path.join('/cualquier/dir', asset['href']))
        # hpsv declara proj:wkt2 (WGS 84) además de proj:epsg; vale cualquiera
        # de las dos formas mientras sea 4326.
        from pyproj import CRS
        assert CRS.from_user_input(m['crs']).to_epsg() == 4326
        a, _, c, _, e, f = asset['proj:transform']
        h, w = asset['proj:shape']
        assert m['bounds'] == pytest.approx((c, f + e * h, c + a * w, f))

    @pytest.mark.parametrize('path', [ITEM_BOTH, ITEM_BOTH_FD])
    def test_B_fixed_asset_uses_its_own_wkt2(self, path):
        """Con -B cada activo trae su CRS. El del activo fijo es la rejilla del
        satélite en metros, no el 4326 que describe el proj:* del Item."""
        item = _load(path)
        asset = item['assets']['image']
        m = Metadata.from_stac_item(item, image_path=asset['href'])
        assert m['crs'] == asset['proj:wkt2']
        assert m['crs'] != item['properties']['proj:wkt2']
        a, _, c, _, e, f = asset['proj:transform']
        h, w = asset['proj:shape']
        assert m['bounds'] == pytest.approx((c, f + e * h, c + a * w, f))
        assert abs(m['bounds'][0]) > 360

    def test_asset_without_crs_does_not_borrow_the_items(self):
        """Con varios activos, uno sin CRS propio no toma el del Item: ese
        proj:* describe a otro activo. Así salía hpsv -B hasta el 2026-09-12."""
        item = _load(ITEM_BOTH)
        del item['assets']['image']['proj:wkt2']
        with pytest.raises(ValueError, match="no declara CRS"):
            Metadata.from_stac_item(item, image_path=item['assets']['image']['href'])

    def test_single_asset_falls_back_to_item_crs(self):
        """Con un solo activo no hay ambigüedad: vale el CRS del Item."""
        item = _load(ITEM_FIXED)
        del item['assets']['image']['proj:wkt2']
        m = Metadata.from_stac_item(item)
        assert m['crs'] == item['properties']['proj:wkt2']

    def test_B_without_matching_image_fails(self):
        item = _load(ITEM_BOTH)
        with pytest.raises(ValueError, match="varios activos"):
            Metadata.from_stac_item(item, image_path='otra.png')
        with pytest.raises(ValueError, match="varios activos"):
            Metadata.from_stac_item(item)

    def test_rejects_flat_sidecar(self):
        flat = {'tool': 'hpsatviews', 'crs': 'goes18',
                'bounds': [881767.62, 3306628.5, 1883776.2, 4308637]}
        with pytest.raises(ValueError, match="no es un Item de STAC"):
            Metadata.from_stac_item(flat)

    def test_rotated_grid_fails(self):
        item = _load(ITEM_FIXED)
        item['assets']['image']['proj:transform'][1] = 0.5
        with pytest.raises(ValueError, match="rotada"):
            Metadata.from_stac_item(item)

    def test_missing_grid_fails(self):
        item = _load(ITEM_FIXED)
        del item['assets']['image']['proj:transform']
        del item['properties']['proj:transform']
        with pytest.raises(ValueError, match="proj:transform"):
            Metadata.from_stac_item(item)

    @pytest.mark.parametrize('platform, expected', [
        ('goes-19', 'G19'), ('GOES-18', 'G18'), ('noaa-21', 'NOAA-21'),
    ])
    def test_platform_short_name(self, platform, expected):
        """G19 y no GOES-19: la convención de CIMSS/CIRA y de los nombres."""
        item = _load(ITEM_FIXED)
        item['properties']['platform'] = platform
        assert Metadata.from_stac_item(item)['satellite'] == expected

    def test_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            Metadata.from_stac_item_file('/no/existe/item.json')

    def test_wkt2_matches_deleted_goes16_alias(self):
        """El CRS que trae el Item y la tabla GOES_PROJECTIONS['goes16'] que se
        borró en la fase 4 ponen los mismos puntos en el mismo sitio."""
        from pyproj import Transformer
        old = ('+proj=geos +h=35786023.0 +lon_0=-75.0 +sweep=x '
               '+a=6378137.0 +b=6356752.31414 +units=m +no_defs')
        new = Metadata.from_stac_item_file(ITEM_FIXED)['crs']
        t_old = Transformer.from_crs('epsg:4326', old, always_xy=True)
        t_new = Transformer.from_crs('epsg:4326', new, always_xy=True)
        for lon, lat in [(-99.1, 19.4), (-120.0, 45.0), (-75.0, 0.0), (-60.0, -30.0)]:
            xo, yo = t_old.transform(lon, lat)
            xn, yn = t_new.transform(lon, lat)
            assert abs(xo - xn) < 1.0 and abs(yo - yn) < 1.0
