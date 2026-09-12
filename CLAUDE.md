# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

LANOT_tools is a satellite imagery processing and visualization suite for LANOT (Laboratorio Nacional de Observación de la Tierra). It converts GeoTIFF satellite data to annotated map images, supports multiple satellite projections (GOES-16/17/18/19, EPSG, Proj4), and handles products from GOES ABI, VIIRS ATMOS/CSPP, and GLM.

## Commands

```bash
# Skew-T de un sondeo NUCAPS (vectorial: .svg, .pdf o .eps)
skewt NUCAPS-EDR_*.nc --lat 19.4 --lon -99.1 -o cdmx.svg --keep-mg

# Run all tests
python3 -m pytest tests/

# Run a single test file
python3 -m pytest tests/test_mapdrawer.py -v

# Run a single test
python3 -m pytest tests/test_mapdrawer.py::TestClass::test_name -v

# Development install (edits take effect immediately)
pip install -e .

# Dev dependencies (pytest); not installed by install.sh
pip install -r requirements-dev.txt

# Server install
sudo ./install.sh
```

Note: use `python3`, not `python` — `python` is not in PATH.

Note: the test suite needs `pytest` **and** the full runtime deps in the *same* interpreter. It does not degrade gracefully — a missing `fiona`, `rasterio` or `netCDF4` aborts collection with `ModuleNotFoundError` before a single test runs, even though the tools themselves treat those as optional at runtime.

On a server-installed machine the only interpreter with the runtime deps is the venv at `/opt/lanot-tools/venv`, which is root-owned, so pytest has to be added there explicitly:

```bash
sudo /opt/lanot-tools/venv/bin/pip install pytest
/opt/lanot-tools/venv/bin/python -m pytest tests/
```

Expected on a healthy checkout: **265 passed, 0 skipped** (medido el 2026-09-12 con `/opt/lanot-tools/venv` + pytest en un `--target`, tras la fase 4 de STAC y la regla de tamaños < 1). Conteos anteriores —224 el 2026-08-30; 114 passed, 33 skipped antes— ya no aplican: aquellos saltos eran por datos de muestra ausentes, no por dependencias.

Los tests del Skew-T que compilan un `.mg` se saltan solos si `mg` no está en el PATH; los del lector NUCAPS, si falta `netCDF4`.

## Architecture

The system has three CLI entry points and six importable library modules:

### Entry Points
- **`geotiff2view.py`** — Reads GeoTIFF → converts to PNG/JPEG with color palettes (CPT). Delegates to `MapDrawer` internally for overlays. Handles single-band + CPT, RGB composites from 3 separate TIFFs, NoData transparency.
- **`skewt.py`** — Reads a NUCAPS sounding → emits a Skew-T Log-P thermodiagram as SVG/PDF/EPS. Unlike the other two tools this one is **vector-only**: it writes a MetaGráfica source file and shells out to `mg` to compile it. See "Skew-T on MetaGráfica" below.
- **`mapdrawer.py`** — Post-processes existing images (PNG, JPEG, or GeoTIFF) with vector overlays, grids, logos, timestamps, colorbars, and GLM lightning data. Also hosts `make_south_room()`, the `--lat-south` helper that frees empty rows at the bottom for the colorbar; `geotiff2view` imports it from here.

### Library Modules
- **`metadata.py`** (`Metadata` class) — Dict-like container for CRS, bounds, timestamp, satellite name. Factory methods: `Metadata.from_rasterio(src)`, `Metadata.from_json_file(path)`, `Metadata.from_dict(data)`. Key helper: `get_mapdrawer_bounds()` converts rasterio (left, bottom, right, top) to MapDrawer (ulx, uly, lrx, lry) format.
- **`colorpalettetable.py`** (`ColorPaletteTable`) — GMT-style CPT file parser. Supports continuous and discrete palettes, special values (B/F/N), and colormaps embedded in GeoTIFF tags (used by CSPP VIIRS ATMOS products).
- **`glm_renderer.py`** — Renders GLM (Geostationary Lightning Mapper) NetCDF files as RGBA layers. Two independent modes: `render_glm_layer()` draws a qualitative glow from L2 LCFA events (`mapdrawer --glm`, or standalone); `render_glm_grid_layer()` accumulates gridded GLMF products (FED/MFA/TOE) over a multi-minute window and colors them by physical value with a CPT (`mapdrawer --glm-grid`). See `plan_glm_grid.md`.
- **`thermo.py`** — Moist-atmosphere thermodynamics in pure numpy, no I/O: Bolton saturation vapor pressure, dewpoint from mixing ratio, dry/moist adiabats, LCL (Bolton 1980), parcel ascent, LFC/EL. Everything is hPa + Kelvin + kg/kg. This is where a Skew-T goes silently wrong, so it has no dependencies and is tested on its own.
- **`nucaps_sounding.py`** — Reads NUCAPS-EDR granules (CSPP HEAP) and extracts one vertical profile. A granule is a 120-FOR swath slice, not a grid, so "the profile at (lat, lon)" means the nearest FOR: it always returns the FOR's *real* coordinates plus the distance to what was asked. Derives dewpoint from `H2O_MR` (NUCAPS does not carry one) and reads CAPE/Lifted Index from `Stability[:, 0]` and `[:, 9]`.
- **`ash_view_generator.py`** — Composites a volcanic ash detection GeoTIFF (uint8 + embedded colormap) onto a base ABI image with georeferenced alignment.

### Key Design Patterns

**Projection handling** — There are no CRS aliases: `--crs` takes `epsg:XXXX`, a Proj4 string or WKT, passed straight to pyproj/rasterio. The GOES fixed-grid CRS comes from the data — the GeoTIFF via rasterio, or `proj:wkt2` in hpsv's STAC Item — never from a private table. The old `GOES_PROJECTIONS` alias table was deleted in STAC phase 4: it hardcoded `+a/+b/+h/+lon_0` while `hpsv` reads them from the NetCDF, and only worked because two repos kept tables in sync by hand.

**Layer system** — `--layer NAME:COLOR:WIDTH[:labels]` syntax. Predefined names: `COASTLINE`, `COUNTRIES`, `MEXSTATES`, and `gridN` (lat/lon grid at N° intervals). Vector data loaded from `/usr/local/share/lanot/gpkg/` (installed) or local path (dev). Layers are drawn in CLI argument order.

**Colorbar from GeoTIFF** — `mapdrawer --colorbar` reads the `colormap` metadata tag embedded by CSPP VIIRS ATMOS. Falls back to `--cpt FILE` if no embedded colormap. Units (K, m, etc.) are auto-detected from filenames like `CldTopTemp`, `CldTopHght`.

**Log-scale CPTs** — `ColorPaletteTable` builds a 256-entry LUT that is *linear in value*, and its discrete parser truncates breakpoints to `int`. Neither form can express log-spaced breaks in physical units. The `glm_*.cpt` palettes work around this by indexing on **interval number** (0, 1, 2, …) and carrying the physical lower edge of each interval in the `;` label; `glm_renderer.cpt_grid_breaks()` reads them back. This keeps the log scale in the CPT rather than in code, and the colorbar labels come out in physical units for free.

**Skew-T on MetaGráfica** — `skewt` does not draw pixels: it emits a `.mg` and runs `mg fig.mg out.svg` (format chosen by the output extension, same convention as `mg` itself). This costs **zero new Python dependencies** but adds a non-pip build dependency: the `mg` binary from `~/proyectos/Metagrafica`, which must be installed and version-pinned on the server. If `mg` is missing the `.mg` is still written and the failure is announced — same degradation style as the missing-`rasterio` path.

**Skew-T geometry: the skew lives in the data, not in the renderer** — mg's `yscale="log"` is *not* used. Under a log axis mg remaps coordinate-by-coordinate and matrices don't compose (structs and bare `grid()`/`ticks()`/`axis()` are errors inside), so a shear can't be expressed there. Instead `skewt.py` computes `y = log(p_max/p)` and `x = T + m·y` in Python and uses a **linear** `plot`; `m` is derived from `--skew` and the box aspect so the angle is the one seen on the page. Consequences: pressure gridlines are irregular in `y`, so each isobar is a `rule(y=…, label=…)` rather than a `yaxis(step=…)`; and the pressure axis gets its name from `yaxis(label=…, ticks="none", tick_labels=false)`.

**Metadata JSON = STAC Item** — For non-GeoTIFF images, `mapdrawer --metadata` reads the STAC Item that `hpsv -j` writes (`Metadata.from_stac_item_file()`); the old flat sidecar with `crs`/`bounds` at the root is rejected. Two traps: the root `bbox` is the 4326 *footprint*, not the raster extent — bounds come from the asset's `proj:transform` + `proj:shape`; and with `-B` the Item has two assets on different grids, so the asset is picked by `href` == image basename and the item-level `proj:*` is trusted only when there is a single asset. `Metadata.from_json_file()`/`save_json()` still handle the flat format for `geotiff2view --save-metadata` and the sidecar `mapdrawer --o_crs` writes.

**Optional dependencies** — Both tools degrade gracefully: no `rasterio` → PIL-only reading (no geo-metadata); no `pyproj` → linear projection only.

**Position indices** — Logo, timestamp, legend, colorbar positions use 0=UL, 1=UR, 2=LL, 3=LR throughout all tools.

**Sizes: < 1 is a fraction of the image width** — `calculate_size()` (`mapdrawer.py`, shared by all three tools) reads `--logo-size`, `--font-size`, `--shape` size and the `--layer` width the same way: `0 < v < 1` → fraction of the width, `≥ 1` → pixels, `N%` → percent. So `COASTLINE:white:0.0005` is ~1 px on a meso sector and 5 px on a 10000 px disk, while `:1` is 1 px. The trap is GMT/QGIS habit: `:0.5` means "thin line" there and **half the image** here. `layer_width()` warns on stderr when a relative line width exceeds 1 % of the width. Until 2026-06 (`f50b864`) the layer width was pixels, which is what servers with older code still do.

### Installed Resource Paths
- CPT palettes: `/usr/local/share/lanot/colortables/`
- Vector layers: `/usr/local/share/lanot/gpkg/`
- Logos: `/usr/local/share/lanot/logos/`
- Predefined regions (conus, fulldisk, etc.): `docs/recortes_coordenadas.csv` relative to install

### Operational Scripts
- **`crea_vistas_viirs.sh`** — Batch processes recent VIIRS products (CLAVRX, ACSPO, Fire) using `geotiff2view`. Selects CPT by filename pattern and writes JPEG to `/var/www/html/polar/jpss/viirs/`.
- **`GLMconus_png.sh`** — Renders latest GLM files over GOES CONUS ABI C13 using `mapdrawer --glm`.
