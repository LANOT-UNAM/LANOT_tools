% Logo del LANOT — «LAN» + el globo como la O + el satélite como la T.
%
% Versión VECTORIAL del logo, para poder incrustarlo en salidas vectoriales sin
% escalar un mapa de bits. No sustituye a los PNG oficiales de
% /usr/local/share/lanot/logos: convive con ellos.
%
% NOTAS --------------------------------------------------------------------
% El satélite es `lanot_sat.mg`, hermano de este archivo, y NO el `satellite.mg`
% de la lib de MetaGráfica: aquél es otro satélite (antena arriba, paneles a los
% lados de un cuerpo vertical) y además no puede tocarse, lo consumen cuatro
% ejemplos del corpus y el curso de percepción remota.
%
% ⚠ Necesita `mg` del 2026-08-30 o posterior: hasta ese día un cambio de tamaño
% borraba la cara de fuente ambiente, así que `font "sanserif"` como sentencia no
% llegaba al `text()` y había que pasarla como argumento. Si las letras salen en
% Times, reinstala MetaGráfica (`make install`).
%
% NADA está puesto a ojo: la colocación del satélite sale de medir el logo oficial
% —en fracción de la altura de MAYÚSCULA, mide 0.99 de alto, su cima queda 0.02 por
% debajo de la cima de las letras y sus ondas terminan 0.01 por debajo de la línea
% base—, la altura de mayúscula sale del cuerpo de la letra (0.717 em en Helvetica),
% y el LIENZO sale de lo dibujado. Cambiar `size` reacomoda todo junto.

include "fulldisk_map.mg"
include "lanot_sat.mg"

size = 60                       % cuerpo de la palabra, en pt
cap  = 0.717*size/72*2.54       % altura de mayúscula, en cm (= unidades de mundo)

gx   = 5.0    gy = 0.75         % centro del globo…
gr   = 0.815                    % …y su radio a scale=0.8 (medido sobre el render)
sx   = 6.0                      % el satélite arranca pasado el globo
sy   = -0.01*cap                % sus ondas, un pelo bajo la línea base
sh   =  0.987*cap               % su alto
sw   =  1.5224*sh               % su ancho: la proporción de la PROPIA struct. Si se
                                % le da otra, el `fit` centra MEET y deja aire a los
                                % lados en vez de llenar la caja.
m    = 0.05                     % margen del lienzo, en cm
lsb  = 0.100*cap                % el hombro izquierdo de la «L»: el `text` se ancla
                                % en su origen tipográfico, no en la tinta, así que
                                % sin corregirlo el margen izquierdo sale cuatro
                                % veces el de los otros tres lados

% El lienzo se ajusta a la tinta. El globo es hoy la pieza más alta y la más baja;
% el `if` lo comprueba en vez de darlo por hecho, porque con un `size` bastante mayor
% las letras lo rebasarían.
x0 = -m                x1 = sx + sw + m
y0 = gy - gr - m       y1 = gy + gr + m
if cap > gy + gr { y1 = cap + m }
if 0 < gy - gr   { y0 = -m }

display_size (x1-x0) (y1-y0)
world_window x0 x1 y0 y1

font "sanserif"
text("LAN", size=size) { (-lsb) 0 }

FullDiskMap(scale=0.8, at=(gx, gy))

fit(LanotSat) { sx sy  (sx+sw) (sy+sh) }
