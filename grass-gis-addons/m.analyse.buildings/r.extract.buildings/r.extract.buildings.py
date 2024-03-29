#!/usr/bin/env python3

############################################################################
#
# MODULE:       r.extract.buildings
#
# AUTHOR(S):    Julia Haas and Guido Riembauer
#
# PURPOSE:      Extracts buildings from nDSM, NDVI and FNK
#
# COPYRIGHT:	(C) 2021 - 2024 by mundialis and the GRASS Development Team
#
# 		This program is free software under the GNU General Public
# 		License (>=v2). Read the file COPYING that comes with GRASS
# 		for details.
#
#############################################################################

# %Module
# % description: Extracts buildings from nDSM, NDVI and FNK.
# % keyword: raster
# % keyword: classification
# % keyword: statistics
# % keyword: buildings analysis
# %end

# %option G_OPT_R_INPUT
# % key: ndsm
# % label: Name of the nDSM raster
# % answer: ndsm
# % guisection: Input
# %end

# %option G_OPT_R_INPUT
# % key: ndvi_raster
# % label: Name of the NDVI raster
# % answer: dop_ndvi_05
# % guisection: Input
# %end

# %option G_OPT_V_INPUT
# % key: fnk_vector
# % label: Name of vector map containing the Flaechennutzungskartierung
# % answer: fnk
# % guisection: Input
# % guidependency: fnk_column
# %end

# %option G_OPT_DB_COLUMN
# % key: fnk_column
# % required: yes
# % label: Name of integer column containing FNK-code
# % answer: code_2020
# % guisection: Input
# %end

# %option
# % key: min_size
# % type: integer
# % required: yes
# % multiple: no
# % label: Minimum size of buildings in sqm
# % answer: 20
# % guisection: Parameters
# %end

# %option
# % key: max_fd
# % type: double
# % required: yes
# % multiple: no
# % label: Maximum value of fractal dimension of identified objects (see v.to.db)
# % answer: 2.1
# % guisection: Parameters
# %end

# %option
# % key: used_thresh
# % required: yes
# % multiple: no
# % label: Set if the percentile or the threshold of the NDVI should be used: ndvi_thresh or ndvi_perc
# % options: ndvi_thresh,ndvi_perc
# % answer: ndvi_thresh
# % guisection: Parameters
# %end

# %option
# % key: ndvi_thresh
# % type: integer
# % required: no
# % multiple: no
# % label: Fix NDVI threshold (on a scale from 0-255) instead of estimated value from ndvi_perc and FNK
# % options: 0-255
# % answer: 145
# % guisection: Parameters
# %end

# %option
# % key: ndvi_perc
# % type: integer
# % required: no
# % multiple: no
# % label: NDVI percentile in vegetated areas to use for thresholding
# % options: 0-100
# % answer: 5
# % guisection: Parameters
# %end

# %option G_OPT_V_OUTPUT
# % answer: buildings
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
# % type: integer
# % required: yes
# % multiple: no
# % label: Edge length of grid tiles for parallel processing
# % answer: 1000
# % guisection: Parallel processing
# %end

# %flag
# % key: s
# % label: Segment image based on nDSM and NDVI before building extraction
# % guisection: Parameters
# %end


import atexit
import os
import re
import shutil
import sys
from uuid import uuid4

import grass.script as grass
from grass.pygrass.modules import Module, ParallelModuleQueue
from grass.pygrass.utils import get_lib_path


# initialize global vars
rm_rasters = []
rm_vectors = []
rm_groups = []
rm_dirs = []
tmp_mask_old = None
orig_region = None


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
    for rmdir in rm_dirs:
        if os.path.isdir(rmdir):
            shutil.rmtree(rmdir)
    if orig_region is not None:
        if grass.find_file(name=orig_region, element="windows")["file"]:
            grass.run_command("g.region", region=orig_region)
            grass.run_command(
                "g.remove", type="region", name=orig_region, **kwargs
            )
    if grass.find_file(name="MASK", element="cell")["file"]:
        try:
            grass.run_command("r.mask", flags="r", quiet=True)
        except Exception:
            pass
    # reactivate potential old mask
    if tmp_mask_old:
        grass.run_command("r.mask", raster=tmp_mask_old, quiet=True)


def main():
    global rm_rasters, tmp_mask_old, rm_vectors, rm_groups, rm_dirs, orig_region

    path = get_lib_path(
        modname="m.analyse.buildings", libname="analyse_buildings_lib"
    )
    if path is None:
        grass.fatal("Unable to find the analyse buildings library directory")
    sys.path.append(path)
    try:
        from analyse_buildings_lib import (
            create_grid,
            get_bins,
            get_percentile,
            set_nprocs,
            test_memory,
            verify_mapsets,
        )
    except Exception:
        grass.fatal("m.analyse.buildings library is not installed")

    ndsm = options["ndsm"]
    ndvi = options["ndvi_raster"]
    fnk_vect = options["fnk_vector"]
    fnk_column = options["fnk_column"]
    min_size = options["min_size"]
    max_fd = options["max_fd"]
    output_vect = options["output"]
    nprocs = int(options["nprocs"])
    tile_size = options["tile_size"]
    nprocs = set_nprocs(nprocs)

    # calculate NDVI threshold
    if options["used_thresh"] == "ndvi_perc":
        grass.message(_("Calculating NDVI threshold..."))
        # rasterizing fnk vect
        fnk_rast = f"fnk_rast_{os.getpid()}"
        rm_rasters.append(fnk_rast)
        grass.run_command(
            "v.to.rast",
            input=fnk_vect,
            use="attr",
            attribute_column=fnk_column,
            output=fnk_rast,
            quiet=True,
        )

        # fnk-codes with potential tree growth (400+ = Vegetation)
        fnk_codes_trees = ["400", "410", "420", "431", "432", "441", "472"]
        fnk_codes_mask = " ".join(fnk_codes_trees)
        grass.run_command(
            "r.mask", raster=fnk_rast, maskcats=fnk_codes_mask, quiet=True
        )

        # get NDVI statistics
        ndvi_percentile = float(options["ndvi_perc"])
        ndvi_thresh = get_percentile(ndvi, ndvi_percentile)
        grass.message(_(f"NDVI threshold is at {ndvi_thresh}."))
        grass.run_command("r.mask", flags="r", quiet=True)
    elif options["used_thresh"] == "ndvi_thresh":
        ndvi_thresh = float(options["ndvi_thresh"])
    else:
        grass.fatal(
            _(
                "The parameter <used_thresh> has to be <ndvi_thresh> or <ndvi_perc>!"
            )
        )

    # Creating tiles
    tiles_list, number_tiles = create_grid(tile_size, "grid_cell", fnk_vect)
    rm_vectors.extend(tiles_list)

    # Start building detection in parallel
    grass.message(_("Applying building detection..."))
    # save current mapset
    start_cur_mapset = grass.gisenv()["MAPSET"]

    # test nprocs setting
    if number_tiles < nprocs:
        nprocs = number_tiles
    queue = ParallelModuleQueue(nprocs=nprocs)
    output_list = list()

    # divide memory
    options["memory"] = test_memory(options["memory"])
    memory = int(int(options["memory"]) / nprocs)

    # Loop over tiles_list
    gisenv = grass.gisenv()
    try:
        for tile_area in tiles_list:
            tile = tile_area.rsplit("_", 1)[1]
            # Module
            new_mapset = f"tmp_mapset_apply_extraction_{tile}_{uuid4()}"
            mapset_path = os.path.join(
                gisenv["GISDBASE"], gisenv["LOCATION_NAME"], new_mapset
            )
            rm_dirs.append(mapset_path)
            bu_output = f"buildings_{tile}_{os.getpid()}"

            param = {
                "area": tile_area,
                "output": bu_output,
                "new_mapset": new_mapset,
                "ndsm": ndsm,
                "ndvi_raster": ndvi,
                "ndvi_thresh": ndvi_thresh,
                "fnk_column": fnk_column,
                "min_size": min_size,
                "max_fd": max_fd,
                "memory": memory,
            }

            if options["used_thresh"] == "ndvi_perc":
                param["fnk_raster"] = fnk_rast
            else:
                param["fnk_vector"] = fnk_vect

            if flags["s"]:
                param["flags"] = "s"

            r_extract_buildings_worker = Module(
                "r.extract.buildings.worker",
                **param,
                run_=False,
            )

            # catch all GRASS outputs to stdout and stderr
            r_extract_buildings_worker.stdout_ = grass.PIPE
            r_extract_buildings_worker.stderr_ = grass.PIPE
            queue.put(r_extract_buildings_worker)
        queue.wait()
    except Exception:
        for proc_num in range(queue.get_num_run_procs()):
            proc = queue.get(proc_num)
            if proc.returncode != 0:
                # save all stderr to a variable and pass it to a GRASS
                # exception
                errmsg = proc.outputs["stderr"].value.strip()
                grass.fatal(
                    _(f"\nERROR by processing <{proc.get_bash()}>: {errmsg}")
                )
    # print all logs of successfully run modules ordered by module as GRASS
    # message
    for proc in queue.get_finished_modules():
        msg = proc.outputs["stderr"].value.strip()
        grass.message(_(f"\nLog of {proc.get_bash()}:"))
        for msg_part in msg.split("\n"):
            if msg_part != "":
                grass.message(_(msg_part))
        # create mapset dict based on Log, so that only those with output are listed
        if "Skipping..." not in msg:
            try:
                # for execution in terminal
                tile_output = re.search(r"Output is:\n<(.*?)>", msg).groups()[
                    0
                ]
            except Exception:
                # for execution in GUI
                tile_output = re.search(r"Output is: <(.*?)>", msg).groups()[0]
            output_list.append(tile_output)

    # verify that switching back to original mapset worked
    verify_mapsets(start_cur_mapset)

    # get outputs from mapsets and merge (minimize edge effects)
    buildings_merged = f"buildings_merged_{os.getpid()}"
    rm_vectors.append(buildings_merged)
    buildings_diss = f"buildings_diss_{os.getpid()}"
    rm_vectors.append(buildings_diss)
    buildings_nocats = f"buildings_nocats_{os.getpid()}"
    rm_vectors.append(buildings_nocats)
    buildings_cats = f"buildings_cats_{os.getpid()}"
    rm_vectors.append(buildings_cats)

    grass.message(_("Merging output from tiles..."))
    if len(output_list) > 1:
        # merge outputs from tiles and add table
        grass.run_command(
            "v.patch",
            input=(",").join(output_list),
            output=buildings_merged,
            quiet=True,
        )

        grass.run_command(
            "v.db.addtable",
            map=buildings_merged,
            columns="value varchar(15)",
            quiet=True,
        )
        grass.run_command(
            "v.db.update",
            map=buildings_merged,
            column="value",
            value="dissolve",
            quiet=True,
        )

        grass.run_command(
            "v.dissolve",
            input=buildings_merged,
            column="value",
            output=buildings_diss,
            quiet=True,
        )

        # split multipolygon and remove potential duplicate features in
        # dissolved layer
        grass.run_command(
            "v.category",
            input=buildings_diss,
            output=buildings_nocats,
            option="del",
            cat=-1,
            quiet=True,
        )
        grass.run_command(
            "v.category",
            input=buildings_nocats,
            output=buildings_cats,
            option="add",
            type="centroid",
            quiet=True,
        )
        grass.run_command(
            "v.to.db",
            map=buildings_cats,
            option="cat",
            columns="cat",
            quiet=True,
            overwrite=True,
        )

    elif len(output_list) == 1:
        grass.run_command(
            "g.copy", vector=f"{output_list[0]},{buildings_cats}", quiet=True
        )

    # filter by shape and size
    grass.message(_("Filtering buildings by shape and size..."))
    area_col = "area_sqm"
    fd_col = "fractal_d"
    grass.run_command(
        "v.to.db",
        map=buildings_cats,
        option="area",
        columns=area_col,
        units="meters",
        quiet=True,
        overwrite=True,
    )
    grass.run_command(
        "v.to.db",
        map=buildings_cats,
        option="fd",
        columns=fd_col,
        units="meters",
        quiet=True,
        overwrite=True,
    )

    buildings_cleaned = f"buildings_cleaned_{os.getpid()}"
    rm_vectors.append(buildings_cleaned)
    grass.run_command(
        "v.db.droprow",
        input=buildings_cats,
        output=buildings_cleaned,
        where=f"{area_col}<{min_size} OR {fd_col}>{max_fd}",
        quiet=True,
    )

    buildings_cleaned_filled = f"buildings_cleaned_filled_{os.getpid()}"
    rm_vectors.append(buildings_cleaned_filled)
    fill_gapsize = min_size
    grass.run_command(
        "v.clean",
        input=buildings_cleaned,
        output=buildings_cleaned_filled,
        tool="rmarea",
        threshold=fill_gapsize,
        quiet=True,
    )

    # assign building height to attribute and estimate no. of stories
    ####################################################################
    # ndsm transformation and segmentation
    grass.message(_("Splitting up buildings by height..."))
    options["memory"] = test_memory(options["memory"])
    grass.run_command("r.mask", vector=buildings_cleaned_filled, quiet=True)

    percentiles = "1,50,99"
    bins = get_bins()
    quants_raw = list(
        grass.parse_command(
            "r.quantile",
            percentiles=percentiles,
            input=ndsm,
            bins=bins,
            quiet=True,
        ).keys()
    )
    quants = [item.split(":")[2] for item in quants_raw]
    grass.message(_(f'The percentiles are: {(", ").join(quants)}'))
    trans_ndsm_mask = f"ndsm_buildings_transformed_{os.getpid()}"
    rm_rasters.append(trans_ndsm_mask)
    med = quants[1]
    p_low = quants[0]
    p_high = quants[2]
    trans_expression = (
        f"{trans_ndsm_mask} = float(if({ndsm} >= {med}, sqrt(({ndsm} - "
        f"{med}) / ({p_high} - {med})), -1.0 * sqrt(({med} - {ndsm}) / "
        f"({med} - {p_low}))))"
    )

    grass.run_command("r.mapcalc", expression=trans_expression, quiet=True)

    # add transformed and cut ndsm to group
    segment_group = f"segment_group_{os.getpid()}"
    rm_groups.append(segment_group)
    grass.run_command(
        "i.group", group=segment_group, input=trans_ndsm_mask, quiet=True
    )

    segmented_ndsm_buildings = f"seg_ndsm_buildings_{os.getpid()}"
    rm_rasters.append(segmented_ndsm_buildings)
    grass.run_command(
        "i.segment",
        group=segment_group,
        output=segmented_ndsm_buildings,
        threshold=0.25,
        memory=options["memory"],
        minsize=400,
        quiet=True,
    )

    grass.run_command("r.mask", flags="r", quiet=True)

    segmented_ndsm_buildings_vect = f"seg_ndsm_buildings_vect_{os.getpid()}"
    rm_vectors.append(segmented_ndsm_buildings_vect)
    grass.run_command(
        "r.to.vect",
        input=segmented_ndsm_buildings,
        output=segmented_ndsm_buildings_vect,
        type="area",
        column="bu_cat",
        quiet=True,
    )

    # filter by shape and size (again after segmentation) and add area and
    # fractal dimension to attribute table
    grass.message(_("Calculating building sizes and fractal dimension..."))
    grass.message(_("Filtering buildings by shape and size..."))
    area_col = "area_sqm"
    fd_col = "fractal_d"
    grass.run_command(
        "v.to.db",
        map=segmented_ndsm_buildings_vect,
        option="area",
        columns=area_col,
        units="meters",
        quiet=True,
        overwrite=True,
    )
    grass.run_command(
        "v.to.db",
        map=segmented_ndsm_buildings_vect,
        option="fd",
        columns=fd_col,
        units="meters",
        quiet=True,
        overwrite=True,
    )

    grass.run_command(
        "v.db.droprow",
        input=segmented_ndsm_buildings_vect,
        output=output_vect,
        where=f"{area_col}<{min_size} OR {fd_col}>{max_fd}",
        quiet=True,
    )

    #####################################################################
    grass.message(_("Extracting building height statistics..."))
    av_story_height = 3.0
    col_prefix = "ndsm"
    grass.run_command(
        "v.rast.stats",
        map=output_vect,
        raster=ndsm,
        method=("minimum,maximum,average,stddev,median,percentile"),
        percentile=95,
        column_prefix=col_prefix,
        quiet=True,
    )
    # rename columns to shorter names
    min_col = f"{col_prefix}_min"
    max_col = f"{col_prefix}_max"
    av_col = f"{col_prefix}_av"
    stddev_col = f"{col_prefix}_sd"  #
    median_col = f"{col_prefix}_med"
    perc_col = f"{col_prefix}_p95"
    grass.run_command(
        "v.db.renamecolumn",
        map=output_vect,
        column=f"{col_prefix}_minimum,{min_col}",
        quiet=True,
    )
    grass.run_command(
        "v.db.renamecolumn",
        map=output_vect,
        column=f"{col_prefix}_maximum,{max_col}",
        quiet=True,
    )
    grass.run_command(
        "v.db.renamecolumn",
        map=output_vect,
        column=f"{col_prefix}_average,{av_col}",
        quiet=True,
    )
    grass.run_command(
        "v.db.renamecolumn",
        map=output_vect,
        column=f"{col_prefix}_stddev,{stddev_col}",
        quiet=True,
    )
    grass.run_command(
        "v.db.renamecolumn",
        map=output_vect,
        column=f"{col_prefix}_median,{median_col}",
        quiet=True,
    )
    grass.run_command(
        "v.db.renamecolumn",
        map=output_vect,
        column=f"{col_prefix}_percentile_95,{perc_col}",
        quiet=True,
    )

    # calculate stories
    column_etagen = "floors"
    grass.run_command(
        "v.db.addcolumn",
        map=output_vect,
        columns=f"{column_etagen} INT",
        quiet=True,
    )
    sql_string = f"ROUND({perc_col}/{av_story_height},0)"
    grass.run_command(
        "v.db.update",
        map=output_vect,
        column=column_etagen,
        query_column=sql_string,
        quiet=True,
    )

    grass.message(_(f"Created output vector layer <{output_vect}>."))


if __name__ == "__main__":
    options, flags = grass.parser()
    atexit.register(cleanup)
    main()
