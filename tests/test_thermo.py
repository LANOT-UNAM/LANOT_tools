"""
Tests para thermo.py — termodinámica de los Skew-T.

Se apoyan en tests/data/nucaps_perfil_cdmx.npz, que es un perfil REAL extraído de
un gránulo NUCAPS-EDR (NOAA-20, 2026-08-29, el FOR más cercano a la CDMX). El
gránulo entero pesa 3.7 MB y vive fuera del repo; el fixture son 3.7 kB y basta,
porque lo que se prueba aquí no lee archivos.

Cubre:
- Bolton: presión de vapor de saturación contra valores de tabla
- Punto de rocío desde razón de mezcla, y su ida y vuelta
- θ conservada sobre la adiabática seca
- LCL de Bolton: coincidencia de T y Td, y coherencia con Poisson
- La adiabática saturada se enfría menos que la seca, y no se desborda arriba
- Parcela continua en el LCL
- LFC/EL: ausencia declarada como nan en un sondeo estable
- El perfil real: punto de rocío por debajo de la temperatura en toda la columna
"""

import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import thermo

FIXTURE = os.path.join(os.path.dirname(__file__), 'data', 'nucaps_perfil_cdmx.npz')


@pytest.fixture(scope='module')
def perfil():
    if not os.path.exists(FIXTURE):
        pytest.skip("falta tests/data/nucaps_perfil_cdmx.npz")
    z = np.load(FIXTURE)
    p, T, w = z['pressure'], z['temperature'], z['h2o_mr']
    ok = (p > 0) & (T > 0)
    order = np.argsort(-p[ok])
    return (p[ok][order].astype(float), T[ok][order].astype(float),
            w[ok][order].astype(float))


# --- Bolton -----------------------------------------------------------------

@pytest.mark.parametrize("t_c, esperado", [
    (0.0, 6.112),      # definición de la constante
    (20.0, 23.37),     # tabla estándar: 23.4 hPa
    (-20.0, 1.2574),   # sobre agua, no sobre hielo (convención Skew-T)
])
def test_presion_vapor_saturacion(t_c, esperado):
    got = float(thermo.saturation_vapor_pressure(t_c + thermo.T0))
    assert got == pytest.approx(esperado, rel=1e-3)


def test_no_desborda_fuera_de_rango():
    """Sin la cota, el denominador cambia de signo cerca de -243.5 °C."""
    with np.errstate(all='raise'):
        v = thermo.saturation_vapor_pressure(np.array([1.0, 100.0, 500.0]))
    assert np.all(np.isfinite(v))


# --- punto de rocío ---------------------------------------------------------

def test_dewpoint_desde_razon_de_mezcla():
    """10 g/kg a 1000 hPa son ~14 °C de punto de rocío."""
    td = float(thermo.dewpoint_from_mixing_ratio(1000.0, 0.010)) - thermo.T0
    assert td == pytest.approx(14.0, abs=0.3)


def test_dewpoint_ida_y_vuelta():
    p = np.array([1000.0, 850.0, 700.0, 500.0])
    w = np.array([0.016, 0.010, 0.006, 0.002])
    td = thermo.dewpoint_from_mixing_ratio(p, w)
    assert thermo.mixing_ratio_from_dewpoint(p, td) == pytest.approx(w, rel=1e-6)


def test_saturado_implica_dewpoint_igual_a_temperatura():
    p, T = 850.0, 283.15
    w = thermo.saturation_mixing_ratio(p, T)
    assert float(thermo.dewpoint_from_mixing_ratio(p, w)) == pytest.approx(T, abs=1e-6)


def test_aire_seco_no_da_un_numero():
    """Sin vapor no hay punto de rocío; tiene que salir nan, no -300 °C."""
    assert np.isnan(float(thermo.dewpoint_from_mixing_ratio(1000.0, 0.0)))


# --- adiabática seca --------------------------------------------------------

def test_theta_se_conserva():
    p = np.array([1000.0, 850.0, 700.0, 500.0, 300.0])
    T = thermo.dry_adiabat(300.0, p)
    assert thermo.potential_temperature(p, T) == pytest.approx(300.0, rel=1e-9)


def test_theta_en_p_ref_es_la_temperatura():
    assert float(thermo.dry_adiabat(295.0, 1000.0)) == pytest.approx(295.0)


# --- LCL --------------------------------------------------------------------

def test_lcl_donde_convergen_t_y_td():
    """En el LCL la parcela está saturada: su T es su Td."""
    p0, T0_, Td0 = 1000.0, 300.15, 290.15
    p_lcl, t_lcl = thermo.lcl(p0, T0_, Td0)
    w = thermo.mixing_ratio_from_dewpoint(p0, Td0)     # se conserva al ascender
    td_lcl = thermo.dewpoint_from_mixing_ratio(p_lcl, w)
    assert float(td_lcl) == pytest.approx(t_lcl, abs=0.35)


def test_lcl_respeta_poisson():
    p0, T0_, Td0 = 1000.0, 300.15, 290.15
    p_lcl, t_lcl = thermo.lcl(p0, T0_, Td0)
    assert p_lcl < p0 and t_lcl < T0_
    assert float(thermo.potential_temperature(p_lcl, t_lcl)) == pytest.approx(
        float(thermo.potential_temperature(p0, T0_)), rel=1e-6)


def test_lcl_en_saturacion_es_el_propio_nivel():
    p_lcl, _ = thermo.lcl(900.0, 285.0, 285.0)
    assert p_lcl == pytest.approx(900.0, abs=1.0)


# --- adiabática saturada ----------------------------------------------------

def test_saturada_se_enfria_menos_que_la_seca():
    p = np.array([1000.0, 900.0, 800.0, 700.0, 600.0, 500.0])
    moist = thermo.moist_lapse(p, 300.0)
    dry = thermo.dry_adiabat(thermo.potential_temperature(1000.0, 300.0), p)
    assert np.all(moist[1:] > dry[1:])
    assert np.all(np.diff(moist) < 0)          # y sigue enfriándose


def test_saturada_no_se_desborda_arriba():
    p = np.array([1000.0 * (100.0 / 1000.0) ** (i / 60) for i in range(61)])
    with np.errstate(all='raise'):
        T = thermo.moist_lapse(p, 303.15)
    assert np.all(np.isfinite(T)) and T[-1] > 150.0


# --- parcela ----------------------------------------------------------------

def test_parcela_continua_en_el_lcl():
    p = np.array([1000.0 * (100.0 / 1000.0) ** (i / 200) for i in range(201)])
    T_par, p_lcl, t_lcl = thermo.parcel_profile(p, 300.15, 290.15)
    assert np.all(np.isfinite(T_par))
    # sin escalones: el codo del LCL es el único cambio de pendiente
    assert np.max(np.abs(np.diff(T_par))) < 1.0
    j = int(np.argmin(np.abs(p - p_lcl)))
    assert T_par[j] == pytest.approx(t_lcl, abs=0.5)


def test_parcela_arranca_en_la_temperatura_de_superficie():
    p = np.array([950.0, 900.0, 850.0, 800.0])
    T_par, _, _ = thermo.parcel_profile(p, 298.15, 293.15)
    assert T_par[0] == pytest.approx(298.15, abs=1e-6)


# --- LFC / EL ---------------------------------------------------------------

def test_sin_lfc_devuelve_nan():
    """Sondeo muy estable: la parcela nunca supera al entorno."""
    p = np.linspace(1000.0, 200.0, 80)
    T_env = 300.0 - 0.002 * (1000.0 - p)          # inversión fortísima
    T_par, p_lcl, _ = thermo.parcel_profile(p, 295.0, 285.0)
    p_lfc, p_el = thermo.lfc_el(p, T_env, T_par, p_lcl)
    assert np.isnan(p_lfc) and np.isnan(p_el)


def test_lfc_y_el_en_un_sondeo_condicionalmente_inestable():
    """Sondeo de manual: 6.5 K/km hasta la tropopausa, parcela de superficie.

    Por debajo del LCL la parcela se enfría a 9.8 K/km y va POR DETRÁS del
    entorno (eso es el CIN); saturada se enfría más despacio, lo alcanza en el
    LFC y vuelve a quedarse fría en el EL. Los tres niveles tienen que salir en
    ese orden o la figura estaría mintiendo sobre dónde empieza la convección.
    """
    p = np.array([1000.0 * (150.0 / 1000.0) ** (i / 120) for i in range(121)])
    z = 44330.0 * (1.0 - (p / 1013.25) ** 0.190263)      # altura estándar
    T_env = np.maximum(303.15 - 6.5 * z / 1000.0, 203.15)
    T_par, p_lcl, _ = thermo.parcel_profile(p, 303.15, 297.15)
    p_lfc, p_el = thermo.lfc_el(p, T_env, T_par, p_lcl)
    assert np.isfinite(p_lfc) and np.isfinite(p_el)
    assert p_el < p_lfc < p_lcl                    # el EL está MÁS ARRIBA
    assert p_lfc == pytest.approx(827.0, abs=15.0)
    assert p_el == pytest.approx(199.0, abs=15.0)
    # y por debajo del LFC la parcela va por detrás: eso es el CIN
    entre = (p < p_lcl) & (p > p_lfc)
    assert np.all(T_par[entre] < T_env[entre])


# --- el perfil real ---------------------------------------------------------

def test_perfil_real_dewpoint_no_supera_la_temperatura(perfil):
    p, T, w = perfil
    td = thermo.dewpoint_from_mixing_ratio(p, w)
    ok = np.isfinite(td)
    assert ok.sum() > 50
    assert np.all(td[ok] <= T[ok] + 0.05)


def test_perfil_real_da_parcela_y_niveles(perfil):
    p, T, w = perfil
    win = p >= 100.0
    p, T, w = p[win], T[win], w[win]
    td = thermo.dewpoint_from_mixing_ratio(p, w)
    with np.errstate(all='raise'):
        T_par, p_lcl, t_lcl = thermo.parcel_profile(p, T[0], td[0])
    assert np.all(np.isfinite(T_par))
    assert p[0] > p_lcl > 100.0                    # el LCL cae dentro de la columna
    p_lfc, p_el = thermo.lfc_el(p, T, T_par, p_lcl)
    # Este sondeo tiene CAPE ~43 J/kg: hay LFC y EL, y están muy juntos
    assert np.isfinite(p_lfc) and np.isfinite(p_el) and p_el < p_lfc
