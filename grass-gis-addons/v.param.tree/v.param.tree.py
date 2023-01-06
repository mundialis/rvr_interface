#!/usr/bin/env python3

############################################################################
#
# MODULE:       v.param.tree
#
# AUTHOR(S):    Lina Krisztian
#
# PURPOSE:      Calculate various tree parameter
#
#
# COPYRIGHT:	(C) 2021 by mundialis and the GRASS Development Team
#
# This program is free software under the GNU General Public
# License (>=v2). Read the file COPYING that comes with GRASS
# for details.
#
#############################################################################

# %Module
# % description: Calculates difference between two vector layers (buildings)
# % keyword: vector
# % keyword: statistics
# % keyword: change detection
# % keyword: classification
# %end

# %option G_OPT_V_INPUT
# % label: Name of the input vector layer containing tree crowns
# %end


import os
import atexit
import grass.script as grass

# initialize global vars
rm_vectors = []


def cleanup():
    nuldev = open(os.devnull, 'w')
    kwargs = {
        'flags': 'f',
        'quiet': True,
        'stderr': nuldev
    }
    for rmv in rm_vectors:
        if grass.find_file(name=rmv, element='vector')['file']:
            grass.run_command(
                'g.remove', type='vector', name=rmv, **kwargs)


def main():

    global rm_vectors

    input = options['input']

    # # parameter
    # Stammposition
        # Luftbilder und daraus abgeleitete normalisierte digitale Objektmodelle können den Stamm selbst nicht abbilden,
        # da er von oben gesehen vom Kronendach verdeckt ist.
        # Die Stammposition kann ausgehend von der Baumkronenfläche mit dem Massenschwerpunkt
        # oder dem geometrischen Median dieser Fläche geschätzt werden.
        # Alternativ kann auch der höchste Punkt der Baumkronenfläche als Schätzung der Stammposition genommen werden.
    # Höhe des Baums
        # Die Baumhöhe kann über das nDOM als höchster Punkt der Kronenfläche bestimmt werden.
    # Kronendurchmesser
        # Der Kronendurchmesser kann auf zwei Arten bestimmt werden:
        # einmal als der Durchmesser eines Kreises mit der gleichen Fläche wie die Kronenfläche,
        # einmal als die größte Ausdehnung der bounding box der Kronenfläche, falls diese Fläche stark von einer Kreisform abweicht.
    # Kronenvolumen
        # Eine genaue Messung des Kronenvolumens erfordert ein echtes 3D Modell der Baumkrone.
        # Alternativ kann eine Kugel als Kronenform angenommen werden und das Volumen über den bekannten Durchmesser berechnet werden.
        # Das Kronenvolumen kann je nach Baumart leicht abweichend berechnet werden (Unterscheidung Laub- und Nadelbaum).
    # Kronenfläche
        # Die Kronenfläche ist die Fläche des Polygons, das als Baumkrone identifiziert wurde.
    # NDVI aus Farbinformation je einzelbaum
        # Für jeden Pixel kann ein NDVI-Wert aus den Luftbildern berechnet werden.
        # Der NDVI eines Einzelbaumes ergibt sich als Mittelwert oder Median aller Pixel einer Kronenfläche (zonale Statistik).
    # Abstand zu Gebäuden
        # Die Lage von Gebäuden kann von ALKIS oder OSM Daten erhalten werden.
        # Für jeden Baum bzw. jede Baumkrone kann dann die Entfernung zum nächsten (minimierte direkte Distanz) Gebäude berechnet werden.
        # Die ID des jeweiligen Objektes kann hierbei mitgeführt werden, um eine nachträgliche Zuordnung zu gewährleisten.
    # Abstand zu Bäumen in Umgebung
        # Bei gegebenen Kronenflächen kann für jede Kronenfläche die Entfernung zur nächsten anderen Kronenfläche bestimmt werden.


    # append to vector as attributes or

if __name__ == "__main__":
    options, flags = grass.parser()
    atexit.register(cleanup)
    main()
