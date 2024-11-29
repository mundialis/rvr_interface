#!/usr/bin/env python3

############################################################################
#
# MODULE:      r.trees.thresholds
#
# AUTHOR(S):   Victoria-Leandra Brunn, Anika Weinmann
#
# PURPOSE:     Proposes thresholds for NDVI and NIR as these depend on the
#              respective flight conditions
#
# COPYRIGHT:   (C) 2024 by mundialis and the GRASS Development Team
#
#       This program is free software under the GNU General Public
#       License (>=v2). Read the file COPYING that comes with GRASS
#       for details.
#
#############################################################################

# %Module
# % description: Proposes thresholds for NDVI and NIR as these depend on the respective flight conditions.
# % keyword: raster
# % keyword: statistics
# % keyword: threshold
# % keyword: machine learning
# % keyword: trees analysis
# %end

# %option G_OPT_V_INPUT
# % key: forest
# % label: Name of the vector map with forest inside e.g. FNK
# % answer: ndsm
# % guisection: Input
# %end

# %option G_OPT_DB_COLUMN
# % key: forest_column
# % label: Name of the column in the forest vector map to filter only forest e.g. for FNK code_2020
# % guisection: Input
# % required: no
# %end

# %option
# % key: forest_values
# % label: Values of the forest_column which to select from
# % answer: 400,410,420,431,432,502
# % multiple: yes
# % guisection: Input
# % required: no
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
# % label: Name of the nDSM raster
# % answer: ndsm
# % guisection: Input
# %end

# %option
# % key: ndsm_threshold
# % type: double
# % required: yes
# % label: nDSM threshold for potential trees
# % answer: 1
# % guisection: Parameters
# %end

# %option G_OPT_M_NPROCS
# % label: Number of cores for multiprocessing, -2 is the number of available cores - 1
# % answer: -2
# % guisection: Parallel processing
# %end

# %option G_OPT_MEMORYMB
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
tmp_mask_old = None
PID = os.getpid()

def cleanup():
    nuldev = open(os.devnull, "w")
    kwargs = {"flags": "f", "quiet": True, "stderr": nuldev}
    for rmrast in rm_rasters:
        if grass.find_file(name=rmrast, element="cell")["file"]:
            grass.run_command("g.remove", type="raster", name=rmrast, **kwargs)
    for rmv in rm_vectors:
        if grass.find_file(name=rmv, element="vector")["file"]:
            grass.run_command("g.remove", type="vector", name=rmv, **kwargs)
    grass.del_temp_region()


def get_percentiles(rast, percentiles=list(range(1, 100, 1))):
    perc_out = grass.parse_command(
        "r.quantile",
        input=rast,
        percentiles=percentiles,
        quiet=True,
    )
    return {
        float(k.split(":")[1]): float(k.split(":")[2])
        for k in perc_out
    }


def main():
    global rm_rasters, tmp_mask_old, rm_vectors

    path = get_lib_path(modname="m.analyse.trees", libname="analyse_trees_lib")
    if path is None:
        grass.fatal("Unable to find the analyse trees library directory")
    sys.path.append(path)
    try:
        from analyse_trees_lib import (
            compute_ndvi_neighbors,
            set_nprocs,
            test_memory,
        )
    except Exception:
        grass.fatal("m.analyse.trees library is not installed")

    grass.message(_("Preparing input data..."))
    if grass.find_file(name="MASK", element="cell")["file"]:
        tmp_mask_old = f"tmp_mask_old_{PID}"
        grass.run_command(
            "g.rename", raster=f"MASK,{tmp_mask_old}", quiet=True
        )

    vect_map = options["forest"]
    nir = options["nir_raster"]
    ndvi = options["ndvi_raster"]
    ndsm = options["ndsm"]
    ndsm_threshold = float(options["ndsm_threshold"])
    forest_column = options["forest_column"]
    forest_values = options["forest_values"].split(",")

    nprocs = int(options["nprocs"])
    nprocs = set_nprocs(nprocs)
    memmb = test_memory(options["memory"])
    # for some modules like r.neighbors and r.slope_aspect, there is
    # no speed gain by using more than 100 MB RAM
    memory_max100mb = 100
    if memmb < 100:
        memory_max100mb = memmb

    grass.use_temp_region()

    # extract forest if "forest_column" is set
    forest = vect_map
    if forest_column:
        forest = f"foest_{PID}"
        forest_where = " or ".join([f"{forest_column}='{val}'" for val in forest_values])
        rm_vectors.append(forest)
        grass.run_command(
            "v.extract",
            input=vect_map,
            output=forest,
            where=f"{forest_where}",
            quiet=True,
        )

    # get percentile of trees in the forests over the height
    grass.run_command("g.region", vector=forest, align=nir)
    grass.run_command("r.mask", vector=forest)
    ndsm_percentiles = get_percentiles(ndsm)
    ndsm_perc = 0
    for ndsm_percentile, ndsm in ndsm_percentiles.items():
        if ndsm < ndsm_threshold:
            ndsm_perc = ndsm_percentile
        else:
            break

    # percentiles for NDVI range
    ndsm_perc_step = ndsm_perc/2. if ndsm_perc < 20 else 10
    min_perc = ndsm_perc - ndsm_perc_step
    max_perc = ndsm_perc + ndsm_perc_step
    percs = [min_perc if min_perc > 0 else 0, ndsm_perc, ndsm_perc + 1, max_perc]

    # get threshold for NDVI
    # TODO use max2 von ndvi berechnet in create_nearest_pixel_ndvi
    ndvi_neighbors = compute_ndvi_neighbors(
        ndvi, nprocs, memory_max100mb, rm_rasters
    )
    ndvi_percentiles = get_percentiles(ndvi_neighbors, percs)
    ndvi_min = ndvi_percentiles[min_perc]
    ndvi_val = (ndvi_percentiles[ndsm_perc] + ndvi_percentiles[ndsm_perc + 1]) / 2.
    ndvi_max = ndvi_percentiles[max_perc]

    # percentiles for NIR range
    ndsm_perc_step = ndsm_perc/2. if ndsm_perc < 20 else 10
    min_perc_nir = ndsm_perc
    max_perc_nir = ndsm_perc + 2 * ndsm_perc_step
    ndsm_perc_nir = ndsm_perc + 1 * ndsm_perc_step
    percs_nir = [min_perc_nir if min_perc_nir > 0 else 0, ndsm_perc_nir, ndsm_perc_nir + 1, max_perc_nir]

    # get threshold for NIR
    nir_percentiles = get_percentiles(nir, percs_nir)
    nir_min = nir_percentiles[min_perc_nir]
    nir_val = (nir_percentiles[ndsm_perc_nir] + nir_percentiles[ndsm_perc_nir + 1]) / 2.
    nir_max = nir_percentiles[max_perc_nir]
    sys.stdout.write(
        f"Proposal for NDVI threshold in the range of [{ndvi_min}, {ndvi_max}]; e.g.:\n"
    )
    sys.stdout.write(f"<NDVI_THRES={ndvi_val}>\n")
    sys.stdout.write("Proposal for NIR threshold:\n")
    sys.stdout.write(
        f"Proposal for NIR threshold in the range of [{nir_min}, {nir_max}]; e.g.:\n"
    )
    sys.stdout.write(f"<NIR_THRES={nir_val}>\n")

    # import pdb; pdb.set_trace()
    grass.run_command("r.mask", flags="r")


if __name__ == "__main__":
    options, flags = grass.parser()
    atexit.register(cleanup)
    main()
