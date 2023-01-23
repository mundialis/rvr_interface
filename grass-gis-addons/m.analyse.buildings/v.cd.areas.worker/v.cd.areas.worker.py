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

# %flag
# % key: q
# % description: Calculate quality measures completeness and correctness
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


def detect_changes(**kwargs):

    input = options["input"]
    ref = options["reference"]
    output = options["output"]
    qa_flag = flags["q"]

    grass.message("Closing small gaps in reference map...")
    # remove potential duplicate features in reference layer
    ref_tmp1 = f"{ref}_catdel_{os.getpid()}"
    rm_vectors.append(ref_tmp1)
    grass.run_command(
        "v.category", input=ref, output=ref_tmp1, option="del", cat=-1, quiet=True
    )

    ref_tmp2 = f"{ref}_catdeladd_{os.getpid()}"
    rm_vectors.append(ref_tmp2)
    grass.run_command(
        "v.category",
        input=ref_tmp1,
        output=ref_tmp2,
        option="add",
        type="centroid",
        quiet=True,
    )

    # buffer reference back and forth to remove very thin gaps
    buffdist = 0.5
    buf_tmp1 = f"{ref}_buf_tmp1_{os.getpid()}"
    rm_vectors.append(buf_tmp1)
    buf_tmp2 = f"{ref}_buf_tmp2_{os.getpid()}"
    rm_vectors.append(buf_tmp2)
    grass.run_command(
        "v.buffer",
        input=ref,
        distance=buffdist,
        flags="cs",
        output=buf_tmp1,
        quiet=True,
    )
    grass.run_command(
        "v.buffer",
        input=buf_tmp1,
        distance=-buffdist,
        output=buf_tmp2,
        flags="cs",
        quiet=True,
    )

    # calculate symmetrical difference of two input vector layers
    grass.message(_("Creation of difference vector map..."))
    vector_tmp1 = f"change_vect_tmp1_{os.getpid()}"
    rm_vectors.append(vector_tmp1)
    grass.run_command(
        "v.overlay",
        ainput=buf_tmp2,
        atype="area",
        binput=input,
        btype="area",
        operator="xor",
        output=vector_tmp1,
        quiet=True,
    )

    # filter with area and fractal dimension
    grass.message(_("Cleaning up based on shape and size..."))
    area_col = "area_sqm"
    fd_col = "fractal_d"

    grass.run_command(
        "v.to.db",
        map=vector_tmp1,
        option="area",
        columns=area_col,
        units="meters",
        quiet=True,
    )

    grass.run_command(
        "v.to.db",
        map=vector_tmp1,
        option="fd",
        columns=fd_col,
        units="meters",
        quiet=True,
    )

    grass.run_command(
        "v.db.droprow",
        input=vector_tmp1,
        output=output,
        where=f"{area_col}<{options['min_size']} OR " f"{fd_col}>{options['max_fd']}",
        quiet=True,
    )

    # rename columns and remove unnecessary columns
    columns_raw = list(grass.parse_command("v.info", map=output, flags="cg").keys())
    columns = [item.split("|")[1] for item in columns_raw]
    # initial list of columns to be removed
    dropcolumns = [area_col, fd_col, "b_cat"]
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

    # quality assessment: calculate completeness and correctness
    # completeness = correctly identified area / total area in reference dataset
    # correctness = correctly identified area / total area in input dataset
    if qa_flag:
        grass.message(_("Calculating quality measures..."))

        # intersection to get area that is equal in both layers
        intersect = f"intersect_{os.getpid()}"
        rm_vectors.append(intersect)
        grass.run_command(
            "v.overlay",
            ainput=input,
            atype="area",
            binput=ref_tmp2,
            btype="area",
            operator="and",
            output=intersect,
            quiet=True,
        )

        area_col = "area_sqm"
        area_identified = float(
            list(
                grass.parse_command(
                    "v.to.db",
                    map=intersect,
                    option="area",
                    columns=area_col,
                    units="meters",
                    flags="pc",
                    quiet=True,
                ).keys()
            )[-1].split("|")[1]
        )

        # area input vector
        area_input = float(
            list(
                grass.parse_command(
                    "v.to.db",
                    map=input,
                    option="area",
                    columns=area_col,
                    units="meters",
                    flags="pc",
                    quiet=True,
                ).keys()
            )[-1].split("|")[1]
        )

        # area reference
        area_ref = float(
            list(
                grass.parse_command(
                    "v.to.db",
                    map=ref,
                    option="area",
                    columns=area_col,
                    units="meters",
                    flags="pc",
                    quiet=True,
                ).keys()
            )[-1].split("|")[1]
        )

        # calculate completeness and correctness
        completeness = area_identified / area_ref
        correctness = area_identified / area_input

        grass.message(
            _(
                f"Completeness is: {round(completeness, 2)}. \n"
                f"Correctness is: {round(correctness, 2)}. \n \n"
                f"Completeness = correctly identified area / total "
                f"area in reference dataset \n"
                f"Correctness = correctly identified area / total "
                f"area in input dataset (e.g. extracted buildings)"
            )
        )

def main():

    global rm_vectors

    path = get_lib_path(modname="m.analyse.buildings", libname="analyse_buildings_lib")
    if path is None:
        grass.fatal("Unable to find the analyse buildings library directory")
    sys.path.append(path)
    try:
        from analyse_buildings_lib import get_bins, test_memory, switch_to_new_mapset
    except Exception:
        grass.fatal("m.analyse.buildings library is not installed")

    input = options["input"]
    ref = options["reference"]
    output = options["output"]
    qa_flag = flags["q"]

    grass.message(_(f"Applying change detection to region {area}..."))

    # switch to another mapset for parallel processing
    gisrc, newgisrc, old_mapset = switch_to_new_mapset(new_mapset)

    # area += f"@{old_mapset}"
    # ndom += f"@{old_mapset}"
    # ndvi += f"@{old_mapset}"
    # if options["fnk_vector"]:
    #     fnk_vect += f"@{old_mapset}"
    # if options["fnk_raster"]:
    #     fnk_rast += f"@{old_mapset}"

    grass.run_command(
        "g.region",
        vector=area,
        align=ndom,
        quiet=True,
    )
    grass.message(_(f"Current region (Tile: {area}):\n{grass.region()}"))

    # check input data (nDOM and NDVI)
    # ndom_stats = grass.parse_command("r.univar", map=ndom, flags="g", quiet=True)
    # ndvi_stats = grass.parse_command("r.univar", map=ndvi, flags="g", quiet=True)
    # if int(ndom_stats["n"]) == 0 or int(ndvi_stats["n"] == 0):
    #     grass.warning(
    #         _(f"At least one of {ndom}, {ndvi} not available in {area}. Skipping...")
    #     )
    #     # set GISRC to original gisrc and delete newgisrc
    #     os.environ["GISRC"] = gisrc
    #     grass.utils.try_remove(newgisrc)
    #
    #     return 0

    # start building extraction
    # kwargs = {
    #     "output": output,
    #     "ndom": ndom,
    #     "ndvi_raster": ndvi,
    #     "min_size": min_size,
    #     "max_fd": max_fd,
    #     "ndvi_thresh": ndvi_thresh,
    #     "memory": memory,
    # }
    #
    # if flags["s"]:
    #     kwargs["flags"] = "s"
    # if options["fnk_vector"]:
    #     kwargs["fnk_vector"] = fnk_vect_tmp
    #     kwargs["fnk_column"] = fnk_column
    # elif options["fnk_raster"]:
    #     kwargs["fnk_raster"] = fnk_rast_tmp

    # run building_extraction
    detect_changes(**kwargs)

    # set GISRC to original gisrc and delete newgisrc
    os.environ["GISRC"] = gisrc
    grass.utils.try_remove(newgisrc)

    grass.message(
        _(
            f"Change detection for {area} DONE \n"
            f"Output is: <{output}@{new_mapset}>"
        )
    )
    return 0


if __name__ == "__main__":
    options, flags = grass.parser()
    atexit.register(cleanup)
    main()
