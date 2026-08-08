#!/bin/bash

# Configuración
SOURCE_DIR="/dataservice/npp-jpss1/viirs/level2"
DEST_DIR="/var/www/html/polar/jpss/viirs"

# 1. Obtener archivos *.tif más recientes (última hora)
FILES=()

# Clavrx: cloud_type, cloud_phase, cld_temp_acha, cld_height_acha, cld_emiss_acha
CLAVRX_DIR="${SOURCE_DIR}/clavrx"
if [ -d "$CLAVRX_DIR" ]; then
    while IFS= read -r -d '' file; do
        FILES+=("$file")
    done < <(find "$CLAVRX_DIR" -maxdepth 1 -type f \( \
        -name "*cloud_type*.tif" -o \
        -name "*cloud_phase*.tif" -o \
        -name "*cld_temp_acha*.tif" -o \
        -name "*cld_height_acha*.tif" -o \
        -name "*cld_emiss_acha*.tif" \
        \) -mmin -60 -print0)
fi

# Acspo: sst
ACSPO_DIR="${SOURCE_DIR}/acspo"
if [ -d "$ACSPO_DIR" ]; then
    while IFS= read -r -d '' file; do
        FILES+=("$file")
    done < <(find "$ACSPO_DIR" -maxdepth 1 -type f -name "*sst*.tif" -mmin -60 -print0)
fi

# Fire: confidence_cat
FIRE_DIR="${SOURCE_DIR}/fire"
if [ -d "$FIRE_DIR" ]; then
    while IFS= read -r -d '' file; do
        FILES+=("$file")
    done < <(find "$FIRE_DIR" -maxdepth 1 -type f -name "*confidence_cat*.tif" -mmin -60 -print0)
fi

# Asci: AOD550 (aerosoles). Solo *.tif; los *.nc de la misma carpeta se ignoran.
ASCI_DIR="${SOURCE_DIR}/asci"
if [ -d "$ASCI_DIR" ]; then
    while IFS= read -r -d '' file; do
        FILES+=("$file")
    done < <(find "$ASCI_DIR" -maxdepth 1 -type f -name "*AOD550*.tif" -mmin -60 -print0)
fi

# 2. y 3. Procesar archivos
echo "Iniciando procesamiento de ${#FILES[@]} archivos..."

for filepath in "${FILES[@]}"; do
    filename=$(basename "$filepath")
    
    # Determinar paleta, directorio de salida y herramienta
    paleta=""
    outdir=""
    herramienta="geotiff2view"

    if [[ "$filename" == *"cloud_type"* ]]; then
        paleta="cloud_type.cpt"
        outdir="clouds"
    elif [[ "$filename" == *"cloud_phase"* ]]; then
        paleta="phase.cpt"
        outdir="clouds"
    elif [[ "$filename" == *"cld_temp_acha"* ]]; then
        paleta="cld_temp_acha.cpt"
        outdir="clouds"
    elif [[ "$filename" == *"cld_height_acha"* ]]; then
        paleta="cld_height_acha.cpt"
        outdir="clouds"
    elif [[ "$filename" == *"cld_emiss_acha"* ]]; then
        outdir="clouds"
        paleta="cld_emiss.cpt"
    elif [[ "$filename" == *"sst"* ]]; then
        paleta="sst.cpt"
        outdir="sst"
    elif [[ "$filename" == *"confidence_cat"* ]]; then
        paleta="viirs_confidence_cat.cpt"
        outdir="fires"
    elif [[ "$filename" == *"AOD550"* ]]; then
        # El TIFF ya viene coloreado con su paleta interna: no se recolorea,
        # solo se decora. El CPT es el respaldo de la colorbar por si el
        # archivo llegara sin el tag 'colormap' embebido.
        paleta="aod550.cpt"
        outdir="aerosols"
        herramienta="mapdrawer"
    else
        continue
    fi

    # Crear directorio destino
    FULL_DEST_DIR="${DEST_DIR}/${outdir}"
    mkdir -p "$FULL_DEST_DIR"

    # Definir argumentos
    args=(
        --layer "COUNTRIES:yellow:0.0005"
        --layer "MEXSTATES:yellow:0.0005"
        --logo-pos 0
        --logo-size 0.2
        --font-size 0.025
        --timestamp-pos 1
        --font-color white
        -s 0.5
        -j
    )

    if [ "$herramienta" = "mapdrawer" ]; then
        # mapdrawer no recolorea: dibuja la colorbar a partir del colormap
        # embebido en el TIFF (--cpt solo actúa como respaldo).
        args+=("--colorbar" "--cpt" "$paleta" "--lat-south" "11")
    else
        # -b es exclusivo de geotiff2view
        args+=("-b")
        if [ -n "$paleta" ]; then
            args+=("-p" "$paleta" "--lat-south" "11")
        fi
    fi

    # Nombre de salida (tif -> jpg)
    outfilename="${filename%.*}.jpg"
    
    # Verificar si el archivo de salida ya existe para omitirlo
    if [ -f "$FULL_DEST_DIR/$outfilename" ]; then
        # echo "Omitiendo: $FULL_DEST_DIR/$outfilename (ya existe)"
        continue
    fi

    # Ejecutar la herramienta correspondiente
    echo "Generando: $FULL_DEST_DIR/$outfilename"
    "$herramienta" "$filepath" "${args[@]}" -o "$FULL_DEST_DIR/$outfilename"
done

echo "Proceso completado."
