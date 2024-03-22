#!/usr/bin/env python3

############################################################################
#
# MODULE:       r.trees.mlapply
#
# AUTHOR(S):    Markus Metz, Lina Krisztian, Julia Haas
#
# PURPOSE:      Applies the tree classification model in parallel to the
#               current region
#
# COPYRIGHT:    (C) 2023 - 2024 by mundialis GmbH & Co. KG and the GRASS
#               Development Team
#
#  This program is free software; you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation; either version 2 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
############################################################################

# %module
# % description: Applies the classification model in parallel to the current region.
# % keyword: raster
# % keyword: classification
# % keyword: statistics
# % keyword: machine learning
# % keyword: trees analysis
# %end

# %option G_OPT_V_INPUT
# % key: area
# % label: Name of vector defining area of interest
# % answer: study_area
# % guisection: Input
# %end

# %option G_OPT_I_GROUP
# % key: group
# % label: Name of input group
# % answer: ml_input
# % guisection: Input
# %end

# %option G_OPT_F_INPUT
# % key: model
# % label: Name of input model file
# % answer: gelsenkirchen_2020_ml_trees_randomforest.gz
# % guisection: Input
# %end

# %option G_OPT_R_OUTPUT
# % key: output
# % label: Name of classified output raster map
# % answer: tree_pixels
# % guisection: Output
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
# % answer: 1000
# % guisection: Parallel processing
# %end


import atexit
import sys
import os
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
        grass.try_rmdir(rmdir)
    grass.del_temp_region()


def main():
    global rm_rasters, tmp_mask_old, rm_vectors, rm_groups, rm_dirs, orig_region

    path = get_lib_path(modname="m.analyse.trees", libname="analyse_trees_lib")
    if path is None:
        grass.fatal("Unable to find the analyse trees library directory")
    sys.path.append(path)
    try:
        from analyse_trees_lib import (
            create_grid,
            set_nprocs,
            verify_mapsets,
        )
    except Exception:
        grass.fatal("m.analyse.trees library is not installed")

    area_vect = options["area"]
    group = options["group"]
    output = options["output"]
    model = options["model"]
    nprocs = int(options["nprocs"])
    tile_size = options["tile_size"]

    nprocs = set_nprocs(nprocs)

    # Test if all required data are there
    g_rasters = grass.read_command(
        "i.group", group=group, flags="lg", quiet=True
    ).split(os.linesep)[:-1]
    for gr in g_rasters:
        if not grass.find_file(name=gr, element="cell")["file"]:
            grass.fatal(_("Raster map <%s> not found" % gr))

    # Creating tiles
    tiles_list, number_tiles = create_grid(tile_size, "grid_cell", area_vect)
    rm_vectors.extend(tiles_list)

    grass.message(_("Applying classification model..."))

    # save the current mapset
    start_cur_mapset = grass.gisenv()["MAPSET"]

    # test nprocs setting
    if number_tiles < nprocs:
        nprocs = number_tiles
    queue = ParallelModuleQueue(nprocs=nprocs)
    output_list = list()

    # Loop over tiles_list
    gisenv = grass.gisenv()
    try:
        for tile_area in tiles_list:
            rm_vectors.append(tile_area)
            tile = tile_area.rsplit("_", 1)[1]
            # Module
            new_mapset = f"tmp_mapset_ml_apply_{tile}_{uuid4()}"
            mapset_path = os.path.join(
                gisenv["GISDBASE"], gisenv["LOCATION_NAME"], new_mapset
            )
            rm_dirs.append(mapset_path)
            tree_output = f"trees_ml_{tile}_{os.getpid()}"
            output_list.append(f"{tree_output}@{new_mapset}")

            param = {
                "area": tile_area,
                "output": tree_output,
                "new_mapset": new_mapset,
                "group": group,
                "model": model,
            }

            r_trees_mlapply_worker = Module(
                "r.trees.mlapply.worker",
                **param,
                run_=False,
            )

            # catch all GRASS outputs to stdout and stderr
            r_trees_mlapply_worker.stdout_ = grass.PIPE
            r_trees_mlapply_worker.stderr_ = grass.PIPE
            queue.put(r_trees_mlapply_worker)
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
            grass.message(_(msg_part))

    # verify that switching back to original mapset worked
    verify_mapsets(start_cur_mapset)

    patch_list = list()
    for worker_output in output_list:
        if grass.find_file(name=worker_output, element="cell")["file"]:
            patch_list.append(worker_output)
        else:
            grass.warning(
                _("Missing classification output %{}").format(worker_output)
            )

    # get outputs from mapsets and patch
    grass.message(_("Patching output from tiles..."))
    if len(patch_list) > 1:
        # merge outputs from tiles and add table
        grass.run_command(
            "r.patch", input=(",").join(patch_list), output=output, quiet=True
        )
    elif len(patch_list) == 1:
        grass.run_command(
            "g.copy", raster=f"{patch_list[0]},{output}", quiet=True
        )

    grass.message(_(f"Created output raster map {output}"))


if __name__ == "__main__":
    options, flags = grass.parser()
    atexit.register(cleanup)
    sys.exit(main())
