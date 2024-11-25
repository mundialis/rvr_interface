#!/usr/bin/env python3

############################################################################
#
# MODULE:       v.trees.param.worker
# AUTHOR(S):    Lina Krisztian
#
# PURPOSE:      Calculate various tree parameters
# COPYRIGHT:   (C) 2023 - 2024 by mundialis GmbH & Co. KG and the GRASS Development Team
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
# % description: Calculate various tree parameters.
# % keyword: vector
# % keyword: classification
# % keyword: statistics
# % keyword: worker
# %end

# %option
# % key: new_mapset
# % type: string
# % required: yes
# % multiple: no
# % key_desc: name
# % description: Name for new mapset
# %end

# %option G_OPT_V_INPUT
# % key: treecrowns
# % description: Subset vector map of tree crowns
# %end

# %option G_OPT_V_INPUT
# % key: treecrowns_complete
# % description: Complete vector map of tree crowns
# %end

# %option G_OPT_R_INPUT
# % key: ndsm
# % required: no
# % description: Name of the nDSM raster
# %end

# %option G_OPT_R_INPUT
# % key: ndvi
# % required: no
# % description: Name of the NDVI raster
# %end

# %option G_OPT_V_INPUT
# % key: buildings
# % required: no
# % description: Name of the buildings vector map
# %end

# %option
# % key: distance_building
# % type: integer
# % required: no
# % description: Range in which is searched for neighbouring buildings
# %end

# %option
# % key: distance_tree
# % type: integer
# % required: no
# % description: Range in which is searched for neighbouring trees
# %end

# %option
# % key: treeparamset
# % required:yes
# % multiple: yes
# % description: Set of tree parameters, which should be calculated
# % options: position,height,diameter,volume,area,ndvi,dist_building,dist_tree
# %end

# %option G_OPT_MEMORYMB
# %end

import os
import sys
import atexit
import math

import grass.script as grass
from grass.pygrass.utils import get_lib_path


# initialize global vars
rm_rasters = []
treetrunk_SQL_temp = None


def cleanup():
    nuldev = open(os.devnull, "w")
    kwargs = {"flags": "f", "quiet": True, "stderr": nuldev}
    for rmrast in rm_rasters:
        if grass.find_file(name=rmrast, element="cell")["file"]:
            grass.run_command("g.remove", type="raster", name=rmrast, **kwargs)
    if treetrunk_SQL_temp:
        grass.try_remove(treetrunk_SQL_temp)


def treeheight(list_attr, treecrowns, ndsm):
    # tree height:
    # The tree height can be determined via the nDSM
    # as the highest point of the crown area
    grass.message(_("Calculating tree height..."))
    col_height = "height"
    col_height_perc = f"{col_height}_p95"
    col_height_max = f"{col_height}_max"
    if col_height_perc in list_attr:
        grass.warning(
            _(
                f"Column {col_height_perc} is already included in vector map "
                f"{treecrowns} and will be overwritten."
            )
        )
        grass.run_command(
            "v.db.dropcolumn",
            map=treecrowns,
            columns=col_height_perc,
            quiet=True,
        )
    if col_height_max in list_attr:
        grass.warning(
            _(
                f"Column {col_height_max} is already included in vector map "
                f"{treecrowns} and will be overwritten."
            )
        )
        grass.run_command(
            "v.db.dropcolumn",
            map=treecrowns,
            columns=col_height_max,
            quiet=True,
        )
    # Maximum and percentile (in case of outliers)
    grass.run_command(
        "v.rast.stats",
        map=treecrowns,
        type="area",
        raster=ndsm,
        column_prefix=col_height,
        method="maximum,percentile",
        percentile=95,
        flags="c",
        quiet=True,
    )
    for rename in [
        f"{col_height}_maximum,{col_height_max}",
        f"{col_height}_percentile_95,{col_height_perc}",
    ]:
        grass.run_command("v.db.renamecolumn", map=treecrowns, column=rename)
    grass.message(_("Tree height was calculated."))


def crownarea(list_attr, treecrowns):
    # Crown area:
    # The crown area is the area of the polygon,
    # identified as the crown of the tree.
    grass.message(_("Calculating crown area..."))
    col_area = "area_sqm"
    if col_area in list_attr:
        grass.warning(
            _(
                f"Column {col_area} is already included in vector map "
                f"{treecrowns} and will be overwritten."
            )
        )
        grass.run_command(
            "v.db.dropcolumn", map=treecrowns, columns=col_area, quiet=True
        )
    grass.run_command(
        "v.to.db", map=treecrowns, option="area", columns=col_area, quiet=True
    )
    grass.message(_("Crown area was calculated."))


def crowndiameter(list_attr, treecrowns):
    # Crown diameter:
    # Crown diameter can be determined in two ways:
    # once as the diameter of a circle,
    # with the same area as the crown area,
    # once as the largest extension of the bounding box of the crown area,
    # if this area deviates strongly from a circular shape.
    # NOTE: can be extended with other/additional methods for diameter
    # currently implemented only as diameter of a circle
    grass.message(_("Calculating crown diameter..."))
    col_diameter = "diameter"
    if col_diameter in list_attr:
        grass.warning(
            _(
                f"Column {col_diameter} is already included in vector map "
                f"{treecrowns} and will be overwritten."
            )
        )
        grass.run_command(
            "v.db.dropcolumn", map=treecrowns, columns=col_diameter, quiet=True
        )
    grass.run_command(
        "v.to.db",
        map=treecrowns,
        option="area",
        columns=col_diameter,
        quiet=True,
    )
    # Assumption of a circle
    grass.run_command(
        "v.db.update",
        map=treecrowns,
        column=col_diameter,
        query_column=f"2*(sqrt({col_diameter}/{math.pi}))",
    )
    grass.message(_("Crown diameter was calculated."))
    return col_diameter


def ndvi_singletree(list_attr, treecrowns, ndvi):
    # NDVI from color information per single tree:
    # For each pixel a NDVI value can be calculated from the aerial images.
    # The NDVI of a single tree results as mean or median value
    # of all pixels of a crown area (zonal statistics).
    grass.message(_("Calculating NDVI per single tree..."))
    col_ndvi = "ndvi"
    col_ndvi_ave = f"{col_ndvi}_av"
    col_ndvi_med = f"{col_ndvi}_med"
    if col_ndvi_ave in list_attr:
        grass.warning(
            _(
                f"Column {col_ndvi_ave} is already included in vector map "
                f"{treecrowns} and will be overwritten."
            )
        )
        grass.run_command(
            "v.db.dropcolumn",
            map=treecrowns,
            columns=f"{col_ndvi_ave}",
            quiet=True,
        )
    if col_ndvi_med in list_attr:
        grass.warning(
            _(
                f"Column {col_ndvi_med} is already included in vector map "
                f"{treecrowns} and will be overwritten."
            )
        )
        grass.run_command(
            "v.db.dropcolumn",
            map=treecrowns,
            columns=f"{col_ndvi_med}",
            quiet=True,
        )
    grass.run_command(
        "v.rast.stats",
        map=treecrowns,
        type="area",
        raster=ndvi,
        column_prefix=col_ndvi,
        method="average,median",
        quiet=True,
        flags="c",
    )
    for attr_old, attr_new in zip(
        [f"{col_ndvi}_average", f"{col_ndvi}_median"],
        [col_ndvi_ave, col_ndvi_med],
    ):
        grass.run_command(
            "v.db.renamecolumn",
            map=treecrowns,
            column=f"{attr_old},{attr_new}",
        )
        # rescale from [0, 255] to [-1, 1]
        grass.run_command(
            "v.db.update",
            map=treecrowns,
            column=attr_new,
            query_column=f"{attr_new}/127.5-1.",
        )
    grass.message(_("NDVI per single tree was calculated."))


def crownvolume(list_attr, treecrowns, col_diameter):
    # Crown volume:
    # Accurate measurement of crown volume requires a true 3D model of the
    # tree crown. Alternatively, a sphere can be assumed as the crown shape
    # and the volume can be calculated using the known diameter.
    # The crown volume can be calculated slightly differently depending on
    # the tree species (distinguishing deciduous and coniferous trees).
    # NOTE: can be extended to include other methodologies.
    # (e.g. distinction deciduous and coniferous tree).
    grass.message(_("Calculating crown volume..."))
    col_volume = "volume"
    if col_volume in list_attr:
        grass.warning(
            _(
                f"Column {col_volume} is already included in vector "
                f"map {treecrowns} and will be overwritten."
            )
        )
    else:
        grass.run_command(
            "v.db.addcolumn",
            map=treecrowns,
            columns=f"{col_volume} double precision",
        )
    # Assumption: Circular volume
    grass.run_command(
        "v.db.update",
        map=treecrowns,
        column=col_volume,
        query_column=f"(4./3.)*{math.pi}*"
        f"({col_diameter}/2.)*"
        f"({col_diameter}/2.)*"
        f"({col_diameter}/2.)",
    )
    grass.message(_("Crown volume was calculated."))


def treetrunk(list_attr, treecrowns):
    # Tree trunk position:
    # aerial photographs and normalized digital object models derived from them
    # cannot depict the trunk itself,
    # as it is obscured by the canopy when viewed from above.
    # The trunk position can be calculated from the tree canopy area
    # with the center of mass or the centroid.
    # Alternatively, the highest point of the tree canopy area
    # can be used as an estimate of the trunk position.
    grass.message(_("Calculating tree trunk position..."))
    # Centroid as tree trunk position
    # Created with Vect_get_point_in_area which gets the point inside area and
    # outside all islands (from the largest IN segment the midpoint is taken).
    col_sp_cent = "pos_rand"
    if f"{col_sp_cent}_x" in list_attr:
        grass.warning(
            _(
                f"Column {col_sp_cent}_x is already included in vector map "
                f"{treecrowns} and will be overwritten."
            )
        )
        grass.run_command(
            "v.db.dropcolumn",
            map=treecrowns,
            columns=f"{col_sp_cent}_x",
            quiet=True,
        )
    if f"{col_sp_cent}_y" in list_attr:
        grass.warning(
            _(
                f"Column {col_sp_cent}_y is already included in vector map "
                f"{treecrowns} and will be overwritten."
            )
        )
        grass.run_command(
            "v.db.dropcolumn",
            map=treecrowns,
            columns=f"{col_sp_cent}_y",
            quiet=True,
        )
    grass.run_command(
        "v.to.db",
        map=treecrowns,
        type="centroid",
        option="coor",
        columns=[f"{col_sp_cent}_x", f"{col_sp_cent}_y"],
        quiet=True,
    )
    # Center of mass (calculated with surface triangulation)
    # as tree trunk position
    v_centerpoints_mean = list(
        grass.parse_command(
            "v.centerpoint",
            input=treecrowns,
            type="area",
            acenter="mean",
            quiet=True,
        ).keys()
    )
    col_sp_mean = "pos_mass"
    if f"{col_sp_mean}_x" in list_attr:
        grass.warning(
            _(
                f"Column {col_sp_mean} is already included in vector "
                f"map {treecrowns} and will be overwritten."
            )
        )
    else:
        grass.run_command(
            "v.db.addcolumn",
            map=treecrowns,
            columns=[
                f"{col_sp_mean}_x double precision",
                f"{col_sp_mean}_y double precision",
            ],
            quiet=True,
        )
    # Create SQL file:
    treetrunk_SQL_temp = grass.tempfile()
    with open(treetrunk_SQL_temp, "w") as sql_file:
        for el in v_centerpoints_mean:
            el_cat = el.split("|")[-1]
            el_x = el.split("|")[0]
            el_y = el.split("|")[1]
            sql_line = (
                f"UPDATE {treecrowns} SET {col_sp_mean}_x={el_x},"
                f" {col_sp_mean}_y={el_y} WHERE cat={el_cat};"
            )
            sql_file.write(f"{sql_line}\n")
    grass.run_command("db.execute", input=treetrunk_SQL_temp, quiet=True)
    grass.message(_("Tree trunk position was calculated."))


def dist_to_building(list_attr, treecrowns, buildings, distance_building):
    # Distance to buildings:
    # The location of buildings can be obtained from ALKIS or OSM data.
    # For each tree or tree crown, the distance to the nearest
    # (minimized direct distance) building can be calculated.
    grass.message(_("Calculating distance to nearest building..."))
    # NOTE: in case of intersection of treecrowns and buildings,
    #       the distance is set to zero (v.distance)
    # Note to "from"-argument of v.distance:
    #   from is a Python "​keyword". This means that the Python parser
    #   does not allow them to be used as identifier names (functions, classes,
    #   variables, parameters etc).
    #   If memory serves, when a module argument/option is a Python keyword,
    #   then the python wrapper appends an underscore to its name.
    #   I.e. you need to replace from with from_
    col_dist_buildings = "dist_bu"
    if col_dist_buildings in list_attr:
        grass.warning(
            _(
                f"Column {col_dist_buildings} is already included in vector "
                f"map {treecrowns} and will be overwritten."
            )
        )
        grass.run_command(
            "v.db.dropcolumn",
            map=treecrowns,
            columns=col_dist_buildings,
            quiet=True,
        )
    grass.run_command(
        "v.db.addcolumn",
        map=treecrowns,
        columns=f"{col_dist_buildings} double precision",
        quiet=True,
    )
    param = {
        "from_": treecrowns,
        "to": buildings,
        "upload": "dist",
        "column": col_dist_buildings,
        "quiet": True,
        "overwrite": True,
    }
    if distance_building:
        param["dmax"] = distance_building
    grass.run_command("v.distance", **param)
    grass.message(_("Distance to nearest building was calculated."))


def dist_to_tree(
    list_attr, treecrowns, treecrowns_complete, pid, distance_tree
):
    # Distance to nearest tree:
    # For given crown areas, the distance to the nearest other crown area
    # can be determined for each crown area.
    grass.message(_("Calculating distance to nearest tree..."))
    # set region to tree-subset with buffer, to ensure
    # all neighbouring trees (within buffer) are rasterized in the next step
    grass.run_command(
        "g.region",
        vector=treecrowns,
    )
    # distance_tree given in meters,
    # to be consistent with distance_building;
    # must be converted to cells for g.regionn
    nsres = grass.parse_command("g.region", flags="m")["nsres"]
    distance_tree_cells = math.ceil(float(distance_tree) / float(nsres))
    grass.run_command(
        "g.region",
        grow=distance_tree_cells,
    )
    treecrowns_rast = f"treecrowns_rast_{pid}"
    rm_rasters.append(treecrowns_rast)
    # use complete treecrown vector map (not only subset)
    # to ensure using ALL neighbours
    grass.run_command(
        "v.to.rast",
        input=treecrowns_complete,
        output=treecrowns_rast,
        use="cat",
        quiet=True,
    )
    treecrowns_cat = [
        int(val)
        for val in list(
            grass.parse_command(
                "v.db.select", map=treecrowns, columns="cat", flags="c"
            ).keys()
        )
    ]
    treecrowns_complete_cat = [
        int(val)
        for val in list(
            grass.parse_command(
                "v.db.select",
                map=treecrowns_complete,
                columns="cat",
                flags="c",
            ).keys()
        )
    ]
    col_dist_trees = "dist_tree"
    if col_dist_trees in list_attr:
        grass.warning(
            _(
                f"Column {col_dist_trees} is already included in vector "
                f"map {treecrowns} and will be overwritten."
            )
        )
        grass.run_command(
            "v.db.dropcolumn",
            map=treecrowns,
            columns=col_dist_trees,
            quiet=True,
        )
    grass.run_command(
        "v.db.addcolumn",
        map=treecrowns,
        columns=f"{col_dist_trees} double precision",
        quiet=True,
    )
    grass.message(
        _(f"Calculating distance for {len(treecrowns_cat)} trees...")
    )
    for cat in treecrowns_cat:
        # create two maps for each cat-value:
        # one with cat-value-polygon ONLY
        # one with all BUT cat-value-polygon
        # then calculate this with r.distance min distance
        map_cat_only = f"map_cat_{cat}_only_{pid}"
        rm_rasters.insert(
            0, map_cat_only
        )  # insert instead of append to rm_rasters, because they
        # have to be deleted before base map treecrowns_rast in cleanup
        rules_cat_only = f"{cat}={cat}"
        grass.write_command(
            "r.reclass",
            input=treecrowns_rast,
            output=map_cat_only,
            rules="-",
            stdin=rules_cat_only.encode(),
            quiet=True,
        )
        # for distance to other trees, set region smaller
        # with option: distance_tree
        grass.run_command(
            "g.region",
            zoom=map_cat_only,
        )
        grass.run_command(
            "g.region",
            grow=distance_tree_cells,
        )
        map_all_but_cat = f"map_all_but_cat_{cat}_{pid}"
        rm_rasters.insert(0, map_all_but_cat)
        rules_all_but_cat = (
            f"1 thru {max(treecrowns_complete_cat)} = "
            f"{int(cat)+1}\n {cat} = NULL"
        )
        grass.write_command(
            "r.reclass",
            input=treecrowns_rast,
            output=map_all_but_cat,
            rules="-",
            stdin=rules_all_but_cat.encode(),
            quiet=True,
        )
        try:
            rdist_out = list(
                grass.parse_command(
                    "r.distance",
                    map=f"{map_cat_only},{map_all_but_cat}",
                    quiet=True,
                ).keys()
            )[0]
            # Subtract resolution so that adjacent trees have distance 0;
            # distance is then no longer from cell center to cell center
            # (this is how distance is defined for r.distance),
            # but from tree crown edge to tree crown edge
            rdist_dist = float(rdist_out.split(":")[2]) - float(nsres)
            if rdist_dist < 0:
                rdist_dist = 0
        except IndexError:
            rdist_dist = "NULL"
        # remove temporary maps already here, to avoid filling up the mapset
        nuldev = open(os.devnull, "w")
        kwargs = {"flags": "f", "quiet": True, "stderr": nuldev}
        for rmrast in [map_cat_only, map_all_but_cat]:
            if grass.find_file(name=rmrast, element="cell")["file"]:
                grass.run_command(
                    "g.remove", type="raster", name=rmrast, **kwargs
                )
        # Set region back, for next iteration
        grass.run_command("g.region", vector=treecrowns)
        grass.run_command(
            "v.db.update",
            map=treecrowns,
            column=col_dist_trees,
            where=f"cat == {cat}",
            value=rdist_dist,
            quiet=True,
        )
    grass.message(_("Distance to nearest tree was calculated."))


def main():
    global rm_rasters, treetrunk_SQL_temp

    pid = os.getpid()

    treecrowns = options["treecrowns"]
    treecrowns_complete = options["treecrowns_complete"]
    ndsm = options["ndsm"]
    ndvi = options["ndvi"]
    buildings = options["buildings"]
    distance_building = options["distance_building"]
    distance_tree = options["distance_tree"]
    treeparamset = options["treeparamset"]
    memory = int(options["memory"])
    new_mapset = options["new_mapset"]

    path = get_lib_path(modname="m.analyse.trees", libname="analyse_trees_lib")
    if path is None:
        grass.fatal("Unable to find the analyse trees library directory.")
    sys.path.append(path)
    try:
        from analyse_trees_lib import (
            freeRAM,
            switch_to_new_mapset,
        )
    except Exception:
        grass.fatal("analyse_trees_lib missing.")

    # Test memory settings
    free_ram = freeRAM("MB", 100)
    if free_ram < memory:
        grass.warning(
            "Using %d MB but only %d MB RAM available." % (memory, free_ram)
        )

    # switch to another mapset for parallel postprocessing
    gisrc, newgisrc, old_mapset = switch_to_new_mapset(new_mapset)
    # create fully qualified names
    if "height" in treeparamset:
        if "@" not in ndsm:
            ndsm = f"{ndsm}@{old_mapset}"
        if not grass.find_file(name=ndsm, element="cell")["file"]:
            grass.fatal(_(f"Input map <{ndsm}> not available!"))
    if "ndvi" in treeparamset:
        if "@" not in ndvi:
            ndvi = f"{ndvi}@{old_mapset}"
        if not grass.find_file(name=ndvi, element="cell")["file"]:
            grass.fatal(_(f"Input map <{ndvi}> not available!"))
    if "dist_building" in treeparamset:
        if "@" not in buildings:
            buildings = f"{buildings}@{old_mapset}"
        if not grass.find_file(name=buildings, element="vector")["file"]:
            grass.fatal(_(f"Input map <{buildings}> not available!"))
    if "@" not in treecrowns_complete:
        treecrowns_complete = f"{treecrowns_complete}@{old_mapset}"
    if not grass.find_file(name=treecrowns_complete, element="vector")["file"]:
        grass.fatal(_(f"Input map <{treecrowns_complete}> not available!"))

    # need vector map in current mapset, for some GRASS modules
    # (e.g. v.rast.stats)
    grass.run_command(
        "g.copy", vector=f"{treecrowns}@{old_mapset},{treecrowns}"
    )

    # set correct extension
    grass.run_command("g.region", vector=treecrowns, flags="ap")

    # List of attribute columns of single tree vector map
    list_attr = [
        el.split("|")[1]
        for el in list(
            grass.parse_command("v.info", map=treecrowns, flags="c").keys()
        )
    ]

    # Calculate various tree parameters
    if not treeparamset or "height" in treeparamset:
        treeheight(list_attr, treecrowns, ndsm)
    if not treeparamset or "area" in treeparamset:
        crownarea(list_attr, treecrowns)
    if (
        not treeparamset
        or "diameter" in treeparamset
        or "volume" in treeparamset
    ):
        col_diameter = crowndiameter(list_attr, treecrowns)
    if not treeparamset or "ndvi" in treeparamset:
        ndvi_singletree(list_attr, treecrowns, ndvi)
    if not treeparamset or "volume" in treeparamset:
        crownvolume(list_attr, treecrowns, col_diameter)
    if not treeparamset or "position" in treeparamset:
        treetrunk(list_attr, treecrowns)
    if not treeparamset or "dist_building" in treeparamset:
        dist_to_building(list_attr, treecrowns, buildings, distance_building)
    if not treeparamset or "dist_tree" in treeparamset:
        dist_to_tree(
            list_attr, treecrowns, treecrowns_complete, pid, distance_tree
        )

    # set GISRC to original gisrc and delete newgisrc
    os.environ["GISRC"] = gisrc
    grass.utils.try_remove(newgisrc)
    grass.message(
        _(f"Calculation of tree parameter for subset {treecrowns} DONE")
    )


if __name__ == "__main__":
    options, flags = grass.parser()
    atexit.register(cleanup)
    main()
