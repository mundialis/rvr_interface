#!/usr/bin/env python3

############################################################################
#
# MODULE:       v.trees.param
# AUTHOR(S):    Lina Krisztian
#
# PURPOSE:      Calculate various tree parameters
# COPYRIGHT:   (C) 2023 - 2024 by mundialis GmbH & Co. KG and the GRASS Development Team
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
# % description: Calculate various tree parameters in parallel.
# % keyword: vector
# % keyword: classification
# % keyword: statistics
# % keyword: trees analysis
# %end

# %option G_OPT_V_INPUT
# % key: treecrowns
# % label: Vector map of tree crowns
# % required: yes
# % guisection: Input
# %end

# %option G_OPT_R_INPUT
# % key: ndom
# % label: Raster map of nDOM
# % required: no
# % guisection: Input
# %end

# %option G_OPT_R_INPUT
# % key: ndvi
# % label: Raster map of NDVI
# % required: no
# % guisection: Input
# %end

# %option G_OPT_V_INPUT
# % key: buildings
# % label: Vector map of buildings
# % required: no
# % guisection: Input
# %end

# %option
# % key: distance_building
# % type: integer
# % label: Range in which neighbouring buildings are searched for
# % required: no
# % guisection: Parameters
# %end

# %option
# % key: distance_tree
# % type: integer
# % label: Range in which neighbouring trees are searched for
# % required: no
# % answer: 500
# % guisection: Parameters
# %end

# %option
# % key: treeparamset
# % label: Set of tree parameters, which should be calculated
# % required: no
# % multiple: yes
# % options: position,hoehe,dm,volumen,flaeche,ndvi,dist_geb,dist_baum
# % answer: position,hoehe,dm,volumen,flaeche,ndvi,dist_geb,dist_baum
# % guisection: Parameters
# %end

# %option G_OPT_MEMORYMB
# % guisection: Parallel processing
# %end

# %option G_OPT_M_NPROCS
# % label: Number of cores for multiprocessing, -2 is the number of available cores - 1
# % answer: -2
# % guisection: Parallel processing
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
mapset_names = []
subset_names = []
location_path = None
nprocs = None
rm_files = []


def cleanup():
    nuldev = open(os.devnull, "w")
    kwargs = {"flags": "f", "quiet": True, "stderr": nuldev}
    for rmvect in subset_names:
        if grass.find_file(name=rmvect, element="vector")["file"]:
            grass.run_command("g.remove", type="vector", name=rmvect, **kwargs)
    # Delete temp_mapsets
    for num, new_mapset in zip(range(nprocs), mapset_names):
        grass.utils.try_rmdir(os.path.join(location_path, new_mapset))
    for rmfile in rm_files:
        try:
            os.remove(rmfile)
        except Exception as e:
            grass.warning(_("Cannot remove file <%s>: %s" % (rmfile, e)))


def main():
    global current_region, mapset_names, subset_names, location_path, nprocs, rm_files

    pid = os.getpid()

    treecrowns = options["treecrowns"]
    ndom = options["ndom"]
    ndvi = options["ndvi"]
    buildings = options["buildings"]
    distance_building = options["distance_building"]
    distance_tree = options["distance_tree"]
    memory = int(options["memory"])
    nprocs = int(options["nprocs"])
    treeparamset = options["treeparamset"].split(",")
    if "dist_geb" in treeparamset and not buildings:
        grass.fatal(_("Need buildings as input."))
    if "ndvi" in treeparamset and not ndvi:
        grass.fatal(_("Need NDVI as input."))
    if "hoehe" in treeparamset and not ndom:
        grass.fatal(_("Need nDOM as input."))

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
            cats_val_file = grass.tempname(12)
            rm_files.append(cats_val_file)
            with open(cats_val_file, "w") as cats_file:
                for val in cats_val:
                    cats_file.write(f"{val}\n")
            subset_ind += size_subset
            grass.run_command(
                "v.extract",
                input=treecrowns,
                output=treecrowns_subsets,
                file=cats_val_file,
                quiet=True,
            )
            # Module
            new_mapset = "tmp_mapset_treeparam_" + sid
            mapset_names.append(new_mapset)
            param = {
                "treecrowns": treecrowns_subsets,
                "treecrowns_complete": treecrowns,
                "treeparamset": treeparamset,
            }
            if ndom:
                param["ndom"] = ndom
            if ndvi:
                param["ndvi"] = ndvi
            if buildings:
                param["buildings"] = buildings
            if distance_building:
                param["distance_building"] = distance_building
            if distance_tree:
                param["distance_tree"] = distance_tree
            v_tree_param = Module(
                "v.trees.param.worker",
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
    grass.message(_(f"Calculated following tree parameters: {treeparamset}"))


if __name__ == "__main__":
    options, flags = grass.parser()
    atexit.register(cleanup)
    main()
