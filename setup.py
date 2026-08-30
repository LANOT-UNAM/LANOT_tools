from setuptools import setup, find_packages

setup(
    name="lanot-tools",
    version="0.1.0",
    description="Herramientas y utilidades comunes para LANOT (Laboratorio Nacional de Observación de la Tierra)",
    author="Abraham Sierra",
    py_modules=["mapdrawer", "geotiff2view", "colorpalettetable", "metadata", "glm_renderer",
                "ash_view_generator", "thermo", "nucaps_sounding", "skewt"],
    install_requires=[
        "Pillow",
        "fiona",
        "pyproj",
        "numpy",
        "rasterio",
        "netCDF4",
        "scipy",
    ],
    extras_require={
        # Solo desarrollo; install.sh no las instala en el servidor.
        "dev": ["pytest"],
    },
    python_requires=">=3.8",
    entry_points={
        'console_scripts': [
            'mapdrawer=mapdrawer:main',
            'geotiff2view=geotiff2view:main',
            'skewt=skewt:main',
        ],
    },
)
