"""El contenedor de polar2grid corre Python 3.9; esta laptop, 3.13.

Desde 3.12 (PEP 701) un f-string admite saltos de línea dentro de `{…}` y las
mismas comillas anidadas. Aquí compila y pasan todas las pruebas; en 3.9 es un
SyntaxError al importar. Así se rompió la compilación del .sif con eaa132d
(`skewt.py`, rótulo del LCL partido en dos líneas). `py_compile` con el
intérprete local no lo ve, por eso se revisan los tokens.
"""

import subprocess
import sys
import tokenize
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent

pytestmark = pytest.mark.skipif(not hasattr(tokenize, 'FSTRING_START'),
                                reason="el tokenizador de < 3.12 ya rechaza esto")


def _fuentes():
    r = subprocess.run(['git', 'ls-files', '*.py'], cwd=RAIZ,
                       capture_output=True, text=True)
    if r.returncode == 0 and r.stdout.strip():
        return [RAIZ / p for p in r.stdout.split()]
    return sorted(RAIZ.glob('*.py')) + sorted((RAIZ / 'tests').glob('*.py'))


def _problemas(path):
    with open(path, 'rb') as fh:
        toks = list(tokenize.tokenize(fh.readline))
    out, pila = [], []          # pila: (comillas, renglón) de cada f-string abierto
    for t in toks:
        if t.type == tokenize.FSTRING_START:
            q = t.string.lstrip('rRfFbB')
            if pila and q[0] == pila[-1][0][0]:
                out.append(f"{t.start[0]}: f-string anidado con las mismas comillas")
            pila.append((q, t.start[0]))
        elif t.type == tokenize.FSTRING_END:
            pila.pop()
        elif pila:
            q, renglon = pila[-1]
            if len(q) == 1 and t.start[0] != renglon:
                out.append(f"{t.start[0]}: salto de línea dentro de un f-string")
                pila[-1] = (q, t.start[0])
            if t.type == tokenize.STRING and t.string.lstrip('rRbBuU')[:1] == q[0]:
                out.append(f"{t.start[0]}: comillas {q} anidadas en un f-string")
    return out


@pytest.mark.parametrize("path", _fuentes(), ids=lambda p: p.name)
def test_fstrings_validos_en_python_39(path):
    assert _problemas(path) == []


def test_el_detector_ve_el_caso_de_eaa132d(tmp_path):
    f = tmp_path / 'malo.py'
    f.write_text("x = (f'{{ {max(1,\n"
                 "                2)} }}')\n")
    assert _problemas(f)
