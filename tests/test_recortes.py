"""Validacion de recortes/recortes_coordenadas.csv.

El CSV lo leen mapdrawer (csv.reader, compara la clave tal cual) y hpsv
(clip_loader.c: strtok por comas, lineas de hasta 256 bytes, salta la cabecera
si contiene "clave"). El 2026-09-23 A6 traia ul_y == lr_y, una caja de altura
cero que ninguno de los dos rechazaba.
"""
import csv
import os

import pytest

CSV = os.path.join(os.path.dirname(__file__), "..", "recortes",
                   "recortes_coordenadas.csv")


def _filas():
    with open(CSV, newline="", encoding="utf-8") as fh:
        return list(csv.reader(fh))


def test_cabecera():
    assert _filas()[0] == ["clave", "region", "ul_x", "ul_y", "lr_x", "lr_y"]


def test_lineas_caben_en_hpsv():
    with open(CSV, "rb") as fh:
        for n, linea in enumerate(fh, 1):
            assert len(linea) < 256, f"linea {n} excede el buffer de clip_loader.c"


def test_claves_unicas_y_en_minusculas():
    claves = [f[0] for f in _filas()[1:]]
    assert len(claves) == len(set(claves))
    for c in claves:
        assert c == c.strip().lower() and c, f"clave '{c}'"


@pytest.mark.parametrize("fila", _filas()[1:], ids=lambda f: f[0])
def test_caja_valida(fila):
    assert len(fila) == 6, f"{fila[0]}: {len(fila)} campos"
    ulx, uly, lrx, lry = (float(v) for v in fila[2:])
    assert -180 <= ulx < lrx <= 180, f"{fila[0]}: longitudes {ulx}, {lrx}"
    assert 90 >= uly > lry >= -90, f"{fila[0]}: latitudes {uly}, {lry}"
