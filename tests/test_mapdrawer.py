"""
Tests para mapdrawer.py

Cubre:
- MapDrawer.set_image() / set_bounds() sin proyección
- draw_fecha() modifica la imagen (no lanza excepción, imagen no toda negra)
- draw_logo() sin logo en disco no lanza excepción
- overlay_glm() delega en render_glm_layer() con los parámetros correctos
  y compone la capa sobre self.image
- CLI --metadata: sólo acepta el Item de STAC de hpsv y falla en voz alta
- calculate_size / layer_width: < 1 es fracción del ancho, >= 1 píxeles
"""

import json
import os
import subprocess
import sys
from unittest.mock import MagicMock, patch
import numpy as np
import pytest
from PIL import Image

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from mapdrawer import MapDrawer, make_south_room, calculate_size, layer_width
from metadata import Metadata


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _solid_image(w=200, h=100, color=(50, 50, 50)):
    """Imagen PIL RGB rellena de un color sólido."""
    return Image.new('RGB', (w, h), color)


def _rgba_layer(w=200, h=100, color=(255, 255, 0, 128)):
    """Imagen RGBA con color sólido semitransparente."""
    return Image.new('RGBA', (w, h), color)


# Rejilla fija de GOES-18. Literal: la tabla de alias GOES_PROJECTIONS se borró
# en la fase 4 de STAC y el CRS ya sólo llega de los datos.
GOES18_PROJ = ('+proj=geos +h=35786023.0 +lon_0=-137.0 +sweep=x '
               '+a=6378137.0 +b=6356752.31414 +units=m +no_defs')


def _meta_with_bounds():
    return Metadata(
        crs=GOES18_PROJ,
        bounds=(-3627271.29, 1583174.66, 1382771.93, 4589200.59),
        satellite='GOES-18',
        timestamp='2026:04:28 19:15:00',
        image_size=(200, 100),
    )


# ---------------------------------------------------------------------------
# set_image / set_bounds
# ---------------------------------------------------------------------------

class TestSetters:
    def test_set_image(self):
        mapper = MapDrawer()
        img = _solid_image()
        mapper.set_image(img)
        assert mapper.image is img

    def test_set_bounds_updates_bounds_dict(self):
        mapper = MapDrawer()
        mapper.set_bounds(-130.0, 50.0, -60.0, 20.0)
        assert mapper.bounds['ulx'] == pytest.approx(-130.0)
        assert mapper.bounds['uly'] == pytest.approx(50.0)
        assert mapper.bounds['lrx'] == pytest.approx(-60.0)
        assert mapper.bounds['lry'] == pytest.approx(20.0)

    def test_image_none_by_default(self):
        mapper = MapDrawer()
        assert mapper.image is None


# ---------------------------------------------------------------------------
# crop
# ---------------------------------------------------------------------------

class TestCrop:
    """Los bounds tras un recorte deben describir los píxeles que quedaron.

    Si no, todo lo que se dibuje después (costas, estados, grilla) se convierte
    de lon/lat a píxel con una escala equivocada y sale desplazado.
    """

    def _mapper(self):
        # 200x100 px sobre 100°x50°: 2 px por grado en ambos ejes.
        mapper = MapDrawer()
        mapper.set_image(_solid_image(w=200, h=100))
        mapper.set_bounds(-130.0, 50.0, -30.0, 0.0)
        return mapper

    def test_crop_inside_data_keeps_requested_bounds(self):
        mapper = self._mapper()
        mapper.crop(-120.0, 40.0, -50.0, 10.0)

        assert mapper.image.size == (140, 60)
        assert mapper.bounds['ulx'] == pytest.approx(-120.0)
        assert mapper.bounds['uly'] == pytest.approx(40.0)
        assert mapper.bounds['lrx'] == pytest.approx(-50.0)
        assert mapper.bounds['lry'] == pytest.approx(10.0)

    def test_crop_past_east_edge_clamps_bounds_to_data(self):
        # El caso real: recortes definidos para GOES-19 (a1, atlantic) pedidos
        # sobre una imagen de GOES-18, que no llega tan al este.
        mapper = self._mapper()
        mapper.crop(-120.0, 40.0, -10.0, 10.0)

        # La imagen se topa con el borde este, y los bounds deben decirlo.
        assert mapper.image.size == (180, 60)
        assert mapper.bounds['lrx'] == pytest.approx(-30.0)
        assert mapper.bounds['ulx'] == pytest.approx(-120.0)

    def test_crop_past_every_edge_clamps_to_full_extent(self):
        mapper = self._mapper()
        mapper.crop(-200.0, 80.0, 20.0, -40.0)

        assert mapper.image.size == (200, 100)
        assert mapper.bounds['ulx'] == pytest.approx(-130.0)
        assert mapper.bounds['uly'] == pytest.approx(50.0)
        assert mapper.bounds['lrx'] == pytest.approx(-30.0)
        assert mapper.bounds['lry'] == pytest.approx(0.0)

    def test_clamped_crop_does_not_move_geography(self):
        # La invariante que fallaba: un punto conocido debe caer en el mismo
        # píxel de la imagen antes y después del recorte, salvo el desplazamiento
        # del borde izquierdo. Es lo que hace que las costas calcen con la imagen.
        mapper = self._mapper()
        u_full, v_full = mapper._geo2pixel(-60.0, 20.0)

        # El recorte empieza en -120°, o sea 10° (20 px) a la derecha de -130°.
        mapper.crop(-120.0, 40.0, -10.0, 10.0)
        u_crop, v_crop = mapper._geo2pixel(-60.0, 20.0)

        assert (u_crop, v_crop) == (u_full - 20, v_full - 20)


# ---------------------------------------------------------------------------
# draw_fecha
# ---------------------------------------------------------------------------

class TestDrawFecha:
    def test_no_exception_with_string(self):
        mapper = MapDrawer()
        mapper.set_image(_solid_image())
        # No debe lanzar excepción
        mapper.draw_fecha("2026/04/28 19:27Z", position=2, fontsize=15)

    def test_no_exception_with_datetime(self):
        from datetime import datetime
        mapper = MapDrawer()
        mapper.set_image(_solid_image())
        dt = datetime(2026, 4, 28, 19, 27)
        mapper.draw_fecha(dt, position=0, fontsize=15)

    def test_image_modified(self):
        """La imagen no debe ser idéntica tras draw_fecha (se escribió texto)."""
        mapper = MapDrawer()
        img = _solid_image(color=(50, 50, 50))
        mapper.set_image(img)
        original = np.array(img.copy())
        mapper.draw_fecha("2026/04/28 19:27Z", position=2, fontsize=20, color='white')
        after = np.array(mapper.image)
        assert not np.array_equal(original, after), \
            "La imagen no cambió tras draw_fecha"

    def test_no_exception_without_image(self):
        """Llamar draw_fecha sin imagen no debe lanzar excepción."""
        mapper = MapDrawer()
        mapper.draw_fecha("2026/04/28 19:27Z")

    @pytest.mark.parametrize("position", [0, 1, 2, 3])
    def test_all_positions(self, position):
        mapper = MapDrawer()
        mapper.set_image(_solid_image(w=400, h=200))
        mapper.draw_fecha("2026/04/28 19:27Z", position=position, fontsize=15)


# ---------------------------------------------------------------------------
# draw_logo
# ---------------------------------------------------------------------------

class TestDrawLogo:
    def test_no_exception_when_logo_missing(self):
        """Si el logo no existe en el path, no debe lanzar excepción."""
        mapper = MapDrawer(lanot_dir='/no/existe')
        mapper.set_image(_solid_image())
        # Sólo imprime advertencia; no debe lanzar
        mapper.draw_logo(position=3)

    def test_no_exception_without_image(self):
        mapper = MapDrawer(lanot_dir='/no/existe')
        mapper.draw_logo(position=0)


# ---------------------------------------------------------------------------
# overlay_glm
# ---------------------------------------------------------------------------

class TestOverlayGlm:
    def test_calls_render_glm_layer_with_correct_args(self):
        """overlay_glm debe llamar a render_glm_layer con los archivos y metadata."""
        mapper = MapDrawer()
        img = _solid_image()
        mapper.set_image(img)
        meta = _meta_with_bounds()

        glm_files = ['a.nc', 'b.nc']
        fake_layer = _rgba_layer(w=200, h=100, color=(255, 255, 0, 100))

        # render_glm_layer se importa localmente en overlay_glm, hay que parchear
        # el módulo glm_renderer directamente, no mapdrawer
        with patch('glm_renderer.render_glm_layer', return_value=fake_layer) as mock_render:
            mapper.overlay_glm(glm_files, meta, color=(255, 255, 0))

        mock_render.assert_called_once()
        call_args = mock_render.call_args
        assert call_args[0][0] == glm_files
        assert call_args[0][1] is meta
        assert call_args[1]['base_color'] == (255, 255, 0)

    def test_image_size_injected_into_metadata(self):
        """overlay_glm debe inyectar image_size en metadata antes de llamar al renderer."""
        mapper = MapDrawer()
        img = _solid_image(w=300, h=150)
        mapper.set_image(img)
        meta = _meta_with_bounds()
        meta.pop('image_size', None)  # eliminar si existía

        with patch('glm_renderer.render_glm_layer', return_value=None):
            mapper.overlay_glm(['fake.nc'], meta)

        assert meta.get('image_size') == (300, 150)

    def test_image_composited_when_layer_returned(self):
        """Si render_glm_layer devuelve una capa, la imagen debe cambiar."""
        mapper = MapDrawer()
        base_color = (50, 50, 50)
        img = _solid_image(w=200, h=100, color=base_color)
        mapper.set_image(img)
        meta = _meta_with_bounds()

        # Capa completamente amarilla y semitransparente
        fake_layer = _rgba_layer(w=200, h=100, color=(255, 255, 0, 200))

        with patch('glm_renderer.render_glm_layer', return_value=fake_layer):
            mapper.overlay_glm(['fake.nc'], meta)

        result_arr = np.array(mapper.image.convert('RGB'))
        # La imagen resultante debe diferir del fondo gris oscuro
        assert result_arr.mean() > np.array(img.convert('RGB')).mean()

    def test_image_unchanged_when_layer_is_none(self):
        """Si render_glm_layer devuelve None, la imagen no debe cambiar."""
        mapper = MapDrawer()
        img = _solid_image()
        mapper.set_image(img)
        original_arr = np.array(img.copy())
        meta = _meta_with_bounds()

        with patch('glm_renderer.render_glm_layer', return_value=None):
            mapper.overlay_glm(['fake.nc'], meta)

        after_arr = np.array(mapper.image.convert('RGB'))
        assert np.array_equal(original_arr, after_arr)

    def test_no_exception_without_image(self):
        """overlay_glm sin imagen establecida no debe lanzar excepción."""
        mapper = MapDrawer()
        meta = _meta_with_bounds()
        # No se llega a importar render_glm_layer porque la guardia de imagen sale antes
        mapper.overlay_glm(['fake.nc'], meta)

    def test_glm_renderer_import_error_handled(self):
        """Si glm_renderer no se puede importar, no debe lanzar excepción."""
        mapper = MapDrawer()
        mapper.set_image(_solid_image())
        meta = _meta_with_bounds()

        with patch.dict('sys.modules', {'glm_renderer': None}):
            # ImportError al intentar from glm_renderer import render_glm_layer
            # El método debe capturarlo gracefully
            try:
                mapper.overlay_glm(['fake.nc'], meta)
            except ImportError:
                pytest.fail("overlay_glm lanzó ImportError en lugar de manejarlo")


# ---------------------------------------------------------------------------
# make_south_room
# ---------------------------------------------------------------------------

def _meta_geo(bottom=20.0, top=40.0):
    """Metadata con bounds geográficos (left, bottom, right, top)."""
    return Metadata(crs='EPSG:4326', bounds=(-120.0, bottom, -100.0, top))


class TestMakeSouthRoom:
    def test_noop_si_el_sur_ya_alcanza_la_latitud(self):
        """Si el borde sur ya está al sur de lat_south no se toca nada."""
        img = _solid_image(w=100, h=200)
        meta = _meta_geo(bottom=5.0)
        out, out_meta = make_south_room(img, meta, lat_south=11.0)
        assert out is img
        assert tuple(out_meta['bounds']) == (-120.0, 5.0, -100.0, 40.0)

    def test_noop_sin_bounds(self):
        img = _solid_image(w=100, h=200)
        out, out_meta = make_south_room(img, Metadata(crs='EPSG:4326'), lat_south=11.0)
        assert out is img

    def test_desplaza_conserva_tamano_y_escala(self):
        """Modo por defecto: mismo tamaño y los mismos grados por píxel."""
        img = _solid_image(w=100, h=200)
        meta = _meta_geo(bottom=20.0, top=40.0)  # 0.1 grados/píxel
        out, out_meta = make_south_room(img, meta, lat_south=11.0)

        assert out.size == img.size
        left, bottom, right, top = out_meta['bounds']
        assert (left, right) == (-120.0, -100.0)
        assert bottom == pytest.approx(11.0, abs=0.1)
        assert (top - bottom) / out.height == pytest.approx(0.1, rel=1e-6)

    def test_desplaza_deja_vacio_el_sur(self):
        """Las filas liberadas abajo quedan en el color de relleno."""
        img = _solid_image(w=100, h=200, color=(50, 50, 50))
        out, _ = make_south_room(img, _meta_geo(), lat_south=11.0)
        arr = np.array(out)
        assert (arr[-1] == 0).all()
        assert (arr[0] == 50).all()

    def test_comprime_preserva_el_norte(self):
        """Con compress=True el borde norte no se mueve y el sur baja a lat_south."""
        img = _solid_image(w=100, h=200)
        out, out_meta = make_south_room(img, _meta_geo(), lat_south=11.0, compress=True)

        assert out.size == img.size
        left, bottom, right, top = out_meta['bounds']
        assert top == 40.0
        assert bottom == 11.0

    def test_noop_si_el_relleno_no_cabe(self):
        """Si el espacio pedido excede la imagen se devuelve sin cambios."""
        img = _solid_image(w=100, h=200)
        meta = _meta_geo(bottom=20.0, top=40.0)
        out, out_meta = make_south_room(img, meta, lat_south=-100.0)
        assert out is img
        assert tuple(out_meta['bounds']) == (-120.0, 20.0, -100.0, 40.0)


# ---------------------------------------------------------------------------
# CLI --metadata
# ---------------------------------------------------------------------------

MAPDRAWER = os.path.join(os.path.dirname(__file__), '..', 'mapdrawer.py')


class TestMetadataCli:
    """Un --metadata ilegible no puede degradar a una imagen sin georreferencia:
    antes se ignoraba en silencio y el error sólo se veía en lo publicado."""

    def _run(self, tmp_path, meta_path):
        img = tmp_path / 'img.png'
        _solid_image().save(img)
        return subprocess.run(
            [sys.executable, MAPDRAWER, str(img), '-m', str(meta_path),
             '-o', str(tmp_path / 'out.png')],
            capture_output=True, text=True, timeout=120)

    def test_flat_sidecar_exits_1(self, tmp_path):
        flat = tmp_path / 'flat.json'
        flat.write_text(json.dumps({'crs': 'goes18', 'bounds': [0, 0, 1, 1]}))
        r = self._run(tmp_path, flat)
        assert r.returncode == 1
        assert 'no es un Item de STAC' in r.stderr
        assert not (tmp_path / 'out.png').exists()

    def test_missing_metadata_file_exits_1(self, tmp_path):
        r = self._run(tmp_path, tmp_path / 'no_existe.json')
        assert r.returncode == 1
        assert 'no existe' in r.stderr
        assert not (tmp_path / 'out.png').exists()


# ---------------------------------------------------------------------------
# Tamaños: < 1 es fracción del ancho, >= 1 píxeles
# ---------------------------------------------------------------------------

class TestCalculateSize:
    @pytest.mark.parametrize('value, expected', [
        ('0.0005', 5), ('0.5', 5000), ('1', 1), ('1.0', 1), ('2', 2),
        ('0.05%', 5), (None, 7), ('abc', 7), ('abc%', 7),
    ])
    def test_rule(self, value, expected):
        assert calculate_size(value, 10000, default=7) == expected


class TestLayerWidth:
    def test_default_is_one_pixel(self, capsys):
        assert layer_width(None, 1276) == 1
        assert layer_width('', 1276) == 1
        assert capsys.readouterr().err == ''

    def test_relative_never_below_one_pixel(self):
        assert layer_width('0.0005', 500) == 1  # int(0.25) = 0

    def test_relative_scales_with_width(self, capsys):
        assert layer_width('0.0005', 10000) == 5
        assert capsys.readouterr().err == ''

    def test_one_is_a_pixel_not_the_whole_image(self, capsys):
        assert layer_width('1', 1276) == 1
        assert layer_width('1.0', 1276) == 1
        assert layer_width('2', 1276) == 2
        assert capsys.readouterr().err == ''

    @pytest.mark.parametrize('value', ['0.5', '5%'])
    def test_warns_on_huge_relative_width(self, value, capsys):
        """El caso de mesoescala: 0.5 pensado como «línea fina» es media imagen."""
        width = layer_width(value, 1276, name=f'--layer COASTLINE:white:{value}')
        assert width > 12
        err = capsys.readouterr().err
        assert 'Advertencia' in err and 'COASTLINE:white' in err

    def test_same_rule_in_all_tools(self):
        """geotiff2view y ash_view_generator no pueden volver a leer píxeles
        por su cuenta: usan las funciones de mapdrawer."""
        import geotiff2view
        assert geotiff2view.calculate_size is calculate_size
        assert geotiff2view.layer_width is layer_width
        root = os.path.join(os.path.dirname(__file__), '..')
        # mapdrawer.py sí tiene float(parts[2]), pero es la latitud de --shape;
        # su grosor de capa lo cubre test_cli_warns_on_half_image_width.
        for name in ('geotiff2view.py', 'ash_view_generator.py'):
            with open(os.path.join(root, name)) as f:
                assert 'float(parts[2])' not in f.read(), name

    def test_cli_warns_on_half_image_width(self, tmp_path):
        img = tmp_path / 'img.png'
        _solid_image().save(img)
        r = subprocess.run(
            [sys.executable, MAPDRAWER, str(img), '--bounds=-120,40,-80,10',
             '--layer', 'COASTLINE:white:0.5', '-o', str(tmp_path / 'out.png')],
            capture_output=True, text=True, timeout=120)
        assert 'Advertencia' in r.stderr and '0.5' in r.stderr
