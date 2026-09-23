% Logo del LANOT como STRUCT incluible: «LAN» + el globo como la O + el satélite
% como la T. Es la misma figura que lanot_logo.mg —que ahora la usa—, pero sin
% lienzo propio, para ponerla dentro de otra figura (el Skew-T de skewt.py):
%
%     include "lanot_logo_struct.mg"
%     LanotLogo(size=20, at=(0.4, 19.1))
%
% `size` es el cuerpo de la palabra en pt, y `at` el origen tipográfico de la «L»
% sobre la línea base, en unidades de quien la llama, que tienen que ser cm (las
% del mundo de una figura con display_size y world_window iguales).
%
% ⚠ No se puede colocar con `fit`: el texto va en pt y no se escala con la caja,
% así que la palabra conservaría su tamaño mientras el globo y el satélite se
% encogen. Por eso la struct no tiene world_window y TODO sale de `size`: las
% medidas de abajo son las del logo a 60 pt multiplicadas por k = size/60.
%
% De dónde sale cada número: ver lanot_logo.mg. Aquí solo se escalan.

include "fulldisk_logo.mg"
include "lanot_sat.mg"

struct LanotLogo(size = 60) {
    k    = size/60
    cap  = 0.717*size/72*2.54      % altura de mayúscula, en cm
    gx   = 5.0*k    gy = 0.75*k    % centro del globo
    sx   = 6.0*k                   % el satélite arranca pasado el globo
    sy   = -0.01*cap               % sus ondas, un pelo bajo la línea base
    sh   =  0.987*cap              % su alto
    sw   =  1.5224*sh              % su ancho: la proporción de la PROPIA struct
    lsb  = 0.100*cap               % el hombro izquierdo de la «L»

    font "sanserif"
    text("LAN", size=size) { (-lsb) 0 }

    FullDiskMap(scale=0.8*k, at=(gx, gy))

    fit(LanotSat) { sx sy  (sx+sw) (sy+sh) }
}
