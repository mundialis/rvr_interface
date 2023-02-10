#!/usr/bin/env python3

############################################################################
#
# MODULE:       v.tree.cd
#
# AUTHOR(S):    Lina Krisztian
#
# PURPOSE:      Calculates changes between two vector layers of trees
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
# % description: Calculates changes between two vector layers of trees
# % keyword: vector
# % keyword: statistics
# % keyword: change detection
# % keyword: classification
# %end

# %option G_OPT_V_INPUT
# % key: inp_t1
# %label: Name of the input vector layer of one timestamp/year
# %end

# %option G_OPT_V_INPUT
# % key: inp_t2
# % label: Name of the input vector layer of another timestamp/year, to compare
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
# % label: basename of output vector maps
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
orig_region = None


def cleanup():
    nuldev = open(os.devnull, "w")
    kwargs = {"flags": "f", "quiet": True, "stderr": nuldev}
    for rmv in rm_vectors:
        if grass.find_file(name=rmv, element="vector")["file"]:
            grass.run_command("g.remove", type="vector", name=rmv, **kwargs)
    for rmdir in rm_dirs:
        if os.path.isdir(rmdir):
            shutil.rmtree(rmdir)
    reset_region(orig_region)


def main():

    global rm_vectors, rm_dirs, orig_region

    pid = os.getpid()

    vec_inp_t1 = options["inp_t1"]
    vec_inp_t2 = options["inp_t2"]
    cd_output = options["output"]
    min_size = options["min_size"]
    max_fd = options["max_fd"]
    nprocs = int(options["nprocs"])
    tile_size = options["tile_size"]

    nprocs = set_nprocs(nprocs)

    orig_region = f'orig_region_{pid}'
    grass.run_command(
        "g.region",
        save=orig_region,
        quiet=True
    )
    grass.run_command(
        "g.region",
        vector=[vec_inp_t1, vec_inp_t2],
        flags='p'
    )

    # check if region is smaller than tile size
    region = grass.region()
    dist_ns = abs(region["n"] - region["s"])
    dist_ew = abs(region["w"] - region["e"])

    # create tiles
    grass.message(_("Creating tiles..."))
    # if area smaller than one tile
    if dist_ns <= float(tile_size) and dist_ew <= float(tile_size):
        grid = f"grid_{pid}"
        rm_vectors.append(grid)
        grass.run_command(
            "v.in.region",
            output=grid,
            quiet=True)
        grass.run_command(
            "v.db.addtable",
            map=grid,
            columns="cat int",
            quiet=True)
    else:
        # set region
        orig_region = f"grid_region_{pid}"
        grass.run_command(
            "g.region",
            save=orig_region,
            quiet=True)
        grass.run_command(
            "g.region",
            res=tile_size,
            flags="a",
            quiet=True)

        # create grid
        grid = f"grid_{pid}"
        rm_vectors.append(grid)
        grass.run_command(
            "v.mkgrid",
            map=grid,
            box=f"{tile_size},{tile_size}",
            quiet=True
        )

        # reset region
        grass.run_command(
            "g.region",
            region=orig_region,
            quiet=True)
        orig_region = None

    # grid only for tiles with trees
    grid_trees = f"grid_with_trees_{pid}"
    rm_vectors.append(grid_trees)
    grid_trees_t1 = f"{grid_trees}_t1"
    rm_vectors.append(grid_trees_t1)
    grid_trees_t2 = f"{grid_trees}_t2"
    rm_vectors.append(grid_trees_t2)
    grass.run_command(
        "v.select",
        ainput=grid,
        binput=vec_inp_t1,
        output=grid_trees_t1,
        operator="overlap",
        quiet=True,
    )
    grass.run_command(
        "v.select",
        ainput=grid,
        binput=vec_inp_t2,
        output=grid_trees_t2,
        operator="overlap",
        quiet=True,
    )
    grass.run_command(
        "v.overlay",
        ainput=grid_trees_t1,
        binput=grid_trees_t2,
        operator='or',
        output=grid_trees,
        quiet=True,
    )
    if not grass.find_file(name=grid_trees, element="vector")["file"]:
        grass.fatal(
            _(
                f"The set region is not overlapping with {grid_trees}. "
                "Please define another region."
            )
        )

    # create list of tiles
    tiles_list = list(
        grass.parse_command(
            "v.db.select",
            map=grid_trees,
            columns="cat",
            flags="c",
            quiet=True
        ).keys()
    )
    number_tiles = len(tiles_list)
    grass.message(_(f"Number of tiles is: {number_tiles}"))

    # Start trees change detection in parallel
    grass.message(_("Applying change detection..."))
    # save current mapset
    start_cur_mapset = grass.gisenv()["MAPSET"]

    # test nprocs setting
    if number_tiles < nprocs:
        nprocs = number_tiles
    queue = ParallelModuleQueue(nprocs=nprocs)
    # output_list = list()
    # area_identified_list = list()
    # area_input_list = list()
    # area_ref_list = list()

    output_ending = ["unchanged", f"only_{vec_inp_t1}", f"only_{vec_inp_t2}"]
    output_dict = {}
    for el in output_ending:
        output_dict[el] = list()

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
            tile_area = f"grid_cell_{tile}_{pid}"
            rm_vectors.append(tile_area)
            tile_output = f"change_{tile}_{pid}"
            grass.run_command(
                "v.extract",
                input=grid_trees,
                where=f"cat == {tile}",
                output=tile_area,
                quiet=True,
            )
            param = {
                "area": tile_area,
                "output": tile_output,
                "new_mapset": new_mapset,
                "inp_t1": vec_inp_t1,
                "inp_t2": vec_inp_t2,
                "output_ending": output_ending,
            }
            v_tree_cd_worker = Module(
            # grass.run_command(
                "v.tree.cd.worker",
                **param,
                run_=False,
            )
            # catch all GRASS outputs to stdout and stderr
            v_tree_cd_worker.stdout_ = grass.PIPE
            v_tree_cd_worker.stderr_ = grass.PIPE
            queue.put(v_tree_cd_worker)
        queue.wait()
    except Exception:
        for proc_num in range(queue.get_num_run_procs()):
            proc = queue.get(proc_num)
            if proc.returncode != 0:
                # save all stderr to a variable and pass it to a GRASS
                # exception
                errmsg = proc.outputs["stderr"].value.strip()
                grass.fatal(_(
                    f"\nERROR by processing <{proc.get_bash()}>: {errmsg}"
                    ))
    # print all logs of successfully run modules ordered by module as GRASS
    # message
    for proc in queue.get_finished_modules():
        msg = proc.outputs["stderr"].value.strip()
        grass.message(_(f"\nLog of {proc.get_bash()}:"))
        for msg_part in msg.split("\n"):
            grass.message(_(msg_part))
            # create mapset dict based on Log
        tile_output = re.search(
            r"Output is:\n<(.*?)>", msg
            ).groups()[0].split(',')
        for ind, el in enumerate(output_ending):
            if tile_output[ind]:
                output_dict[el].append(tile_output[ind])
        # output_list.append(tile_output)

    # verify that switching back to original mapset worked
    verify_mapsets(start_cur_mapset)
    grass.message(_("Merging output from tiles..."))
    cd_output_all = list()
    for i in output_dict:
        # get outputs from mapsets and merge (minimize edge effects)
        change_merged = f"change_merged_{i}_{pid}"
        rm_vectors.append(change_merged)
        change_diss = f"change_diss_{i}_{pid}"
        rm_vectors.append(change_diss)
        cd_output_i = f"{cd_output}_{i}"
        cd_output_all.append(cd_output_i)
        if len(queue.get_finished_modules()) > 1:
            # merge outputs from tiles and add table
            grass.run_command(
                "v.patch",
                input=output_dict[i],
                output=change_merged,
                flags="e",
                quiet=True,
            )
            # add new column with building_cat
            grass.run_command(
                "v.db.addcolumn",
                map=change_merged,
                column="new_cat INTEGER"
                )
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

        else:
            grass.run_command(
                "g.copy",
                vector=f"{output_dict[i][0]},{change_diss}",
                quiet=True
            )

        # filter with area and fractal dimension
        if i not in output_ending[0]:  # only for diff maps
            grass.message(_("Cleaning up based on shape and size..."))
            area_col = "area_sqm"
            fd_col = "fractal_d"

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
                output=cd_output_i,
                where=f"{area_col}<{min_size} OR " f"{fd_col}>{max_fd}",
                quiet=True,
            )
        else:
            grass.run_command(
                "g.rename",
                vector=f"{change_diss},{cd_output_i}",
                quiet=True
            )

    # # add column "source" and populate with name of ref or input map
    # grass.run_command(
    #     "v.db.addcolumn",
    #     map=cd_output,
    #     columns="source VARCHAR(100)",
    #     quiet=True,
    # )
    # grass.run_command(
    #     "v.db.update",
    #     map=cd_output,
    #     column="source",
    #     value=bu_input.split("@")[0],
    #     where="b_cat IS NOT NULL",
    #     quiet=True,
    # )
    # grass.run_command(
    #     "v.db.update",
    #     map=cd_output,
    #     column="source",
    #     value=bu_ref.split("@")[0],
    #     where="a_cat IS NOT NULL",
    #     quiet=True,
    # )

    # # remove unnecessary columns
    # columns_raw = list(grass.parse_command("v.info", map=cd_output, flags="cg").keys())
    # columns = [item.split("|")[1] for item in columns_raw]
    # # initial list of columns to be removed
    # dropcolumns = []
    # for col in columns:
    #     if col not in ("cat", "Etagen", area_col, fd_col, "source"):
    #         dropcolumns.append(col)

    # grass.run_command(
    #     "v.db.dropcolumn", map=cd_output, columns=(",").join(dropcolumns), quiet=True
    # )

    grass.message(_(f"Created output vector maps <{cd_output_all}>"))

    # if flags["q"]:
    #     # quality assessment: calculate completeness and correctness
    #     # completeness = correctly identified area / total area in reference dataset
    #     # correctness = correctly identified area / total area in input dataset
    #     grass.message(_("Calculating quality measures..."))

    #     # sum up areas from tiles and calculate measures
    #     area_identified = sum(area_identified_list)
    #     area_input = sum(area_input_list)
    #     area_ref = sum(area_ref_list)

    #     # print areas
    #     grass.message(_(f"The area of the input layer is {round(area_input, 2)} sqm."))
    #     grass.message(
    #         _(f"The area of the reference layer is {round(area_ref, 2)} sqm.")
    #     )
    #     grass.message(
    #         _(
    #             f"The overlapping area of both layers (correctly "
    #             f"identified area) is {round(area_identified, 2)} sqm."
    #         )
    #     )

    #     # calculate completeness and correctness
    #     completeness = area_identified / area_ref
    #     correctness = area_identified / area_input

    #     grass.message(
    #         _(
    #             f"Completeness is: {round(completeness, 2)}. \n"
    #             f"Correctness is: {round(correctness, 2)}. \n \n"
    #             f"Completeness = correctly identified area / total area in "
    #             f"reference dataset \n"
    #             f"Correctness = correctly identified area / total area in "
    #             f"input dataset (e.g. extracted buildings)"
    #         )
    #     )


if __name__ == "__main__":
    options, flags = grass.parser()
    path = get_lib_path(modname="m.analyse.trees", libname="analyse_trees_lib")
    if path is None:
        grass.fatal("Unable to find the analyse trees library directory")
    sys.path.append(path)
    try:
        from analyse_trees_lib import set_nprocs, verify_mapsets, reset_region
    except Exception:
        grass.fatal("m.analyse.trees library is not installed")
    atexit.register(cleanup)
    main()
