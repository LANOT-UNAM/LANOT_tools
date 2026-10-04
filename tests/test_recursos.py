"""
recursos.sha256 y install.sh: el repo es la fuente de las CPT, logos y recortes
que viven en /usr/local/share/lanot.

Cubre:
- el manifiesto coincide con los archivos del repo (si no, falta correr
  ./genera_manifiesto.sh) y no deja fuera nada de lo que se instala
- install.sh --solo-recursos copia, respalda lo que difiere y no toca lo local
- install.sh --verifica reporta lo que falta o difiere y sale con 1
"""

import glob
import hashlib
import os
import shutil
import subprocess

import pytest

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
MANIFIESTO = os.path.join(REPO, 'recursos.sha256')
INSTALL = os.path.join(REPO, 'install.sh')

pytestmark = pytest.mark.skipif(
    shutil.which('bash') is None or shutil.which('sha256sum') is None,
    reason='install.sh necesita bash y sha256sum')


def _manifiesto():
    with open(MANIFIESTO) as f:
        return dict(reversed(line.rstrip('\n').split('  ', 1)) for line in f)


def _fuente(rel):
    """Mismo mapeo que fuente_de() en install.sh."""
    if rel.startswith(('colortables/', 'logos/')):
        return os.path.join(REPO, rel)
    if rel == 'docs/recortes_coordenadas.csv':
        return os.path.join(REPO, 'recortes', 'recortes_coordenadas.csv')
    return None


def _sha256(path):
    with open(path, 'rb') as f:
        return hashlib.sha256(f.read()).hexdigest()


def _install(lanot_dir, *args):
    env = dict(os.environ, LANOT_DIR=str(lanot_dir))
    return subprocess.run(['bash', INSTALL, *args], env=env,
                          capture_output=True, text=True, timeout=120)


class TestManifiesto:
    def test_sums_match_repo(self):
        mal = [rel for rel, suma in _manifiesto().items()
               if _fuente(rel) and _sha256(_fuente(rel)) != suma]
        assert not mal, f'corre ./genera_manifiesto.sh: {mal}'

    def test_nothing_installable_left_out(self):
        instalables = (glob.glob(os.path.join(REPO, 'colortables', '*.cpt'))
                       + [p for ext in ('svg', 'pdf', 'png')
                          for p in glob.glob(os.path.join(REPO, 'logos', '*.' + ext))])
        rels = {os.path.relpath(p, REPO) for p in instalables}
        rels.add('docs/recortes_coordenadas.csv')
        faltan = rels - set(_manifiesto())
        assert not faltan, f'corre ./genera_manifiesto.sh: {sorted(faltan)}'

    def test_gpkg_listed_for_verification(self):
        """Los gpkg que usa mapdrawer: no se copian, pero --verifica los revisa."""
        gpkg = {rel for rel in _manifiesto() if rel.startswith('gpkg/')}
        assert gpkg == {'gpkg/costas_mundo_10m.gpkg', 'gpkg/paises_fronteras_10m.gpkg',
                        'gpkg/mexico_estados.gpkg'}


class TestInstallSh:
    def test_solo_recursos_copies_and_backs_up(self, tmp_path):
        cpt = tmp_path / 'colortables'
        cpt.mkdir()
        (cpt / 'rainbow.cpt').write_text('# editada a mano\n')
        (cpt / 'local.cpt').write_text('# solo en este servidor\n')

        r = _install(tmp_path, '--solo-recursos')

        # Sale con 1 solo por los gpkg, que no copia
        assert r.returncode == 1
        for rel, suma in _manifiesto().items():
            dest = tmp_path / rel
            if _fuente(rel):
                assert _sha256(dest) == suma, rel
            else:
                assert not dest.exists()
                assert f'FALTA    {rel} (no está en el repo' in r.stdout.replace('\x1b[0;31m', '').replace('\x1b[0m', '')
        baks = list(cpt.glob('rainbow.cpt.bak-*'))
        assert len(baks) == 1 and baks[0].read_text() == '# editada a mano\n'
        assert (cpt / 'local.cpt').read_text() == '# solo en este servidor\n'
        assert 'local.cpt (no está en el repo; no se toca)' in r.stdout

    def test_verifica_reports_and_changes_nothing(self, tmp_path):
        _install(tmp_path, '--solo-recursos')
        (tmp_path / 'colortables' / 'sst.cpt').write_text('# otra\n')
        (tmp_path / 'logos' / 'lanot_negro_sn.png').unlink()
        antes = sorted(p.name for p in tmp_path.rglob('*'))

        r = _install(tmp_path, '--verifica')

        salida = r.stdout.replace('\x1b[0;31m', '').replace('\x1b[0m', '')
        assert r.returncode == 1
        assert 'DIFIERE  colortables/sst.cpt' in salida
        assert 'FALTA    logos/lanot_negro_sn.png' in salida
        assert (tmp_path / 'colortables' / 'sst.cpt').read_text() == '# otra\n'
        assert sorted(p.name for p in tmp_path.rglob('*')) == antes

    def test_reinstall_without_cmp_backs_up_nothing(self, tmp_path):
        """La imagen base del .sif de polar2grid no trae cmp (diffutils): una
        segunda instalación no puede tomar todo por distinto y respaldarlo."""
        share = tmp_path / 'share'
        _install(share, '--solo-recursos')
        fake = tmp_path / 'bin'
        fake.mkdir()
        (fake / 'cmp').write_text('#!/bin/sh\nexit 2\n')
        (fake / 'cmp').chmod(0o755)
        env = dict(os.environ, LANOT_DIR=str(share),
                   PATH=f"{fake}{os.pathsep}{os.environ['PATH']}")
        r = subprocess.run(['bash', INSTALL, '--solo-recursos'], env=env,
                           capture_output=True, text=True, timeout=120)
        assert '0 nuevos, 0 reemplazados' in r.stdout
        assert not list(share.rglob('*.bak-*'))

    def test_unknown_option_exits_2(self, tmp_path):
        assert _install(tmp_path, '--no-existe').returncode == 2
