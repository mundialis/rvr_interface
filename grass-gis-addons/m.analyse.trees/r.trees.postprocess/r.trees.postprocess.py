#!/usr/bin/env python3

############################################################################
#
# MODULE:       r.trees.postprocess
#
# AUTHOR(S):    Markus Metz, Lina Krisztian
#
# PURPOSE:      Combines tree pixel to single trees
#
# COPYRIGHT:    (C) 2023 - 2024 by mundialis and the GRASS Development Team
#
#       This program is free software under the GNU General Public
#       License (>=v2). Read the file COPYING that comes with GRASS
#       for details.
#
#############################################################################

# %Module
# % description: Combines tree pixels to single trees.
# % keyword: raster
# % keyword: classification
# % keyword: statistics
# % keyword: geomorphology
# % keyword: trees analysis
# %end

# %option G_OPT_R_INPUT
# % key: tree_pixels
# % label: Name of the tree raster
# % description: Non-tree pixels must be NULL
# % answer: tree_pixels
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
# % key: ndvi_raster
# % label: Name of the NDVI raster
# % answer: top_ndvi_02
# % guisection: Input
# %end

# %option G_OPT_R_INPUT
# % key: ndsm
# % label: Name of the NDSM raster
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
# % key: nearest
# % label: Name of raster with nearest peak IDs
# % answer: nearest_tree
# % guisection: Input
# %end

# %option G_OPT_R_INPUT
# % key: peaks
# % label: Name of raster with peaks and ridges
# % answer: tree_peaks
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

# %option
# % key: ndvi_threshold
# % type: double
# % required: yes
# % label: NDVI threshold for potential trees
# % answer: 130
# % guisection: Parameters
# %end

# %option
# % key: nir_threshold
# % type: double
# % required: yes
# % label: NIR threshold for potential trees
# % answer: 130
# % guisection: Parameters
# %end

# %option
# % key: ndsm_threshold
# % type: double
# % required: yes
# % label: nDSM threshold for potential trees
# % answer: 1
# % guisection: Parameters
# %end

# %option
# % key: slopep75_threshold
# % type: double
# % required: yes
# % label: Threshold for 75 percentile of slope for potential trees
# % answer: 70
# % guisection: Parameters
# %end

# %option
# % key: area_threshold
# % type: double
# % required: yes
# % label: Area size threshold for potential trees
# % answer: 5
# % guisection: Parameters
# %end

# %option G_OPT_R_OUTPUT
# % key: trees_raster
# % label: Name for output raster with single trees
# % answer: tree_objects
# % guisection: Output
# %end

# %option G_OPT_V_OUTPUT
# % key: trees_vector
# % label: Name for output vector with single trees
# % answer: tree_objects
# % guisection: Output
# %end

# %option G_OPT_MEMORYMB
# % guisection: Parallel processing
# %end

# %option G_OPT_M_NPROCS
# % label: Number of cores for multiprocessing, -2 is the number of available cores - 1
# % answer: -2
# % guisection: Parallel processing
# %end


import atexit
import os
import sys
import grass.script as grass
from grass.pygrass.utils import get_lib_path

# initialize global vars
rm_rasters = []
rm_vectors = []
rm_groups = []
tmp_mask_old = None


def cleanup():
    nuldev = open(os.devnull, "w")
    kwargs = {"flags": "f", "quiet": True, "stderr": nuldev}
    # reactivate potential old mask
    if tmp_mask_old:
        grass.run_command("r.mask", raster=tmp_mask_old, quiet=True)
    for rmrast in rm_rasters:
        if grass.find_file(name=rmrast, element="cell")["file"]:
            grass.run_command("g.remove", type="raster", name=rmrast, **kwargs)
    for rmv in rm_vectors:
        if grass.find_file(name=rmv, element="vector")["file"]:
            grass.run_command("g.remove", type="vector", name=rmv, **kwargs)
    for rmgroup in rm_groups:
        if grass.find_file(name=rmgroup, element="group")["file"]:
            grass.run_command("g.remove", type="group", name=rmgroup, **kwargs)
    grass.del_temp_region()


def main():
    global rm_rasters, tmp_mask_old, rm_vectors, rm_groups

    path = get_lib_path(modname="m.analyse.trees", libname="analyse_trees_lib")
    if path is None:
        grass.fatal("Unable to find the analyse trees library directory.")
    sys.path.append(path)
    try:
        from analyse_trees_lib import (
            calculate_nd,
            set_nprocs,
            test_memory,
        )
    except Exception:
        grass.fatal("analyse_trees_lib missing.")

    grass.message(_("Preparing input data..."))
    if grass.find_file(name="MASK", element="cell")["file"]:
        tmp_mask_old = "tmp_mask_old_%s" % os.getpid()
        grass.run_command(
            "g.rename", raster="%s,%s" % ("MASK", tmp_mask_old), quiet=True
        )

    tree_pixels = options["tree_pixels"]
    green = options["green_raster"]
    blue = options["blue_raster"]
    nir = options["nir_raster"]
    ndvi = options["ndvi_raster"]
    ndvi_split = ndvi.split("@")[0]
    ndwi = options["ndwi_raster"]
    ndgb = options["ndgb_raster"]
    ndsm = options["ndsm"]
    slope = options["slope"]
    nearest = options["nearest"]
    peaks = options["peaks"]
    ndvi_threshold = options["ndvi_threshold"]
    nir_threshold = options["nir_threshold"]
    ndsm_threshold = options["ndsm_threshold"]
    slopep75_threshold = options["slopep75_threshold"]
    area_threshold = options["area_threshold"]
    trees_raster = options["trees_raster"]
    trees_vector = options["trees_vector"]
    nprocs = int(options["nprocs"])

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

    # estimate trees from nearest peak IDs and various bands

    # pixel-based refinement

    # FUTURE: mode on the initial classification to change pixels that
    # do not conform to the classification of most surrounding pixels

    # cut to ndvi
    # threshold=130
    # this threshold is difficult:
    # - higher such that shadow areas are removed -> many trees are removed
    # - lower such that trees are kept -> shadow areas are kept

    # mathematical morphology: opening to remove isolated small patches of high ndvi
    grass.run_command(
        "r.neighbors",
        input=ndvi,
        output=f"{ndvi_split}_min1",
        size=3,
        method="minimum",
        nprocs=nprocs,
        memory=memory_max100mb,
    )
    grass.run_command(
        "r.neighbors",
        input=f"{ndvi_split}_min1",
        output=f"{ndvi_split}_min2",
        size=3,
        method="minimum",
        nprocs=nprocs,
        memory=memory_max100mb,
    )
    grass.run_command(
        "r.neighbors",
        input=f"{ndvi_split}_min2",
        output=f"{ndvi_split}_max1",
        size=3,
        method="maximum",
        nprocs=nprocs,
        memory=memory_max100mb,
    )
    grass.run_command(
        "r.neighbors",
        input=f"{ndvi_split}_max1",
        output=f"{ndvi_split}_max2",
        size=3,
        method="maximum",
        nprocs=nprocs,
        memory=memory_max100mb,
    )
    rm_rasters.append(f"{ndvi_split}_min1")
    rm_rasters.append(f"{ndvi_split}_min2")
    rm_rasters.append(f"{ndvi_split}_max1")
    rm_rasters.append(f"{ndvi_split}_max2")

    grass.mapcalc(
        f"trees_ml_nearest = if({tree_pixels} == 2, {nearest}, null())"
    )
    rm_rasters.append("trees_ml_nearest")
    grass.mapcalc(
        f"trees_ml_pixel_ndvi = if({ndvi_split}_max2 < {ndvi_threshold}, null(), trees_ml_nearest)"
    )
    rm_rasters.append("trees_ml_pixel_ndvi")

    # cut to nir: all pixels below 100 are not vegetation
    # removes shadows with high ndvi e.g. on roofs
    # needed
    grass.mapcalc(
        f"trees_ml_pixel_nir = if({nir} < {nir_threshold}, null(), trees_ml_pixel_ndvi)"
    )
    rm_rasters.append("trees_ml_pixel_nir")

    # cut to ndsm: all pixels below 1 meter are not tree crowns
    # needed
    grass.mapcalc(
        f"trees_ml_pixel_ndsm = if({ndsm} < {ndsm_threshold}, null(), trees_ml_pixel_nir)"
    )
    rm_rasters.append("trees_ml_pixel_ndsm")

    # fill gaps after pixel-based refinement
    # mathematical morphology: dilation
    grass.run_command(
        "r.neighbors",
        input="trees_ml_pixel_ndsm",
        output="trees_ml_pixel_filt_fill1_dbl",
        size=3,
        method="mode",
        nprocs=nprocs,
        memory=memory_max100mb,
    )
    grass.mapcalc(
        "trees_ml_pixel_filt_fill1 = round(trees_ml_pixel_filt_fill1_dbl)"
    )
    # remove large DCELL map immediately
    grass.run_command(
        "g.remove",
        type="raster",
        name="trees_ml_pixel_filt_fill1_dbl",
        flags="f",
    )
    rm_rasters.append("trees_ml_pixel_filt_fill1")
    grass.run_command(
        "r.neighbors",
        input="trees_ml_pixel_filt_fill1",
        output="trees_ml_pixel_filt_fill2_dbl",
        size=3,
        method="mode",
        nprocs=nprocs,
        memory=memory_max100mb,
    )
    grass.mapcalc(
        "trees_ml_pixel_filt_fill2 = round(trees_ml_pixel_filt_fill2_dbl)"
    )
    # remove large DCELL map immediately
    grass.run_command(
        "g.remove",
        type="raster",
        name="trees_ml_pixel_filt_fill2_dbl",
        flags="f",
    )
    rm_rasters.append("trees_ml_pixel_filt_fill2")

    # object-based refinement

    # create new clumps
    # r.clump not diagonal
    grass.run_command(
        "r.clump",
        input="trees_ml_pixel_filt_fill2",
        output="trees_ml_object_all",
    )
    rm_rasters.append("trees_ml_object_all")

    # extract peak (2), ridge (3), other (4)
    grass.mapcalc(
        f"trees_peak_ridge_other = if(isnull({peaks}), 4, if({peaks} == 2 || {peaks} == 3, {peaks}, 4))"
    )
    rm_rasters.append("trees_peak_ridge_other")

    # remove all clumps without a peak or ridge
    # needed
    grass.run_command(
        "r.stats.zonal",
        base="trees_ml_object_all",
        cover="trees_peak_ridge_other",
        output="trees_ml_object_all_min",
        method="min",
    )
    rm_rasters.append("trees_ml_object_all_min")
    grass.mapcalc(
        "trees_ml_object_all_min_filt = if(trees_ml_object_all_min > 3, null(), trees_ml_object_all)"
    )
    rm_rasters.append("trees_ml_object_all_min_filt")

    # remove low-lying objects with max(ndsm) < 3
    # needed
    grass.run_command(
        "r.stats.zonal",
        base="trees_ml_object_all_min_filt",
        cover=ndsm,
        method="max",
        output="trees_ml_object_ndsmmax",
    )
    rm_rasters.append("trees_ml_object_ndsmmax")
    grass.mapcalc(
        f"trees_ml_object_ndsm = if(trees_ml_object_ndsmmax < {ndsm_threshold}, null(), trees_ml_object_all)"
    )
    rm_rasters.append("trees_ml_object_ndsm")

    # mean NDVI per object must be > X ?
    # some effect
    grass.run_command(
        "r.stats.zonal",
        base="trees_ml_object_ndsm",
        cover=f"{ndvi_split}_max2",
        method="average",
        output="trees_ml_object_ndviavg",
    )
    rm_rasters.append("trees_ml_object_ndviavg")
    grass.mapcalc(
        f"trees_ml_object_ndvi = if(trees_ml_object_ndviavg < {ndvi_threshold}, null(), trees_ml_object_all)"
    )
    rm_rasters.append("trees_ml_object_ndvi")

    # problems
    # roofs with some vegetation
    # solar panels

    # normalized difference green-blue
    # for solar panels
    # threshold 121 removes also some trees (dark trees, trees partially shadowed by other trees)
    # r.stats.zonal base=trees_object_all cover=TOM_378000_5711000_20cm.ndgb method=average output=trees_object_ndgb

    # green: not specific enough

    # slope
    # removes bushes with a height of 3-5 meter
    # needed
    # r.stats.zonal base=trees_object_all cover=ndsm_slope method=average output=trees_object_slope_avg
    grass.run_command(
        "r.stats.quantile",
        base="trees_ml_object_ndvi",
        cover=slope,
        percentiles="75,90",
        output="trees_ml_object_slope_p75,trees_ml_object_slope_p90",
    )
    rm_rasters.append("trees_ml_object_slope_p75")
    rm_rasters.append("trees_ml_object_slope_p90")

    # threshold for slope_p75: 70
    grass.mapcalc(
        f"trees_ml_object_slope = if(trees_ml_object_slope_p75 < {slopep75_threshold}, null(), trees_ml_object_ndvi)"
    )
    rm_rasters.append("trees_ml_object_slope")

    # vectorize
    grass.run_command(
        "r.to.vect",
        input="trees_ml_object_slope",
        output="trees_ml_object_filt_all",
        type="area",
        flags="svc",
    )
    rm_vectors.append("trees_ml_object_filt_all")

    # remove small areas smaller than 5sqm
    grass.run_command(
        "v.clean",
        input="trees_ml_object_filt_all",
        output=trees_vector,
        tool="rmarea",
        threshold=area_threshold,
    )

    # rasterize again
    grass.run_command(
        "v.to.rast",
        input=trees_vector,
        output=trees_raster,
        type="area",
        use="cat",
    )

    grass.message(_("Post-processing of tree classification finished"))


if __name__ == "__main__":
    options, flags = grass.parser()
    atexit.register(cleanup)
    main()
