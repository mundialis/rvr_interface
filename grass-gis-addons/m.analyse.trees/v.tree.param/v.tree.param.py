#!/usr/bin/env python3

############################################################################
#
# MODULE:       v.tree.param
# AUTHOR(S):    Lina Krisztian
#
# PURPOSE:      Calculate various tree parameters
# COPYRIGHT:   (C) 2023 by mundialis GmbH & Co. KG and the GRASS Development Team
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
#############################################################################

# %Module
# % description: Calculate various tree parameters in parallel
# % keyword: vector
# % keyword: classification
# %end

# %option G_OPT_V_INPUT
# % key: treecrowns
# % description: Vector map of tree crowns
# % required: yes
# %end

# %option G_OPT_R_INPUT
# % key: ndom
# % description: Raster map of nDOM
# % required: yes
# %end

# %option G_OPT_R_INPUT
# % key: ndvi
# % description: Raster map of NDVI
# % required: yes
# %end

# %option G_OPT_V_INPUT
# % key: buildings
# % description: Vector map of buildings
# % required: yes
# %end

# %option
# % key: distance_building
# % type: integer
# % description: range in which neighbouring buildings are searched for
# % required: no
# %end

# %option
# % key: distance_tree
# % type: integer
# % description: range in which neighbouring trees are searched for
# % required: no
# % answer: 500
# %end

# %option G_OPT_M_NPROCS
# % description: Number of cores for multiprocessing, -2 is the number of available cores - 1
# % answer: -2
# %end

# %option G_OPT_MEMORYMB
# % description: Memory which is used by all processes (it is divided by nprocs for each single parallel process)
# %end

import os
import sys
import atexit
import multiprocessing as mp
import math

import grass.script as grass
from grass.pygrass.modules import Module, ParallelModuleQueue
from grass.pygrass.utils import get_lib_path


# initialize global vars
current_region = None
mapset_names = None
subset_names = None
location_path = None
nprocs = None


def cleanup():
    nuldev = open(os.devnull, "w")
    kwargs = {"flags": "f", "quiet": True, "stderr": nuldev}
    if grass.find_file(name=current_region, element="windows")["file"]:
        grass.message(_("Setting region back."))
        grass.run_command("g.region", region=current_region)
        grass.run_command(
            "g.remove", type="region", name=current_region, **kwargs
        )
    for rmvect in subset_names:
        if grass.find_file(name=rmvect, element="vector")["file"]:
            grass.run_command("g.remove", type="vector", name=rmvect, **kwargs)
    # Delete temp_mapsets
    for num, new_mapset in zip(range(nprocs), mapset_names):
        grass.utils.try_rmdir(os.path.join(location_path, new_mapset))


def main():
    global current_region, mapset_names, subset_names, location_path, nprocs

    pid = os.getpid()

    treecrowns = options["treecrowns"]
    ndom = options["ndom"]
    ndvi = options["ndvi"]
    buildings = options["buildings"]
    distance_building = options["distance_building"]
    distance_tree = options["distance_tree"]
    memory = int(options["memory"])
    nprocs = int(options["nprocs"])

    path = get_lib_path(modname="m.analyse.trees", libname="analyse_trees_lib")
    if path is None:
        grass.fatal("Unable to find the analyse trees library directory.")
    sys.path.append(path)
    try:
        from analyse_trees_lib import (
            freeRAM,
            verify_mapsets,
        )
    except Exception:
        grass.fatal("analyse_trees_lib missing.")

    # Test memory and nprocs settings
    if nprocs == -2:
        nprocs = mp.cpu_count() - 1 if mp.cpu_count() > 1 else 1
    else:
        nprocs_real = mp.cpu_count()
        if nprocs > nprocs_real:
            grass.warning(
                "Using %d parallel processes but only %d CPUs available."
                % (nprocs, nprocs_real)
            )
    free_ram = freeRAM("MB", 100)
    if free_ram < memory:
        grass.warning(
            "Using %d MB but only %d MB RAM available." % (memory, free_ram)
        )

    # Test if required addon is installed
    if not grass.find_program("v.centerpoint", "--help"):
        grass.fatal(
            _(
                "The 'v.centerpoint' module was not found,"
                " install it first:" + "\n" + "g.extension v.centerpoint"
            )
        )

    # set some common environmental variables, like:
    os.environ.update(
        dict(
            GRASS_COMPRESSOR="LZ4",
            GRASS_MESSAGE_FORMAT="plain",
        )
    )

    # set correct extension and resolution
    current_region = f"current_region_{pid}"
    grass.run_command("g.region", save=current_region)
    grass.message(_("Set region to:"))
    grass.run_command("g.region", raster=ndom, flags="ap")

    # save current mapset
    start_cur_mapset = grass.gisenv()["MAPSET"]

    treecrowns_cat = list(
        grass.parse_command(
            "v.db.select", map=treecrowns, columns="cat", flags="c"
        ).keys()
    )
    size_subset = math.ceil(len(treecrowns_cat) / nprocs)

    queue = ParallelModuleQueue(nprocs=nprocs)
    use_memory = round(memory / nprocs)
    mapset_names = list()
    subset_names = list()
    subset_ind = 0
    try:
        for num in range(nprocs):
            # use pid to create a unique mapset and vector subset name
            sid = f"{num}_{pid}"
            # split treecrowns in subsets
            treecrowns_subsets = f"{treecrowns}_temp_{sid}"
            subset_names.append(treecrowns_subsets)
            # in case that category values have "gaps" (e.g. 1,2,5,6,7),
            # select cat-values from treecrowns_cat-list:
            cats_val = treecrowns_cat[subset_ind : subset_ind + size_subset]
            subset_ind += size_subset
            grass.run_command(
                "v.extract",
                input=treecrowns,
                output=treecrowns_subsets,
                cats=cats_val,
                quiet=True,
            )
            # Module
            new_mapset = "tmp_mapset_treeparam_" + sid
            mapset_names.append(new_mapset)
            param = {
                "ndom": ndom,
                "ndvi": ndvi,
                "buildings": buildings,
                "treecrowns": treecrowns_subsets,
                "treecrowns_complete": treecrowns,
            }
            if distance_building:
                param["distance_building"] = distance_building
            if distance_tree:
                param["distance_tree"] = distance_tree
            v_tree_param = Module(
                "v.tree.param.worker",
                **param,
                new_mapset=new_mapset,
                memory=use_memory,
                run_=False,
            )
            # catch all GRASS outputs to stdout and stderr
            v_tree_param.stdout_ = grass.PIPE
            v_tree_param.stderr_ = grass.PIPE
            queue.put(v_tree_param)
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

    # verify that switching the mapset worked
    location_path = verify_mapsets(start_cur_mapset)

    # patching
    grass.message(_("Patching the treecrown subsets ..."))
    treecrown_subset_mapset = list()
    if nprocs > 1:
        for subset_name, mapset_name in zip(subset_names, mapset_names):
            treecrown_subset_mapset.append(f"{subset_name}@{mapset_name}")
        grass.run_command(
            "v.patch",
            input=treecrown_subset_mapset,
            output=treecrowns,
            flags="e",
            overwrite=True,
            quiet=True,
        )
    else:
        # if only single mapset, no patching needed
        # instead rename/overwrite treecrown-vector map with
        # in temp mapset created temp-subset-treecrown-vector-map
        grass.run_command(
            "g.copy",
            vector=f"{subset_names[0]}@{mapset_names[0]},{treecrowns}",
            overwrite=True,
        )


if __name__ == "__main__":
    options, flags = grass.parser()
    atexit.register(cleanup)
    main()
