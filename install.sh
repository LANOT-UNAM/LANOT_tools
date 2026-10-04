#!/bin/bash
#
# Script de instalación de LANOT_tools para servidor
# Instala el paquete en /opt/lanot-tools con virtualenv
# y crea comando mapdrawer accesible globalmente
#
# Uso: sudo ./install.sh

set -e  # Salir si hay errores

# Colores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuración
INSTALL_DIR="/opt/lanot-tools"
VENV_DIR="${INSTALL_DIR}/venv"
SRC_DIR="${INSTALL_DIR}/src"
BIN_WRAPPER_MD="/usr/local/bin/mapdrawer"
BIN_WRAPPER_G2V="/usr/local/bin/geotiff2view"
BIN_WRAPPER_SKT="/usr/local/bin/skewt"
# LANOT_DIR: la misma variable que leen las herramientas (sudo la descarta
# salvo con -E; sirve sobre todo para --verifica y para los tests).
SHARE_DIR="${LANOT_DIR:-/usr/local/share/lanot}"

# Directorio del script (donde está el código fuente)
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Recursos compartidos: recursos.sha256 (lo genera genera_manifiesto.sh) dice
# qué archivo va en qué ruta de SHARE_DIR y con qué contenido. El repo es la
# fuente: antes las CPT, logos, recortes y gpkg se copiaban a mano a cada
# servidor y se desviaban.
MANIFIESTO="${SCRIPT_DIR}/recursos.sha256"

# Archivo del repo que se instala en la ruta relativa $1, o nada si no está en
# el repo (los gpkg: se copian a mano y aquí solo se verifican).
fuente_de() {
    case "$1" in
        colortables/*|logos/*) echo "${SCRIPT_DIR}/$1" ;;
        docs/recortes_coordenadas.csv) echo "${SCRIPT_DIR}/recortes/recortes_coordenadas.csv" ;;
        *) echo "" ;;
    esac
}

# Compara SHARE_DIR con el manifiesto sin tocar nada. Devuelve 1 si algo falta
# o difiere. Lo que sobra en colortables/ solo se avisa: puede ser local.
verifica_recursos() {
    local ok=0 mal=0 suma rel dest real nota
    while read -r suma rel; do
        dest="${SHARE_DIR}/${rel}"
        nota=""
        [ -z "$(fuente_de "$rel")" ] && nota=" (no está en el repo: se copia a mano)"
        if [ ! -f "$dest" ]; then
            echo -e "  ${RED}FALTA${NC}    ${rel}${nota}"
            mal=$((mal + 1))
        else
            real=$(sha256sum "$dest" | cut -d' ' -f1)
            if [ "$real" != "$suma" ]; then
                echo -e "  ${RED}DIFIERE${NC}  ${rel}${nota}"
                mal=$((mal + 1))
            else
                ok=$((ok + 1))
            fi
        fi
    done < "${MANIFIESTO}"
    if [ -d "${SHARE_DIR}/colortables" ]; then
        for f in "${SHARE_DIR}"/colortables/*; do
            [ -e "$f" ] || continue
            rel="colortables/$(basename "$f")"
            case "$rel" in *.bak-*) continue ;; esac
            if ! cut -d' ' -f3- "${MANIFIESTO}" | grep -qxF -- "$rel"; then
                echo -e "  ${YELLOW}SOBRA${NC}    ${rel} (no está en el repo; no se toca)"
            fi
        done
    fi
    echo "  ${ok} iguales al repo, ${mal} faltan o difieren (${SHARE_DIR})"
    [ "$mal" -eq 0 ]
}

# Copia al SHARE_DIR lo que el manifiesto dice que está en el repo; lo que
# difiere se respalda como <archivo>.bak-<fecha> antes de reemplazarlo.
instala_recursos() {
    local STAMP _nuevos _reemplazados _iguales _suma _rel _src _dest
    STAMP=$(date +%Y%m%d-%H%M%S)
    _nuevos=0; _reemplazados=0; _iguales=0
    while read -r _suma _rel; do
        _src=$(fuente_de "${_rel}")
        [ -n "${_src}" ] || continue
        _dest="${SHARE_DIR}/${_rel}"
        mkdir -p "$(dirname "${_dest}")"
        if [ ! -e "${_dest}" ]; then
            cp "${_src}" "${_dest}"
            _nuevos=$((_nuevos + 1))
        elif cmp -s "${_src}" "${_dest}"; then
            _iguales=$((_iguales + 1))
        else
            cp -p "${_dest}" "${_dest}.bak-${STAMP}"
            cp "${_src}" "${_dest}"
            echo "  - ${_rel} difería: respaldo en $(basename "${_dest}").bak-${STAMP}"
            _reemplazados=$((_reemplazados + 1))
        fi
    done < "${MANIFIESTO}"
    echo "  ✓ Recursos en ${SHARE_DIR}: ${_nuevos} nuevos, ${_reemplazados} reemplazados, ${_iguales} sin cambio"
}

if [ "${1:-}" = "--verifica" ]; then
    echo -e "${GREEN}=== Recursos de LANOT_tools contra recursos.sha256 ===${NC}"
    verifica_recursos
    exit $?
elif [ "${1:-}" = "--solo-recursos" ]; then
    echo -e "${GREEN}=== Recursos de LANOT_tools (sin tocar el código ni el venv) ===${NC}"
    instala_recursos
    verifica_recursos
    exit $?
elif [ -n "${1:-}" ]; then
    echo "Uso: sudo ./install.sh            instala"
    echo "     sudo ./install.sh --solo-recursos   instala solo CPT, logos y recortes"
    echo "     ./install.sh --verifica      compara los recursos instalados con el repo"
    exit 2
fi

# Verificar que se ejecuta como root
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}Error: Este script debe ejecutarse como root (use sudo)${NC}"
    exit 1
fi

echo -e "${GREEN}=== Instalación de LANOT_tools ===${NC}"
echo ""
echo "Directorio de instalación: ${INSTALL_DIR}"
echo "Código fuente desde: ${SCRIPT_DIR}"
echo ""

# Paso 1: Verificar dependencias del sistema
echo -e "${YELLOW}[1/7] Verificando dependencias del sistema...${NC}"
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}Error: python3 no está instalado${NC}"
    exit 1
fi

PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)
echo "  ✓ Python ${PYTHON_VERSION} encontrado"

# Paso 2: Crear directorio de instalación
echo -e "${YELLOW}[2/7] Creando directorio de instalación...${NC}"
mkdir -p "${INSTALL_DIR}"
echo "  ✓ Directorio ${INSTALL_DIR} creado"

# Paso 3: Copiar código fuente
echo -e "${YELLOW}[3/7] Copiando código fuente...${NC}"
rm -rf "${SRC_DIR}"
cp -r "${SCRIPT_DIR}" "${SRC_DIR}"
# Limpiar archivos innecesarios
rm -rf "${SRC_DIR}/.git" "${SRC_DIR}/__pycache__" "${SRC_DIR}"/*.pyc "${SRC_DIR}"/build "${SRC_DIR}"/*.egg-info
echo "  ✓ Código fuente copiado a ${SRC_DIR}"

# Paso 4: Instalar recursos compartidos según recursos.sha256
echo -e "${YELLOW}[4/7] Instalando recursos compartidos...${NC}"
# - CPT, recortes y logos: se copian del repo. Si el instalado difiere, se
#   respalda como <archivo>.bak-<fecha> antes de reemplazarlo: el repo manda,
#   pero un cambio hecho a mano en el servidor no se pierde.
# - recortes_coordenadas.csv lo leen mapdrawer y hpsv
#   (hpsatviews/include/clip_loader.h), los dos con esta ruta en el código.
#   El 2026-09-23 kawak no tenía `ash` y A6 traía la misma latitud arriba y
#   abajo: por eso se instala desde aquí y no se edita en el servidor.
# - logos/: solo lo que lista el manifiesto (.svg/.pdf y los .png que leen
#   las herramientas). Los .mg son el FUENTE y se quedan en el repo.
#   ⚠ Ese directorio NO es nuestro en exclusiva: ahí vive el juego de logos
#   oficiales en PNG/JPG. Se copia encima, nunca se limpia.
# - gpkg: no están en el repo; solo se verifican abajo.
instala_recursos
if ! verifica_recursos; then
    echo -e "${YELLOW}  Aviso: los recursos instalados no coinciden con recursos.sha256 (arriba).${NC}"
    echo "  Si son gpkg, cópialos a mano; si es otro archivo, corre ./genera_manifiesto.sh."
fi

# Paso 5: Crear/actualizar virtualenv
echo -e "${YELLOW}[5/7] Configurando virtualenv...${NC}"
if [ -d "${VENV_DIR}" ]; then
    echo "  - Virtualenv existente encontrado, recreando..."
    rm -rf "${VENV_DIR}"
fi
python3 -m venv "${VENV_DIR}"
echo "  ✓ Virtualenv creado en ${VENV_DIR}"

# Paso 6: Instalar paquete
echo -e "${YELLOW}[6/7] Instalando paquete y dependencias...${NC}"
echo "  - Actualizando pip..."
"${VENV_DIR}/bin/pip" install --upgrade pip --quiet
echo "  ✓ pip actualizado"
echo "  - Instalando lanot-tools (esto puede tomar un momento)..."
if "${VENV_DIR}/bin/pip" install "${SRC_DIR}" --quiet; then
    echo "  ✓ lanot-tools instalado con dependencias"
else
    echo -e "${RED}  ✗ Error instalando lanot-tools${NC}"
    exit 1
fi

# Paso 7: Crear wrapper script
echo -e "${YELLOW}[7/7] Creando comandos globales...${NC}"
cat > "${BIN_WRAPPER_MD}" << 'EOF'
#!/bin/bash
# Wrapper para mapdrawer - ejecuta desde virtualenv
VENV_DIR="/opt/lanot-tools/venv"
exec "${VENV_DIR}/bin/mapdrawer" "$@"
EOF

chmod +x "${BIN_WRAPPER_MD}"
echo "  ✓ Comando ${BIN_WRAPPER_MD} creado"

cat > "${BIN_WRAPPER_G2V}" << 'EOF'
#!/bin/bash
# Wrapper para geotiff2view - ejecuta desde virtualenv
VENV_DIR="/opt/lanot-tools/venv"
exec "${VENV_DIR}/bin/geotiff2view" "$@"
EOF

chmod +x "${BIN_WRAPPER_G2V}"
echo "  ✓ Comando ${BIN_WRAPPER_G2V} creado"

cat > "${BIN_WRAPPER_SKT}" << 'EOF'
#!/bin/bash
# Wrapper para skewt - ejecuta desde virtualenv
VENV_DIR="/opt/lanot-tools/venv"
exec "${VENV_DIR}/bin/skewt" "$@"
EOF

chmod +x "${BIN_WRAPPER_SKT}"
echo "  ✓ Comando ${BIN_WRAPPER_SKT} creado"

# Verificación
echo ""
# `skewt` compila su figura con `mg` (MetaGráfica), que es un binario C++ fuera de
# pip: el venv no puede traerlo. Sin él skewt escribe el .mg y avisa, así que no es
# fatal para la instalación, pero sí hay que decirlo aquí y no descubrirlo en la
# primera corrida de la cadena.
if ! command -v mg > /dev/null 2>&1; then
    echo -e "${YELLOW}  Nota: 'mg' (MetaGráfica) no está en el PATH.${NC}"
    echo "  skewt escribirá el .mg pero no podrá compilarlo a SVG/PDF/EPS."
fi
echo -e "${YELLOW}Verificando instalación...${NC}"
VERIFY_OK=1
for cmd in "${BIN_WRAPPER_MD}" "${BIN_WRAPPER_G2V}" "${BIN_WRAPPER_SKT}"; do
    if ! salida=$("${cmd}" --help 2>&1); then
        echo -e "${RED}  ✗ Falló '${cmd} --help':${NC}"
        echo "${salida}" | tail -20
        VERIFY_OK=0
    fi
done

if [ "${VERIFY_OK}" -eq 1 ]; then
    if ! command -v mapdrawer > /dev/null 2>&1; then
        echo -e "${YELLOW}  Nota: $(dirname "${BIN_WRAPPER_MD}") no está en el PATH de este shell${NC}"
        echo "  (común bajo sudo por 'secure_path'); los comandos sí funcionan como usuario normal."
    fi
    echo -e "${GREEN}✓ Instalación completada exitosamente!${NC}"
    echo ""
    echo "Puede usar los comandos desde cualquier ubicación:"
    echo "  $ mapdrawer --help"
    echo "  $ geotiff2view --help"
    echo ""
    echo "Para desinstalar, ejecute:"
    echo "  $ sudo ${SCRIPT_DIR}/uninstall.sh"
    echo "  o manualmente: sudo rm -rf ${INSTALL_DIR} ${BIN_WRAPPER_MD} ${BIN_WRAPPER_G2V} ${BIN_WRAPPER_SKT}"
else
    echo -e "${RED}✗ Error en la verificación. La instalación puede estar incompleta.${NC}"
    echo "Intente ejecutar manualmente: ${BIN_WRAPPER_MD} --help y ${BIN_WRAPPER_G2V} --help"
    exit 1
fi
