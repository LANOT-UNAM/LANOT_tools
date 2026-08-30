#! /usr/bin/env python3
# -*- coding: utf-8 -*-
"""
skewt - Termodiagramas Skew-T Log-P a partir de sondeos satelitales NUCAPS.

El motor de dibujo es MetaGráfica (`mg`): Python calcula el perfil, la
termodinámica y la geometría del sesgo, y emite un `.mg` que `mg` compila a SVG,
PDF o EPS. El formato lo elige la extensión de la salida, igual que en `mg`.

Por qué el eje logarítmico NO es el `yscale="log"` de mg: el sesgo de un Skew-T es
un shear en el espacio (T, log p), y con eje log mg remapea coordenada por
coordenada —las matrices no componen— así que el shear no se puede expresar ahí.
Haciendo y = log(p_ref/p) en Python el `plot` es lineal, el sesgo es aritmética, y
toda la física queda del lado que se puede probar.

Autor: Alejandro Aguilar Sierra
LANOT - Laboratorio Nacional de Observación de la Tierra
"""

import os
import sys
import math
import shutil
import argparse
import subprocess

import numpy as np

import thermo

MG_BIN = os.environ.get('MG_BIN', 'mg')
FORMATS = ('.svg', '.pdf', '.eps')

# Isolíneas del fondo. Los pasos son los de un Skew-T de servicio; el rango de las
# adiabáticas va mucho más allá de la ventana a propósito, porque con el sesgo una
# curva que nace fuera de la caja entra en ella más arriba.
ISOTHERM_STEP = 10          # °C
DRY_THETA = range(-40, 201, 10)          # °C
MOIST_T0 = range(-30, 41, 5)             # °C, temperatura de partida en p_ref
MIXING_RATIOS = (0.4, 1, 2, 3, 5, 8, 12, 20, 30)      # g/kg
MIXING_TOP_HPA = 200        # arriba de esto la línea de mezcla no dice nada útil

STYLE = {
    'isotherm':   ('steelblue', 0.25, None),
    'dry':        ('orange',    0.25, None),
    'moist':      ('seagreen',  0.25, 'dashed'),
    'mixing':     ('olive',     0.25, 'dotted'),
    'isobar':     ('gray',      0.25, None),
    'temp':       ('red',       1.1,  None),
    'dewpoint':   ('green',     1.1,  None),
    'parcel':     ('black',     0.7,  'dashed'),
    'level':      ('purple',    0.4,  'dotted'),
}


def _fmt(v, dec=3):
    return f"{v:.{dec}f}"


def _has_extent(seg, tol=1e-6):
    """True si el tramo mide algo. La tolerancia va en unidades de datos (°C y
    log p), muy por debajo de los tres decimales con que se emite."""
    return any(abs(b[0] - a[0]) > tol or abs(b[1] - a[1]) > tol
               for a, b in zip(seg, seg[1:]))


class SkewT:
    """Geometría del diagrama y emisión del `.mg`.

    Todo lo que dibuja pasa por `x_of`/`y_of` y por `clip`, así que el sesgo y el
    recorte al marco se definen en un solo sitio.
    """

    def __init__(self, tmin=-40.0, tmax=40.0, pmin=100.0, pmax=1000.0,
                 width=16.0, height=20.0, skew=45.0, font_size=8.0):
        self.tmin, self.tmax = float(tmin), float(tmax)
        self.pmin, self.pmax = float(pmin), float(pmax)
        self.width, self.height = float(width), float(height)
        self.font_size = float(font_size)

        # Márgenes de la caja: a la izquierda cabe el rótulo de presión más el
        # nombre del eje; arriba, el encabezado de tres renglones.
        self.box = (2.3, 1.9, self.width - 0.7, self.height - 2.6)
        self.ymax = math.log(self.pmax / self.pmin)

        bw = self.box[2] - self.box[0]
        bh = self.box[3] - self.box[1]
        # Pendiente del sesgo tal que una isoterma suba `skew` grados EN LA PÁGINA.
        # Sale de igualar dx_pagina/dy_pagina = tan(skew) con el mapeo del plot.
        self.m = (math.tan(math.radians(skew)) * (self.tmax - self.tmin) * bh
                  / (self.ymax * bw))

        # Rejilla en p, uniforme en log: es la que hace que una curva calculada se
        # vea suave en el diagrama, que es donde se mira.
        n = 60
        self.p_grid = self.pmax * (self.pmin / self.pmax) ** (np.arange(n + 1) / n)

    # --- geometría ---------------------------------------------------------
    def y_of(self, p):
        return np.log(self.pmax / np.asarray(p, dtype=float))

    def x_of(self, T_C, p):
        return np.asarray(T_C, dtype=float) + self.m * self.y_of(p)

    def inside(self, x, y):
        return (self.tmin <= x <= self.tmax) and (0.0 <= y <= self.ymax)

    def clip(self, pts):
        """Parte una polilínea en los tramos que caen dentro de la caja de datos."""
        segs, cur = [], []

        def edge(a, b):
            """Punto del borde entre `a` (dentro) y `b` (fuera), por bisección."""
            lo, hi = a, b
            for _ in range(40):
                mid = (0.5 * (lo[0] + hi[0]), 0.5 * (lo[1] + hi[1]))
                if self.inside(*mid):
                    lo = mid
                else:
                    hi = mid
            return lo

        for a, b in zip(pts, pts[1:]):
            if not (np.isfinite(a[0]) and np.isfinite(a[1])):
                if cur:
                    segs.append(cur)
                    cur = []
                continue
            if not (np.isfinite(b[0]) and np.isfinite(b[1])):
                continue
            ia, ib = self.inside(*a), self.inside(*b)
            if ia and ib:
                if not cur:
                    cur.append(a)
                cur.append(b)
            elif ia:
                if not cur:
                    cur.append(a)
                cur.append(edge(a, b))
                segs.append(cur)
                cur = []
            elif ib:
                cur = [edge(b, a), b]
        if cur:
            segs.append(cur)
        # `len(s) > 1` no basta: una curva que toca una ESQUINA exacta de la caja
        # da un tramo de dos puntos idénticos —el punto cae dentro, el siguiente
        # fuera, y `edge` biseca hasta volver al mismo sitio—, que se emitía como
        # `polyline { -40.000 0.000  -40.000 0.000 }`.
        return [s for s in segs if len(s) > 1 and _has_extent(s)]

    def curve(self, T_C, p):
        """Puntos (x, y) del diagrama para una curva dada en (T °C, p)."""
        return list(zip(np.asarray(self.x_of(T_C, p), dtype=float).ravel(),
                        np.asarray(self.y_of(p), dtype=float).ravel()))

    # --- emisión -----------------------------------------------------------
    def _polys(self, out, key, curves):
        color, lw, dash = STYLE[key]
        out.append(f'  color "{color}"  line_width {lw}'
                   + (f'  dash "{dash}"' if dash else '  dash "solid"'))
        for pts in curves:
            for seg in self.clip(pts):
                body = "  ".join(f"{_fmt(x)} {_fmt(y)}" for x, y in seg)
                out.append(f"  polyline {{ {body} }}")

    def _background(self, out):
        out.append("\n  % isotermas")
        # Arranca muy a la izquierda: con el sesgo, una isoterma de -140 °C en la
        # base entra a la caja en la parte alta del diagrama.
        t0 = int(self.tmin - self.m * self.ymax) - ISOTHERM_STEP
        t1 = int(self.tmax) + ISOTHERM_STEP
        self._polys(out, 'isotherm',
                    [self.curve(np.full(self.p_grid.shape, t), self.p_grid)
                     for t in range(t0, t1 + 1, ISOTHERM_STEP)])

        out.append("\n  % adiabáticas secas (θ constante)")
        self._polys(out, 'dry',
                    [self.curve(thermo.dry_adiabat(th + thermo.T0, self.p_grid)
                                - thermo.T0, self.p_grid) for th in DRY_THETA])

        out.append("\n  % adiabáticas saturadas")
        self._polys(out, 'moist',
                    [self.curve(thermo.moist_lapse(self.p_grid, t + thermo.T0)
                                - thermo.T0, self.p_grid) for t in MOIST_T0])

        out.append("\n  % razón de mezcla de saturación (g/kg)")
        pm = self.p_grid[self.p_grid >= MIXING_TOP_HPA]
        self._polys(out, 'mixing',
                    [self.curve(thermo.temperature_at_mixing_ratio(pm, w / 1000.0)
                                - thermo.T0, pm) for w in MIXING_RATIOS])

    def _isobars(self, out):
        out.append("\n  % isobaras: rule por nivel, porque en y=log(p) no van a paso fijo")
        color, lw, _ = STYLE['isobar']
        out.append(f'  color "{color}"  line_width {lw}  dash "solid"')
        for p in (1000, 850, 700, 500, 400, 300, 250, 200, 150, 100):
            if self.pmin <= p <= self.pmax:
                out.append(f'  rule(y={_fmt(float(self.y_of(p)), 4)}, '
                           f'label="{p}", label_at="axis")')

    def _profile(self, out, snd):
        pc = snd.p - 0.0
        out.append("\n  % perfil medido")
        self._polys(out, 'temp', [self.curve(snd.T - thermo.T0, pc)])
        self._polys(out, 'dewpoint', [self.curve(snd.Td - thermo.T0, pc)])

    def _parcel(self, out, snd):
        """Parcela levantada desde el nivel más bajo, con LCL, LFC y EL."""
        if not (np.isfinite(snd.T[0]) and np.isfinite(snd.Td[0])):
            return None
        # Solo dentro de la ventana: los niveles de NUCAPS llegan a 0.016 hPa y una
        # pseudoadiabática integrada hasta ahí no es que se salga del dibujo, es que
        # deja de tener sentido físico y desborda el exponencial de Bolton.
        win = snd.p >= self.pmin
        p_win, T_win = snd.p[win], snd.T[win]
        T_par, p_lcl, t_lcl = thermo.parcel_profile(p_win, T_win[0], snd.Td[win][0])
        out.append("\n  % parcela (calculada aquí, no por NUCAPS)")
        self._polys(out, 'parcel', [self.curve(T_par - thermo.T0, p_win)])

        p_lfc, p_el = thermo.lfc_el(p_win, T_win, T_par, p_lcl)
        color, lw, dash = STYLE['level']
        out.append(f'  color "{color}"  line_width {lw}  dash "{dash}"')
        for name, p in (("LCL", p_lcl), ("LFC", p_lfc), ("EL", p_el)):
            if not (np.isfinite(p) and self.pmin <= p <= self.pmax):
                continue
            y = float(self.y_of(p))
            out.append(f'  polyline {{ {_fmt(self.tmin)} {_fmt(y, 4)}  '
                       f'{_fmt(self.tmax)} {_fmt(y, 4)} }}')
            # El nombre va DENTRO de la caja: el rótulo de un `rule` cae sobre el
            # eje, donde ya están los hectopascales, y se pisarían.
            out.append(f'  text("{name} {p:.0f}", align="left", size={self.font_size - 1}) '
                       f'{{ {_fmt(self.tmin + 0.02 * (self.tmax - self.tmin))} '
                       f'{_fmt(y + 0.012 * self.ymax, 4)} }}')
        return p_lcl, p_lfc, p_el

    def _header(self, out, snd, title):
        """Sitio, hora y calidad. Lo que permite creerle a la figura o no."""
        cx = self.width / 2.0
        when = snd.timestamp.strftime('%Y/%m/%d %H:%MZ') if snd.timestamp else 's/hora'
        site = f"{abs(snd.lat):.2f}°{'N' if snd.lat >= 0 else 'S'}  " \
               f"{abs(snd.lon):.2f}°{'W' if snd.lon < 0 else 'E'}"
        if snd.requested_lat is not None:
            site += f"   ({snd.dist_km:.0f} km del punto pedido)"
        quality = f"Quality_Flag {snd.quality}: {snd.quality_label}"
        out.append("")
        out.append(f'  font_size {self.font_size + 3}')
        out.append(f'text("{title}", align="center") {{ {_fmt(cx)} {_fmt(self.height - 0.7)} }}')
        out.append(f'  font_size {self.font_size}')
        out.append(f'text("{snd.satellite} {snd.sensor}   {when}", align="center") '
                   f'{{ {_fmt(cx)} {_fmt(self.height - 1.25)} }}')
        out.append(f'text("{site}   —   {quality}", align="center") '
                   f'{{ {_fmt(cx)} {_fmt(self.height - 1.70)} }}')

    def _legend(self, out):
        """Qué es cada curva.

        Arriba a la izquierda es la esquina fría de la troposfera alta, que ningún
        perfil real visita: abajo a la izquierda chocaba con los rótulos del LCL y
        del LFC, que cuelgan del borde izquierdo.
        """
        tc, tw, _ = STYLE['temp']
        dc, dw, _ = STYLE['dewpoint']
        pc, pw, pd = STYLE['parcel']
        out.append("\n  % leyenda")
        out.append(f'  legend(at="top-left", margin=8, sample_width=18, '
                   f'gap=4, font_size={self.font_size - 1}) {{')
        out.append(f'    entry("Temperatura") {{ color "{tc}" line_width {tw} '
                   f'polyline {{ 0 0.5  1 0.5 }} }}')
        out.append(f'    entry("Punto de rocío") {{ color "{dc}" line_width {dw} '
                   f'polyline {{ 0 0.5  1 0.5 }} }}')
        out.append(f'    entry("Parcela") {{ color "{pc}" line_width {pw} '
                   f'dash "{pd}" polyline {{ 0 0.5  1 0.5 }} }}')
        out.append('  }')

    def _table(self, out, snd):
        """CAPE y LI, rotulados como de NUCAPS.

        Importa el rótulo: la parcela dibujada la calculamos nosotros y estos dos
        números los recuperó NUCAPS. Si algún día discrepan a la vista, la figura
        tiene que decir de quién es cada cosa.
        """
        # Los valores van como TEXTO: así el CAPE lleva entero y el LI un decimal
        # —una sola `decimals=` no puede con los dos— y sobre todo así el que no se
        # recuperó puede decir "n/d". Omitir la fila lo dejaría indistinguible de
        # un producto que nunca la trae, que es degradar en silencio.
        cape = f"{snd.cape:.0f} J/kg" if np.isfinite(snd.cape) else "n/d"
        li = f"{snd.lifted_index:+.1f} K" if np.isfinite(snd.lifted_index) else "n/d"
        rows = [f'    row("CAPE", "{cape}")', f'    row("LI", "{li}")']
        out.append("\n  % parámetros de inestabilidad, tal como los recuperó NUCAPS")
        out.append(f'  table(at="top-right", col_widths=(30,44), '
                   f'label_col=true, font_size={self.font_size - 1}, margin=6) {{')
        out.extend(rows)
        out.append('  }')

    def render(self, snd, title="Skew-T Log-P"):
        """Devuelve el fuente `.mg` completo del diagrama."""
        bx0, by0, bx1, by1 = self.box
        out = [
            "% Termodiagrama Skew-T Log-P — generado por skewt.py, no editar a mano",
            # El .mg es un artefacto versionable: tiene que explicarse solo, sin el
            # gránulo al lado. Los mismos datos que rotula el encabezado, más el FOR.
            f"% Datos: {os.path.basename(snd.source_file)},",
            f"% FOR {snd.for_index} — {snd.satellite} {snd.sensor}, "
            f"{snd.timestamp.strftime('%Y-%m-%d %H:%MZ') if snd.timestamp else 's/hora'}, "
            f"{abs(snd.lat):.2f}°{'N' if snd.lat >= 0 else 'S'} "
            f"{abs(snd.lon):.2f}°{'W' if snd.lon < 0 else 'E'}, "
            f"Quality_Flag {snd.quality}: {snd.quality_label}.",
            f"display_size {_fmt(self.width, 2)} {_fmt(self.height, 2)}",
            f"font_size {self.font_size}",
            f"world_window 0 {_fmt(self.width, 2)} 0 {_fmt(self.height, 2)}",
            "",
            # El ancho del CROMO (marco, ejes, marcas) va FUERA del `plot`: en mg
            # los ejes y la leyenda NO heredan el estado del cuerpo —solo los
            # `rule`—, así que puesto dentro no hacía nada y el marco salía al
            # ancho por omisión, 1 pt en vez de 0.4.
            "line_width 0.4",
            f"plot(x=({_fmt(self.tmin, 1)},{_fmt(self.tmax, 1)}), "
            f"y=(0,{_fmt(self.ymax, 4)}), "
            f"box=({_fmt(bx0, 2)},{_fmt(by0, 2)}, {_fmt(bx1, 2)},{_fmt(by1, 2)}), "
            f"frame=true) {{",
        ]
        self._background(out)
        self._profile(out, snd)
        self._parcel(out, snd)
        self._isobars(out)
        out.append("\n  % ejes")
        out.append('  xaxis(step=10, label="Temperatura (°C)")')
        out.append('  yaxis(label="Presión (hPa)", ticks="none", tick_labels=false)')
        self._legend(out)
        self._table(out, snd)
        out.append("}")
        self._header(out, snd, title)
        return "\n".join(out) + "\n"


def compile_mg(mg_path, out_path, verbose=False):
    """Compila el `.mg` con `mg`. Devuelve True si salió la figura."""
    exe = shutil.which(MG_BIN)
    if exe is None:
        print(f"[skewt] no encuentro '{MG_BIN}' en el PATH; queda el fuente "
              f"{mg_path}, que es lo que se compila.", file=sys.stderr)
        return False
    cmd = [exe, mg_path, out_path]
    if verbose:
        print("[skewt] " + " ".join(cmd), file=sys.stderr)
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.stdout.strip() and verbose:
        print(r.stdout.strip(), file=sys.stderr)
    if r.stderr.strip():
        print(r.stderr.strip(), file=sys.stderr)
    if r.returncode != 0:
        print(f"[skewt] mg falló con código {r.returncode}; queda {mg_path}",
              file=sys.stderr)
        return False
    return True


def _size(text):
    try:
        w, h = text.lower().split('x')
        return float(w), float(h)
    except ValueError:
        raise argparse.ArgumentTypeError("--size va como ANCHOxALTO en cm, p.ej. 16x20")


def main():
    ap = argparse.ArgumentParser(
        description="Termodiagrama Skew-T Log-P de un sondeo NUCAPS.",
        epilog="El formato de salida lo elige la extensión de -o: .svg, .pdf o .eps.")
    ap.add_argument("files", nargs='+', metavar="ARCHIVO.nc",
                    help="gránulos NUCAPS-EDR; se busca el FOR más cercano en todos")
    ap.add_argument("-o", "--output", required=True, metavar="SALIDA",
                    help="archivo de salida (.svg, .pdf o .eps)")
    ap.add_argument("--lat", type=float, help="latitud del punto objetivo")
    ap.add_argument("--lon", type=float, help="longitud del punto objetivo")
    ap.add_argument("--max-dist", type=float, default=100.0, metavar="KM",
                    help="descarta si el FOR más cercano queda más lejos (def. 100)")
    ap.add_argument("--temp-min", type=float, default=-40.0)
    ap.add_argument("--temp-max", type=float, default=40.0)
    ap.add_argument("--pres-min", type=float, default=100.0, metavar="HPA")
    ap.add_argument("--pres-max", type=float, default=1000.0, metavar="HPA")
    ap.add_argument("--skew", type=float, default=45.0, metavar="GRADOS",
                    help="inclinación de las isotermas en la página (def. 45)")
    ap.add_argument("--size", type=_size, default=(16.0, 20.0), metavar="ANCHOxALTO",
                    help="tamaño en cm (def. 16x20)")
    ap.add_argument("--title", default=None)
    ap.add_argument("--keep-mg", action="store_true",
                    help="conserva el .mg intermedio junto a la salida")
    ap.add_argument("--quality-any", action="store_true",
                    help="dibuja aunque el retrieval esté rechazado")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    ext = os.path.splitext(args.output)[1].lower()
    if ext not in FORMATS:
        ap.error(f"la extensión de la salida debe ser una de {', '.join(FORMATS)}; "
                 f"mg no produce raster")

    import nucaps_sounding
    try:
        snd = nucaps_sounding.read_sounding(
            args.files, args.lat, args.lon,
            max_dist_km=args.max_dist,
            require_accepted=not args.quality_any,
            verbose=args.verbose)
    except (ValueError, ImportError) as e:
        print(f"[skewt] {e}", file=sys.stderr)
        return 1

    if not snd.accepted:
        print(f"[skewt] AVISO: Quality_Flag={snd.quality} ({snd.quality_label}); "
              f"el perfil se dibuja pero no es un dato aceptado.", file=sys.stderr)
    if args.verbose:
        print(f"[skewt] {snd}", file=sys.stderr)

    title = args.title or f"Sondeo NUCAPS {snd.satellite}"
    diagram = SkewT(args.temp_min, args.temp_max, args.pres_min, args.pres_max,
                    args.size[0], args.size[1], args.skew)

    mg_path = os.path.splitext(args.output)[0] + ".mg"
    with open(mg_path, "w") as fh:
        fh.write(diagram.render(snd, title))
    if args.verbose:
        print(f"[skewt] fuente: {mg_path}", file=sys.stderr)

    ok = compile_mg(mg_path, args.output, args.verbose)
    if ok and not args.keep_mg:
        os.remove(mg_path)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
