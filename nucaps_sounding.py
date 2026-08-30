#! /usr/bin/env python3
# -*- coding: utf-8 -*-
"""
nucaps_sounding - Lectura de perfiles verticales de los sondeos NUCAPS de CSPP HEAP.

Un gránulo NUCAPS-EDR es un TRAMO DE SWATH de 120 campos de regard (FOR), no una
rejilla: pedir "el perfil en (lat, lon)" es en realidad pedir el FOR más cercano,
que puede quedar lejos o caer en el gránulo de al lado. Por eso el lector acepta
varios archivos y siempre devuelve la distancia y las coordenadas REALES del FOR.

Autor: Alejandro Aguilar Sierra
LANOT - Laboratorio Nacional de Observación de la Tierra
"""

import os
import re
import sys
from datetime import datetime, timezone

import numpy as np

import thermo
from metadata import Metadata

try:
    import netCDF4
    HAS_NETCDF4 = True
except ImportError:
    HAS_NETCDF4 = False

# Columnas del arreglo `Stability` (16 parámetros por FOR). No hay variables CAPE
# ni Lifted_Index propias: son columnas de ese arreglo, y los índices salen del
# código de CSPP Sounder QL (sounder_packages/nucaps.py, stability_cape y
# stability_lifted_index). Documentado en docs/plan_cape_lifted_index.md.
STABILITY_CAPE = 0
STABILITY_LIFTED_INDEX = 9

# Trampa heredada de NUCAPS, avisada por el propio código de CIMSS: los no
# recuperados quedan como -999.0, que NO es el _FillValue declarado (-9999.0), así
# que netCDF4 no los enmascara. Se ven en `Stability` de estos mismos archivos.
NUCAPS_MISSING = (-999.0, -9999.0)

EARTH_RADIUS_KM = 6371.0


class Sounding:
    """Un perfil vertical y lo que hace falta para rotularlo con honradez."""

    def __init__(self, **kw):
        self.__dict__.update(kw)

    def __repr__(self):
        return (f"<Sounding {self.lat:.3f},{self.lon:.3f} "
                f"{len(self.p)} niveles QF={self.quality} "
                f"({self.quality_label}) a {self.dist_km:.1f} km>")

    @property
    def accepted(self):
        """Solo `Quality_Flag == 0` es 'accepted'; todo lo demás es un rechazo."""
        return self.quality == 0


def _to_nan(arr):
    """Arreglo enmascarado o con centinelas → float con NaN donde no hay dato."""
    out = np.ma.filled(np.ma.asarray(arr).astype(float), np.nan)
    for sentinel in NUCAPS_MISSING:
        out = np.where(out == sentinel, np.nan, out)
    return out


def haversine_km(lat1, lon1, lat2, lon2):
    """Distancia de círculo máximo en km. Vectorizada en el segundo par."""
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dp = p2 - p1
    dl = np.radians(np.asarray(lon2) - lon1)
    a = np.sin(dp / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


def _quality_label(var, value):
    """Etiqueta del Quality_Flag leída del PROPIO archivo, no de una tabla nuestra.

    Los `flag_values`/`flag_meanings` vienen en los atributos de la variable, así
    que si NUCAPS cambia el catálogo la vista no miente sin que nadie se entere.
    """
    try:
        values = list(np.asarray(var.flag_values).ravel())
        meanings = str(var.flag_meanings).split()
        return meanings[values.index(value)]
    except (AttributeError, ValueError, IndexError):
        return 'accepted' if value == 0 else f'flag {value}'


def _scan(paths):
    """Recorre los archivos y devuelve (rutas, lat, lon, índice global→(archivo, FOR))."""
    lats, lons, owner = [], [], []
    for path in paths:
        with netCDF4.Dataset(path) as ds:
            la = _to_nan(ds.variables['Latitude'][:])
            lo = _to_nan(ds.variables['Longitude'][:])
        lats.append(la)
        lons.append(lo)
        owner.extend((path, i) for i in range(la.size))
    if not owner:
        raise ValueError("no se pudo leer ningún FOR de los archivos dados")
    return np.concatenate(lats), np.concatenate(lons), owner


def read_sounding(paths, lat=None, lon=None, max_dist_km=100.0,
                  require_accepted=True, verbose=False):
    """Extrae el perfil del FOR más cercano a (lat, lon) entre todos los archivos.

    Sin coordenadas, toma el FOR más cercano al centroide del segmento, que es lo
    que la especificación llama "el punto central del segmento".

    Lanza `ValueError` si el FOR más cercano queda a más de `max_dist_km`, o si su
    retrieval fue rechazado y `require_accepted` sigue en pie: un perfil rechazado
    se dibuja igual de bonito y dice algo que no es.
    """
    if not HAS_NETCDF4:
        raise ImportError("leer sondeos NUCAPS requiere netCDF4")
    if isinstance(paths, (str, os.PathLike)):
        paths = [paths]
    paths = sorted(str(p) for p in paths)

    all_lat, all_lon, owner = _scan(paths)

    requested = (lat, lon)
    if lat is None or lon is None:
        lat = float(np.nanmean(all_lat))
        lon = float(np.nanmean(all_lon))
        if verbose:
            print(f"[nucaps] sin --lat/--lon: centro del segmento "
                  f"({lat:.3f}, {lon:.3f})", file=sys.stderr)

    dist = haversine_km(lat, lon, all_lat, all_lon)
    k = int(np.nanargmin(dist))
    path, i = owner[k]
    dist_km = float(dist[k])

    if dist_km > max_dist_km:
        raise ValueError(
            f"el FOR más cercano a ({lat:.3f}, {lon:.3f}) queda a "
            f"{dist_km:.1f} km, por encima del límite de {max_dist_km:.0f} km. "
            f"NUCAPS es un swath: el punto puede caer fuera de la pasada.")

    with netCDF4.Dataset(path) as ds:
        qvar = ds.variables['Quality_Flag']
        quality = int(np.ma.filled(qvar[i], -9999))
        quality_label = _quality_label(qvar, quality)
        if quality != 0 and require_accepted:
            raise ValueError(
                f"el FOR {i} de {os.path.basename(path)} tiene Quality_Flag="
                f"{quality} ({quality_label}); su perfil no es un dato aceptado. "
                f"Usa --quality-any para dibujarlo de todos modos.")

        p = _to_nan(ds.variables['Pressure'][i])
        T = _to_nan(ds.variables['Temperature'][i])
        w = _to_nan(ds.variables['H2O_MR'][i])          # kg/kg, así lo declara
        p_surf = float(_to_nan(ds.variables['Surface_Pressure'][i]))
        for_lat = float(_to_nan(ds.variables['Latitude'][i]))
        for_lon = float(_to_nan(ds.variables['Longitude'][i]))
        stability = _to_nan(ds.variables['Stability'][i])
        t_msec = float(_to_nan(ds.variables['Time'][i]))

    # Niveles utilizables. En estos archivos los que están bajo la superficie ya
    # vienen como _FillValue, pero el filtro se queda: el mismo lector tiene que
    # servir para un NUCAPS que no los haya recortado.
    good = np.isfinite(p) & np.isfinite(T)
    if np.isfinite(p_surf):
        good &= p <= p_surf + 1e-6
    p, T, w = p[good], T[good], w[good]

    order = np.argsort(-p)                      # de la superficie hacia arriba
    p, T, w = p[order], T[order], w[order]

    Td = thermo.dewpoint_from_mixing_ratio(p, w)

    cape = stability[STABILITY_CAPE] if stability.size > STABILITY_CAPE else np.nan
    li = (stability[STABILITY_LIFTED_INDEX]
          if stability.size > STABILITY_LIFTED_INDEX else np.nan)

    meta = Metadata()
    meta.enrich_from_filename(os.path.basename(path))
    timestamp = (datetime.fromtimestamp(t_msec / 1000.0, tz=timezone.utc)
                 if np.isfinite(t_msec) else None)

    return Sounding(
        p=p, T=T, Td=Td, w=w,
        lat=for_lat, lon=for_lon,
        requested_lat=requested[0], requested_lon=requested[1],
        dist_km=dist_km,
        surface_pressure=p_surf,
        cape=float(cape), lifted_index=float(li),
        quality=quality, quality_label=quality_label,
        timestamp=timestamp,
        satellite=meta.get('satellite', 'NOAA'),
        sensor='CrIS+ATMS',       # todo NUCAPS-EDR lo es; no va en el nombre
        source_file=path, for_index=i,
        n_files=len(paths),
    )
