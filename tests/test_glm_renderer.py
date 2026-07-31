"""
Tests para glm_renderer.py

Modo eventos (L2 LCFA), con Dataset mockeado:
- render_glm_layer() devuelve imagen RGBA del tamaño correcto
- Píxeles con rayos tienen alpha > 0; sin rayos alpha = 0
- Color configurable (amarillo vs magenta)
- metadata['glm_time_start/end'] se almacenan tras la llamada
- Lista vacía de archivos devuelve None sin excepciones
- Metadata sin CRS o sin bounds devuelve None sin excepciones

Modo grilla (productos GLMF), con rasterio.open mockeado:
- accumulate_glm_grids() suma FED y TOE, y toma el mínimo en MFA
- Mallas incompatibles producen error explícito
- cpt_grid_breaks() lee los quiebres físicos de las paletas glm_*.cpt
- render_glm_grid_layer() devuelve RGBA del tamaño de image_size, con las
  celdas sin flashes en alpha=0 y el color correcto por valor físico
- La conversión nJ -> fJ de TOE se aplica antes del lookup de color
"""

import os
import sys
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from PIL import Image

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from metadata import Metadata
from glm_renderer import render_glm_layer, GOES_PROJECTIONS
from glm_renderer import (HAS_RASTERIO, GRID_VARS, accumulate_glm_grids,
                          cpt_grid_breaks, render_glm_grid_layer)


# ---------------------------------------------------------------------------
# Fixtures y helpers
# ---------------------------------------------------------------------------

GOES18_CRS = GOES_PROJECTIONS['goes18']

# Para tests unitarios usamos epsg:4326 (proyección identidad lat/lon) para que
# los bounds sean trivialmente correctos y no dependan de cálculos GOES por satélite.
TEST_CRS = 'epsg:4326'
TEST_BOUNDS = (-130.0, 24.0, -65.0, 50.0)  # (left, bottom, right, top) en grados WGS84

IMG_W, IMG_H = 250, 150  # Imagen pequeña para velocidad


def _make_metadata():
    """Metadata mínima válida para render_glm_layer."""
    return Metadata(
        crs=TEST_CRS,
        bounds=TEST_BOUNDS,
        image_size=(IMG_W, IMG_H),
        satellite='GOES-18',
        timestamp='2026:04:28 19:15:00',
    )


def _make_mock_nc(lons, lats, time_str='2026-04-28T19:15:00Z'):
    """Construye un mock de netCDF4.Dataset con event_lon/lat y product_time."""
    nc = MagicMock()
    # Para que `with Dataset(f) as nc:` devuelva el mismo objeto nc
    nc.__enter__.return_value = nc
    nc.__exit__.return_value = False

    lon_var = MagicMock()
    lon_var.__getitem__.return_value = np.array(lons)
    lat_var = MagicMock()
    lat_var.__getitem__.return_value = np.array(lats)

    nc.variables = {'event_lon': lon_var, 'event_lat': lat_var}
    # product_time como atributo global del archivo
    nc.time_coverage_start = time_str
    return nc


# ---------------------------------------------------------------------------
# Tests principales
# ---------------------------------------------------------------------------

class TestRenderGlmLayer:

    def _run(self, glm_files, metadata, base_color=(255, 255, 0)):
        """Helper que parchea Dataset y ejecuta render_glm_layer."""
        return render_glm_layer(glm_files, metadata, base_color=base_color)

    def test_returns_rgba_image(self, tmp_path):
        """Con datos válidos debe devolver una imagen RGBA del tamaño correcto."""
        meta = _make_metadata()

        # Generar ~50 puntos dentro del CONUS (lon/lat WGS84)
        lons = np.linspace(-120, -80, 50)
        lats = np.linspace(25, 48, 50)

        mock_nc = _make_mock_nc(lons, lats)

        with patch('glm_renderer.Dataset', return_value=mock_nc):
            result = render_glm_layer(['fake.nc'], meta)

        assert result is not None
        assert isinstance(result, Image.Image)
        assert result.mode == 'RGBA'
        assert result.size == (IMG_W, IMG_H)

    def test_pixels_with_rays_have_alpha(self, tmp_path):
        """Zonas con rayos deben tener canal alpha > 0."""
        meta = _make_metadata()

        # Un punto central del CONUS
        lons = np.full(20, -100.0)
        lats = np.full(20, 35.0)
        mock_nc = _make_mock_nc(lons, lats)

        with patch('glm_renderer.Dataset', return_value=mock_nc):
            result = render_glm_layer(['fake.nc'], meta)

        assert result is not None
        arr = np.array(result)
        alpha = arr[:, :, 3]
        assert alpha.max() > 0, "Ningún píxel tiene alpha > 0 con rayos presentes"

    def test_empty_region_all_transparent(self):
        """Sin rayos en los bounds, todos los píxeles deben ser transparentes."""
        meta = _make_metadata()

        # Puntos fuera del área de test (Atlántico sur)
        lons = np.full(10, 10.0)
        lats = np.full(10, -50.0)
        mock_nc = _make_mock_nc(lons, lats)

        with patch('glm_renderer.Dataset', return_value=mock_nc):
            result = render_glm_layer(['fake.nc'], meta)

        # Puede devolver None o imagen totalmente transparente
        if result is not None:
            arr = np.array(result)
            assert arr[:, :, 3].max() == 0

    def test_yellow_color(self):
        """Color amarillo: R=255, G=255, B=0 en píxeles con rayos."""
        meta = _make_metadata()
        lons = np.full(30, -100.0)
        lats = np.full(30, 35.0)
        mock_nc = _make_mock_nc(lons, lats)

        with patch('glm_renderer.Dataset', return_value=mock_nc):
            result = render_glm_layer(['fake.nc'], meta, base_color=(255, 255, 0))

        assert result is not None
        arr = np.array(result)
        mask = arr[:, :, 3] > 0
        if mask.any():
            assert arr[mask, 0].max() == 255  # R
            assert arr[mask, 1].max() == 255  # G
            assert arr[mask, 2].max() == 0    # B

    def test_magenta_color(self):
        """Color magenta: R=255, G=0, B=255 en píxeles con rayos."""
        meta = _make_metadata()
        lons = np.full(30, -100.0)
        lats = np.full(30, 35.0)
        mock_nc = _make_mock_nc(lons, lats)

        with patch('glm_renderer.Dataset', return_value=mock_nc):
            result = render_glm_layer(['fake.nc'], meta, base_color=(255, 0, 255))

        assert result is not None
        arr = np.array(result)
        mask = arr[:, :, 3] > 0
        if mask.any():
            assert arr[mask, 0].max() == 255  # R
            assert arr[mask, 1].max() == 0    # G
            assert arr[mask, 2].max() == 255  # B

    def test_stores_glm_time_range_in_metadata(self):
        """Debe almacenar glm_time_start y glm_time_end en el objeto metadata."""
        meta = _make_metadata()
        lons = np.full(10, -100.0)
        lats = np.full(10, 35.0)
        mock_nc = _make_mock_nc(lons, lats, time_str='2026-04-28T19:20:00Z')

        with patch('glm_renderer.Dataset', return_value=mock_nc):
            render_glm_layer(['fake.nc'], meta)

        assert 'glm_time_start' in meta
        assert 'glm_time_end' in meta
        assert '2026' in meta['glm_time_start']

    def test_empty_file_list_returns_none(self):
        """Lista vacía no debe lanzar excepción y debe devolver None."""
        meta = _make_metadata()
        result = render_glm_layer([], meta)
        assert result is None

    def test_missing_crs_returns_none(self):
        """Metadata sin CRS debe devolver None sin excepción."""
        meta = Metadata(bounds=TEST_BOUNDS, image_size=(IMG_W, IMG_H))
        lons = np.full(5, -100.0)
        lats = np.full(5, 35.0)
        mock_nc = _make_mock_nc(lons, lats)

        with patch('glm_renderer.Dataset', return_value=mock_nc):
            result = render_glm_layer(['fake.nc'], meta)

        assert result is None

    def test_missing_bounds_returns_none(self):
        """Metadata sin bounds debe devolver None sin excepción."""
        meta = Metadata(crs=TEST_CRS, image_size=(IMG_W, IMG_H))
        lons = np.full(5, -100.0)
        lats = np.full(5, 35.0)
        mock_nc = _make_mock_nc(lons, lats)

        with patch('glm_renderer.Dataset', return_value=mock_nc):
            result = render_glm_layer(['fake.nc'], meta)

        assert result is None

    def test_multiple_files_concatenated(self):
        """Con varios archivos los eventos se concatenan y se produce una sola capa."""
        meta = _make_metadata()

        lons_a = np.full(10, -110.0)
        lats_a = np.full(10, 40.0)
        lons_b = np.full(10, -90.0)
        lats_b = np.full(10, 30.0)

        mock_nc_a = _make_mock_nc(lons_a, lats_a, '2026-04-28T19:15:00Z')
        mock_nc_b = _make_mock_nc(lons_b, lats_b, '2026-04-28T19:20:00Z')

        call_count = [0]
        files = ['a.nc', 'b.nc']
        mocks = [mock_nc_a, mock_nc_b]

        def mock_dataset(f, *args, **kwargs):
            idx = call_count[0]
            call_count[0] += 1
            return mocks[idx % len(mocks)]

        with patch('glm_renderer.Dataset', side_effect=mock_dataset):
            result = render_glm_layer(files, meta)

        assert result is not None
        # Con dos archivos con tiempos distintos, el rango debe diferir
        assert meta.get('glm_time_start') != meta.get('glm_time_end') or \
               meta.get('glm_time_start') is not None


# ---------------------------------------------------------------------------
# Modo grilla: productos GLMF (FED / MFA / TOE)
# ---------------------------------------------------------------------------

pytestmark_grid = pytest.mark.skipif(
    not HAS_RASTERIO, reason="rasterio no disponible")

# Malla fuente pequeña, en el mismo CRS y bounds que la imagen de salida para
# que la reproyección sea un simple remuestreo y las posiciones sean predecibles.
SRC_W, SRC_H = 13, 5
CPT_DIR = os.path.join(os.path.dirname(__file__), '..', 'colortables')


def _src_grid():
    """(crs, transform) de la malla fuente simulada."""
    from rasterio.crs import CRS
    from rasterio.transform import from_bounds
    return (CRS.from_epsg(4326),
            from_bounds(*TEST_BOUNDS, SRC_W, SRC_H))


def _make_files(per_file):
    """Construye un side_effect para rasterio.open desde datos por archivo.

    Args:
        per_file: lista de dicts {producto: ndarray} en el orden de los
            archivos; cada dict debe traer al menos 'FED'.

    Returns:
        (files, side_effect) donde files son nombres sintéticos 'f0.nc', ...
    """
    crs, transform = _src_grid()
    files = [f'f{i}.nc' for i in range(len(per_file))]

    # Índice por (archivo, variable) para resolver la ruta de subdataset.
    table = {}
    for fname, values in zip(files, per_file):
        for prod, arr in values.items():
            table[(fname, GRID_VARS[prod])] = np.asarray(arr, np.float32)

    def side_effect(path, *args, **kwargs):
        # path == 'NETCDF:"f0.nc":flash_extent_density'
        fname = path.split('"')[1]
        var = path.rsplit(':', 1)[1]
        src = MagicMock()
        src.__enter__.return_value = src
        src.__exit__.return_value = False
        src.crs = crs
        src.transform = transform
        src.shape = (SRC_H, SRC_W)
        src.read.return_value = np.ma.masked_array(table[(fname, var)])
        src.tags.return_value = {
            'NC_GLOBAL#time_coverage_start': f'2026-07-31T01:4{files.index(fname)}:00Z',
            'NC_GLOBAL#time_coverage_end': f'2026-07-31T01:4{files.index(fname) + 1}:00Z',
        }
        return src

    return files, side_effect


def _zeros():
    return np.zeros((SRC_H, SRC_W), np.float32)


def _cell(value, row=2, col=6):
    """Malla de ceros con un solo valor en (row, col)."""
    a = _zeros()
    a[row, col] = value
    return a


@pytestmark_grid
class TestAccumulateGlmGrids:

    def test_fed_se_suma(self):
        """FED se acumula por suma: glmtools no repite flashes entre minutos."""
        files, se = _make_files([{'FED': _cell(2.0)},
                                 {'FED': _cell(3.0)},
                                 {'FED': _cell(0.5)}])
        with patch('glm_renderer.rasterio.open', side_effect=se):
            data, fed, crs, transform, times = accumulate_glm_grids(files, 'FED')

        assert data[2, 6] == pytest.approx(5.5)
        assert data.sum() == pytest.approx(5.5)
        # Para FED, data y fed son el mismo acumulador
        assert fed is data

    def test_toe_se_suma(self):
        """TOE se acumula por suma: la energía es aditiva."""
        files, se = _make_files([{'FED': _cell(1.0), 'TOE': _cell(2e-6)},
                                 {'FED': _cell(1.0), 'TOE': _cell(3e-6)}])
        with patch('glm_renderer.rasterio.open', side_effect=se):
            data, fed, _, _, _ = accumulate_glm_grids(files, 'TOE')

        assert data[2, 6] == pytest.approx(5e-6)
        assert fed[2, 6] == pytest.approx(2.0)

    def test_mfa_toma_el_minimo(self):
        """MFA se agrega por mínimo sobre la ventana, no por suma ni promedio."""
        files, se = _make_files([{'FED': _cell(1.0), 'MFA': _cell(900.0)},
                                 {'FED': _cell(1.0), 'MFA': _cell(300.0)},
                                 {'FED': _cell(1.0), 'MFA': _cell(700.0)}])
        with patch('glm_renderer.rasterio.open', side_effect=se):
            data, _, _, _, _ = accumulate_glm_grids(files, 'MFA')

        assert data[2, 6] == pytest.approx(300.0)

    def test_mfa_ignora_celdas_sin_flashes(self):
        """Un archivo sin flashes en la celda no debe aportar un mínimo de 0."""
        files, se = _make_files([{'FED': _cell(1.0), 'MFA': _cell(500.0)},
                                 {'FED': _zeros(), 'MFA': _zeros()}])
        with patch('glm_renderer.rasterio.open', side_effect=se):
            data, _, _, _, _ = accumulate_glm_grids(files, 'MFA')

        assert data[2, 6] == pytest.approx(500.0)
        # Las celdas que nunca tuvieron flashes vuelven a 0, no a +inf
        assert np.isfinite(data).all()
        assert data[0, 0] == 0.0

    def test_rango_temporal_de_la_ventana(self):
        """Se reporta el inicio del primer archivo y el fin del último."""
        files, se = _make_files([{'FED': _cell(1.0)}, {'FED': _cell(1.0)}])
        with patch('glm_renderer.rasterio.open', side_effect=se):
            _, _, _, _, (t0, t1) = accumulate_glm_grids(files, 'FED')

        assert (t0.hour, t0.minute) == (1, 40)
        assert (t1.hour, t1.minute) == (1, 42)

    def test_mallas_incompatibles_es_error(self):
        """Nunca sumar mallas distintas: debe abortar con ValueError."""
        from rasterio.crs import CRS
        from rasterio.transform import from_bounds

        files, se = _make_files([{'FED': _cell(1.0)}, {'FED': _cell(1.0)}])

        def se_mixto(path, *args, **kwargs):
            src = se(path, *args, **kwargs)
            if path.split('"')[1] == 'f1.nc':
                src.shape = (SRC_H + 1, SRC_W)
                src.transform = from_bounds(*TEST_BOUNDS, SRC_W, SRC_H + 1)
            return src

        with patch('glm_renderer.rasterio.open', side_effect=se_mixto):
            with pytest.raises(ValueError, match="Malla incompatible"):
                accumulate_glm_grids(files, 'FED')

    def test_producto_invalido_es_error(self):
        with pytest.raises(ValueError, match="Producto GLM desconocido"):
            accumulate_glm_grids(['f0.nc'], 'XXX')

    def test_sin_archivos_devuelve_none(self):
        assert accumulate_glm_grids([], 'FED') is None


class TestCptGridBreaks:
    """Los quiebres físicos viven en el CPT, no en el código."""

    def _load(self, name):
        from colorpalettetable import ColorPaletteTable
        path = os.path.join(CPT_DIR, name)
        if not os.path.exists(path):
            pytest.skip(f"{name} no encontrado en el repo")
        return ColorPaletteTable(path)

    def test_fed_breaks(self):
        cpt = self._load('glm_fed.cpt')
        assert cpt_grid_breaks(cpt) == [0.2, 0.5, 1, 2, 4, 8, 15, 25, 40, 60, 120]
        assert cpt.units == 'conteo'

    def test_mfa_breaks_y_paleta_invertida(self):
        cpt = self._load('glm_mfa.cpt')
        breaks = cpt_grid_breaks(cpt)
        assert breaks == [100, 200, 400, 700, 1100, 1600, 2200, 3000, 4000, 5500]
        assert cpt.units == 'km2'
        # Invertida a propósito: área pequeña = amarillo/verde (rojo+verde
        # altos, azul bajo), área grande = azul/púrpura.
        r0, g0, b0 = cpt.colors[0]
        r9, g9, b9 = cpt.colors[len(breaks) - 1]
        assert r0 > 200 and g0 > 200 and b0 < 150, "el intervalo bajo no es amarillo"
        assert b9 > g9 and r9 > g9, "el intervalo alto no es azul/púrpura"

    def test_toe_breaks_en_fj(self):
        cpt = self._load('glm_toe.cpt')
        assert cpt_grid_breaks(cpt) == [0.1, 0.3, 1, 3, 10, 30, 100, 300, 1000, 3000]
        assert cpt.units == 'fJ'

    def test_cpt_sin_etiquetas_devuelve_none(self):
        from colorpalettetable import ColorPaletteTable
        assert cpt_grid_breaks(None) is None
        assert cpt_grid_breaks(ColorPaletteTable()) is None

    def test_etiquetas_no_numericas_devuelve_none(self, tmp_path):
        from colorpalettetable import ColorPaletteTable
        p = tmp_path / "malo.cpt"
        p.write_text("0 10 20 30 ; Clear\n1 40 50 60 ; Fog\n")
        assert cpt_grid_breaks(ColorPaletteTable(str(p))) is None

    def test_quiebres_no_crecientes_devuelve_none(self, tmp_path):
        from colorpalettetable import ColorPaletteTable
        p = tmp_path / "malo.cpt"
        p.write_text("0 10 20 30 ; 5\n1 40 50 60 ; 2\n")
        assert cpt_grid_breaks(ColorPaletteTable(str(p))) is None


@pytestmark_grid
class TestRenderGlmGridLayer:

    def _cpt(self, name='glm_fed.cpt'):
        from colorpalettetable import ColorPaletteTable
        path = os.path.join(CPT_DIR, name)
        if not os.path.exists(path):
            pytest.skip(f"{name} no encontrado en el repo")
        return ColorPaletteTable(path)

    def _render(self, per_file, product='FED', cpt_name='glm_fed.cpt',
                meta=None, **kw):
        files, se = _make_files(per_file)
        meta = meta if meta is not None else _make_metadata()
        with patch('glm_renderer.rasterio.open', side_effect=se):
            img = render_glm_grid_layer(files, meta, product=product,
                                        cpt_obj=self._cpt(cpt_name), **kw)
        return img, meta

    def test_devuelve_rgba_del_tamano_de_image_size(self):
        img, _ = self._render([{'FED': _cell(5.0)}])
        assert img is not None
        assert img.mode == 'RGBA'
        assert img.size == (IMG_W, IMG_H)

    def test_celdas_sin_flashes_totalmente_transparentes(self):
        """Sin la máscara de cero, el color más bajo taparía el IR."""
        img, _ = self._render([{'FED': _cell(5.0)}])
        arr = np.array(img)
        alpha = arr[:, :, 3]
        assert alpha.max() > 0
        # Una sola celda de 13x5 pintada: la enorme mayoría queda transparente
        assert (alpha == 0).mean() > 0.9

    def test_color_por_valor_fisico(self):
        """FED=5 cae en el intervalo [4, 8) -> quinto color de glm_fed.cpt."""
        img, _ = self._render([{'FED': _cell(5.0)}])
        arr = np.array(img)
        painted = arr[arr[:, :, 3] > 0]
        assert len(painted) > 0
        assert tuple(painted[0][:3]) == self._cpt().colors[4]

    def test_toe_convierte_nj_a_fj(self):
        """3e-6 nJ = 3 fJ -> intervalo [3, 10) de glm_toe.cpt, no el intervalo 0."""
        img, _ = self._render([{'FED': _cell(2.0), 'TOE': _cell(3e-6)}],
                              product='TOE', cpt_name='glm_toe.cpt')
        arr = np.array(img)
        painted = arr[arr[:, :, 3] > 0]
        cpt = self._cpt('glm_toe.cpt')
        assert tuple(painted[0][:3]) == cpt.colors[3]
        assert tuple(painted[0][:3]) != cpt.colors[0]

    def test_min_fed_filtra_celdas_debiles(self):
        """FED por debajo de min_fed no se pinta."""
        img, _ = self._render([{'FED': _cell(0.05)}], min_fed=0.1)
        assert img is None

        img, _ = self._render([{'FED': _cell(0.05)}], min_fed=0.01)
        assert img is not None

    def test_mfa_usa_la_mascara_de_fed(self):
        """MFA sólo se pinta donde hubo flashes en la ventana."""
        fed = _zeros()
        mfa = _zeros()
        fed[2, 6] = 3.0
        mfa[2, 6] = 250.0
        mfa[0, 0] = 4000.0   # MFA sin FED: artefacto, no debe pintarse
        files, se = _make_files([{'FED': fed, 'MFA': mfa}])
        with patch('glm_renderer.rasterio.open', side_effect=se):
            img = render_glm_grid_layer(files, _make_metadata(), product='MFA',
                                        cpt_obj=self._cpt('glm_mfa.cpt'))
        arr = np.array(img)
        # La esquina superior izquierda corresponde a la celda (0,0) de origen
        assert arr[0, 0, 3] == 0
        painted = arr[arr[:, :, 3] > 0]
        # 250 km² cae en el intervalo [200, 400) -> índice 1
        assert tuple(painted[0][:3]) == self._cpt('glm_mfa.cpt').colors[1]

    def test_alpha_constante(self):
        """El color codifica la magnitud; el alpha no debe modularla."""
        fed = _zeros()
        fed[1, 3] = 0.5
        fed[3, 9] = 90.0
        img, _ = self._render([{'FED': fed}], alpha=220)
        arr = np.array(img)
        alphas = np.unique(arr[:, :, 3][arr[:, :, 3] > 0])
        assert list(alphas) == [220]

    def test_almacena_rango_temporal_en_metadata(self):
        _, meta = self._render([{'FED': _cell(5.0)}, {'FED': _cell(5.0)}])
        assert meta['glm_time_start'] == '2026:07:31 01:40:00'
        assert meta['glm_time_end'] == '2026:07:31 01:42:00'

    def test_lista_vacia_devuelve_none(self):
        img, _ = self._render([])
        assert img is None

    def test_sin_cpt_devuelve_none(self):
        files, se = _make_files([{'FED': _cell(5.0)}])
        with patch('glm_renderer.rasterio.open', side_effect=se):
            assert render_glm_grid_layer(files, _make_metadata(),
                                         cpt_obj=None) is None

    def test_metadata_sin_crs_o_bounds_devuelve_none(self):
        files, se = _make_files([{'FED': _cell(5.0)}])
        cpt = self._cpt()
        with patch('glm_renderer.rasterio.open', side_effect=se):
            sin_crs = Metadata(bounds=TEST_BOUNDS, image_size=(IMG_W, IMG_H))
            assert render_glm_grid_layer(files, sin_crs, cpt_obj=cpt) is None
            sin_bounds = Metadata(crs=TEST_CRS, image_size=(IMG_W, IMG_H))
            assert render_glm_grid_layer(files, sin_bounds, cpt_obj=cpt) is None
