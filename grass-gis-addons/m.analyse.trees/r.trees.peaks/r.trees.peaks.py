#!/usr/bin/env python3

############################################################################
#
# MODULE:       r.trees.peaks
#
# AUTHOR(S):    Markus Metz <metz at mundialis.de>
#
# PURPOSE:      Assigns pixels to nearest peak (tree crown)
#
# COPYRIGHT:    (C) 2023 by mundialis and the GRASS Development Team
#
#       This program is free software under the GNU General Public
#       License (>=v2). Read the file COPYING that comes with GRASS
#       for details.
#
#############################################################################

# %Module
# % description: Assigns pixels to nearest peak (tree crown).
# % keyword: raster
# % keyword: statistics
# % keyword: geomorhology
# % keyword: classification
# %end

# %option G_OPT_R_INPUT
# % key: ndsm
# % type: string
# % required: yes
# % multiple: no
# % label: Name of the nDSM raster
# %end

# %option
# % key: forms_res
# % type: double
# % required: no
# % label: Resolution to use for forms detection
# % answer: 0.8
# %end

# %option G_OPT_R_OUTPUT
# % key: nearest
# % required: yes
# % multiple: no
# % label: Output raster map with ID of nearest tree
# % answer: trees_nearest
# % guisection: Output
# %end

# %option G_OPT_R_OUTPUT
# % key: peaks
# % required: yes
# % multiple: no
# % label: Output raster map with peaks and ridges
# % guisection: Output
# %end

# %option G_OPT_R_OUTPUT
# % key: slope
# % required: yes
# % multiple: no
# % label: Output raster map with nDSM slope
# % guisection: Output
# %end

# %option G_OPT_MEMORYMB
# %end


import atexit
import os
import grass.script as grass

# initialize global vars
rm_rasters = []
rm_vectors = []
rm_groups = []
tmp_mask_old = None


def cleanup():
    nuldev = open(os.devnull, "w")
    kwargs = {"flags": "f", "quiet": True, "stderr": nuldev}
    for rmrast in rm_rasters:
        if grass.find_file(name=rmrast, element="raster")["file"]:
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

    grass.message(_("Preparing input data..."))
    if grass.find_file(name="MASK", element="raster")["file"]:
        tmp_mask_old = "tmp_mask_old_%s" % os.getpid()
        grass.run_command(
            "g.rename", raster="%s,%s" % ("MASK", tmp_mask_old), quiet=True
        )

    ndsm = options["ndsm"]
    ndsm_slope = options["slope"]
    nearest = options["nearest"]
    trees_peaks = options["peaks"]
    forms_res = float(options["forms_res"])
    memmb = options["memory"]

    org_region = grass.region()
    grass.use_temp_region()

    # the resolution of the ndsm must not be too fine,
    # otherwise several peaks within a single tree crown will be detected
    # good choice: res=0.5 - 1
    grass.run_command("g.region", res=forms_res, flags="a")
    ndsm_resampled = ndsm
    rinfo = grass.raster_info(ndsm)
    if rinfo["nsres"] < forms_res:
        ndsm_resampled = f"{ndsm}_resampled"
        rm_rasters.append(ndsm_resampled)
        grass.run_command(
            "r.resamp.stats",
            input=ndsm,
            output=ndsm_resampled,
            method="maximum",
        )
    elif rinfo["nsres"] > forms_res:
        ndsm_resampled = f"{ndsm}_resampled"
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

    ndsm_forms = f"{ndsm}_forms"
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
    )
    # invert slope, make sure all values are positive
    slope_max = grass.raster_info(f"{ndsm_slope}")["max"]
    slope_max += 10
    grass.mapcalc(f"{ndsm_slope}_inv = {slope_max} - {ndsm_slope}")
    rm_rasters.append(f"{ndsm_slope}_inv")

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
