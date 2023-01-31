#!/usr/bin/env python3

############################################################################
#
# MODULE:       v.tree.param
# AUTHOR(S):    Lina Krisztian
#
# PURPOSE:      Calculate various tree parameters
# COPYRIGHT:   (C) 2023 by mundialis GmbH & Co. KG and the GRASS Development Team
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
# % key: einzelbaeume
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
# % key: gebaeude
# % description: Vector map of gebaeude
# % required: yes
# %end

# %option
# % key: abstand_gebaeude_umkreis
# % type: integer
# % description: range in which neighbouring buildings are searched for
# % required: no
# %end

# %option
# % key: abstand_baum_umkreis
# % description: range in which neighbouring trees are searched for
# % required: no
# % answer: 500
# %end

import os
import atexit
import grass.script as grass
import math

# initialize global vars
rm_rasters = []
stammposition_SQL_temp = None
current_region = None


def cleanup():
    nuldev = open(os.devnull, 'w')
    kwargs = {
        'flags': 'f',
        'quiet': True,
        'stderr': nuldev
    }
    if grass.find_file(name=current_region, element='windows')['file']:
        grass.message(_("Setze region zurück."))
        grass.run_command(
            "g.region",
            region=current_region
        )
        grass.run_command(
            "g.remove",
            type="region",
            name=current_region,
            **kwargs
        )
    for rmrast in rm_rasters:
        if grass.find_file(name=rmrast, element='raster')['file']:
            grass.run_command(
                'g.remove', type='raster', name=rmrast, **kwargs)
    if stammposition_SQL_temp:
        grass.try_remove(stammposition_SQL_temp)


def baumhoehe(list_attr, einzelbaeume, ndom):
    # Höhe des Baums:
    # Die Baumhöhe kann über das nDOM als höchster Punkt
    # der Kronenfläche bestimmt werden.
    grass.message(_("Berechne die Baumhöhen..."))
    col_hoehe = 'hoehe'
    col_hoehe_perc = f"{col_hoehe}_percentile_95"
    col_hoehe_max = f"{col_hoehe}_maximum"
    if col_hoehe_perc in list_attr:
        grass.warning(_(
            f"Spalte {col_hoehe_perc} ist in Vektorkarte {einzelbaeume} "
            "bereits enthalten und wird überschrieben."
        ))
        grass.run_command(
            "v.db.dropcolumn",
            map=einzelbaeume,
            columns=col_hoehe_perc,
            quiet=True
        )
    if col_hoehe_max in list_attr:
        grass.warning(_(
            f"Spalte {col_hoehe_max} ist in Vektorkarte {einzelbaeume} "
            "bereits enthalten und wird überschrieben."
        ))
        grass.run_command(
            "v.db.dropcolumn",
            map=einzelbaeume,
            columns=col_hoehe_max,
            quiet=True
        )
    # Maximum und Perzentil (für den Fall von Ausreißern)
    grass.run_command(
        "v.rast.stats",
        map=einzelbaeume,
        type='area',
        raster=ndom,
        column_prefix=col_hoehe,
        method='maximum,percentile',
        percentile=95,
        quiet=True
    )
    grass.message(_("Die Baumhöhen wurden berechnet."))


def kronenflaeche(einzelbaeume):
    # Kronenfläche:
    # Die Kronenfläche ist die Fläche des Polygons,
    # das als Baumkrone identifiziert wurde.
    grass.message(_("Berechne die Kronenflächen..."))
    col_flaeche = 'flaeche'
    grass.run_command(
        "v.to.db",
        map=einzelbaeume,
        option='area',
        columns=col_flaeche,
        quiet=True
    )
    grass.message(_("Die Kronenflächen wurden berechnet."))


def kronendurchmesser(einzelbaeume):
    # Kronendurchmesser:
    # Der Kronendurchmesser kann auf zwei Arten bestimmt werden:
    # einmal als der Durchmesser eines Kreises,
    # mit der gleichen Fläche wie die Kronenfläche,
    # einmal als die größte Ausdehnung der bounding box der Kronenfläche,
    # falls diese Fläche stark von einer Kreisform abweicht.
    # NOTE: kann um andere/weitere Methoden für Durchmesser erweitert werden
    #       aktuell nur als Durchmesser eines Kreises implementiert
    grass.message(_("Berechne die Kronendurchmesser..."))
    col_durchmesser = 'durchmesser'
    grass.run_command(
        "v.to.db",
        map=einzelbaeume,
        option='perimeter',
        columns=col_durchmesser,
        quiet=True
    )
    # Annahme Kreis
    grass.run_command(
        "v.db.update",
        map=einzelbaeume,
        column=col_durchmesser,
        query_column=f"{col_durchmesser}/{math.pi}"
    )
    grass.message(_("Die Kronendurchmesser wurde berechnet."))
    return col_durchmesser


def ndvi_einzelbaum(list_attr, einzelbaeume, ndvi):
    # NDVI aus Farbinformation je einzelbaeume:
    # Für jeden Pixel kann ein NDVI-Wert aus den Luftbildern berechnet werden.
    # Der NDVI eines einzelbaeumees ergibt sich als Mittelwert oder Median
    # aller Pixel einer Kronenfläche (zonale Statistik).
    grass.message(_("Berechne den NDVI je einzelbaeume..."))
    col_ndvi = 'ndvi'
    if f"{col_ndvi}_average" and f"{col_ndvi}_median" in list_attr:
        grass.warning(_(
            f"Spalte {col_ndvi}_average und {col_ndvi}_median "
            f"sind in Vektorkarte {einzelbaeume} "
            "bereits enthalten und werden überschrieben."
        ))
    grass.run_command(
        "v.rast.stats",
        map=einzelbaeume,
        type='area',
        raster=ndvi,
        column_prefix=col_ndvi,
        method='average,median',
        quiet=True,
        flags='c'
    )
    grass.message(_("Der NDVI je einzelbaeume wurde berechnet."))


def kronenvolumen(list_attr, einzelbaeume, col_durchmesser):
    # Kronenvolumen:
    # Eine genaue Messung des Kronenvolumens erfordert ein echtes 3D Modell der
    # Baumkrone. Alternativ kann eine Kugel als Kronenform angenommen werden
    # und das Volumen über den bekannten Durchmesser berechnet werden.
    # Das Kronenvolumen kann je nach Baumart leicht abweichend berechnet werden
    # (Unterscheidung Laub- und Nadelbaum).
    # NOTE: kann um andere Methodiken erweitert werden
    #       (z.B. Unterscheidung Laub- und Nadelbaum)
    grass.message(_("Berechne die Kronenvolumen..."))
    col_volumen = 'volumen'
    if col_volumen in list_attr:
        grass.warning(_(
            f"Spalte {col_volumen} ist in Vektorkarte {einzelbaeume} "
            "bereits enthalten und wird überschrieben."
        ))
    else:
        grass.run_command(
            "v.db.addcolumn",
            map=einzelbaeume,
            columns=f'{col_volumen} double precision'
        )
    # Annahme: Kreisvolumen
    grass.run_command(
        "v.db.update",
        map=einzelbaeume,
        column=col_volumen,
        query_column=f"(4./3.)*{math.pi}*"
                     f"({col_durchmesser}/2.)*"
                     f"({col_durchmesser}/2.)*"
                     f"({col_durchmesser}/2.)"
    )
    grass.message(_("Die Kronenvolumen wurden berechnet."))


def stammposition(list_attr, einzelbaeume):
    # Stammposition:
    # Luftbilder und daraus abgeleitete normalisierte digitale Objektmodelle
    # können den Stamm selbst nicht abbilden,
    # da er von oben gesehen vom Kronendach verdeckt ist.
    # Die Stammposition kann ausgehend von der Baumkronenfläche
    # mit dem Massenschwerpunkt oder dem Zentroid bestimmt werden.
    # Alternativ kann auch der höchste Punkt der Baumkronenfläche
    # als Schätzung der Stammposition genommen werden.
    grass.message(_("Berechne die Stammpositionen..."))
    # Zentroid als Stammposition
    col_sp_cent = 'stammposition_zentroid'
    grass.run_command(
        "v.to.db",
        map=einzelbaeume,
        type='centroid',
        option='coor',
        columns=[f'{col_sp_cent}_x', f'{col_sp_cent}_y'],
        quiet=True
    )
    # Massenschwerpunkt (berechnet mit Flächentriangulation)
    # als Stammposition
    v_centerpoints_mean = list(grass.parse_command(
                            "v.centerpoint",
                            input=einzelbaeume,
                            type='area',
                            acenter='mean',
                            quiet=True
                          ).keys())
    # SQL file erstellen:
    col_sp_mean = 'stammposition_massenschwerpunkt'
    if f'{col_sp_mean}_x' in list_attr:
        grass.warning(_(
            f"Spalte {col_sp_mean} ist in Vektorkarte {einzelbaeume} "
            "bereits enthalten und wird überschrieben."
        ))
    else:
        grass.run_command(
            "v.db.addcolumn",
            map=einzelbaeume,
            columns=[f'{col_sp_mean}_x double precision',
                     f'{col_sp_mean}_y double precision'],
            quiet=True
        )
    stammposition_SQL_temp = grass.tempfile()
    with open(stammposition_SQL_temp, 'w') as sql_file:
        for el in v_centerpoints_mean:
            el_cat = el.split('|')[-1]
            el_x = el.split('|')[0]
            el_y = el.split('|')[1]
            sql_line = (f'UPDATE {einzelbaeume} SET {col_sp_mean}_x={el_x},'
                        f' {col_sp_mean}_y={el_y} WHERE cat={el_cat};')
            sql_file.write(f'{sql_line}\n')
    grass.run_command(
        "db.execute",
        input=stammposition_SQL_temp,
        quiet=True
    )
    grass.message(_("Die Stammpositionen wurden berechnet."))


def abstand_gebaeude(list_attr,
                     einzelbaeume,
                     gebaeude,
                     abstand_gebaeude_umkreis):
    # Abstand zu Gebäuden:
    # Die Lage von Gebäuden kann von ALKIS oder OSM Daten erhalten werden.
    # Für jeden Baum bzw. jede Baumkrone kann dann die Entfernung zum nächsten
    # (minimierte direkte Distanz) Gebäude berechnet werden.
    grass.message(_("Berechne den Abstand zum nächsten Gebäude..."))
    # NOTE: in case of intersection of einzelbaeume and gebaeude,
    #       the distance is set to zero (v.distance)
    # Note to "from"-argument of v.distance:
    #   from is a Python "​keyword". This means that the Python parser
    #   does not allow them to be used as identifier names (functions, classes,
    #   variables, parameters etc).
    #   If memory serves, when a module argument/option is a Python keyword,
    #   then the python wrapper appends an underscore to its name.
    #   I.e. you need to replace from with from_
    col_dist_gebaeude = 'abstand_gebaeude'
    if col_dist_gebaeude in list_attr:
        grass.warning(_(
            f"Spalte {col_dist_gebaeude} ist in Vektorkarte {einzelbaeume} "
            "bereits enthalten und wird überschrieben."
        ))
        grass.run_command(
            "v.db.dropcolumn",
            map=einzelbaeume,
            columns=col_dist_gebaeude,
            quiet=True
        )
    grass.run_command(
        "v.db.addcolumn",
        map=einzelbaeume,
        columns=f'{col_dist_gebaeude} double precision',
        quiet=True
    )
    param = {
        "from_": einzelbaeume,
        "to": gebaeude,
        "upload": 'dist',
        "column": col_dist_gebaeude,
        "quiet": True,
        "overwrite": True
    }
    if abstand_gebaeude_umkreis:
        param["dmax"] = abstand_gebaeude_umkreis
    grass.run_command(
        "v.distance",
        **param
    )
    grass.message(_("Abstand zum nächsten Gebäude wurde berechnet."))


def abstand_baeume(list_attr, einzelbaeume, pid, abstand_baum_umkreis, ndom):
    # Abstand zu Bäumen in Umgebung:
    # Bei gegebenen Kronenflächen kann für jede Kronenfläche die Entfernung
    # zur nächsten anderen Kronenfläche bestimmt werden.
    grass.message(_("Berechne den Abstand zum nächsten Baum..."))
    einzelbaeume_rast = f'einzelbaeume_rast_{pid}'
    rm_rasters.append(einzelbaeume_rast)
    grass.run_command(
        "v.to.rast",
        input=einzelbaeume,
        output=einzelbaeume_rast,
        use='cat',
        quiet=True
    )
    einzelbaeume_cat = list(grass.parse_command(
                        "v.db.select",
                        map=einzelbaeume,
                        columns='cat',
                        flags='c'
                    ).keys())
    col_dist_trees = 'abstand_baum'
    if col_dist_trees in list_attr:
        grass.warning(_(
            f"Spalte {col_dist_trees} ist in Vektorkarte {einzelbaeume} "
            "bereits enthalten und wird überschrieben."
        ))
        grass.run_command(
            "v.db.dropcolumn",
            map=einzelbaeume,
            columns=col_dist_trees,
            quiet=True
        )
    grass.run_command(
        "v.db.addcolumn",
        map=einzelbaeume,
        columns=f'{col_dist_trees} double precision',
        quiet=True
    )

    for cat in einzelbaeume_cat:
        grass.message(_("Berechne Abstand für Baum:"
                        f"{cat}/{len(einzelbaeume_cat)}"))
        # für jeden cat-value zwei maps erstellen:
        #   eine NUR mit cat-value-polygon
        #   eine mit allen AUßER cat-value-polygon
        # diese dann mit r.distance min distanz berechnen
        map_cat_only = f'map_cat_{cat}_only_{pid}'
        rm_rasters.insert(
            0, map_cat_only
            )  # insert to rm_rasters, because they have to be
        # deleted before base map einzelbaeume_rast in cleanup
        rules_cat_only = f'{cat}={cat}'
        grass.write_command(
            "r.reclass",
            input=einzelbaeume_rast,
            output=map_cat_only,
            rules="-",
            stdin=rules_cat_only.encode(),
            quiet=True
        )
        # fuer Abstand zu anderen Baeumen, region kleiner setzen
        # mit option: abstand_baum_umkreis
        grass.run_command(
            "g.region",
            zoom=map_cat_only,
        )
        # abstand_baum_umkreis in Metern gegeben,
        # damit einheitlich mit abstand_gebaeude_umkreis
        # muss für g.region in cells umgerechnet werden
        nsres = grass.parse_command("g.region", flags='m')["nsres"]
        abstand_baum_umkreis_cells = math.ceil(
            float(abstand_baum_umkreis)/float(nsres)
            )
        grass.run_command(
            "g.region",
            grow=abstand_baum_umkreis_cells,
        )
        map_all_but_cat = f'map_all_but_cat_{cat}_{pid}'
        rm_rasters.insert(0, map_all_but_cat)
        rules_all_but_cat = (f'1 thru {len(einzelbaeume_cat)} = {int(cat)+1}'
                             f'\n {cat} = NULL')
        grass.write_command(
            "r.reclass",
            input=einzelbaeume_rast,
            output=map_all_but_cat,
            rules="-",
            stdin=rules_all_but_cat.encode(),
            quiet=True
        )
        try:
            rdist_out = list(grass.parse_command(
                "r.distance",
                map=f"{map_cat_only},{map_all_but_cat}",
                quiet=True
            ).keys())[0]
            # resolution subtrahieren, damit benachbarte Bäume Distanz 0 haben;
            # Abstand ist dann nicht mehr von cell center zu cell center
            # (so ist Abstand bei r.distance definiert),
            # sondern von Baumkronenrand zu Baumkronenrand
            rdist_dist = float(rdist_out.split(':')[2]) - float(nsres)
            if rdist_dist < 0:
                rdist_dist = 0
        except IndexError:
            rdist_dist = 'NULL'
        # Region zurück setzen, für nächste Iteration
        grass.run_command(
            "g.region",
            raster=ndom
        )
        grass.run_command(
            "v.db.update",
            map=einzelbaeume,
            column=col_dist_trees,
            where=f"cat == {cat}",
            value=rdist_dist,
            quiet=True
        )
    grass.message(_("Abstand zum nächsten Baum wurde berechnet."))


def main():

    global rm_rasters, stammposition_SQL_temp, current_region

    pid = os.getpid()

    einzelbaeume = options['einzelbaeume']
    ndom = options['ndom']
    ndvi = options['ndvi']
    gebaeude = options['gebaeude']
    abstand_gebaeude_umkreis = options['abstand_gebaeude_umkreis']
    abstand_baum_umkreis = options['abstand_baum_umkreis']

    # Testen, ob benötigtes Addon installiert ist
    if not grass.find_program('v.centerpoint', '--help'):
        grass.fatal(_("The 'v.centerpoint' module was not found,"
                      " install it first:"
                      + "\n" + "g.extension v.centerpoint"))

    # korrekte Ausdehnung und Auflösung setzen
    current_region = f'current_region_{pid}'
    grass.run_command(
        "g.region",
        save=current_region
    )
    grass.message(_("Region gesetzt auf:"))
    grass.run_command(
        "g.region",
        raster=ndom,
        flags='ap'
        )

    # Liste der Attribut-spalten der Einzelbaeume-Vektorkarte
    list_attr = [el.split('|')[1] for el
                 in list(grass.parse_command(
                    "v.info",
                    map=einzelbaeume,
                    flags='c'
                    ).keys())]

    # Berechne verschiedene Baumparameter
    baumhoehe(list_attr, einzelbaeume, ndom)
    kronenflaeche(einzelbaeume)
    col_durchmesser = kronendurchmesser(einzelbaeume)
    ndvi_einzelbaum(list_attr, einzelbaeume, ndvi)
    kronenvolumen(list_attr, einzelbaeume, col_durchmesser)
    stammposition(list_attr, einzelbaeume)
    abstand_gebaeude(list_attr, einzelbaeume, gebaeude,
                     abstand_gebaeude_umkreis)
    abstand_baeume(list_attr, einzelbaeume, pid, abstand_baum_umkreis, ndom)


if __name__ == "__main__":
    options, flags = grass.parser()
    atexit.register(cleanup)
    main()
