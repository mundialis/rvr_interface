#!/usr/bin/env python3

############################################################################
#
# MODULE:       v.tree.cd.worker
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
# % key: new_mapset
# % type: string
# % required: yes
# % multiple: no
# % key_desc: name
# % description: Name for new mapset
# %end

# %option G_OPT_V_INPUT
# % key: area
# % multiple: no
# % description: Input natural tiles as vector map
# %end


import atexit
import os
import sys

import grass.script as grass
from grass.pygrass.utils import get_lib_path


# initialize global vars
rm_vectors = []


def cleanup():
    nuldev = open(os.devnull, "w")
    kwargs = {"flags": "f", "quiet": True, "stderr": nuldev}
    for rmv in rm_vectors:
        if grass.find_file(name=rmv, element="vector")["file"]:
            grass.run_command("g.remove", type="vector", name=rmv, **kwargs)


def same_trees(vec_inp_t1, vec_inp_t2, output):
    # intersection
    grass.run_command(
        "v.overlay",
        ainput=vec_inp_t1,
        atype="area",
        binput=vec_inp_t2,
        btype="area",
        operator="and",
        output=output,
        quiet=True,
    )


def diff_trees(vec_inp_t1, vec_inp_t2, output_onlyt1, output_onlyt2):
    grass.run_command(
        "v.overlay",
        ainput=vec_inp_t1,
        atype="area",
        binput=vec_inp_t2,
        btype="area",
        operator="not",
        output=output_onlyt1,
        quiet=True,
    )
    grass.run_command(
        "v.overlay",
        ainput=vec_inp_t2,
        atype="area",
        binput=vec_inp_t1,
        btype="area",
        operator="not",
        output=output_onlyt2,
        quiet=True,
    )


def detect_changes(**kwargs):

    vec_inp_t1 = kwargs["inp_t1"]
    vec_inp_t2 = kwargs["inp_t2"]
    output = kwargs["output"]

    output_unchanged = f"{output}_unchanged_trees"
    same_trees(vec_inp_t1, vec_inp_t2, output_unchanged)
    output_onlyt1 = f"{output}_only_{vec_inp_t1}"
    output_onlyt2 = f"{output}_only_{vec_inp_t2}"
    diff_trees(vec_inp_t1, vec_inp_t2, output_onlyt1, output_onlyt2)

    # # remove potential duplicate features
    # grass.message("Removing potential duplicate features in reference map...")
    # ref_tmp1 = f"bu_ref_catdel_{os.getpid()}"
    # rm_vectors.append(ref_tmp1)
    # grass.run_command(
    #     "v.category",
    #     input=buf_tmp2,
    #     output=ref_tmp1,
    #     option="del",
    #     cat=-1,
    #     quiet=True,
    # )

    # ref_tmp2 = f"bu_ref_catdeladd_{os.getpid()}"
    # rm_vectors.append(ref_tmp2)
    # grass.run_command(
    #     "v.category",
    #     input=ref_tmp1,
    #     output=ref_tmp2,
    #     option="add",
    #     type="centroid",
    #     quiet=True,
    # )


def main():

    global rm_vectors

    path = get_lib_path(modname="m.analyse.trees", libname="analyse_trees_lib")
    if path is None:
        grass.fatal("Unable to find the analyse trees library directory")
    sys.path.append(path)
    try:
        from analyse_trees_lib import switch_to_new_mapset
    except Exception:
        grass.fatal("m.analyse.trees library is not installed")

    vec_inp_t1 = options["inp_t1"]
    vec_inp_t2 = options["inp_t2"]
    output = options["output"]
    min_size = options["min_size"]
    max_fd = options["max_fd"]
    new_mapset = options["new_mapset"]
    area = options["area"]

    grass.message(_(f"Applying change detection to region {area}..."))

    # switch to another mapset for parallel processing
    gisrc, newgisrc, old_mapset = switch_to_new_mapset(new_mapset)

    area += f"@{old_mapset}"
    vec_inp_t1 += f"@{old_mapset}"
    vec_inp_t2 += f"@{old_mapset}"

    grass.run_command(
        "g.region",
        vector=area,
        quiet=True,
    )

    # clip trees input t1 to region
    vec_inp_t1_clipped = f"vec_inp_t1_clipped_{os.getpid()}"
    rm_vectors.append(vec_inp_t1_clipped)
    grass.run_command(
        "v.clip",
        input=vec_inp_t1,
        output=vec_inp_t1_clipped,
        flags="r",
        quiet=True
    )

    # clip trees input t2 to region
    vec_inp_t2_clipped = f"vec_inp_t2_clipped_{os.getpid()}"
    rm_vectors.append(vec_inp_t2_clipped)
    grass.run_command(
        "v.clip",
        input=vec_inp_t2,
        output=vec_inp_t2_clipped,
        flags="r",
        quiet=True
    )

    # check if trees remain
    warn_msg = "At least one of the inputs is missing. Skipping..."
    db_connection_input = grass.parse_command(
        "v.db.connect",
        map=vec_inp_t1_clipped,
        flags="p",
        quiet=True
    )

    db_connection_inp_t2 = grass.parse_command(
        "v.db.connect",
        map=vec_inp_t2_clipped,
        flags="p",
        quiet=True
    )
    # TODO: Aufsplitten in 4 Fälle beide Inputs verfügbar,
    # beide Inputs nicht da, nur einer von beiden da
    if not db_connection_input or not db_connection_inp_t2:
        grass.warning(_(f"{warn_msg}"))

        return 0

    grass.message(_(f"Current region (Tile: {area}):\n{grass.region()}"))

    # start change detection
    kwargs = {
        "output": output,
        "input": vec_inp_t1_clipped,
        "inp_t2": vec_inp_t2_clipped,
        "min_size": min_size,
        "max_fd": max_fd,
    }
    detect_changes(**kwargs)

    # set GISRC to original gisrc and delete newgisrc
    os.environ["GISRC"] = gisrc
    grass.utils.try_remove(newgisrc)

    grass.message(
        _(f"Change detection for {area} DONE \n"
          f"Output is: <{output}@{new_mapset}>")
    )

    return 0


if __name__ == "__main__":
    options, flags = grass.parser()
    atexit.register(cleanup)
    main()
