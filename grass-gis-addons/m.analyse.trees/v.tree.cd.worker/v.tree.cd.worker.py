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

# %option
# % key: output_ending
# % required: yes
# % multiple: yes
# % label: Suffix for three output vector maps
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


# def detect_changes(**kwargs):

#     vec_inp_t1 = kwargs["inp_t1"]
#     vec_inp_t2 = kwargs["inp_t2"]
#     output = kwargs["output"]
#     output_ending = kwargs["output_ending"]

#     output_unchanged = f"{output}_{output_ending.split(',')[0]}"
#     same_trees(vec_inp_t1, vec_inp_t2, output_unchanged)
#     output_onlyt1 = f"{output}_{output_ending.split(',')[1]}"
#     output_onlyt2 = f"{output}_{output_ending.split(',')[2]}"
#     diff_trees(vec_inp_t1, vec_inp_t2, output_onlyt1, output_onlyt2)

#     # # remove potential duplicate features
#     # grass.message("Removing potential duplicate features in reference map...")
#     # ref_tmp1 = f"bu_ref_catdel_{os.getpid()}"
#     # rm_vectors.append(ref_tmp1)
#     # grass.run_command(
#     #     "v.category",
#     #     input=buf_tmp2,
#     #     output=ref_tmp1,
#     #     option="del",
#     #     cat=-1,
#     #     quiet=True,
#     # )

#     # ref_tmp2 = f"bu_ref_catdeladd_{os.getpid()}"
#     # rm_vectors.append(ref_tmp2)
#     # grass.run_command(
#     #     "v.category",
#     #     input=ref_tmp1,
#     #     output=ref_tmp2,
#     #     option="add",
#     #     type="centroid",
#     #     quiet=True,
#     # )

#     return output_unchanged, output_onlyt1, output_onlyt2


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
    output_ending = options["output_ending"]

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
    grass.message(_(f"Current region (Tile: {area}):\n{grass.region()}"))

    # clip trees input t1 to region (input t1 is complete map from orig mapset)
    vec_inp_t1_clipped = f"vec_inp_t1_clipped_{os.getpid()}"
    rm_vectors.append(vec_inp_t1_clipped)
    grass.run_command(
        "v.clip",
        input=vec_inp_t1,
        output=vec_inp_t1_clipped,
        flags="r",
        quiet=True
    )

    # clip trees input t2 to region (input t2 is complete map from orig mapset)
    vec_inp_t2_clipped = f"vec_inp_t2_clipped_{os.getpid()}"
    rm_vectors.append(vec_inp_t2_clipped)
    grass.run_command(
        "v.clip",
        input=vec_inp_t2,
        output=vec_inp_t2_clipped,
        flags="r",
        quiet=True
    )

    # check if trees in both maps
    db_connection_inp_t1 = grass.parse_command(
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

    # get attribute columns (except cat)
    # NOTE: assume both inputs have same attribute columns
    attr_col = [el.split('|')[1] for el in list(grass.parse_command(
        "v.info",
        map=vec_inp_t1,
        flags="c"
    ))]
    attr_col.remove('cat')

    # map output names:
    output_unchanged = f"{output}_{output_ending.split(',')[0]}"
    output_onlyt1 = f"{output}_{output_ending.split(',')[1]}"
    output_onlyt2 = f"{output}_{output_ending.split(',')[2]}"
    if not db_connection_inp_t1:
        # if only t2 in region contained, simplify:
        output_unchanged = str()
        output_onlyt1 = str()
        grass.run_command(
            "g.rename",
            vector=f"{vec_inp_t2_clipped},{output_onlyt2}"
        )
        # adjust columns, so it can be patched with attributes
        # outside of worker
        grass.run_command(
            "v.db.addcolumn",
            map=output_onlyt2,
            columns=['a_cat integer', 'b_cat integer']
        )
        output_onlyt2 += f"@{new_mapset}"
    elif not db_connection_inp_t2:
        # if only t1 in region contained, simplify:
        output_unchanged = str()
        grass.run_command(
            "g.rename",
            vector=f"{vec_inp_t1_clipped},{output_onlyt1}"
        )
        # adjust columns, so it can be patched with attributes
        # outside of worker
        grass.run_command(
            "v.db.addcolumn",
            map=output_onlyt1,
            columns=['a_cat integer', 'b_cat integer']
        )
        output_onlyt1 += f"@{new_mapset}"
        output_onlyt2 = str()
    else:
        # start change detection
        same_trees(vec_inp_t1, vec_inp_t2, output_unchanged)
        diff_trees(vec_inp_t1, vec_inp_t2, output_onlyt1, output_onlyt2)
        for vecmap in [output_unchanged, output_onlyt1, output_onlyt2]:
            for attr_el in attr_col:
                # difference calculation only for reasonable columns
                if attr_el in ["hoe_max",
                               "hoe_perc95",
                               "flaeche",
                               "Dm",
                               "ndvi_ave",
                               "ndvi_med",
                               "volumen",
                               "dist_geb",
                               "dist_baum"]:
                    grass.run_command(
                        "v.db.update",
                        map=vecmap,
                        column=f"b_{attr_el}",
                        query_column=f"b_{attr_el}-a_{attr_el}"  # t2-t1
                    )
                # keep only one column (t2 attr values for non-diff columns)
                grass.run_command(
                    "v.db.renamecolumn",
                    map=vecmap,
                    column=f"b_{attr_el},{attr_el}",
                )
                grass.run_command(
                    "v.db.dropcolumn",
                    map=vecmap,
                    columns=f"a_{attr_el}",
                )
        # kwargs = {
        #     "output": output,
        #     "inp_t1": vec_inp_t1_clipped,
        #     "inp_t2": vec_inp_t2_clipped,
        #     "min_size": min_size,
        #     "max_fd": max_fd,
        #     "output_ending": output_ending,
        # }
        # output_unchanged, output_onlyt1, output_onlyt2 = detect_changes(
        #     **kwargs
        #     )
        output_unchanged += f"@{new_mapset}"
        output_onlyt1 += f"@{new_mapset}"
        output_onlyt2 += f"@{new_mapset}"

    # set GISRC to original gisrc and delete newgisrc
    os.environ["GISRC"] = gisrc
    grass.utils.try_remove(newgisrc)

    grass.message(
        _(f"Change detection for {area} DONE \n"
          f"Output is: <{output_unchanged},"
          f"{output_onlyt1},"
          f"{output_onlyt2}>")
    )


if __name__ == "__main__":
    options, flags = grass.parser()
    atexit.register(cleanup)
    main()
