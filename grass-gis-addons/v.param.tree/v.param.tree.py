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

# %option G_OPT_V_INPUT
# % key: buildings
# % description: Vector map of buildings
# % required: yes
# %end

import os
import atexit
import grass.script as grass
import math

# initialize global vars
rm_rasters = []


def cleanup():
    nuldev = open(os.devnull, 'w')
    kwargs = {
        'flags': 'f',
        'quiet': True,
        'stderr': nuldev
    }
    for rmrast in rm_rasters:
        if grass.find_file(name=rmrast, element='raster')['file']:
            grass.run_command(
                'g.remove', type='raster', name=rmrast, **kwargs)


def main():

    global rm_rasters

    pid = os.getpid()

    treecrowns = options['treecrowns']
    ndom = options['ndom']
    ndvi = options['ndvi']
    buildings = options['buildings']

    # Testen, ob benötigtes Addon installiert ist
    if not grass.find_program('v.centerpoint', '--help'):
        grass.fatal(_("The 'v.centerpoint' module was not found,"
                      " install it first:"
                      + "\n" + "g.extension v.centerpoint"))

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
    # Eine genaue Messung des Kronenvolumens erfordert ein echtes 3D Modell der
    # Baumkrone. Alternativ kann eine Kugel als Kronenform angenommen werden
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

    # Stammposition:
    # Luftbilder und daraus abgeleitete normalisierte digitale Objektmodelle
    # können den Stamm selbst nicht abbilden,
    # da er von oben gesehen vom Kronendach verdeckt ist.
    # Die Stammposition kann ausgehend von der Baumkronenfläche
    # mit dem Massenschwerpunkt oder dem geometrischen Median
    # dieser Fläche geschätzt werden.
    # Alternativ kann auch der höchste Punkt der Baumkronenfläche
    # als Schätzung der Stammposition genommen werden.
    # TODO: complete
    # TODO: output von v.centerpoint appenden: nicht als Punkt, sondern als attribute
    grass.message(_("Berechne die Stammposition..."))
    # Massenschwerpunkt (berechnet mit Flächentriangulation)
    v_centerpoints_mean = list(grass.parse_command(
                            "v.centerpoint",
                            input=treecrowns,
                            type='area',
                            acenter='mean',
                          ).keys())

    # geometrischer Median (minimaler Abstand zur Flächentriangulation)
    # liegt möglicherweise nicht innerhalb des Gebiets
    # ==> daher nicht benutzt
    grass.message(_("Stammposition wurde berechnet."))

    # Abstand zu Gebäuden:
    # Die Lage von Gebäuden kann von ALKIS oder OSM Daten erhalten werden.
    # Für jeden Baum bzw. jede Baumkrone kann dann die Entfernung zum nächsten
    # (minimierte direkte Distanz) Gebäude berechnet werden.
    # Die ID des jeweiligen Objektes kann hierbei mitgeführt werden,
    # um eine nachträgliche Zuordnung zu gewährleisten.
    grass.message(_("Berechne den Abstand zum nächsten Gebäude..."))
    # Note: in case of intersection of treecrowns and buildings,
    #       the distance is set to zero (v.distance)
    # Note to "from"-argument of v.distance:
    #   from is a Python "​keyword". This means that the Python parser
    #   does not allow them to be used as identifier names (functions, classes,
    #   variables, parameters etc).
    #   If memory serves, when a module argument/option is a Python keyword,
    #   then the python wrapper appends an underscore to its name.
    #   I.e. you need to replace from with from_
    # TODO: WARNUNG: Mehr Kategorien gefunden im to_layer;
    #       Möglichkeit Kategorien anzugeben?
    col_dist_buildings = 'dist_buildings'
    col_dist_buildings_id = 'dist_buildings_OI'
    grass.run_command(
        "v.db.addcolumn",
        map=treecrowns,
        columns=[f'{col_dist_buildings} double precision',
                 f'{col_dist_buildings_id} character'],
        quiet=True
    )
    grass.run_command(
        "v.distance",
        from_=treecrowns,
        to=buildings,
        upload=['dist', 'to_attr'],
        to_column='OI',
        column=[col_dist_buildings, col_dist_buildings_id],
        quiet=True
    )
    grass.message(_("Abstand zum nächsten Gebäude wurde berechnet."))

    # Abstand zu Bäumen in Umgebung:
    # Bei gegebenen Kronenflächen kann für jede Kronenfläche die Entfernung
    # zur nächsten anderen Kronenfläche bestimmt werden.
    grass.message(_("Berechne den Abstand zum nächsten Baum..."))

    # For testing:
    treecrowns = 'trees_subset_20'

    # TODO: ensure: polygone unique IDs (v.category?): nicht alle areas zentroide?? (mehr areas als zentroide)
    treecrowns_rast = f'treecrowns_rast_{pid}'
    rm_rasters.append(treecrowns_rast)
    grass.run_command(
        "v.to.rast",
        input=treecrowns,
        output=treecrowns_rast,
        use='cat'
    )
    # # NO clump, since already have unique ids
    # treecrowns_rast_clump = f'treecrowns_rast_clump_{pid}'
    # grass.run_command(
    #     "r.clump",
    #     input=treecrowns_rast,
    #     output=treecrowns_rast_clump,
    # )
    print("now distance")
    treecrowns_cat = list(grass.parse_command(
                        "v.db.select",
                        map=treecrowns,
                        columns='cat',
                        flags='c'
                    ).keys())
    for cat in treecrowns_cat:
        grass.message(_(f"Started with cat: {cat}"))
        # für jeden cat-value zwei maps erstellen:
        #   eine NUR mit cat-value-polygon
        #   eine mit allen AUßER cat-value-polygon
        # diese dann mit r.distance min distanz berechnen
        map_cat_only = f'map_cat_{cat}_only_{pid}'
        rm_rasters.append(map_cat_only)
        rules_cat_only = f'{cat}={cat}'
        grass.write_command(
            "r.reclass",
            input=treecrowns_rast,
            output=map_cat_only,
            rules="-",
            stdin=rules_cat_only.encode(),
            quiet=True
        )
        map_all_but_cat = f'map_all_but_cat_{cat}_{pid}'
        rm_rasters.append(map_all_but_cat)
        rules_all_but_cat = (f'1 thru {len(treecrowns_cat)} = {int(cat)+1}'
                             f'\n {cat} = NULL')
        grass.write_command(
            "r.reclass",
            input=treecrowns_rast,
            output=map_all_but_cat,
            rules="-",
            stdin=rules_all_but_cat.encode(),
            quiet=True
        )

        # cell centers considered for distance calculation
        #  ==> neighbouring trees still have dist 0.1
        # NOTE: bei v.distance nicht so (?)
        rdist = grass.parse_command(
            "r.distance",
            maps=f"{map_all_but_cat},{map_cat_only}",
        )
        print(f"rdist {rdist}")

        # TODO: append min_dist (als rdist extraxieren)
        #       to corresponding line (cat) of dist_trees-column
    grass.message(_("Abstand zum nächsten Baum wurde berechnet."))


if __name__ == "__main__":
    options, flags = grass.parser()
    atexit.register(cleanup)
    main()
