#!/usr/bin/env python3

############################################################################
#
# MODULE:       v.trees.species
#
# AUTHOR(S):    Anika Weinmann
#
# PURPOSE:      Classifies trees in deciduous and coniferous trees
#
# COPYRIGHT:    (C) 2023 by mundialis and the GRASS Development Team
#
#       This program is free software under the GNU General Public
#       License (>=v2). Read the file COPYING that comes with GRASS
#       for details.
#
#############################################################################

# %Module
# % description: Classifies trees in deciduous and coniferous trees.
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

# %option G_OPT_R_INPUT
# % key: nir_raster
# % required: yes
# % label: Name of the NIR band
# %end

# %option G_OPT_R_INPUT
# % key: ndvi
# % required: yes
# % label: Name of the NDVI raster
# %end

# %option G_OPT_R_INPUT
# % key: ndwi
# % required: no
# % label: Name of the NDWI raster
# %end

# %option G_OPT_R_INPUT
# % key: ndsm
# % required: yes
# % label: Name of the nDSM raster
# %end

# %option G_OPT_V_INPUT
# % key: treecrowns
# % description: Vector map of tree crowns
# % required: yes
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
rm_groups = []
rm_cols = []
rm_dirs = []
orig_region = None

# signature file for deciduous and coniferous tree classes generated with i.gensig
SIG_TPL = """2
#
GROUP_INP
1
#
1228884
1
153.458 104.037 112.471 86.8647 154.113 105.666 101.207 50.676
151.557
-276.121 903.074
-300.094 1050.82 1258.37
-177.708 496.09 574.509 402.016
-39.8637 630.268 793.346 282.008 827.354
-157.611 338.284 392.058 209.187 119.993 180.041
-251.309 816.664 961.235 490.869 568.543 313.178 756.338
-26.3307 11.8829 7.53811 6.99278 -43.2813 22.6544 8.8078 207.928
#
234426
2
140.476 114.589 123.256 95.8778 137.706 118.511 111.324 58.7915
143.751
-276.029 1155.04
-295.199 1322.1 1536.92
-202.776 662.4 764.167 534.241
-49.3205 833.796 1002.58 372.967 920.51
-147.281 340.369 381.736 242.21 123.408 162.629
-258.009 1046.56 1207.78 653.627 736.488 321.448 969.445
7.58959 -4.76423 -6.83861 -31.0306 6.9694 -9.01781 -14.213 148.679
"""


def cleanup():
    try:
        from analyse_trees_lib import reset_region
    except Exception:
        grass.fatal("analyse_trees_lib missing.")
    nulldev = open(os.devnull, "w")
    kwargs = {"flags": "f", "quiet": True, "stderr": nulldev}
    for rmrast in rm_rasters:
        if grass.find_file(name=rmrast, element="cell")["file"]:
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
    if orig_region is not None:
        reset_region(orig_region)
    for rmdir in rm_dirs:
        if os.path.isdir(rmdir):
            grass.try_rmdir(rmdir)
    for rmgroup in rm_groups:
        if grass.find_file(name=rmgroup, element="group")["file"]:
            grass.run_command("g.remove", type="group", name=rmgroup, **kwargs)


def main():
    global rm_rasters, rm_groups, rm_cols, orig_region, rm_dirs

    path = get_lib_path(modname="m.analyse.trees", libname="analyse_trees_lib")
    if path is None:
        grass.fatal("Unable to find the analyse trees library directory")
    sys.path.append(path)
    try:
        from analyse_trees_lib import reset_region, set_nprocs, test_memory
    except Exception:
        grass.fatal("analyse_trees_lib missing.")

    treecrowns = options["treecrowns"]
    green = options["green_raster"]
    blue = options["blue_raster"]
    red = options["red_raster"]
    nir = options["nir_raster"]
    ndvi = options["ndvi"]
    ndwi = options["ndwi"]
    ndsm = options["ndsm"]
    nprocs = set_nprocs(int(options["nprocs"]))
    memory = test_memory(options["memory"])

    tmp_name = grass.tempname(12)

    # save orignal region
    orig_region = f"orig_region_{tmp_name}"
    grass.run_command("g.region", save=orig_region, quiet=True)

    grass.message(_("Computing brightness ..."))
    brightness = f"brightness_{tmp_name}"
    rm_rasters.append(brightness)
    grass.mapcalc(f"{brightness} = round(({red} + {green} + {blue})/3.0)")

    grass.message(_("Resample nDSM ..."))
    grass.run_command("g.region", res=1, flags="a")
    ndsm_med = f"ndsm_med_{tmp_name}"
    rm_rasters.append(ndsm_med)
    grass.run_command(
        "r.resamp.stats",
        input=ndsm,
        output=ndsm_med,
        method="median",
        quiet=True,
    )
    grass.message(_("Computing nDSM slope ..."))
    ndsm_med_slope = f"ndsm_med_slope_{tmp_name}"
    rm_rasters.append(ndsm_med_slope)
    grass.run_command(
        "r.slope.aspect",
        elevation=ndsm_med,
        slope=ndsm_med_slope,
        memory=memory,
        nprocs=nprocs,
        quiet=True,
    )
    grass.message(_("Computing nDSM slope median in neighboring pixels ..."))
    ndsm_med_slope_n7 = f"ndsm_med_slope_n7_{tmp_name}"
    rm_rasters.append(ndsm_med_slope_n7)
    grass.run_command(
        "r.neighbors",
        input=ndsm_med_slope,
        output=ndsm_med_slope_n7,
        size=7,
        method="median",
        memory=memory,
        nprocs=nprocs,
        quiet=True,
    )
    reset_region(orig_region)

    if not ndwi:
        grass.message(_("Computing NDWI ..."))
        ndwi = f"ndwi_{tmp_name}"
        rm_rasters.append(ndwi)
        grass.mapcalc(
            f"{ndwi} = round(255 * (1.0 + ( float({green} - {nir})/"
            f"({green} + {nir}) ))/2)"
        )

    grass.message(_("Classifying deciduous and coniferous trees ..."))
    classification_group = f"classification_group_{tmp_name}"
    rm_groups.append(classification_group)
    grass.run_command(
        "i.group",
        group=classification_group,
        subgroup=classification_group,
        input=f"{ndvi},{red},{green},{blue},{nir},{ndwi},{brightness}"
        f",{ndsm_med_slope_n7}",
        quiet=True,
    )
    class_ln = f"class_ln_{tmp_name}"
    rm_rasters.append(class_ln)
    # create signature file
    sig_name = f"sig_tree_species_{tmp_name}"
    gisenv = grass.parse_command("g.gisenv", flags="n")
    sig_file_dest = os.path.join(
        gisenv["GISDBASE"],
        gisenv["LOCATION_NAME"],
        gisenv["MAPSET"],
        "signatures",
        "sig",
        sig_name,
        "sig",
    )
    sig_dir = os.path.dirname(sig_file_dest)
    rm_dirs.append(sig_dir)
    os.makedirs(sig_dir)
    group_inp = (
        f"{ndvi} {red} {green} {blue} {nir} {ndwi} {brightness}"
        f" {ndsm_med_slope_n7}"
    )
    with open(sig_file_dest, "w") as file:
        file.write(SIG_TPL.replace("GROUP_INP", group_inp))
    grass.run_command(
        "i.maxlik",
        group=classification_group,
        subgroup=classification_group,
        signaturefile=sig_name,
        output=class_ln,
        quiet=True,
    )
    class_ln_col_prefix = f"class_ln_{tmp_name}"
    class_ln_col_sum = f"{class_ln_col_prefix}_sum"
    class_ln_col_number = f"{class_ln_col_prefix}_number"
    rm_cols.append(class_ln_col_sum)
    rm_cols.append(class_ln_col_number)
    grass.run_command(
        "v.rast.stats",
        map=treecrowns,
        raster=class_ln,
        method="number,sum",
        column_prefix=class_ln_col_prefix,
        quiet=True,
    )
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
        column="speciesINT",
        query_column=f"round({class_ln_col_sum} / ({class_ln_col_number}))",
        quiet=True,
    )
    grass.run_command(
        "v.db.update",
        map=treecrowns,
        column="species",
        value="deciduous",  # Laubbaum
        where="speciesINT == 1",
        quiet=True,
    )
    grass.run_command(
        "v.db.update",
        map=treecrowns,
        column="species",
        value="coniferous",  # Nadelbaum
        where="speciesINT == 2",
        quiet=True,
    )

    grass.message(
        _(
            "Classifying deciduous and coniferous trees done. Added tree species"
            " columns: <species> and <speciesINT>."
        )
    )


if __name__ == "__main__":
    options, flags = grass.parser()
    atexit.register(cleanup)
    main()
