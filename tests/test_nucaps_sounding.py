"""
Tests para nucaps_sounding.py — el lector de sondeos NUCAPS-EDR.

Se construye un gránulo NetCDF MINIATURA en tmp_path (3 FOR, los niveles del
perfil real del fixture) en vez de versionar los 3.7 MB del original. Así el
lector se ejercita de verdad —enmascarado, elección del FOR, calidad— sobre la
estructura exacta del producto, sin meter un binario grande al repo.

Cubre:
- el -999.0 de NUCAPS, que NO es el _FillValue declarado, queda enmascarado
- los niveles por debajo de Surface_Pressure se caen
- se elige el FOR más cercano, y se devuelven SUS coordenadas y la distancia
- sin --lat/--lon se cae al centro del segmento
- un FOR más lejos que --max-dist es un error, no una figura silenciosamente mala
- un retrieval rechazado es un error salvo que se pida lo contrario
- la etiqueta de calidad sale de flag_values/flag_meanings del propio archivo
- CAPE y Lifted Index salen de Stability[0] y Stability[9]
"""

import os
import sys
import warnings

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

netCDF4 = pytest.importorskip("netCDF4")

import nucaps_sounding as ns

FIXTURE = os.path.join(os.path.dirname(__file__), 'data', 'nucaps_perfil_cdmx.npz')

FLAG_VALUES = np.array([0, 1, 2, 4, 8, 9, 16, 17, 24, 25], dtype='i4')
FLAG_MEANINGS = ('accepted reject_physical reject_MIT reject_NOAA_reg reject_iMIT '
                 'reject_phy_and_iMIT reject_iNOAA reject_phy_and_iNOAA '
                 'reject_iMIT_and_iNOAA reject_phy_and_iMIT_and_iNOAA')


@pytest.fixture(scope='module')
def perfil():
    if not os.path.exists(FIXTURE):
        pytest.skip("falta tests/data/nucaps_perfil_cdmx.npz")
    return np.load(FIXTURE)


def escribe_granulo(path, perfil, lats, lons, quality, stability_over=None,
                    p_surf=None):
    """Un NUCAPS-EDR miniatura con la estructura del real y N FOR iguales."""
    ps = float(perfil['surface_pressure']) if p_surf is None else p_surf

    # netCDF4 1.7.4 emite un DeprecationWarning de numpy ≥2.5 al ESCRIBIR arreglos
    # ("Setting the shape on a NumPy array has been deprecated"). Es de la
    # biblioteca, no nuestro, y solo lo tocamos aquí: el código de producción
    # únicamente lee, y la lectura no lo dispara. Se silencia en este punto —no en
    # toda la suite— para que el día que netCDF4 se actualice esto quede visible.
    with warnings.catch_warnings():
        warnings.filterwarnings('ignore', category=DeprecationWarning,
                                message='Setting the shape on a NumPy array')
        _escribe(path, perfil, lats, lons, quality, stability_over, ps)
    return str(path)


def _escribe(path, perfil, lats, lons, quality, stability_over, ps):
    p = perfil['pressure'].astype('f4')
    T = perfil['temperature'].astype('f4')
    w = perfil['h2o_mr'].astype('f4')
    n, nl = len(lats), p.size
    with netCDF4.Dataset(path, 'w') as ds:
        ds.createDimension('Number_of_CrIS_FORs', n)
        ds.createDimension('Number_of_P_Levels', nl)
        ds.createDimension('Number_of_Stability_Parameters', 16)

        def var(name, dims, dtype='f4', fill=-9999.0):
            return ds.createVariable(name, dtype, dims, fill_value=fill)

        var('Latitude', ('Number_of_CrIS_FORs',))[:] = np.asarray(lats, 'f4')
        var('Longitude', ('Number_of_CrIS_FORs',))[:] = np.asarray(lons, 'f4')
        var('Surface_Pressure', ('Number_of_CrIS_FORs',))[:] = np.full(n, ps, 'f4')
        var('Time', ('Number_of_CrIS_FORs',), 'f8')[:] = np.full(
            n, float(perfil['time_msec']), 'f8')

        dims2 = ('Number_of_CrIS_FORs', 'Number_of_P_Levels')
        var('Pressure', dims2)[:] = np.tile(p, (n, 1))
        var('Temperature', dims2)[:] = np.tile(T, (n, 1))
        var('H2O_MR', dims2)[:] = np.tile(w, (n, 1))

        st = np.tile(perfil['stability'].astype('f4'), (n, 1))
        if stability_over:
            for col, val in stability_over.items():
                st[:, col] = val
        var('Stability', ('Number_of_CrIS_FORs',
                          'Number_of_Stability_Parameters'))[:] = st

        qf = ds.createVariable('Quality_Flag', 'i4', ('Number_of_CrIS_FORs',),
                               fill_value=-9999)
        qf.flag_values = FLAG_VALUES
        qf.flag_meanings = FLAG_MEANINGS
        qf[:] = np.asarray(quality, 'i4')


@pytest.fixture
def granulo(tmp_path, perfil):
    """Tres FOR sobre el centro de México, el del medio en (19.47, -98.72)."""
    return escribe_granulo(
        tmp_path / 'NUCAPS-EDR_v3r2_j01_s202608291918189_e_c.nc', perfil,
        lats=[18.0, 19.47, 21.0], lons=[-98.0, -98.72, -99.5],
        quality=[0, 0, 0], stability_over={0: 1500.0, 9: -3.5})


# --- selección del FOR ------------------------------------------------------

def test_elige_el_for_mas_cercano(granulo):
    s = ns.read_sounding([granulo], 19.5, -98.7)
    assert s.for_index == 1
    assert (s.lat, s.lon) == pytest.approx((19.47, -98.72), abs=0.01)


def test_devuelve_las_coordenadas_del_for_no_las_pedidas(granulo):
    s = ns.read_sounding([granulo], 19.0, -98.5)
    assert (s.requested_lat, s.requested_lon) == (19.0, -98.5)
    assert s.lat != 19.0 and s.dist_km > 0


def test_sin_coordenadas_toma_el_centro(granulo):
    s = ns.read_sounding([granulo])
    assert s.for_index == 1                 # el del medio del segmento
    assert s.requested_lat is None


def test_mas_lejos_del_limite_es_un_error(granulo):
    with pytest.raises(ValueError, match="km"):
        ns.read_sounding([granulo], 0.0, 0.0, max_dist_km=100.0)


def test_busca_en_todos_los_archivos(tmp_path, perfil, granulo):
    otro = escribe_granulo(tmp_path / 'otro.nc', perfil,
                           lats=[30.0, 31.0], lons=[-105.0, -106.0],
                           quality=[0, 0])
    s = ns.read_sounding([granulo, otro], 30.9, -105.9)
    assert os.path.basename(s.source_file) == 'otro.nc'
    assert s.n_files == 2


# --- calidad ----------------------------------------------------------------

def test_rechazado_no_se_dibuja_por_omision(tmp_path, perfil):
    g = escribe_granulo(tmp_path / 'malo.nc', perfil, lats=[19.5], lons=[-98.7],
                        quality=[1])
    with pytest.raises(ValueError, match="reject_physical"):
        ns.read_sounding([g], 19.5, -98.7)


def test_rechazado_se_dibuja_si_se_pide(tmp_path, perfil):
    g = escribe_granulo(tmp_path / 'malo.nc', perfil, lats=[19.5], lons=[-98.7],
                        quality=[9])
    s = ns.read_sounding([g], 19.5, -98.7, require_accepted=False)
    assert s.quality == 9
    assert s.quality_label == 'reject_phy_and_iMIT'
    assert not s.accepted


def test_la_etiqueta_sale_del_archivo(granulo):
    """No de una tabla nuestra: si NUCAPS cambia el catálogo, no mentimos."""
    s = ns.read_sounding([granulo], 19.5, -98.7)
    assert s.quality_label == 'accepted' and s.accepted


# --- enmascarado ------------------------------------------------------------

def test_el_999_de_nucaps_queda_enmascarado(tmp_path, perfil):
    """-999.0 NO es el _FillValue declarado (-9999.0), así que netCDF4 lo deja pasar."""
    g = escribe_granulo(tmp_path / 'g.nc', perfil, lats=[19.5], lons=[-98.7],
                        quality=[0], stability_over={0: 1200.0, 9: -999.0})
    s = ns.read_sounding([g], 19.5, -98.7)
    assert s.cape == pytest.approx(1200.0)
    assert np.isnan(s.lifted_index)          # y no -999, que se dibujaría como dato


def test_cae_lo_que_esta_bajo_la_superficie(tmp_path, perfil):
    g = escribe_granulo(tmp_path / 'g.nc', perfil, lats=[19.5], lons=[-98.7],
                        quality=[0], p_surf=500.0)
    s = ns.read_sounding([g], 19.5, -98.7)
    assert s.p.max() <= 500.0 + 1e-6
    assert s.surface_pressure == pytest.approx(500.0)


def test_los_niveles_van_de_la_superficie_hacia_arriba(granulo):
    s = ns.read_sounding([granulo], 19.5, -98.7)
    assert np.all(np.diff(s.p) < 0)
    assert np.all(np.isfinite(s.p)) and np.all(np.isfinite(s.T))


# --- variables derivadas ----------------------------------------------------

def test_cape_y_li_salen_de_stability(granulo):
    s = ns.read_sounding([granulo], 19.5, -98.7)
    assert s.cape == pytest.approx(1500.0)          # Stability[0]
    assert s.lifted_index == pytest.approx(-3.5)    # Stability[9]


def test_deriva_el_punto_de_rocio(granulo):
    """NUCAPS no lo trae: sale de H2O_MR, y no puede superar a la temperatura."""
    s = ns.read_sounding([granulo], 19.5, -98.7)
    ok = np.isfinite(s.Td)
    assert ok.sum() > 50
    assert np.all(s.Td[ok] <= s.T[ok] + 0.05)


def test_identifica_satelite_y_sensor(granulo):
    s = ns.read_sounding([granulo], 19.5, -98.7)
    assert s.satellite == 'NOAA-20'          # del j01 del nombre, vía Metadata
    assert s.sensor == 'CrIS+ATMS'
    assert s.timestamp is not None and s.timestamp.year == 2026
