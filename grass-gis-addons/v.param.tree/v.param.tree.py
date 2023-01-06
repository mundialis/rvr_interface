#!/usr/bin/env python3

############################################################################
#
# MODULE:       v.param.tree
# AUTHOR(S):    Lina Krisztian
#
# PURPOSE:      Calculate various tree parameters
# COPYRIGHT:   (C) 2022 by mundialis GmbH & Co. KG and the GRASS Development Team
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
#############################################################################

# %Module
# % description: Calculate various tree parameters
# % keyword: vector
# % keyword: classification
# %end

# %option G_OPT_V_INPUT
# % key: treecrowns
# % description: Vector map of tree crowns
# % required: yes
# %end

# %option G_OPT_R_INPUT
# % key: ndom
# % description: Raster map of nDOM
# % required: yes
# %end

# %option G_OPT_R_INPUT
# % key: ndvi
# % description: Raster map of NDVI
# % required: yes
# %end

import os
import atexit
import grass.script as grass
import math

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

    treecrowns = options['treecrowns']
    ndom = options['ndom']
    ndvi = options['ndvi']

    # Höhe des Baums:
    # Die Baumhöhe kann über das nDOM als höchster Punkt
    # der Kronenfläche bestimmt werden.
    grass.message(_("Berechne die Baumhöhe..."))
    col_hoehe = 'hoehe'
    grass.run_command(
        "v.rast.stats",
        map=treecrowns,
        type='area',
        raster=ndom,
        column_prefix=col_hoehe,
        method='maximum',
        quiet=True
    )
    grass.run_command(
        "v.db.renamecolumn",
        map=treecrowns,
        column=f"{col_hoehe}_maximum,{col_hoehe}",
        quiet=True
    )
    grass.message(_("Die Baumhöhe wurde berechnet."))

    # Kronenfläche:
    # Die Kronenfläche ist die Fläche des Polygons,
    # das als Baumkrone identifiziert wurde.
    grass.message(_("Berechne die Kronenfläche..."))
    col_flaeche = 'flaeche'
    grass.run_command(
        "v.to.db",
        map=treecrowns,
        option='area',
        columns=col_flaeche,
        quiet=True
    )
    grass.message(_("Die Kronenfläche wurde berechnet."))

    # Kronendurchmesser:
    # TODO: andere Methoden für Durchmesser ?
    # Der Kronendurchmesser kann auf zwei Arten bestimmt werden:
    # einmal als der Durchmesser eines Kreises,
    # mit der gleichen Fläche wie die Kronenfläche,
    # einmal als die größte Ausdehnung der bounding box der Kronenfläche,
    # falls diese Fläche stark von einer Kreisform abweicht.
    grass.message(_("Berechne den Kronendurchmesser..."))
    col_durchmesser = 'durchmesser'
    grass.run_command(
        "v.to.db",
        map=treecrowns,
        option='perimeter',
        columns=col_durchmesser,
        quiet=True
    )
    grass.message(_("Kronendurchmesser wurde berechnet."))

    # NDVI aus Farbinformation je Einzelbaum:
    # Für jeden Pixel kann ein NDVI-Wert aus den Luftbildern berechnet werden.
    # Der NDVI eines Einzelbaumes ergibt sich als Mittelwert oder Median
    # aller Pixel einer Kronenfläche (zonale Statistik).
    grass.message(_("Berechne NDVI je Einzelbaum:"))
    col_ndvi = 'ndvi'
    grass.run_command(
        "v.rast.stats",
        map=treecrowns,
        type='area',
        raster=ndvi,
        column_prefix=col_ndvi,
        method='average,median',
        quiet=True
    )
    grass.message(_("NDVI je Einzelbaum wurde berechnet."))

    # Kronenvolumen:
    # Eine genaue Messung des Kronenvolumens erfordert ein echtes 3D Modell der Baumkrone.
    # Alternativ kann eine Kugel als Kronenform angenommen werden
    # und das Volumen über den bekannten Durchmesser berechnet werden.
    # Das Kronenvolumen kann je nach Baumart leicht abweichend berechnet werden
    # (Unterscheidung Laub- und Nadelbaum).
    # TODO: andere Methodiken (z.B. Unterscheidung Laub- und Nadelbaum)
    grass.message(_("Berechne das Kronenvolumen..."))
    col_volumen = 'volumen'
    grass.run_command(
        "v.db.addcolumn",
        map=treecrowns,
        columns=f'{col_volumen} double precision'
    )
    # Annahme: Kreisvolumen
    grass.run_command(
        "v.db.update",
        map=treecrowns,
        column=col_volumen,
        query_column=f"(4./3.)*{math.pi}*"
                     f"({col_durchmesser}/2.)*"
                     f"({col_durchmesser}/2.)*"
                     f"({col_durchmesser}/2.)"
    )
    grass.message(_("Kronenvolumen wurde berechnet."))


    # # parameter
    # Stammposition
        # Luftbilder und daraus abgeleitete normalisierte digitale Objektmodelle können den Stamm selbst nicht abbilden,
        # da er von oben gesehen vom Kronendach verdeckt ist.
        # Die Stammposition kann ausgehend von der Baumkronenfläche mit dem Massenschwerpunkt
        # oder dem geometrischen Median dieser Fläche geschätzt werden.
        # Alternativ kann auch der höchste Punkt der Baumkronenfläche als Schätzung der Stammposition genommen werden.
    # Abstand zu Gebäuden
        # Die Lage von Gebäuden kann von ALKIS oder OSM Daten erhalten werden.
        # Für jeden Baum bzw. jede Baumkrone kann dann die Entfernung zum nächsten (minimierte direkte Distanz) Gebäude berechnet werden.
        # Die ID des jeweiligen Objektes kann hierbei mitgeführt werden, um eine nachträgliche Zuordnung zu gewährleisten.
    # Abstand zu Bäumen in Umgebung
        # Bei gegebenen Kronenflächen kann für jede Kronenfläche die Entfernung zur nächsten anderen Kronenfläche bestimmt werden.


if __name__ == "__main__":
    options, flags = grass.parser()
    atexit.register(cleanup)
    main()
