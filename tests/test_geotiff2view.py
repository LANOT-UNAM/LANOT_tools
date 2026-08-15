"""
Tests para geotiff2view.py

Cubre el caso "el GeoTIFF no tiene un solo píxel válido": no se escribe imagen y
se sale con SIN_DATOS_VALIDOS (3), para que quien invoque pueda distinguirlo de
un fallo. Antes se pintaba todo del color de nodata y salía un JPG en negro que
la cadena de procesamiento contaba como producto bueno.

El caso real que lo motivó: el EVI de la pasada j01_d20260813_b45264 viene con
cero píxeles válidos desde el producto de CSPP LSR (2026-08-14).
"""

import os
import subprocess
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from geotiff2view import SIN_DATOS_VALIDOS

rasterio = pytest.importorskip("rasterio")
from rasterio.transform import from_origin

GEOTIFF2VIEW = os.path.join(os.path.dirname(__file__), '..', 'geotiff2view.py')
CPT_DIR = os.path.join(os.path.dirname(__file__), '..', 'colortables')


# 256x256 y no menos: con imágenes muy chicas el tamaño de fuente de la barra
# de color sale 0 y PIL aborta (ImageFont: "font size must be greater than 0").
# Es un caso límite ajeno a esto, pero hunde la prueba de control si se ignora.
def _escribir_tif(ruta, datos, nodata):
    perfil = dict(driver='GTiff', height=datos.shape[0], width=datos.shape[1],
                  count=1, dtype=datos.dtype.name, crs='EPSG:4326',
                  transform=from_origin(-100, 25, 0.01, 0.01), nodata=nodata)
    with rasterio.open(ruta, 'w', **perfil) as dst:
        dst.write(datos, 1)
    return ruta


@pytest.fixture
def tif_vacio(tmp_path):
    """Float32 enteramente NaN."""
    return _escribir_tif(str(tmp_path / 'vacio.tif'),
                         np.full((256, 256), np.nan, dtype='float32'), float('nan'))


@pytest.fixture
def tif_vacio_entero(tmp_path):
    """Int16 enteramente igual a su nodata: el vacío no siempre es NaN."""
    return _escribir_tif(str(tmp_path / 'vacio_int.tif'),
                         np.full((256, 256), -999, dtype='int16'), -999)


@pytest.fixture
def tif_con_datos(tmp_path):
    datos = np.linspace(0, 1, 256 * 256).reshape(256, 256).astype('float32')
    datos[0, 0] = np.nan          # algo de nodata, pero no todo
    return _escribir_tif(str(tmp_path / 'lleno.tif'), datos, float('nan'))


def _correr(entrada, salida, *extra):
    return subprocess.run(
        [sys.executable, GEOTIFF2VIEW, entrada, '-o', salida, '-j', *extra],
        capture_output=True, text=True)


# ---------------------------------------------------------------------------
# Sin datos válidos
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("fixture_name", ['tif_vacio', 'tif_vacio_entero'])
def test_vacio_sale_con_codigo_reservado(fixture_name, tmp_path, request):
    entrada = request.getfixturevalue(fixture_name)
    salida = str(tmp_path / 'salida.jpg')

    r = _correr(entrada, salida)

    assert r.returncode == SIN_DATOS_VALIDOS
    assert not os.path.exists(salida), "no debe escribirse una imagen en negro"


def test_vacio_avisa_sin_necesidad_de_verbose(tif_vacio, tmp_path):
    """El aviso es la única señal de que el producto se quedó sin vista."""
    r = _correr(tif_vacio, str(tmp_path / 'salida.jpg'))

    assert 'Sin datos válidos' in r.stderr


def test_vacio_con_paleta(tif_vacio, tmp_path):
    """La rama con CPT es otra ruta de load_geotiff() y también debe cubrirse."""
    salida = str(tmp_path / 'salida.jpg')
    cpt = os.path.join(CPT_DIR, 'ndvi.cpt')

    r = _correr(tif_vacio, salida, '-b', '-p', cpt)

    assert r.returncode == SIN_DATOS_VALIDOS
    assert not os.path.exists(salida)


def test_vacio_no_escribe_metadatos(tif_vacio, tmp_path):
    salida = str(tmp_path / 'salida.jpg')
    meta = str(tmp_path / 'meta.json')

    r = _correr(tif_vacio, salida, '--save-metadata', meta)

    assert r.returncode == SIN_DATOS_VALIDOS
    assert not os.path.exists(meta)


# ---------------------------------------------------------------------------
# Control: con datos no cambia nada
# ---------------------------------------------------------------------------

def test_con_datos_genera_imagen(tif_con_datos, tmp_path):
    salida = str(tmp_path / 'salida.jpg')

    r = _correr(tif_con_datos, salida)

    assert r.returncode == 0
    assert os.path.exists(salida)


def test_con_datos_y_paleta_genera_imagen(tif_con_datos, tmp_path):
    salida = str(tmp_path / 'salida.jpg')
    cpt = os.path.join(CPT_DIR, 'ndvi.cpt')

    r = _correr(tif_con_datos, salida, '-b', '-p', cpt)

    assert r.returncode == 0
    assert os.path.exists(salida)
