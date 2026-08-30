"""
Tests para skewt.py — la geometría del sesgo y la emisión del `.mg`.

Lo que se prueba aquí es lo que no se ve mirando la figura:
- y = log(p_ref/p): p_max cae en y=0 y p_min en el borde de arriba
- una isoterma sale RECTA y con la inclinación EN LA PÁGINA que se pidió
- el recorte no deja ni un punto fuera de la caja, y parte en varios tramos
- el `.mg` emitido compila con `mg` a los tres formatos (si `mg` está)

El sondeo de estos tests es sintético a propósito: la geometría no depende del
dato, y así corren sin netCDF4 y sin gránulo.
"""

import os
import shutil
import subprocess
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import thermo
import skewt


@pytest.fixture
def diag():
    return skewt.SkewT(tmin=-40, tmax=40, pmin=100, pmax=1000,
                       width=16, height=20, skew=45)


def page_xy(d, x, y):
    """(x, y) de datos → centímetros en la página, con el mapeo del `plot`."""
    bx0, by0, bx1, by1 = d.box
    return (bx0 + (x - d.tmin) / (d.tmax - d.tmin) * (bx1 - bx0),
            by0 + y / d.ymax * (by1 - by0))


# --- eje logarítmico --------------------------------------------------------

def test_pref_cae_en_cero(diag):
    assert float(diag.y_of(1000.0)) == pytest.approx(0.0, abs=1e-12)


def test_pmin_cae_en_el_borde_de_arriba(diag):
    assert float(diag.y_of(100.0)) == pytest.approx(diag.ymax, rel=1e-12)


def test_el_eje_es_logaritmico(diag):
    """Dos décadas iguales ocupan lo mismo: es lo que distingue log de lineal."""
    a = float(diag.y_of(300.0) - diag.y_of(1000.0))
    b = float(diag.y_of(90.0) - diag.y_of(300.0))
    assert a == pytest.approx(b, rel=1e-9)


# --- el sesgo ---------------------------------------------------------------

def test_en_la_base_x_es_la_temperatura(diag):
    """A p_ref el sesgo no ha corrido nada: la isoterma nace en su propio valor."""
    assert float(diag.x_of(15.0, 1000.0)) == pytest.approx(15.0)


def test_isoterma_es_recta(diag):
    p = np.array([1000.0, 700.0, 500.0, 300.0, 150.0, 100.0])
    pts = diag.curve(np.full(p.shape, -10.0), p)
    xs, ys = np.array([q[0] for q in pts]), np.array([q[1] for q in pts])
    pend = np.diff(xs) / np.diff(ys)
    assert pend == pytest.approx(pend[0], rel=1e-9)


@pytest.mark.parametrize("skew_deg", [30.0, 45.0, 60.0])
def test_isoterma_con_la_inclinacion_pedida(skew_deg):
    """El ángulo es EN LA PÁGINA, no en unidades de datos: es lo que se ve."""
    d = skewt.SkewT(tmin=-40, tmax=40, pmin=100, pmax=1000, skew=skew_deg)
    p = np.array([1000.0, 100.0])
    (x0, y0), (x1, y1) = d.curve(np.full(p.shape, 0.0), p)
    (px0, py0), (px1, py1) = page_xy(d, x0, y0), page_xy(d, x1, y1)
    assert (px1 - px0) / (py1 - py0) == pytest.approx(
        np.tan(np.radians(skew_deg)), rel=1e-9)


# --- recorte ----------------------------------------------------------------

def test_recorte_no_deja_puntos_fuera(diag):
    """Una adiabática seca entra y sale de la caja; ni un punto puede quedar fuera."""
    pts = diag.curve(thermo.dry_adiabat(370.0, diag.p_grid) - thermo.T0, diag.p_grid)
    for seg in diag.clip(pts):
        for x, y in seg:
            assert diag.tmin - 1e-6 <= x <= diag.tmax + 1e-6
            assert -1e-6 <= y <= diag.ymax + 1e-6


def test_recorte_parte_en_varios_tramos(diag):
    """Una curva que sale y vuelve a entrar da dos tramos, no un puente falso."""
    y = np.linspace(0, diag.ymax, 41)
    x = np.where((y > 0.6) & (y < 1.4), diag.tmax + 50.0, 0.0)
    segs = diag.clip(list(zip(x, y)))
    assert len(segs) == 2


def test_curva_entera_dentro_sale_de_una_pieza(diag):
    pts = diag.curve(np.full(5, 0.0), np.array([1000.0, 800, 600, 400, 250]))
    segs = diag.clip(pts)
    assert len(segs) == 1 and len(segs[0]) == 5


def test_una_curva_que_toca_una_esquina_no_da_tramo(diag):
    """La adiabática seca de θ = −40 °C toca la esquina exacta de la caja: el
    punto cae dentro, el siguiente fuera, y la bisección vuelve al mismo sitio.
    Salía como `polyline { -40.000 0.000  -40.000 0.000 }`."""
    pts = [(diag.tmin, 0.0), (diag.tmin - 1.0, -0.05), (diag.tmin - 2.0, -0.1)]
    assert diag.clip(pts) == []


def test_ningun_tramo_tiene_longitud_cero(diag):
    for th in (-40.0, -30.0, 100.0, 200.0):
        pts = diag.curve(thermo.dry_adiabat(th + thermo.T0, diag.p_grid) - thermo.T0,
                         diag.p_grid)
        for seg in diag.clip(pts):
            largo = sum(abs(b[0] - a[0]) + abs(b[1] - a[1])
                        for a, b in zip(seg, seg[1:]))
            assert largo > 1e-6, seg


def test_curva_entera_fuera_no_sale(diag):
    pts = diag.curve(np.full(5, 500.0), np.array([1000.0, 800, 600, 400, 250]))
    assert diag.clip(pts) == []


# --- emisión ----------------------------------------------------------------

def _sondeo_sintetico():
    p = np.array([1000.0 * (100.0 / 1000.0) ** (i / 40) for i in range(41)])
    z = 44330.0 * (1.0 - (p / 1013.25) ** 0.190263)
    T = np.maximum(303.15 - 6.5 * z / 1000.0, 203.15)
    Td = T - np.linspace(4.0, 35.0, p.size)
    return _Sondeo(p, T, Td)


class _Sondeo:
    def __init__(self, p, T, Td):
        self.p, self.T, self.Td = p, T, Td
        self.lat, self.lon = 19.47, -98.72
        self.requested_lat, self.requested_lon = 19.4, -99.1
        self.dist_km = 40.5
        self.cape, self.lifted_index = 1250.0, -4.2
        self.quality, self.quality_label = 0, 'accepted'
        self.timestamp = None
        self.satellite, self.sensor = 'NOAA-20', 'CrIS+ATMS'
        self.source_file, self.for_index = 'sintetico.nc', 0

    @property
    def accepted(self):
        return self.quality == 0


def test_el_ancho_del_cromo_va_fuera_del_plot(diag):
    """En mg el marco, los ejes y la leyenda NO heredan el estado del cuerpo del
    `plot` —solo los `rule`—, así que un `line_width` dentro del bloque no llega
    y el cromo sale al ancho por omisión (1 pt). Tiene que ir antes del `plot`."""
    src = diag.render(_sondeo_sintetico(), "Prueba")
    lineas = src.splitlines()
    i_lw = next(k for k, l in enumerate(lineas) if l.strip() == 'line_width 0.4')
    i_plot = next(k for k, l in enumerate(lineas) if l.startswith('plot('))
    assert i_lw < i_plot

    # y dentro del bloque no puede quedar ninguna sentencia de ancho para el cromo
    cuerpo = lineas[i_plot:next(k for k, l in enumerate(lineas) if l == '}')]
    anchos = [l.strip() for l in cuerpo if l.strip().startswith('line_width')]
    assert anchos == [], anchos


def test_render_emite_las_piezas_esperadas(diag):
    src = diag.render(_sondeo_sintetico(), "Prueba")
    for pieza in ('display_size', 'plot(', 'rule(y=', 'xaxis(', 'yaxis(',
                  'legend(', 'table(', 'polyline', 'CAPE', 'accepted'):
        assert pieza in src, f"falta {pieza} en el .mg emitido"
    assert src.count('{') == src.count('}')


def test_un_parametro_no_recuperado_se_declara_no_se_omite(diag):
    """NUCAPS deja el Lifted Index sin recuperar a menudo. Quitar la fila lo haría
    indistinguible de un producto que nunca la trae: tiene que decir n/d."""
    snd = _sondeo_sintetico()
    snd.lifted_index = float('nan')
    src = diag.render(snd, "Prueba")
    assert 'row("LI", "n/d")' in src
    assert 'row("CAPE", "1250 J/kg")' in src


def test_la_cabecera_del_mg_se_explica_sola(diag):
    """El `.mg` es un artefacto versionable: tiene que decir de qué gránulo, qué
    FOR, qué satélite, cuándo, dónde y con qué calidad, sin el .nc al lado."""
    cabecera = "\n".join(l for l in diag.render(_sondeo_sintetico(), "Prueba")
                         .splitlines() if l.startswith('%'))
    for pieza in ('sintetico.nc', 'FOR 0', 'NOAA-20', 'CrIS+ATMS',
                  '19.47°N', '98.72°W', 'Quality_Flag 0', 'accepted'):
        assert pieza in cabecera, f"falta {pieza} en la cabecera"


def test_render_rotula_el_sitio_real_no_el_pedido(diag):
    """El FOR está a 40 km del punto pedido; la figura tiene que decir dónde está."""
    src = diag.render(_sondeo_sintetico(), "Prueba")
    assert '19.47' in src and '98.72' in src
    assert '40 km del punto pedido' in src


@pytest.mark.skipif(shutil.which(skewt.MG_BIN) is None,
                    reason="mg no está en el PATH")
@pytest.mark.parametrize("ext", ['.svg', '.pdf', '.eps'])
def test_el_mg_emitido_compila(diag, tmp_path, ext):
    mg_file = tmp_path / "d.mg"
    mg_file.write_text(diag.render(_sondeo_sintetico(), "Prueba"))
    out = tmp_path / ("d" + ext)
    r = subprocess.run([shutil.which(skewt.MG_BIN), str(mg_file), str(out)],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert out.exists() and out.stat().st_size > 1000
    # Un símbolo o un argumento desconocido NO aborta a mg: avisa y sigue, así que
    # sin esto un .mg mal emitido pasaría la prueba con la figura estropeada.
    assert 'Warning' not in r.stderr, r.stderr
    assert 'Error' not in r.stderr, r.stderr


# --- CLI --------------------------------------------------------------------

def test_size_se_parsea():
    assert skewt._size("16x20") == (16.0, 20.0)


def test_size_mal_escrito_es_error():
    import argparse
    with pytest.raises(argparse.ArgumentTypeError):
        skewt._size("16-20")
