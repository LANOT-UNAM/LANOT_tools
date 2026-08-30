% Satélite de la marca del LANOT — la T de LANOT.
%
% Reconstrucción en MetaGráfica del satélite del logo del LANOT. La estructura sale
% del original EN COLOR (`satelite.png`, en esta carpeta); las proporciones generales
% y la colocación, del logo oficial en negro (~/Dropbox/cca/lanot/logos/).
%
% NOTAS --------------------------------------------------------------------
% ⚠ NO es lib/satellite.mg de MetaGráfica y no debe llamarse `satellite.mg`: el
% `include` busca LOCAL (junto al archivo principal) ANTES que la lib instalada, así
% que un archivo con ese nombre eclipsaría al de la lib para cualquier figura que se
% compile en este directorio. Aquél además es otro satélite —antena arriba, paneles
% a los lados de un cuerpo vertical— y no puede tocarse: lo consumen cuatro ejemplos
% del corpus y el curso de percepción remota.
%
% ⚠ TODO VA CON RELLENOS, ningún trazo, y es una decisión medida: en MetaGráfica la
% geometría escala con `fit` pero el ancho de línea NO (un fit 5× multiplica los
% radios por 5 y deja el trazo en 1 pt). Una marca se usa de favicon a cartel, así
% que un solo trazo bastaría para que cambiara de carácter con el tamaño. Las ondas,
% que son lo que más pediría un `arc` grueso, van como cuñas rellenas por eso.
% Verificado: la misma marca a 3 cm y a 24 cm, rasterizada al mismo tamaño, da CERO
% píxeles de diferencia.
%
% ⚠ LAS PIEZAS ESTÁN SEPARADAS, y la separación es de TONO, no de hueco — que es
% como la hace el original en color: alas y cuerpo en `col`, cúpula y brazos en
% `col2`, más claro. En el logo oficial en NEGRO esa estructura no se ve (brazos,
% huecos y borde del plato desaparecen en la silueta), así que con `col2 = col` esta
% misma struct degrada a aquella silueta fundida. Las alas además NO tocan el cuerpo:
% hay un hueco de 0.02 del vano cruzado por un brazo, como en el original.
%
% Proporciones en fracción del VANO de los paneles, medidas sobre el original en
% color (vano = 336 px): cuerpo 0.15 de ancho y esquinas de radio 0.03 —es un
% rectángulo redondeado, NO una cápsula: con extremos semicirculares el cuerpo se
% lee como una campana—, hueco cuerpo-ala 0.018, brazo 0.030 de alto, plato 0.29 de
% ancho por 0.09 de alto colgando bajo el cuerpo, travesaño inclinado -6°.
%
% El original lleva 7 celdas por fila; `cols` las parametriza —4 para la marca
% pequeña, 7 para la fiel— porque a tamaño de logo siete se empastan.

struct LanotSat(cols = 4, col = "black", col2 = "gray", bg = "white",
                tilt = -6, ondas = 3) {
    % La ventana local ESTÁ AJUSTADA A LA TINTA, y no de adorno: `fit` mapea la
    % VENTANA, no lo dibujado, así que un margen sobrante encoge la marca y la
    % descentra en su hueco. x: la punta del ala girada llega a 0.508; y: de la
    % cresta de la onda exterior (-0.484) a la cima del remate (0.180).
    world_window -0.51 0.51 -0.48 0.16

    bw  =  0.079         % semiancho del cuerpo
    rr  =  0.030         % radio de sus esquinas
    by0 = -0.105         % base del cuerpo   (alto 0.22, como el original)
    by1 =  0.115         % cima del cuerpo
    wy  =  0.095         % semialto del travesaño
    wx0 =  0.098         % donde arranca el ala: el cuerpo acaba en 0.079, el resto
                         % es el hueco que cruza el brazo
    wx1 =  0.500         % punta del ala (el vano ES la unidad: span = 1)
    g   =  0.030         % grueso de los bastidores entre celdas. En el original son
                         % 0.37 de la celda; aquí salen 0.46 porque con cuatro
                         % columnas las celdas son más grandes, y ese peso es lo que
                         % mantiene el aire del logo cuando la marca se ve pequeña.

    % --- brazos y alas -------------------------------------------------------
    % Todo va dentro del giro: en el original el travesaño está inclinado y el asta
    % se queda vertical, que es lo que lo hace leer como una T. Los brazos arrancan
    % DENTRO del cuerpo (0.03), que se dibuja después y les tapa el nacimiento.
    { rotate tilt
      for s = -1 to 1 step 2 {
        rectangle(fill=col2) { (s*0.030) (-0.015)  (s*wx0) 0.015 }
        rectangle(fill=col)  { (s*wx0)   (-wy)     (s*wx1) wy }
        cw = (wx1 - wx0 - (cols+1)*g)/cols
        for i = 0 to cols-1 {
          cx = wx0 + g + i*(cw + g)
          rectangle(fill=bg) { (s*cx) (g/2)     ((s*(cx+cw))) (wy-g) }
          rectangle(fill=bg) { (s*cx) (-wy+g)   ((s*(cx+cw))) (-g/2) }
        }
      }
    }

    % --- cuerpo: rectángulo REDONDEADO ---------------------------------------
    % Las cuatro esquinas en un `compound`: las sub-primitivas se encadenan en UN
    % solo trayecto, así que los lados salen de la unión de un cuarto de vuelta con
    % el siguiente y no hay que dibujarlos. Es la misma construcción de las ondas.
    compound(fill=col) {
      arc(rr, from=0,   to=90)  { (bw-rr)  (by1-rr) }
      arc(rr, from=90,  to=180) { (-bw+rr) (by1-rr) }
      arc(rr, from=180, to=270) { (-bw+rr) (by0+rr) }
      arc(rr, from=270, to=360) { (bw-rr)  (by0+rr) }
    }
    % remate de arriba (la «cola»), el mismo rectángulo redondeado en pequeño
    cw2 = 0.048   ch2 = 0.045   cr2 = 0.018
    compound(fill=col) {
      arc(cr2, from=0,   to=90)  { (cw2-cr2)  (by1+ch2-cr2) }
      arc(cr2, from=90,  to=180) { (-cw2+cr2) (by1+ch2-cr2) }
      arc(cr2, from=180, to=270) { (-cw2+cr2) (by1-0.005+cr2) }
      arc(cr2, from=270, to=360) { (cw2-cr2)  (by1-0.005+cr2) }
    }

    % --- plato: cuelga del cuerpo, en el tono claro --------------------------
    % No lleva falda ni se funde con el cuerpo: son dos piezas, y lo que las separa
    % es el tono. La cúpula toca la base del cuerpo y baja hasta su boca.
    dr  = 0.125          % semiancho del plato
    dh  = 0.105          % altura de la cúpula (2.4 de ancho por 1 de alto contando
                         % la boca: más honda que ancha, o parece platillo volador)
    drm = 0.026          % semialto de la elipse de la boca (escorzo)
    ym  = by0 - dh       % la boca
    arc(dr, dh, from=0, to=180, fill=col2) { 0 ym }
    ellipse(dr, drm, fill=col2) { 0 ym }
    % La boca: una lente delgada del color del fondo —el interior del plato— con la
    % bocina al centro. Va desplazada hacia arriba para que el borde DELANTERO quede
    % más grueso que el trasero, que es lo que da el escorzo.
    ellipse((dr-0.016), (drm-0.014), fill=bg) { 0 (ym+0.004) }
    ellipse(0.026, 0.009, fill=col) { 0 (ym+0.004) }

    % --- ondas: cuñas rellenas, no arcos trazados ----------------------------
    % El centro es la BOCA del plato; el barrido (±48° alrededor de la vertical) sale
    % del original y los radios exteriores quedan en 0.13 / 0.19 / 0.26 del vano.
    oy = ym
    for k = 1 to ondas {
      r = 0.025 + k*0.072
      compound(fill=col) {
        arc((r+0.027), from=222, to=318) { 0 oy }
        arc(r, from=318, to=222) { 0 oy }
      }
    }
}
