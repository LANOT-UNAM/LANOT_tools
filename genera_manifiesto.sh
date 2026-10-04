#!/bin/bash
#
# Regenera recursos.sha256: el sha256 de cada recurso que vive en
# /usr/local/share/lanot, con su ruta relativa a ese directorio.
#
#   ./genera_manifiesto.sh          # después de cambiar una CPT, un logo,
#                                   # los recortes o un gpkg
#
# install.sh copia lo que está en el repo y lo verifica contra este archivo;
# `install.sh --verifica` solo compara lo instalado con él. Un test falla si
# el manifiesto no coincide con los archivos del repo.
#
# Los gpkg NO están en el repo (ver CLAUDE.md): sus sumas se toman de lo
# instalado en esta máquina (${LANOT_DIR:-/usr/local/share/lanot}/gpkg), así
# que hay que correr esto donde estén los gpkg buenos. install.sh no los
# copia; --verifica sí avisa si un servidor tiene otros.

set -e
export LC_ALL=C

REPO="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
SHARE="${LANOT_DIR:-/usr/local/share/lanot}"
GPKG=(costas_mundo_10m.gpkg paises_fronteras_10m.gpkg mexico_estados.gpkg)

suma() {  # suma ARCHIVO RUTA_INSTALADA
    printf '%s  %s\n' "$(sha256sum "$1" | cut -d' ' -f1)" "$2"
}

{
    for f in "${REPO}"/colortables/*.cpt; do
        suma "$f" "colortables/$(basename "$f")"
    done
    suma "${REPO}/recortes/recortes_coordenadas.csv" docs/recortes_coordenadas.csv
    for f in "${REPO}"/logos/*.svg "${REPO}"/logos/*.pdf "${REPO}"/logos/*.png; do
        [ -e "$f" ] && suma "$f" "logos/$(basename "$f")"
    done
    for g in "${GPKG[@]}"; do
        if [ ! -f "${SHARE}/gpkg/${g}" ]; then
            echo "Error: falta ${SHARE}/gpkg/${g}; corre esto donde estén los gpkg" >&2
            exit 1
        fi
        suma "${SHARE}/gpkg/${g}" "gpkg/${g}"
    done
} | sort -k2 > "${REPO}/recursos.sha256"

echo "recursos.sha256: $(wc -l < "${REPO}/recursos.sha256") archivos"
