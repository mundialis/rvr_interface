#!/usr/bin/env python3

############################################################################
#
# MODULE:       r.trees.peaks
#
# AUTHOR(S):    Markus Metz, Lina Krisztian
#
# PURPOSE:      Assigns pixels to nearest peak (tree crown)
#
# COPYRIGHT:    (C) 2023 - 2024 by mundialis and the GRASS Development Team
#
#       This program is free software under the GNU General Public
#       License (>=v2). Read the file COPYING that comes with GRASS
#       for details.
#
#############################################################################

# %Module
# % description: Assigns pixels to nearest peak (tree crown).
# % keyword: raster
# % keyword: classificati1on
# % keyword: statistics
# % keyword: geomorphology
# % keyword: trees analysis
# %end

# %option G_OPT_V_INPUT
# % key: area
# % label: Name of vector defining area of interest
# % answer: study_area
# % guisection: Input
# %end

# %option G_OPT_R_INPUT
# % key: ndsm
# % multiple: no
# % label: Name of the nDSM raster
# % answer: ndsm
# % guisection: Input
# %end

# %option
# % key: forms_res
# % type: double
# % required: yes
# % label: Resolution to use for forms detection
# % answer: 0.8
# % guisection: Parameters
# %end

# %option G_OPT_R_OUTPUT
# % key: nearest
# % multiple: no
# % label: Output raster map with ID of nearest tree
# % answer: nearest_tree
# % guisection: Output
# %end

# %option G_OPT_R_OUTPUT
# % key: peaks
# % multiple: no
# % label: Output raster map with peaks and ridges
# % answer: tree_peaks
# % guisection: Output
# %end

# %option G_OPT_R_OUTPUT
# % key: slope
# % multiple: no
# % label: Output raster map with nDSM slope
# % answer: ndsm_slope
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

# %option
# % key: tile_size
# % type: double
# % required: no
# % label: Edge length of grid tiles in map units for parallel processing
# % answer: 2000
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
        from analyse_trees_lib import create_grid, set_nprocs, test_memory
    except Exception:
        grass.fatal("analyse_trees_lib missing.")

    grass.message(_("Preparing input data..."))
    if grass.find_file(name="MASK", element="cell")["file"]:
        tmp_mask_old = "tmp_mask_old_%s" % os.getpid()
        grass.run_command(
            "g.rename", raster="%s,%s" % ("MASK", tmp_mask_old), quiet=True
        )

    ndsm = options["ndsm"]
    ndsm_slope = options["slope"]
    nearest = options["nearest"]
    trees_peaks = options["peaks"]
    forms_res = float(options["forms_res"])
    area = options["area"]
    tile_size = options["tile_size"]
    nprocs = int(options["nprocs"])

    nprocs = set_nprocs(nprocs)

    if not grass.find_file(name=area, element="vector")["file"]:
        grass.fatal(_("Vector defining study area <%s> not found!") % area)

    memmb = test_memory(options["memory"])
    # for some modules like r.neighbors and r.slope_aspect, there is
    # no speed gain by using more than 100 MB RAM
    memory_max100mb = 100
    if memmb < 100:
        memory_max100mb = memmb

    org_region = grass.region()
    grass.use_temp_region()

    # the resolution of the ndsm must not be too fine,
    # otherwise several peaks within a single tree crown will be detected
    # good choice: res=0.5 - 1
    grass.run_command("g.region", res=forms_res, flags="a")
    ndsm_resampled = ndsm
    rinfo = grass.raster_info(ndsm)
    if rinfo["nsres"] < forms_res:
        ndsm_resampled = f"{ndsm.split('@')[0]}_resampled"
        rm_rasters.append(ndsm_resampled)
        grass.run_command(
            "r.resamp.stats",
            input=ndsm,
            output=ndsm_resampled,
            method="maximum",
        )
    elif rinfo["nsres"] > forms_res:
        ndsm_resampled = f"{ndsm.split('@')[0]}_resampled"
        rm_rasters.append(ndsm_resampled)
        radius_gauss = rinfo["nsres"] * 1.5
        radius_box = rinfo["nsres"] * 3
        grass.run_command(
            "r.resamp.filter",
            input=ndsm,
            output=ndsm_resampled,
            filter="gauss,box",
            radius=f"{radius_gauss},{radius_box}",
        )

    ndsm_forms = f"{ndsm.split('@')[0]}_forms"
    grass.run_command(
        "r.geomorphon", elevation=ndsm_resampled, forms=ndsm_forms, search=7
    )
    rm_rasters.append(ndsm_forms)

    # extract peak (2) + ridge (3)
    trees_peaks_tmp1 = f"{trees_peaks}_tmp1"
    grass.mapcalc(
        f"{trees_peaks_tmp1} = if({ndsm_forms} == 2 || {ndsm_forms} == 3, 1, null())"
    )
    rm_rasters.append(trees_peaks_tmp1)

    # r.clump not diagonal
    trees_peaks_tmp2 = f"{trees_peaks}_tmp2"
    grass.run_command(
        "r.clump", input=trees_peaks_tmp1, output=trees_peaks_tmp2
    )
    rm_rasters.append(trees_peaks_tmp2)

    # remove all clumps without a peak
    trees_peaks_tmp3 = f"{trees_peaks}_tmp3"
    grass.run_command(
        "r.stats.zonal",
        base=trees_peaks_tmp2,
        cover=ndsm_forms,
        output=trees_peaks_tmp3,
        method="min",
    )
    rm_rasters.append(trees_peaks_tmp3)

    # clean up peaks (2) + ridges (3)
    grass.mapcalc(
        f"{trees_peaks} = if({trees_peaks_tmp3} == 3, null(), {ndsm_forms})"
    )

    # clean up clumps
    trees_peaks_tmp4 = f"{trees_peaks}_tmp4"
    grass.mapcalc(
        f"{trees_peaks_tmp4} = if({trees_peaks_tmp3} == 3, null(), {trees_peaks_tmp2})"
    )
    rm_rasters.append(trees_peaks_tmp4)

    # set region back to original
    grass.run_command(
        "g.region",
        n=org_region["n"],
        s=org_region["s"],
        e=org_region["e"],
        w=org_region["w"],
        nsres=org_region["nsres"],
        ewres=org_region["ewres"],
    )

    # unique id of nearest tree crown
    # similar to watershed segmentation
    grass.run_command(
        "r.slope.aspect",
        elevation=ndsm,
        slope=ndsm_slope,
        format="percent",
        flags="e",
        memory=memory_max100mb,
        nprocs=nprocs,
    )
    # invert slope, make sure all values are positive
    slope_max = grass.raster_info(f"{ndsm_slope}")["max"]
    slope_max += 10
    grass.mapcalc(f"{ndsm_slope}_inv = {slope_max} - {ndsm_slope}")
    rm_rasters.append(f"{ndsm_slope}_inv")

    grid_prefix = "cost_grid"
    tiles_list, number_tiles = create_grid(tile_size, grid_prefix, area)

    if number_tiles == 1:
        # assign all pixels to the nearest (tree) peak
        grass.run_command(
            "r.cost",
            input=f"{ndsm_slope}_inv",
            output="trees_costs_tmp",
            nearest=nearest,
            start_raster=trees_peaks_tmp4,
            mem=memmb,
        )
        rm_rasters.append("trees_costs_tmp")
    else:
        # loop over grids, expand each grid by 100 meter
        grow_cells = int(100 / org_region["nsres"])

        for i in range(number_tiles):
            j = i + 1
            grass.message(_(f"Cost analysis for tile {j} of {number_tiles}..."))

            tile_area = tiles_list[i]

            # set region to tile, align to ndsm slope
            grass.run_command(
                "g.region",
                vector=tile_area,
                align=ndsm_slope,
            )
            # grow region to avoid edge effects of the cost analysis
            grass.run_command("g.region", grow=grow_cells)
            rm_vectors.append(tile_area)

            grass.run_command(
                "r.cost",
                input=f"{ndsm_slope}_inv",
                output=f"trees_costs_tmp_tile_{j}",
                nearest=f"{nearest}_tile_{j}",
                start_raster=trees_peaks_tmp4,
                mem=memmb,
            )
            rm_rasters.append(f"trees_costs_tmp_tile_{j}")

            if i == 0:
                grass.run_command(
                    "g.rename",
                    raster=f"trees_costs_tmp_tile_{j},trees_costs_tmp",
                )
                grass.run_command(
                    "g.rename", raster=f"{nearest}_tile_{j},{nearest}"
                )
                rm_rasters.append("trees_costs_tmp")
            else:
                # rename intermediate result rasters
                grass.run_command(
                    "g.rename", raster="trees_costs_tmp,trees_costs_tmp_tmp"
                )
                grass.run_command("g.rename", raster=f"{nearest},{nearest}_tmp")

                # patch new tile with current result using the lowest cost
                # to select the nearest id
                # this will become slower with increasing tile number
                grass.run_command(
                    "g.region", raster=f"{nearest}_tmp,{nearest}_tile_{j}"
                )
                # shrink region to original region
                do_shrink = False
                patch_region = grass.region()
                if patch_region["w"] < org_region["w"]:
                    patch_region["w"] = org_region["w"]
                    do_shrink = True
                if patch_region["s"] < org_region["s"]:
                    patch_region["s"] = org_region["s"]
                    do_shrink = True
                if patch_region["e"] > org_region["e"]:
                    patch_region["e"] = org_region["e"]
                    do_shrink = True
                if patch_region["n"] > org_region["n"]:
                    patch_region["n"] = org_region["n"]
                    do_shrink = True

                if do_shrink:
                    grass.run_command(
                        "g.region",
                        n=patch_region["n"],
                        s=patch_region["s"],
                        e=patch_region["e"],
                        w=patch_region["w"],
                    )

                # patch id of nearest clump
                grass.mapcalc(
                    f"{nearest} = if(isnull({nearest}_tmp), {nearest}_tile_{j}, "
                    f"if(isnull({nearest}_tile_{j}), {nearest}_tmp, "
                    f"if(trees_costs_tmp_tmp < trees_costs_tmp_tile_{j}, "
                    f"{nearest}_tmp, {nearest}_tile_{j})))"
                )

                # patch accumulated costs
                grass.mapcalc(
                    f"trees_costs_tmp = if(isnull(trees_costs_tmp_tmp), trees_costs_tmp_tile_{j}, "
                    f"if(isnull(trees_costs_tmp_tile_{j}), trees_costs_tmp_tmp, "
                    f"if(trees_costs_tmp_tmp < trees_costs_tmp_tile_{j}, "
                    f"trees_costs_tmp_tmp, trees_costs_tmp_tile_{j})))"
                )

                # remove very large temporary maps immediately
                grass.run_command(
                    "g.remove",
                    type="raster",
                    name=f"trees_costs_tmp_tmp,{nearest}_tmp",
                    flags="f",
                    quiet=True,
                )
                grass.run_command(
                    "g.remove",
                    type="raster",
                    name=f"trees_costs_tmp_tile_{j},{nearest}_tile_{j}",
                    flags="f",
                    quiet=True,
                )

            # set region back to original
            grass.run_command(
                "g.region",
                n=org_region["n"],
                s=org_region["s"],
                e=org_region["e"],
                w=org_region["w"],
                nsres=org_region["nsres"],
                ewres=org_region["ewres"],
            )

    grass.message(
        _(
            "Created output raster maps with peaks, and ridges, "
            "with nearest tree ID, and with slope."
        )
    )


if __name__ == "__main__":
    options, flags = grass.parser()
    atexit.register(cleanup)
    main()
