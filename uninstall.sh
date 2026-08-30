#!/bin/bash
#
# Script de desinstalación de LANOT_tools
#
# Uso: sudo ./uninstall.sh

set -e

# Colores
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Verificar root
if [ "$EUID" -ne 0 ]; then 
    echo -e "${RED}Error: Este script debe ejecutarse como root (use sudo)${NC}"
    exit 1
fi

INSTALL_DIR="/opt/lanot-tools"
BIN_WRAPPER_MD="/usr/local/bin/mapdrawer"
BIN_WRAPPER_G2V="/usr/local/bin/geotiff2view"
BIN_WRAPPER_SKT="/usr/local/bin/skewt"

echo -e "${YELLOW}=== Desinstalación de LANOT_tools ===${NC}"
echo ""

# Confirmar
read -p "¿Está seguro de desinstalar LANOT_tools? (s/N): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Ss]$ ]]; then
    echo "Desinstalación cancelada."
    exit 0
fi

# Eliminar comandos
if [ -f "${BIN_WRAPPER_MD}" ]; then
    rm -f "${BIN_WRAPPER_MD}"
    echo -e "${GREEN}✓ Eliminado: ${BIN_WRAPPER_MD}${NC}"
fi

if [ -f "${BIN_WRAPPER_G2V}" ]; then
    rm -f "${BIN_WRAPPER_G2V}"
    echo -e "${GREEN}✓ Eliminado: ${BIN_WRAPPER_G2V}${NC}"
fi

if [ -f "${BIN_WRAPPER_SKT}" ]; then
    rm -f "${BIN_WRAPPER_SKT}"
    echo -e "${GREEN}✓ Eliminado: ${BIN_WRAPPER_SKT}${NC}"
fi

# Eliminar los logos que instalamos — y SOLO ésos.
# ⚠ Nada de `rm -rf` sobre el directorio: ahí viven también los logos oficiales
# en PNG/JPG, que no son nuestros. Se quitan por nombre, tomando la lista del
# propio repo, y el directorio se borra solo si queda vacío.
LOGO_DIR="/usr/local/share/lanot/logos"
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
if [ -d "${LOGO_DIR}" ]; then
    for f in "${SCRIPT_DIR}/logos/"*.svg "${SCRIPT_DIR}/logos/"*.pdf; do
        [ -e "$f" ] || continue
        if [ -f "${LOGO_DIR}/$(basename "$f")" ]; then
            rm -f "${LOGO_DIR}/$(basename "$f")"
            echo -e "${GREEN}✓ Eliminado: ${LOGO_DIR}/$(basename "$f")${NC}"
        fi
    done
    rmdir "${LOGO_DIR}" 2>/dev/null && echo -e "${GREEN}✓ Eliminado: ${LOGO_DIR} (quedó vacío)${NC}"
fi

# Eliminar directorio de instalación
if [ -d "${INSTALL_DIR}" ]; then
    rm -rf "${INSTALL_DIR}"
    echo -e "${GREEN}✓ Eliminado: ${INSTALL_DIR}${NC}"
fi

echo ""
echo -e "${GREEN}Desinstalación completada.${NC}"
