#!/usr/bin/env python3

############################################################################
#
# MODULE:       v.trees.cd.worker
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
# % keyword: worker
# %end

# %option G_OPT_V_INPUT
# % key: inp_t1
# %label: Name of the input vector layer of one timestamp/year
# %end

# %option G_OPT_V_INPUT
# % key: inp_t2
# % label: Name of the input vector layer of another timestamp/year, to compare
# %end

# %option G_OPT_V_OUTPUT
# % label: Basename of output vector maps
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
# % key: output_suffix
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


def same_trees(vec_inp_t1, vec_inp_t2, output, attr_col):
    # function: get congruent trees and update attribute table
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
    # check if area-column given:
    if "area_sqm" in attr_col:
        # keep 'area_sqm' of vec t1 for filtering overlap of congruent areas
        # (outside of the worker)
        area_col_t1 = "area_sqm_t1"
        grass.run_command(
            "v.db.addcolumn",
            map=output,
            column=area_col_t1,
            quiet=True,
        )
        grass.run_command(
            "v.db.update",
            map=output,
            column=area_col_t1,
            query_column="a_area_sqm",
            quiet=True,
        )
    else:
        grass.warning(
            _(
                "Could not find column <area_sqm>, "
                "which is required for filtering congruent treecrowns."
                "You might need to run 'v.tree.param' first on the input data."
            )
        )
    # difference calculations for congruent trees:
    for attr_el in attr_col:
        # difference calculation only for reasonable columns
        if attr_el in [
            "height_max",
            "height_perc95",
            "area_sqm",
            "diameter",
            "ndvi_ave",
            "ndvi_med",
            "volume",
            "dist_bu",
            "dist_tree",
        ]:
            grass.run_command(
                "v.db.update",
                map=output,
                column=f"b_{attr_el}",
                query_column=f"b_{attr_el}-a_{attr_el}",  # t2-t1
            )
        # keep only one column
        # t2 (most recent) attr values for non-diff columns
        grass.run_command(
            "v.db.renamecolumn",
            map=output,
            column=f"b_{attr_el},{attr_el}",
        )
        grass.run_command(
            "v.db.dropcolumn",
            map=output,
            columns=f"a_{attr_el}",
        )


def diff_trees(vec_inp_t1, vec_inp_t2, output_onlyt1, output_onlyt2, attr_col):
    # function: get changed trees
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
    # kepp only relevant columns after overlay (from a-input)
    for vecmap in [output_onlyt1, output_onlyt2]:
        for attr_el in attr_col:
            grass.run_command(
                "v.db.renamecolumn",
                map=vecmap,
                column=f"a_{attr_el},{attr_el}",
            )
            grass.run_command(
                "v.db.dropcolumn",
                map=vecmap,
                columns=f"b_{attr_el}",
            )


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
    new_mapset = options["new_mapset"]
    area = options["area"]
    output_suffix = options["output_suffix"]

    grass.message(_(f"Applying change detection to region {area}..."))

    # switch to another mapset for parallel processing
    gisrc, newgisrc, old_mapset = switch_to_new_mapset(new_mapset)

    area += f"@{old_mapset}"
    
    vec_inp_t1 = (
        f"{vec_inp_t1}@{old_mapset}"
        if "@" not in vec_inp_t1
        else vec_inp_t1
    )
    
    vec_inp_t2 = (
        f"{vec_inp_t2}@{old_mapset}"
        if "@" not in vec_inp_t2
        else vec_inp_t2
    )
    
    # set region to current tile (area)
    grass.run_command(
        "g.region",
        vector=area,
        quiet=True,
    )
    grass.message(_(f"Current region (Tile: {area}):\n{grass.region()}"))

    # -------- check if trees in both maps:
    # clip trees input t1 to region (input t1 is complete map from orig mapset)
    vec_inp_t1_clipped = f"vec_inp_t1_clipped_{os.getpid()}"
    rm_vectors.append(vec_inp_t1_clipped)
    grass.run_command(
        "v.clip",
        input=vec_inp_t1,
        output=vec_inp_t1_clipped,
        flags="r",
        quiet=True,
    )
    # clip trees input t2 to region (input t2 is complete map from orig mapset)
    vec_inp_t2_clipped = f"vec_inp_t2_clipped_{os.getpid()}"
    rm_vectors.append(vec_inp_t2_clipped)
    grass.run_command(
        "v.clip",
        input=vec_inp_t2,
        output=vec_inp_t2_clipped,
        flags="r",
        quiet=True,
    )
    # check in which maps are trees
    db_connection_inp_t1 = grass.parse_command(
        "v.db.connect", map=vec_inp_t1_clipped, flags="p", quiet=True
    )
    db_connection_inp_t2 = grass.parse_command(
        "v.db.connect", map=vec_inp_t2_clipped, flags="p", quiet=True
    )

    # -------- compute three output maps:
    # map output names
    output_congruent = f"{output}_{output_suffix.split(',')[0]}"
    output_onlyt1 = f"{output}_{output_suffix.split(',')[1]}"
    output_onlyt2 = f"{output}_{output_suffix.split(',')[2]}"
    # case distinction:
    if not db_connection_inp_t1 and not db_connection_inp_t2:
        # in some cases (border effects) there might be a tree-tile identified
        # outside the worker, even though no tree-map is contained within tile
        gmessage = (
            f"No trees within tile {area} in mapset: {new_mapset}."
            f"Skipping..."
        )
    elif not db_connection_inp_t1:
        # if only t2 in region/current tile contained, simplify:
        grass.run_command(
            "g.rename", vector=f"{vec_inp_t2_clipped},{output_onlyt2}"
        )
        # adjust columns, so it can be patched with attributes
        # outside of worker
        grass.run_command(
            "v.db.addcolumn",
            map=output_onlyt2,
            columns=["a_cat integer", "b_cat integer"],
        )
        grass.run_command(
            "v.db.update",
            map=output_onlyt2,
            column="a_cat",
            query_column="cat",
            quiet=True,
        )
        # needed outside worker to get list of vector maps for patching
        output_onlyt2 += f"@{new_mapset}"
        gmessage = (
            f"Change detection for {area} DONE \n"
            f"Output is: <,,{output_onlyt2}>"
        )
    elif not db_connection_inp_t2:
        # if only t1 in region/current tile contained, simplify:
        grass.run_command(
            "g.rename", vector=f"{vec_inp_t1_clipped},{output_onlyt1}"
        )
        # adjust columns, so it can be patched with attributes
        # outside of worker
        grass.run_command(
            "v.db.addcolumn",
            map=output_onlyt1,
            columns=["a_cat integer", "b_cat integer"],
        )
        grass.run_command(
            "v.db.update",
            map=output_onlyt1,
            column="a_cat",
            query_column="cat",
            quiet=True,
        )
        # needed outside worker to get list of vector maps for patching
        output_onlyt1 += f"@{new_mapset}"
        gmessage = (
            f"Change detection for {area} DONE \n"
            f"Output is: <,{output_onlyt1},>"
        )
    else:
        # in case both maps are within region/current tile:

        # get attribute columns (except cat)
        #   - needed for renaming/updating attribute columns
        # NOTE: assume both inputs have same attribute columns
        attr_col = [
            el.split("|")[1]
            for el in list(
                grass.parse_command("v.info", map=vec_inp_t1, flags="c")
            )
        ]
        attr_col.remove("cat")

        # calculate three output maps
        same_trees(vec_inp_t1, vec_inp_t2, output_congruent, attr_col)
        diff_trees(
            vec_inp_t1, vec_inp_t2, output_onlyt1, output_onlyt2, attr_col
        )
        # needed outside worker to get list of vector maps for patching
        output_congruent += f"@{new_mapset}"
        output_onlyt1 += f"@{new_mapset}"
        output_onlyt2 += f"@{new_mapset}"
        gmessage = (
            f"Change detection for {area} DONE \n"
            f"Output is: <{output_congruent},"
            f"{output_onlyt1},"
            f"{output_onlyt2}>"
        )

    # set GISRC to original gisrc and delete newgisrc
    os.environ["GISRC"] = gisrc
    grass.utils.try_remove(newgisrc)

    grass.message(_(gmessage))


if __name__ == "__main__":
    options, flags = grass.parser()
    atexit.register(cleanup)
    main()
