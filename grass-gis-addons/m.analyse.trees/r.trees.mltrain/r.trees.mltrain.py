#!/usr/bin/env python3

############################################################################
#
# MODULE:       r.trees.mltrain
#
# AUTHOR(S):    Markus Metz, Lina Krisztian, Guido Riembauer, Victoria-Leandra Brunn
#
# PURPOSE:      Trains a random forest model for tree detection
#
# COPYRIGHT:    (C) 2023 - 2024 by mundialis and the GRASS Development Team
#
#       This program is free software under the GNU General Public
#       License (>=v2). Read the file COPYING that comes with GRASS
#       for details.
#
#############################################################################

# %Module
# % description: Trains a random forest model for tree detection.
# % keyword: raster
# % keyword: classification
# % keyword: statistics
# % keyword: machine learning
# % keyword: trees analysis
# %end

# %option G_OPT_R_INPUT
# % key: red_raster
# % label: Name of the red raster
# % answer: top_red_02
# % guisection: Input
# %end

# %option G_OPT_R_INPUT
# % key: green_raster
# % label: Name of the green raster
# % answer: top_green_02
# % guisection: Input
# %end

# %option G_OPT_R_INPUT
# % key: blue_raster
# % label: Name of the blue raster
# % answer: top_blue_02
# % guisection: Input
# %end

# %option G_OPT_R_INPUT
# % key: nir_raster
# % label: Name of the NIR raster
# % answer: top_nir_02
# % guisection: Input
# %end

# %option G_OPT_R_INPUT
# % key: nearest_pixel_ndvi
# % label: raster with trees identified by NDVI value
# % required: no
# % answer: nearest_pixel_ndvi
# % guisection: Input
# %end

# %option G_OPT_R_INPUT
# % key: nearest
# % label: Name of raster with nearest peak IDs
# % required: no
# % answer: nearest_tree
# % guisection: Input
# %end

# %option
# % key: ndvi_threshold
# % type: double
# % required: no
# % label: NDVI threshold for potential trees
# % answer: 130
# % guisection: Parameters
# %end

# %option G_OPT_R_INPUT
# % key: ndvi_raster
# % label: Name of the NDVI raster
# % answer: top_ndvi_02
# % guisection: Input
# %end

# %option G_OPT_R_INPUT
# % key: ndsm
# % label: Name of the nDSM raster
# % answer: ndsm
# % guisection: Input
# %end

# %option G_OPT_R_INPUT
# % key: slope
# % label: Name of the nDSM slope raster
# % answer: ndsm_slope
# % guisection: Input
# %end

# %option G_OPT_R_INPUT
# % key: ndwi_raster
# % required: no
# % label: Name of the NDWI raster
# % guisection: Optional input
# %end

# %option G_OPT_R_INPUT
# % key: ndgb_raster
# % required: no
# % label: Name of the normalized green-blue difference raster
# % guisection: Optional input
# %end

# %option G_OPT_R_INPUT
# % key: trees_raw_r
# % required: no
# % label: Name of the preliminary tree map raster
# % guisection: Input
# %end

# %option G_OPT_V_INPUT
# % key: trees_raw_v
# % required: no
# % label: Name of the preliminary tree map vector
# % guisection: Input
# %end

# %option
# % key: num_samples
# % type: integer
# % required: no
# % label: Number of sample points for each class in training
# % guisection: Optional input
# %end

# %option
# % key: group
# % type: string
# % required: yes
# % gisprompt: new,group,group
# % label: Name of output imagery group
# % answer: ml_input
# % guisection: Output
# %end

# %option G_OPT_F_OUTPUT
# % key: save_model
# % label: Save model to file (for compression use e.g. '.gz' extension)
# % description: Name of file to store model results using python joblib
# % answer: ml_trees_randomforest.gz
# % guisection: Output
# %end

# %option G_OPT_M_NPROCS
# % label: Number of cores for multiprocessing, -2 is the number of available cores - 1
# % answer: -2
# % guisection: Parallel processing
# %end

# %option G_OPT_MEMORYMB
# % guisection: Parallel processing
# %end

# %rules
# % exclusive: trees_raw_r,trees_raw_v
# % required: trees_raw_r,trees_raw_v
# % required: nearest_pixel_ndvi,nearest
# % excludes: nearest_pixel_ndvi,nearest,ndvi_threshold
# % requires_all: nearest,ndvi_threshold
# %end

import atexit
import os
import sys
import grass.script as grass
from grass.pygrass.utils import get_lib_path

# initialize global vars
rm_rasters = []
tmp_mask_old = None


def cleanup():
    nuldev = open(os.devnull, "w")
    kwargs = {"flags": "f", "quiet": True, "stderr": nuldev}
    for rmrast in rm_rasters:
        if grass.find_file(name=rmrast, element="cell")["file"]:
            grass.run_command("g.remove", type="raster", name=rmrast, **kwargs)
    grass.del_temp_region()


def numsamplecheck(number_samples, rastername):
    raster_samples = int(
        grass.parse_command("r.univar", map=rastername, flags="g")["n"]
    )
    if number_samples > raster_samples:
        grass.warning(
            _(
                f"The chosen number of pixels {number_samples} is exceeding the total number of ",
                f"non-null pixels in the given rastermap {rastername}. ",
                f"The number of pixels will be set to the maximal amount of {raster_samples}.",
            )
        )
        number_samples = raster_samples
    return number_samples


def main():
    global rm_rasters, tmp_mask_old

    path = get_lib_path(modname="m.analyse.trees", libname="analyse_trees_lib")
    if path is None:
        grass.fatal("Unable to find the analyse trees library directory")
    sys.path.append(path)
    try:
        from analyse_trees_lib import (
            calculate_nd,
            create_nearest_pixel_ndvi,
            set_nprocs,
            test_memory,
        )
    except Exception:
        grass.fatal("m.analyse.trees library is not installed")

    grass.message(_("Preparing input data..."))
    if grass.find_file(name="MASK", element="cell")["file"]:
        tmp_mask_old = "tmp_mask_old_%s" % os.getpid()
        grass.run_command(
            "g.rename", raster="%s,%s" % ("MASK", tmp_mask_old), quiet=True
        )

    red = options["red_raster"]
    green = options["green_raster"]
    blue = options["blue_raster"]
    nir = options["nir_raster"]
    ndvi = options["ndvi_raster"]
    ndwi = options["ndwi_raster"]
    ndgb = options["ndgb_raster"]
    ndsm = options["ndsm"]
    slope = options["slope"]
    group_name = options["group"]
    model_file = options["save_model"]
    nprocs = int(options["nprocs"])
    nearest_pixel_ndvi = options["nearest_pixel_ndvi"]
    nearest = options["nearest"]
    ndvi_threshold = options["ndvi_threshold"]

    nprocs = set_nprocs(nprocs)
    memmb = test_memory(options["memory"])
    # for some modules like r.neighbors and r.slope_aspect, there is
    # no speed gain by using more than 100 MB RAM
    memory_max100mb = 100
    if memmb < 100:
        memory_max100mb = memmb

    grass.use_temp_region()

    if not ndwi:
        ndwi = "ndwi"
        calculate_nd(green, nir, ndwi)

    if not ndgb:
        ndgb = "ndgb"
        calculate_nd(green, blue, ndgb)

    if options["trees_raw_v"]:
        trees_raw_v_rast = f"trees_raw_v_rast_{os.getpid()}"
        rm_rasters.append(trees_raw_v_rast)

        grass.run_command(
            "v.to.rast",
            input=options["trees_raw_v"],
            output=trees_raw_v_rast,
            use="value",
            value=2,
        )
        trees_basemap = trees_raw_v_rast
    else:
        trees_basemap = options["trees_raw_r"]

    # non trees
    if not grass.find_file(name=nearest_pixel_ndvi, element="cell")["file"]:
        create_nearest_pixel_ndvi(
            ndvi,
            ndvi_threshold,
            nearest,
            nprocs,
            memory_max100mb,
            rm_rasters,
            nearest_pixel_ndvi,
        )
        rm_rasters.append(nearest_pixel_ndvi)

    # false trees
    # problem areas with high NDVI like shadows on roofs, solar panels
    # trees_object_filt_large = NULL and nearest_pixel_ndvi != NULL
    grass.mapcalc(
        f"false_trees = if(isnull({nearest_pixel_ndvi}), null(), if(isnull({trees_basemap}), 1, null()))"
    )

    # other areas clearly not trees
    grass.mapcalc(
        f"notrees = if(isnull({nearest_pixel_ndvi}) && isnull({trees_basemap}), 1, null())"
    )
    rm_rasters.append("false_trees")
    rm_rasters.append("notrees")

    # extract training points
    # extract "num_samples" cells if given
    if options["num_samples"]:
        num_samples = int(options["num_samples"])

        realsamples = numsamplecheck(num_samples, trees_basemap)
        grass.run_command(
            "r.random",
            input=trees_basemap,
            raster="trees_trainpnts",
            npoints=realsamples,
            flags="s",
        )

        # false trees
        realsamples = numsamplecheck(num_samples, "false_trees")
        grass.run_command(
            "r.random",
            input="false_trees",
            raster="false_trees_trainpnts",
            npoints=realsamples,
            flags="s",
        )

        # other areas clearly not trees
        realsamples = numsamplecheck(num_samples, "notrees")
        grass.run_command(
            "r.random",
            input="notrees",
            raster="notrees_trainpnts",
            npoints=realsamples,
            flags="s",
        )
        rm_rasters.append("trees_trainpnts")
        rm_rasters.append("false_trees_trainpnts")
        rm_rasters.append("notrees_trainpnts")

        patch_list = [
            "trees_trainpnts",
            "false_trees_trainpnts",
            "notrees_trainpnts",
        ]
    else:
        patch_list = [trees_basemap, "false_trees", "notrees"]

    # patch trees, false trees and non-trees
    grass.run_command(
        "r.patch",
        input=patch_list,
        output="ml_trainpnts",
    )
    rm_rasters.append("ml_trainpnts")

    # train the model
    # see https://scikit-learn.org/stable/modules/tree.html#tips-on-practical-use
    # for tips on parameters
    ml_model = "RandomForestClassifier"
    min_samples_leaf = 5
    n_estimators = 100
    max_depth = 10

    # create group of input data for ml
    if grass.find_file(name="ml_input", element="group")["name"]:
        grass.run_command("g.remove", type="group", name="ml_input", flags="f")

    grass.run_command(
        "i.group",
        group=group_name,
        input=f"{red},{green},{blue},{nir},{ndvi},{ndwi},{ndgb},{ndsm},{slope}",
    )

    # train the model
    grass.try_remove(model_file)
    grass.run_command(
        "r.learn.train",
        group=group_name,
        training_map="ml_trainpnts",
        save_model=model_file,
        model_name=ml_model,
        cv=5,
        flags="f",
        n_jobs=2,
        min_samples_leaf=min_samples_leaf,
        n_estimators=n_estimators,
        max_depth=max_depth,
    )

    grass.message(
        _("Training of {} model for tree detection finished").format(ml_model)
    )


if __name__ == "__main__":
    options, flags = grass.parser()
    atexit.register(cleanup)
    main()
