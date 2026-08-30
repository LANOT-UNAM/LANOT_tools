#! /usr/bin/env python3
# -*- coding: utf-8 -*-
"""
thermo - Termodinámica de la atmósfera húmeda para los termodiagramas Skew-T.

Numpy puro, sin entrada/salida y sin dependencias opcionales: es la parte que se
equivoca en silencio —un perfil mal derivado se dibuja igual de bonito— así que
vive aislada y se prueba sola, sin necesidad de netCDF4 ni de un gránulo.

Convenciones, sin excepción en todo el módulo:
  - presión en hPa (= mb, que es como la declara NUCAPS)
  - temperaturas en KELVIN en las firmas; las de Celsius lo dicen en el nombre
  - razón de mezcla en kg/kg (que es como la declara `H2O_MR`), no en g/kg

Autor: Alejandro Aguilar Sierra
LANOT - Laboratorio Nacional de Observación de la Tierra
"""

import numpy as np

# --- Constantes ------------------------------------------------------------
RD = 287.05          # J/(kg K), gas seco
RV = 461.51          # J/(kg K), vapor de agua
EPSILON = RD / RV    # 0.6220, razón de masas moleculares
CP = 1004.6          # J/(kg K), calor específico a presión constante del aire seco
LV = 2.501e6         # J/kg, calor latente de vaporización a 0 °C
KAPPA = RD / CP      # 0.2857, exponente de Poisson
P_REF = 1000.0       # hPa, presión de referencia de la temperatura potencial
T0 = 273.15          # K

# Coeficientes de Bolton (1980), ec. 10. La formulación es SOBRE AGUA también por
# debajo de 0 °C, que es la convención de los Skew-T y la de las tablas con las que
# se comparan los sondeos: usar hielo movería el punto de rocío varios grados en la
# troposfera alta y las líneas de razón de mezcla dejarían de cuadrar con las de
# cualquier otro diagrama.
_B_A = 6.112         # hPa
_B_B = 17.67
_B_C = 243.5         # °C


def saturation_vapor_pressure(T_K):
    """Presión de vapor de saturación (hPa) sobre agua. Bolton (1980), ec. 10."""
    Tc = np.asarray(T_K, dtype=float) - T0
    # Acotado al rango donde la fórmula significa algo. Fuera de él no hay dato
    # atmosférico, y sin la cota el denominador cambia de signo cerca de -243.5 °C
    # y el exponencial se desborda: un desbordamiento aquí llega a la figura como
    # una curva plausible, no como un error.
    Tc = np.clip(Tc, -100.0, 100.0)
    return _B_A * np.exp(_B_B * Tc / (Tc + _B_C))


def dewpoint_from_vapor_pressure(e_hPa):
    """Punto de rocío (K) a partir de la presión de vapor. Inversa de Bolton."""
    e = np.asarray(e_hPa, dtype=float)
    # Por debajo de esto el logaritmo se va a -inf y el resultado no significa nada:
    # es aire seco hasta donde el sondeo puede decir, no un punto de rocío bajísimo.
    e = np.where(e > 1e-10, e, np.nan)
    lg = np.log(e / _B_A)
    return _B_C * lg / (_B_B - lg) + T0


def vapor_pressure_from_mixing_ratio(p_hPa, w_kgkg):
    """Presión de vapor (hPa) a partir de la razón de mezcla: e = w·p/(ε + w)."""
    p = np.asarray(p_hPa, dtype=float)
    w = np.asarray(w_kgkg, dtype=float)
    return w * p / (EPSILON + w)


def dewpoint_from_mixing_ratio(p_hPa, w_kgkg):
    """Punto de rocío (K) desde presión y razón de mezcla.

    Es la pieza sin la cual NUCAPS no puede dibujar un Skew-T: el producto trae
    `H2O_MR` en kg/kg y NO trae punto de rocío.
    """
    return dewpoint_from_vapor_pressure(
        vapor_pressure_from_mixing_ratio(p_hPa, w_kgkg))


def saturation_mixing_ratio(p_hPa, T_K):
    """Razón de mezcla de saturación (kg/kg)."""
    p = np.asarray(p_hPa, dtype=float)
    es = saturation_vapor_pressure(T_K)
    # es < p siempre en la atmósfera real; el clip evita el infinito si un nivel
    # espurio pide saturación por encima de su propia presión.
    return EPSILON * es / np.maximum(p - es, 1e-6)


def mixing_ratio_from_dewpoint(p_hPa, Td_K):
    """Razón de mezcla (kg/kg) desde el punto de rocío. Inversa de la anterior."""
    return saturation_mixing_ratio(p_hPa, Td_K)


def temperature_at_mixing_ratio(p_hPa, w_kgkg):
    """Temperatura (K) a la que `w` es la razón de mezcla de SATURACIÓN a `p`.

    Es la que traza las líneas de razón de mezcla de saturación del fondo del
    diagrama: para cada línea de w constante, su temperatura nivel a nivel.
    """
    return dewpoint_from_vapor_pressure(
        vapor_pressure_from_mixing_ratio(p_hPa, w_kgkg))


def potential_temperature(p_hPa, T_K):
    """Temperatura potencial (K): θ = T·(1000/p)^κ."""
    p = np.asarray(p_hPa, dtype=float)
    return np.asarray(T_K, dtype=float) * (P_REF / p) ** KAPPA


def dry_adiabat(theta_K, p_hPa):
    """Temperatura (K) sobre la adiabática seca de θ dada: T = θ·(p/1000)^κ."""
    p = np.asarray(p_hPa, dtype=float)
    return float(theta_K) * (p / P_REF) ** KAPPA


def lcl(p_hPa, T_K, Td_K):
    """Nivel de condensación por ascenso (LCL) → (presión hPa, temperatura K).

    Bolton (1980), ec. 15 para la temperatura; la presión sale de Poisson, porque
    de la superficie al LCL el ascenso es seco y θ se conserva.
    """
    T = float(T_K)
    Td = float(Td_K)
    if not np.isfinite(Td):
        return float('nan'), float('nan')
    Td = min(Td, T)                      # sobresaturación en el dato: se satura y ya
    t_lcl = 1.0 / (1.0 / (Td - 56.0) + np.log(T / Td) / 800.0) + 56.0
    p_lcl = float(p_hPa) * (t_lcl / T) ** (1.0 / KAPPA)
    return p_lcl, t_lcl


def _moist_lapse_dTdp(p_hPa, T_K):
    """Gradiente pseudoadiabático dT/dp (K/hPa). Saturado, sin agua líquida a bordo."""
    ws = saturation_mixing_ratio(p_hPa, T_K)
    num = 1.0 + LV * ws / (RD * T_K)
    den = 1.0 + LV * LV * ws * EPSILON / (CP * RD * T_K * T_K)
    return (RD * T_K / (CP * p_hPa)) * num / den


def moist_lapse(p_grid_hPa, T_start_K, p_start_hPa=None, substeps=4):
    """Integra la adiabática saturada sobre `p_grid_hPa` desde (p_start, T_start).

    Devuelve un arreglo de temperaturas (K) del mismo tamaño que `p_grid_hPa`.
    Sin forma cerrada: se integra. Los `substeps` por tramo son cuatro porque con
    la rejilla logarítmica que usa el diagrama el error ya queda por debajo de la
    centésima de grado, y el fondo se redibuja en cada figura.
    """
    p_grid = np.atleast_1d(np.asarray(p_grid_hPa, dtype=float))
    T = float(T_start_K)
    out = np.empty(p_grid.size, dtype=float)
    p = float(p_grid[0] if p_start_hPa is None else p_start_hPa)
    for i, p_target in enumerate(p_grid):
        dp = (p_target - p) / substeps
        for _ in range(substeps):
            # Punto medio: el mismo costo por paso que Euler dos veces, mitad de
            # sesgo acumulado sobre los ~60 tramos de una adiabática completa.
            k1 = _moist_lapse_dTdp(p, T)
            k2 = _moist_lapse_dTdp(p + dp / 2.0, T + k1 * dp / 2.0)
            T += k2 * dp
            p += dp
        out[i] = T
    return out


def parcel_profile(p_hPa, T_start_K, Td_start_K):
    """Trayectoria de la parcela levantada desde (p[0], T_start, Td_start).

    Seca hasta el LCL, saturada por encima. Devuelve (T_parcela_K, p_lcl, T_lcl),
    con `T_parcela_K` alineada con `p_hPa`.
    """
    p = np.asarray(p_hPa, dtype=float)
    p_lcl, t_lcl = lcl(p[0], T_start_K, Td_start_K)
    if not np.isfinite(p_lcl):
        return np.full(p.size, np.nan), p_lcl, t_lcl

    theta = potential_temperature(p[0], T_start_K)
    T = np.where(p >= p_lcl, dry_adiabat(theta, p), np.nan)

    above = p < p_lcl
    if np.any(above):
        # Se integra desde el LCL, no desde el primer nivel de la rejilla: el LCL
        # cae entre dos niveles y arrancar en el más cercano metería un escalón
        # justo donde la curva tiene su codo.
        T[above] = moist_lapse(p[above], t_lcl, p_start_hPa=p_lcl)
    return T, p_lcl, t_lcl


def _crossings(p_hPa, diff):
    """Presiones donde `diff` cambia de signo, interpoladas linealmente en log(p)."""
    p = np.asarray(p_hPa, dtype=float)
    d = np.asarray(diff, dtype=float)
    ok = np.isfinite(d)
    p, d = p[ok], d[ok]
    out = []
    for i in range(d.size - 1):
        if d[i] == 0.0:
            out.append(p[i])
        elif d[i] * d[i + 1] < 0.0:
            f = d[i] / (d[i] - d[i + 1])
            out.append(float(np.exp(np.log(p[i]) + f * (np.log(p[i + 1]) - np.log(p[i])))))
    return out


def lfc_el(p_hPa, T_env_K, T_parcel_K, p_lcl_hPa=None):
    """Nivel de convección libre y nivel de equilibrio → (p_lfc, p_el) en hPa.

    El LFC es el primer cruce en el que la parcela pasa a ser MÁS CÁLIDA que el
    entorno, buscado desde el LCL hacia arriba (por debajo del LCL un cruce no es
    un LFC: la parcela todavía no está saturada). El EL es el cruce siguiente, ya
    con la parcela enfriándose por debajo del entorno.

    Devuelve `nan` en los que no existan, que es el caso corriente de un sondeo
    estable — y hay que dibujarlo como ausencia, no como cero.
    """
    p = np.asarray(p_hPa, dtype=float)
    diff = np.asarray(T_parcel_K, dtype=float) - np.asarray(T_env_K, dtype=float)

    if p_lcl_hPa is not None and np.isfinite(p_lcl_hPa):
        mask = p <= p_lcl_hPa
        p, diff = p[mask], diff[mask]

    xs = _crossings(p, diff)
    if not xs:
        return float('nan'), float('nan')

    order = np.argsort([-x for x in xs])          # de abajo (mayor p) hacia arriba
    xs = [xs[i] for i in order]

    p_lfc = float('nan')
    for x in xs:
        # ¿Queda la parcela más cálida justo ENCIMA de este cruce?
        above = p < x
        if np.any(above) and np.isfinite(diff[above][0]) and diff[above][0] > 0:
            p_lfc = x
            break
    if not np.isfinite(p_lfc):
        return float('nan'), float('nan')

    p_el = float('nan')
    for x in xs:
        if x < p_lfc:
            p_el = x
            break
    return p_lfc, p_el
