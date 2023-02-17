#!/usr/bin/env python3

############################################################################
#
# MODULE:       v.trees.species
#
# AUTHOR(S):    Anika Weinmann
#
# PURPOSE:      Classifies trees in deciduous and conifer trees
#
# COPYRIGHT:    (C) 2023 by mundialis and the GRASS Development Team
#
#       This program is free software under the GNU General Public
#       License (>=v2). Read the file COPYING that comes with GRASS
#       for details.
#
#############################################################################

# %Module
# % description: Classifies trees in deciduous and conifer trees.
# % keyword: raster
# % keyword: statistics
# % keyword: classification
# %end

# %option G_OPT_R_INPUT
# % key: red_raster
# % required: yes
# % label: Name of the NIR raster
# %end

# %option G_OPT_R_INPUT
# % key: green_raster
# % required: yes
# % label: Name of the green band
# %end

# %option G_OPT_R_INPUT
# % key: blue_raster
# % required: yes
# % label: Name of the blue band
# %end

# %option G_OPT_V_INPUT
# % key: treecrowns
# % description: Vector map of tree crowns
# % required: yes
# %end

# %option
# % key: brightness_threshold
# % type: double
# % required: no
# % label: define brightness threshold for the distinction between deciduous and conifer trees
# % answer: 125
# %end

# %option
# % key: ratio_threshold
# % type: double
# % required: no
# % label: define brightness ratio threshold for the distinction between deciduous and conifer trees
# % answer: 0.3
# %end

# %option G_OPT_M_NPROCS
# % description: Number of cores for multiprocessing, -2 is the number of available cores - 1
# % answer: -2
# %end

# %option G_OPT_MEMORYMB
# % description: Memory which is used by all processes (it is divided by nprocs for each single parallel process)
# %end


import atexit
import os
import sys
import grass.script as grass
from grass.pygrass.utils import get_lib_path

# initialize global vars
rm_rasters = []
rm_cols = []


def cleanup():
    nuldev = open(os.devnull, "w")
    kwargs = {"flags": "f", "quiet": True, "stderr": nuldev}
    for rmrast in rm_rasters:
        if grass.find_file(name=rmrast, element="raster")["file"]:
            grass.run_command("g.remove", type="raster", name=rmrast, **kwargs)
    trees = options["treecrowns"]
    trees_attr = grass.vector_columns(trees).keys()
    del_cols = list()
    for rmcol in rm_cols:
        if rmcol in trees_attr:
            del_cols.append(rmcol)
    if len(rm_cols) > 0 and len(del_cols) > 0:
        grass.run_command(
            "v.db.dropcolumn",
            map=trees,
            columns=del_cols,
            quiet=True,
        )


def main():
    global rm_rasters, rm_cols

    path = get_lib_path(modname="m.analyse.trees", libname="analyse_trees_lib")
    if path is None:
        grass.fatal("Unable to find the analyse trees library directory")
    sys.path.append(path)
    try:
        from analyse_trees_lib import set_nprocs, test_memory
    except Exception:
        grass.fatal("analyse_trees_lib missing.")

    treecrowns = options["treecrowns"]
    green = options["green_raster"]
    blue = options["blue_raster"]
    red = options["red_raster"]
    thres = options["brightness_threshold"]
    ratio_thres = options["ratio_threshold"]
    nprocs = set_nprocs(int(options["nprocs"]))
    memory = test_memory(options["memory"])

    grass.message(_("Classifying deciduous and conifer trees ..."))
    brightness = grass.tempname(12)
    rm_rasters.append(brightness)
    grass.mapcalc(f"{brightness} = round(({red} + {green} + {blue})/3.0)")
    brightness_neighbors_med = grass.tempname(12)
    rm_rasters.append(brightness_neighbors_med)
    grass.run_command(
        "r.neighbors",
        input=brightness,
        output=brightness_neighbors_med,
        method="median",
        memory=memory,
        nprocs=nprocs,
        size=7,
        quiet=True,
    )
    brightness_med_thres = grass.tempname(12)
    rm_rasters.append(brightness_med_thres)
    grass.mapcalc(
        f"{brightness_med_thres} = if({brightness_neighbors_med} > {thres}, "
        "1, null() )"
    )
    rm_cols.append("b_thres_number")
    rm_cols.append("b_thres_null_cells")
    grass.run_command(
        "v.rast.stats",
        map=treecrowns,
        raster=brightness_med_thres,
        method="number,null_cells",
        column_prefix="b_thres",
        quiet=True,
    )
    rm_cols.append("b_thres_ratio")
    grass.run_command(
        "v.db.addcolumn",
        map=treecrowns,
        columns="b_thres_ratio DOUBLE PRECISION,speciesINT INTEGER,"
        "species VARCHAR",
        quiet=True,
    )
    grass.run_command(
        "v.db.update",
        map=treecrowns,
        column="b_thres_ratio",
        query_column="b_thres_number / (b_thres_number + b_thres_null_cells)",
        quiet=True,
    )
    grass.run_command(
        "v.db.update",
        map=treecrowns,
        column="speciesINT",
        value=1,  # deciduous tree
        where=f"b_thres_ratio < {ratio_thres}",
        quiet=True,
    )
    grass.run_command(
        "v.db.update",
        map=treecrowns,
        column="speciesINT",
        value=2,  # conifer tree
        where=f"b_thres_ratio >= {ratio_thres}",
        quiet=True,
    )
    grass.run_command(
        "v.db.update",
        map=treecrowns,
        column="species",
        value="deciduous",
        where=f"b_thres_ratio < {ratio_thres}",
        quiet=True,
    )
    grass.run_command(
        "v.db.update",
        map=treecrowns,
        column="species",
        value="conifer",
        where=f"b_thres_ratio >= {ratio_thres}",
        quiet=True,
    )

    grass.message(
        _(
            "Classifying deciduous and conifer trees done. Added tree species"
            " columns: <species> and <speciesINT>."
        )
    )


if __name__ == "__main__":
    options, flags = grass.parser()
    atexit.register(cleanup)
    main()
