#!/usr/bin/env python3

############################################################################
#
# MODULE:       v.cd.areas
#
# AUTHOR(S):    Julia Haas
#
# PURPOSE:      Calculates difference between two vector layers (e.g. buildings)
#               and optionally calculates quality measures
#
#
# COPYRIGHT:	(C) 2023 by mundialis and the GRASS Development Team
#
# 		This program is free software under the GNU General Public
# 		License (>=v2). Read the file COPYING that comes with GRASS
# 		for details.
#
#############################################################################

# %Module
# % description: Calculates difference between two vector layers (e.g. buildings)
# % keyword: vector
# % keyword: statistics
# % keyword: change detection
# % keyword: classification
# %end

# %option G_OPT_V_INPUT
# %label: Name of the input vector layer
# %end

# %option G_OPT_V_INPUT
# % key: reference
# % label: Name of the reference vector layer
# %end

# %option
# % key: min_size
# % type: integer
# % required: no
# % multiple: no
# % label: Minimum size of identified change areas in sqm
# % answer: 5
# %end

# %option
# % key: max_fd
# % type: double
# % required: no
# % multiple: no
# % label: Maximum value of fractal dimension of identified change areas (see v.to.db)
# % answer: 2.5
# %end

# %option G_OPT_V_OUTPUT
# % guisection: Output
# %end

# %option
# % key: nprocs
# % type: integer
# % required: no
# % multiple: no
# % label: Number of parallel processes
# % description: Number of cores for multiprocessing, -2 is the number of available cores - 1
# % answer: -2
# %end

# %option
# % key: tile_size
# % type: integer
# % required: yes
# % multiple: no
# % label: define edge length of grid tiles for parallel processing
# % answer: 1000
# %end

# %flag
# % key: q
# % description: Calculate quality measures completeness and correctness
# %end


import atexit
import os
import re
import sys
from uuid import uuid4

import grass.script as grass
from grass.pygrass.modules import Module, ParallelModuleQueue
from grass.pygrass.utils import get_lib_path
import shutil


# initialize global vars
rm_vectors = []
rm_dirs = []


def cleanup():
    nuldev = open(os.devnull, "w")
    kwargs = {"flags": "f", "quiet": True, "stderr": nuldev}
    for rmv in rm_vectors:
        if grass.find_file(name=rmv, element="vector")["file"]:
            grass.run_command("g.remove", type="vector", name=rmv, **kwargs)
    for rmdir in rm_dirs:
        if os.path.isdir(rmdir):
            shutil.rmtree(rmdir)


def main():

    global rm_vectors, rm_dirs

    path = get_lib_path(modname="m.analyse.buildings", libname="analyse_buildings_lib")
    if path is None:
        grass.fatal("Unable to find the analyse buildings library directory")
    sys.path.append(path)
    try:
        from analyse_buildings_lib import set_nprocs, verify_mapsets
    except Exception:
        grass.fatal("m.analyse.buildings library is not installed")

    bu_input = options["input"]
    bu_ref = options["reference"]
    cd_output = options["output"]
    min_size = options["min_size"]
    max_fd = options["max_fd"]
    nprocs = int(options["nprocs"])
    tile_size = options["tile_size"]

    nprocs = set_nprocs(nprocs)

    # check if region is smaller than tile size
    region = grass.region()
    dist_ns = abs(region["n"] - region["s"])
    dist_ew = abs(region["w"] - region["e"])

    # create tiles
    grass.message(_("Creating tiles..."))
    # if area smaller than one tile
    if dist_ns <= float(tile_size) and dist_ew <= float(tile_size):
        grid = f"grid_{os.getpid()}"
        rm_vectors.append(grid)
        grass.run_command("v.in.region", output=grid, quiet=True)
        grass.run_command("v.db.addtable", map=grid, columns="cat int", quiet=True)
    else:
        # set region
        orig_region = f"grid_region_{os.getpid()}"
        grass.run_command("g.region", save=orig_region, quiet=True)
        grass.run_command("g.region", res=tile_size, flags="a", quiet=True)

        # create grid
        grid = f"grid_{os.getpid()}"
        rm_vectors.append(grid)
        grass.run_command(
            "v.mkgrid", map=grid, box=f"{tile_size},{tile_size}", quiet=True
        )

        # reset region
        grass.run_command("g.region", region=orig_region, quiet=True)
        orig_region = None

    # grid only for tiles with buildings
    grid_bu = f"grid_with_buildings_{os.getpid()}"
    rm_vectors.append(grid_bu)
    grass.run_command(
        "v.select",
        ainput=grid,
        binput=bu_input,
        output=grid_bu,
        operator="overlap",
        quiet=True,
    )

    if grass.find_file(name=grid_bu, element="vector")["file"] == "":
        grass.fatal(
            _(
                f"The set region is not overlapping with {bu_input}. "
                f"Please define another region."
            )
        )

    # create list of tiles
    tiles_list = list(
        grass.parse_command(
            "v.db.select", map=grid, columns="cat", flags="c", quiet=True
        ).keys()
    )

    number_tiles = len(tiles_list)
    grass.message(_(f"Number of tiles is: {number_tiles}"))

    # Start building detection in parallel
    grass.message(_("Applying change detection..."))
    # save current mapset
    start_cur_mapset = grass.gisenv()["MAPSET"]

    # test nprocs setting
    if number_tiles < nprocs:
        nprocs = number_tiles
    queue = ParallelModuleQueue(nprocs=nprocs)
    output_list = list()
    area_identified_list = list()
    area_input_list = list()
    area_ref_list = list()

    # Loop over tiles_list
    gisenv = grass.gisenv()
    try:
        for tile in tiles_list:
            # Module
            new_mapset = f"tmp_mapset_apply_extraction_{tile}_{uuid4()}"
            mapset_path = os.path.join(
                gisenv["GISDBASE"], gisenv["LOCATION_NAME"], new_mapset
            )
            rm_dirs.append(mapset_path)
            tile_output = f"change_{tile}_{os.getpid()}"
            tile_area = f"grid_cell_{tile}_{os.getpid()}"
            rm_vectors.append(tile_area)

            grass.run_command(
                "v.extract",
                input=grid,
                where=f"cat == {tile}",
                output=tile_area,
                quiet=True,
            )

            param = {
                "area": tile_area,
                "output": tile_output,
                "new_mapset": new_mapset,
                "input": bu_input,
                "reference": bu_ref,
            }

            if flags["q"]:
                param["flags"] = "q"

            v_cd_areas_worker = Module(
                "v.cd.areas.worker",
                **param,
                run_=False,
            )

            # catch all GRASS outputs to stdout and stderr
            v_cd_areas_worker.stdout_ = grass.PIPE
            v_cd_areas_worker.stderr_ = grass.PIPE
            queue.put(v_cd_areas_worker)
        queue.wait()
        # grass.run_command("v.cd.areas.worker", **param, quiet=True) # TODO: remove in the end!
    except Exception:
        for proc_num in range(queue.get_num_run_procs()):
            proc = queue.get(proc_num)
            if proc.returncode != 0:
                # save all stderr to a variable and pass it to a GRASS
                # exception
                errmsg = proc.outputs["stderr"].value.strip()
                grass.fatal(_(f"\nERROR by processing <{proc.get_bash()}>: {errmsg}"))
    # print all logs of successfully run modules ordered by module as GRASS
    # message
    for proc in queue.get_finished_modules():
        msg = proc.outputs["stderr"].value.strip()
        grass.message(_(f"\nLog of {proc.get_bash()}:"))
        for msg_part in msg.split("\n"):
            grass.message(_(msg_part))
        # create mapset dict based on Log, so that only those with output are listed
        if "Skipping..." not in msg:
            tile_output = re.search(r"Output is:\n<(.*?)>", msg).groups()[0]
            output_list.append(tile_output)
            if flags["q"]:
                area_identified = re.search(
                    r"area identified is: <(.*?)>", msg
                ).groups()[0]
                area_identified_list.append(float(area_identified))
                area_input = re.search(
                    r"area buildings input is: <(.*?)>", msg
                ).groups()[0]
                area_input_list.append(float(area_input))
                area_ref = re.search(
                    r"area buildings reference is: <(.*?)>", msg
                ).groups()[0]
                area_ref_list.append(float(area_ref))

    # verify that switching back to original mapset worked
    verify_mapsets(start_cur_mapset)

    # get outputs from mapsets and merge (minimize edge effects)
    change_merged = f"change_merged_{os.getpid()}"
    rm_vectors.append(change_merged)
    change_diss = f"change_diss_{os.getpid()}"
    rm_vectors.append(change_diss)
    # change_diss_ab = f"change_diss_ab_{os.getpid()}"
    # rm_vectors.append(change_diss_ab)

    grass.message(_("Merging output from tiles..."))
    if len(output_list) > 1:

        # merge outputs from tiles and add table
        grass.run_command(
            "v.patch",
            input=output_list,
            output=change_merged,
            flags="e",
            quiet=True,
        )

        # add new column with building_cat
        grass.run_command("v.db.addcolumn", map=change_merged, column="new_cat INTEGER")

        grass.run_command(
            "v.db.update",
            map=change_merged,
            column="new_cat",
            where="a_cat IS NOT NULL",
            query_column="a_cat",
            quiet=True,
        )

        grass.run_command(
            "v.db.update",
            map=change_merged,
            column="new_cat",
            where="b_cat IS NOT NULL",
            query_column="b_cat",
            quiet=True,
        )

        # dissolve by column "new_cat"
        grass.run_command(
            "v.extract",
            input=change_merged,
            output=change_diss,
            dissolve_column="new_cat",
            flags="d",
            quiet=True,
        )

    elif len(output_list) == 1:
        grass.run_command(
            "g.copy", vector=f"{output_list[0]},{change_diss}", quiet=True
        )

    # filter with area and fractal dimension
    grass.message(_("Cleaning up based on shape and size..."))
    area_col = "area_sqm"
    fd_col = "fractal_dimension"

    grass.run_command(
        "v.to.db",
        map=change_diss,
        option="area",
        columns=area_col,
        units="meters",
        quiet=True,
    )

    grass.run_command(
        "v.to.db",
        map=change_diss,
        option="fd",
        columns=fd_col,
        units="meters",
        quiet=True,
    )

    grass.run_command(
        "v.db.droprow",
        input=change_diss,
        output=cd_output,
        where=f"{area_col}<{min_size} OR " f"{fd_col}>{max_fd}",
        quiet=True,
    )

    # add column "source" and populate with name of ref or input map
    grass.run_command(
        "v.db.addcolumn",
        map=cd_output,
        columns="source VARCHAR(100)",
        quiet=True,
    )
    grass.run_command(
        "v.db.update",
        map=cd_output,
        column="source",
        value=bu_input.split("@")[0],
        where="b_cat IS NOT NULL",
        quiet=True,
    )
    grass.run_command(
        "v.db.update",
        map=cd_output,
        column="source",
        value=bu_ref.split("@")[0],
        where="a_cat IS NOT NULL",
        quiet=True,
    )

    # remove unnecessary columns
    columns_raw = list(grass.parse_command("v.info", map=cd_output, flags="cg").keys())
    columns = [item.split("|")[1] for item in columns_raw]
    # initial list of columns to be removed
    dropcolumns = []
    for col in columns:
        if col not in ("cat", "Etagen", area_col, fd_col, "source"):
            dropcolumns.append(col)

    grass.run_command(
        "v.db.dropcolumn", map=cd_output, columns=(",").join(dropcolumns), quiet=True
    )

    grass.message(_(f"Created output vector map <{cd_output}>"))

    if flags["q"]:
        # quality assessment: calculate completeness and correctness
        # completeness = correctly identified area / total area in reference dataset
        # correctness = correctly identified area / total area in input dataset
        grass.message(_("Calculating quality measures..."))

        # sum up areas from tiles and calculate measures
        area_identified = sum(area_identified_list)
        area_input = sum(area_input_list)
        area_ref = sum(area_ref_list)

        # print areas
        grass.message(_(f"The area of the input layer is {round(area_input, 2)} sqm."))
        grass.message(
            _(f"The area of the reference layer is {round(area_ref, 2)} sqm.")
        )
        grass.message(
            _(
                f"The overlapping area of both layers (correctly "
                f"identified area) is {round(area_identified, 2)} sqm."
            )
        )

        # calculate completeness and correctness
        completeness = area_identified / area_ref
        correctness = area_identified / area_input

        grass.message(
            _(
                f"Completeness is: {round(completeness, 2)}. \n"
                f"Correctness is: {round(correctness, 2)}. \n \n"
                f"Completeness = correctly identified area / total area in "
                f"reference dataset \n"
                f"Correctness = correctly identified area / total area in "
                f"input dataset (e.g. extracted buildings)"
            )
        )


if __name__ == "__main__":
    options, flags = grass.parser()
    atexit.register(cleanup)
    main()
