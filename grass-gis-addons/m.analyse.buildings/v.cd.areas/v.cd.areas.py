#!/usr/bin/env python3

############################################################################
#
# MODULE:       v.cd.areas
#
# AUTHOR(S):    Julia Haas <haas at mundialis.de>
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
        # TODO: wee which are used
        from analyse_buildings_lib import get_bins, get_percentile, set_nprocs, verify_mapsets
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

        # create list of tiles
        tiles_list = list(
            grass.parse_command(
                "v.db.select", map=grid, columns="cat", flags="c", quiet=True
            ).keys()
        )
        #tiles_list = [1, 2, 3]

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

        # # divide memory
        # options["memory"] = test_memory(options["memory"])
        # memory = int(int(options["memory"]) / nprocs)

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


                #import pdb; pdb.set_trace()

                param = {
                    "area": tile_area,
                    "output": tile_output,
                    "new_mapset": new_mapset,
                    "input": bu_input,
                    "reference": bu_ref,
                    "min_size": min_size,
                    "max_fd": max_fd
                }

                if flags["q"]:
                    param["flags"] = "q"
                #import pdb; pdb.set_trace()


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
            #grass.run_command("v.cd.areas.worker", **param, quiet=True) # TODO: remove in the end!
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

        # verify that switching back to original mapset worked
        verify_mapsets(start_cur_mapset)

        # get outputs from mapsets and merge (minimize edge effects)
        change_merged = f"change_merged_{os.getpid()}"
        rm_vectors.append(change_merged)
        change_diss = f"change_diss_{os.getpid()}"
        rm_vectors.append(change_diss)
        change_nocats = f"change_nocats_{os.getpid()}"
        rm_vectors.append(change_nocats)
        change_cats = f"change_cats_{os.getpid()}"
        rm_vectors.append(change_cats)

        grass.message(_("Merging output from tiles..."))
        if len(output_list) > 1:

            # merge outputs from tiles and add table
            grass.run_command(
                "v.patch", input=output_list, output=change_merged, quiet=True
            )
            grass.run_command(
                "v.db.addtable",
                map=change_merged,
                columns="value varchar(15)",
                quiet=True,
            )
            grass.run_command(
                "v.db.update",
                map=change_merged,
                column="value",
                value="dissolve",
                quiet=True,
            )

            grass.run_command(
                "v.dissolve",
                input=change_merged,
                column="value",
                output=change_diss,
                quiet=True,
            )

            # split multipolygon and remove potential duplicate features in
            # dissolved layer
            grass.run_command(
                "v.category",
                input=change_diss,
                output=change_nocats,
                option="del",
                cat=-1,
                quiet=True,
            )

            grass.run_command(
                "v.category",
                input=change_nocats,
                output=change_cats,
                option="add",
                type="centroid",
                quiet=True,
            )

            grass.run_command(
                "v.to.db", map=change_cats, option="cat", columns="cat_new", quiet=True
            )

            import pdb; pdb.set_trace()

        # elif len(output_list) == 1:
        #     grass.run_command(
        #         "g.copy", vector=f"{output_list[0]},{buildings_cats}", quiet=True
        #     )


        # filter with area and fractal dimension
        grass.message(_("Cleaning up based on shape and size..."))
        area_col = "area_sqm"
        fd_col = "fractal_d"

        grass.run_command(
            "v.to.db",
            map=change_cats,
            option="area",
            columns=area_col,
            units="meters",
            quiet=True,
        )

        grass.run_command(
            "v.to.db",
            map=change_cats,
            option="fd",
            columns=fd_col,
            units="meters",
            quiet=True,
        )

        grass.run_command(
            "v.db.droprow",
            input=change_cats,
            output=cd_output,
            where=f"{area_col}<{options['min_size']} OR " f"{fd_col}>{options['max_fd']}",
            quiet=True,
        )

        import pdb; pdb.set_trace()

        # rename columns and remove unnecessary columns
        columns_raw = list(grass.parse_command("v.info", map=output, flags="cg").keys())
        columns = [item.split("|")[1] for item in columns_raw]
        # initial list of columns to be removed
        dropcolumns = [area_col, fd_col, "b_cat", "cat_new"]
        for col in columns:
            items = list(
                grass.parse_command(
                    "v.db.select", flags="c", map=output, columns=col, quiet=True
                ).keys()
            )
            if len(items) < 2 or col.startswith("a_"):
                # empty cols return a length of 1 with ['']
                # all columns from reference ("a_*") loose information during buffer
                dropcolumns.append(col)
            elif col.startswith("b_"):
                if col != "b_cat":
                    grass.run_command(
                        "v.db.renamecolumn",
                        map=output,
                        column=f"{col},{col[2:]}",
                        quiet=True,
                    )

        # add column "source" and populate with name of ref or input map
        grass.run_command(
            "v.db.addcolumn",
            map=output,
            columns="source VARCHAR(100)",
            quiet=True,
        )
        grass.run_command(
            "v.db.update",
            map=output,
            column="source",
            value=input.split("@")[0],
            where="b_cat IS NOT NULL",
            quiet=True,
        )
        grass.run_command(
            "v.db.update",
            map=output,
            column="source",
            value=ref.split("@")[0],
            where="a_cat IS NOT NULL",
            quiet=True,
        )
        grass.run_command(
            "v.db.dropcolumn", map=output, columns=(",").join(dropcolumns), quiet=True
        )

        grass.message(_(f"Created output vector map <{output}>"))

        import pdb; pdb.set_trace()

if __name__ == "__main__":
    options, flags = grass.parser()
    atexit.register(cleanup)
    main()
