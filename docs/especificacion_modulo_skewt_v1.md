# Especificación Técnica: Módulo de Termodiagramas Skew-T

> **Implementado el 2026-08-30.** Las decisiones que este documento dejaba
> abiertas —sobre todo la §1— y los cinco puntos en los que el dato real lo
> desmintió están en [`plan_skewt.md`](plan_skewt.md). El motor es MetaGráfica,
> y la v1 sale solo en vectorial: el `-d DPI` de la §4 se cayó con el raster.

**Repositorio:** `LANOT_tools`  
**Objetivo:** Implementar un módulo para la generación de perfiles atmosféricos verticales (termodiagramas Skew-T Log-P) a partir de salidas de modelos (ej. WRF) y sondeos satelitales. Empezaremos con datos generados por CSPP polar. Debe integrarse a la colección de herramientas de este repo.

## 1. Arquitectura y Tecnologías
Por principio, no usamos matplotlib porque es como usar un misil para matar mosquitos. Hasta ahora mapdrawer trabaja con imágenes raster pero este tipo de diagramas puede requerir dibujar en una plataforma vectorial con salida SVG o PDF. Evaluar y decidir si usamos un módulo nuevo y adaptar algoritmos geométricos, curvas de Bézier y operaciones booleanas de trazados, renderizando el sistema de coordenadas Skew-T de forma nativa. Buscar biblioteca en python equivalente a PIL.

## 2. Entradas y Análisis de Datos (Data Parsing)
*   **Ingesta de Archivos:** El módulo debe aceptar la ruta a un único archivo de datos atmosféricos como entrada. Como primer paso debe leer formatos de sondeo satelital como HEAP NUCAPS para integrarse adecuadamente al flujo de trabajo del procesamiento satelital.
*   **Coordenadas Objetivo:** La interfaz de línea de comandos (CLI) debe aceptar coordenadas específicas (latitud central `--lat_0` y longitud `--lon_0`) para localizar y extraer el perfil atmosférico vertical de ese punto exacto.
*   **Comportamiento por Defecto:** Si no se proporcionan coordenadas explícitas, el módulo calculará y utilizará automáticamente el punto central del segmento de datos.
*   **Extracción de Variables:** El analizador debe ser capaz de extraer matrices verticales unidimensionales de presión (mbar/hPa), temperatura y temperatura del punto de rocío para la huella especificada.

## 3. Renderizado y Representación Visual
*   **Sistema de Coordenadas:** El motor de renderizado debe mapear los datos a una cuadrícula estándar Skew-T Log-P. Esto implica representar la presión en un eje Y logarítmico (típicamente de 1000 a 100 mbar) y la temperatura en un eje X sesgado.
*   **Representación de Datos:** 
    *   Línea de temperatura ambiente: Trazada típicamente en color rojo.
    *   Línea de temperatura del punto de rocío: Trazada típicamente en color verde.
*   **Isolíneas de Fondo:** La cuadrícula base debe renderizar de manera clara las líneas termodinámicas esenciales: isotermas, isobaras, adiabáticas secas, adiabáticas húmedas y líneas de relación de mezcla de saturación.

## 4. Configuración y Parámetros de CLI
Compatible con las otras herramientas como mapdrawer. Salidas png, jpeg y ahora uno vertical como SVG y PDF.
*   **Límites Configurables:** El módulo debe incluir argumentos CLI para establecer dinámicamente los límites de trazado de temperatura máxima (`--temp_max`) y mínima (`--temp_min`).
*   **Control de Exportación:** Permitir a los usuarios especificar explícitamente el nombre del archivo de salida (por ejemplo, utilizando las banderas `-o` o `--output_file`).
*   **Resolución:** Incluir un parámetro para establecer la resolución de salida en puntos por pulgada (`-d DPI`). El valor predeterminado debe ser 200 DPI para garantizar la generación de gráficos rasterizados de alta calidad.

## 5. Salidas y Mejoras Analíticas
*   **Parámetros de Inestabilidad:** El módulo debe tener la capacidad de calcular y superponer parámetros de estabilidad termodinámica sobre el diagrama. Esto incluye Energía Potencial Convectiva Disponible (CAPE) y el Índice de Elevación (Lifted Index), los cuales proporcionan un contexto crítico para el análisis de los sondeos atmosféricos.

Referencia: CSPP_Sounder_QL_Installation_Guide_v1.4.pdf
