#!/usr/bin/env python3

############################################################################
#
# MODULE:       v.trees.cd
#
# AUTHOR(S):    Julia Haas and Lina Krisztian
#
# PURPOSE:      Calculates changes between two vector layers of trees
#
#
# COPYRIGHT:	(C) 2023 - 2024 by mundialis and the GRASS Development Team
#
# 		This program is free software under the GNU General Public
# 		License (>=v2). Read the file COPYING that comes with GRASS
# 		for details.
#
#############################################################################

# %Module
# % description: Calculates changes between two vector layers of trees.
# % keyword: vector
# % keyword: classification
# % keyword: statistics
# % keyword: change detection
# % keyword: trees analysis
# %end

# %option G_OPT_V_INPUT
# %label: Name of the input vector layer of one timestamp/year
# % guisection: Input
# % answer: tree_objects
# %end

# %option G_OPT_V_INPUT
# % key: reference
# % label: Name of the reference vector layer of another timestamp/year, to compare
# % answer: reference_trees
# % guisection: Input
# %end

# %option
# % key: congr_thresh
# % type: integer
# % required: yes
# % multiple: no
# % label: Threshold for overlap (in percentage) above which trees are considered to be congruent
# % answer: 90
# % guisection: Parameters
# %end

# %option
# % key: diff_min_size
# % type: double
# % required: yes
# % multiple: no
# % label: Minimum size of identified change areas in sqm
# % answer: 0.25
# % guisection: Parameters
# %end

# %option
# % key: diff_max_fd
# % type: double
# % required: yes
# % multiple: no
# % label: Maximum value of fractal dimension of identified change areas (see v.to.db)
# % answer: 2.5
# % guisection: Parameters
# %end

# %option G_OPT_V_OUTPUT
# % label: Basename for output vector maps
# % answer: trees_difference
# % guisection: Output
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


def patch_tiles(inp, change_merged, change_diss):
    # get outputs from mapsets and merge (minimize edge effects)
    if len(inp) > 1:
        # merge outputs from tiles and add table
        grass.run_command(
            "v.patch",
            input=inp,
            output=change_merged,
            flags="e",
            quiet=True,
        )
        # add new column with building_cat
        grass.run_command(
            "v.db.addcolumn",
            map=change_merged,
            column="new_cat INTEGER",
            quiet=True,
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
            "g.copy", vector=f"{inp[0]},{change_diss}", quiet=True
        )


def filter_congruent(change_diss, cd_output_i, vec_congr_thr, pid):
    rm_vec_columns = list()
    # for congruent map
    area_col_overlap = f"area_sqm_{pid}"
    rm_vec_columns.append(area_col_overlap)
    grass.run_command(
        "v.to.db",
        map=change_diss,
        option="area",
        columns=area_col_overlap,
        units="meters",
        quiet=True,
    )
    attr_col = [
        el.split("|")[1]
        for el in list(
            grass.parse_command("v.info", map=change_diss, flags="c")
        )
    ]
    area_col_t1 = "area_sqm_t1"
    if area_col_t1 not in attr_col:
        grass.warning(
            _(
                f"No column <{area_col_t1}> contained in vector map "
                f"{change_diss}. Can not filter congruent areas "
                f"with <vec_congr_thr={vec_congr_thr}>."
                "Keeping all overlapping areas."
            )
        )
        grass.run_command(
            "g.rename", vector=f"{change_diss},{cd_output_i}", quiet=True
        )
    else:
        rm_vec_columns.append("area_sqm_t1")
        grass.run_command(
            "v.db.droprow",
            input=change_diss,
            output=cd_output_i,
            where=(f"{area_col_overlap}<{vec_congr_thr}*0.01*{area_col_t1}"),
            quiet=True,
        )
    return rm_vec_columns


def filter_difmaps(
    change_diss, cd_output_i, vec_diff_min_size, vec_diff_max_fd, pid
):
    rm_vec_columns = list()
    # for diff maps
    area_col = f"area_sqm_{pid}"
    fd_col = f"fractal_d_{pid}"
    grass.message(_("Cleaning up based on shape and size..."))
    grass.run_command(
        "v.to.db",
        map=change_diss,
        option="area",
        columns=area_col,
        units="meters",
        quiet=True,
    )
    rm_vec_columns.append(area_col)
    grass.run_command(
        "v.to.db",
        map=change_diss,
        option="fd",
        columns=fd_col,
        units="meters",
        quiet=True,
    )
    rm_vec_columns.append(fd_col)
    grass.run_command(
        "v.db.droprow",
        input=change_diss,
        output=cd_output_i,
        where=(
            f"{area_col}<{vec_diff_min_size} OR {fd_col}>{vec_diff_max_fd}"
        ),
        quiet=True,
    )
    return rm_vec_columns


def main():
    global rm_vectors, rm_dirs, orig_region

    pid = os.getpid()

    vec_inp_t1 = options["input"]
    vec_inp_t2 = options["reference"]
    cd_output = options["output"]
    vec_congr_thr = options["congr_thresh"]
    vec_diff_min_size = options["diff_min_size"]
    vec_diff_max_fd = options["diff_max_fd"]
    nprocs = int(options["nprocs"])
    tile_size = options["tile_size"]

    nprocs = set_nprocs(nprocs)

    # set region to treecrowns
    orig_region = f"orig_region_{pid}"
    grass.run_command("g.region", save=orig_region, quiet=True)
    grass.run_command("g.region", vector=[vec_inp_t1, vec_inp_t2], flags="p")

    # create grid:
    grid_trees, tiles_list, number_tiles, rm_vectors_grid = create_grid_cd(
        tile_size, vec_inp_t1, vec_inp_t2
    )
    [rm_vectors.append(el) for el in rm_vectors_grid]

    # Start trees change detection in parallel:
    grass.message(_("Applying change detection..."))
    # save current mapset
    start_cur_mapset = grass.gisenv()["MAPSET"]
    # test nprocs setting
    if number_tiles < nprocs:
        nprocs = number_tiles
    queue = ParallelModuleQueue(nprocs=nprocs)

    # prepare names for output maps
    output_suffix = [
        "congruent",
        f"only_{vec_inp_t1.split('@')[0]}",
        f"only_{vec_inp_t2.split('@')[0]}",
    ]
    output_dict = {}
    for el in output_suffix:
        output_dict[el] = list()

    # ---------- calculate three output maps:
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
            # single tile
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
                "output_suffix": output_suffix,
            }
            v_tree_cd_worker = Module(
                "v.trees.cd.worker",
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
            # create mapset dict based on Log
        if "Skipping..." not in msg:
            try:
                # for execution in terminal
                tile_output = (
                    re.search(r"Output is:\n<(.*?)>", msg)
                    .groups()[0]
                    .split(",")
                )
            except Exception:
                # for execution in GUI
                tile_output = (
                    re.search(r"Output is: <(.*?)>", msg)
                    .groups()[0]
                    .split(",")
                )
            for ind, el in enumerate(output_suffix):
                if tile_output[ind]:
                    output_dict[el].append(tile_output[ind])

    # verify that switching back to original mapset worked
    verify_mapsets(start_cur_mapset)

    # ---------- Patch output
    grass.message(_("Merging output from tiles..."))
    cd_output_all = list()
    areas_count = list()
    for i in output_dict:
        change_merged = f"change_merged_{i}_{pid}"
        rm_vectors.append(change_merged)
        change_diss = f"change_diss_{i}_{pid}"
        rm_vectors.append(change_diss)
        inp = output_dict[i]
        patch_tiles(inp, change_merged, change_diss)

        cd_output_i = f"{cd_output}_{i}"
        cd_output_all.append(cd_output_i)

        rm_vec_columns = list()
        # filter with area and fractal dimension
        if i in output_suffix[0]:
            rm_vec_columns = filter_congruent(
                change_diss, cd_output_i, vec_congr_thr, pid
            )
        else:
            rm_vec_columns = filter_difmaps(
                change_diss,
                cd_output_i,
                vec_diff_min_size,
                vec_diff_max_fd,
                pid,
            )
        # remove unnecessary columns
        # only for non-empty vector (i.e. vector with attribute table)
        if grass.vector_db(cd_output_i):
            grass.run_command(
                "v.db.dropcolumn",
                map=cd_output_i,
                columns=rm_vec_columns,
                quiet=True,
            )
        areas_count.append(
            grass.parse_command(
                "v.info",
                map=cd_output_i,
                flags="t",
            ).areas
        )
    grass.message(
        _(
            f"Created output vector maps <{cd_output_all}>.\n"
            f"Amount of congruent trees: {areas_count[0]}.\n"
            f"Amount of (gone) trees in input {vec_inp_t1}: {areas_count[1]}\n"
            f"Amount of (new) trees in input {vec_inp_t2}: {areas_count[2]}."
        )
    )


if __name__ == "__main__":
    options, flags = grass.parser()
    path = get_lib_path(modname="m.analyse.trees", libname="analyse_trees_lib")
    if path is None:
        grass.fatal("Unable to find the analyse trees library directory")
    sys.path.append(path)
    try:
        from analyse_trees_lib import (
            set_nprocs,
            verify_mapsets,
            reset_region,
            create_grid_cd,
        )
    except Exception:
        grass.fatal("m.analyse.trees library is not installed")
    atexit.register(cleanup)
    main()
