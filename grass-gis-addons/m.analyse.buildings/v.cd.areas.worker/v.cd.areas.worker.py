#!/usr/bin/env python3

############################################################################
#
# MODULE:       v.cd.areas
#
# AUTHOR(S):    Julia Haas
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

    bu_input = kwargs["input"]
    bu_ref = kwargs["reference"]
    output = kwargs["output"]

    grass.message("Closing small gaps in reference map...")
    # buffer reference back and forth to remove very thin gaps
    buffdist = 0.5
    buf_tmp1 = f"bu_ref_buf_tmp1_{os.getpid()}"
    rm_vectors.append(buf_tmp1)
    buf_tmp2 = f"bu_ref_buf_tmp2_{os.getpid()}"
    rm_vectors.append(buf_tmp2)
    grass.run_command(
        "v.buffer",
        input=bu_ref,
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

    # remove potential duplicate features in reference layer
    grass.message("Removing potential duplicate features in reference map...")
    ref_tmp1 = f"bu_ref_catdel_{os.getpid()}"
    rm_vectors.append(ref_tmp1)
    grass.run_command(
        "v.category", input=buf_tmp2, output=ref_tmp1, option="del", cat=-1, quiet=True
    )

    ref_tmp2 = f"bu_ref_catdeladd_{os.getpid()}"
    rm_vectors.append(ref_tmp2)
    grass.run_command(
        "v.category",
        input=ref_tmp1,
        output=ref_tmp2,
        option="add",
        type="centroid",
        quiet=True,
    )

    # calculate symmetrical difference of two input vector layers
    grass.message(_("Creation of difference vector map..."))
    output_vect = f"{output}"
    rm_vectors.append(output_vect)
    grass.run_command(
        "v.overlay",
        ainput=ref_tmp2,  # reference
        atype="area",
        binput=bu_input,  # buildings
        btype="area",
        operator="xor",
        output=output_vect,
        quiet=True,
    )

    # quality assessment: calculate completeness and correctness
    # completeness = correctly identified area / total area in reference dataset
    # correctness = correctly identified area / total area in input dataset
    if "flags" in kwargs:
        grass.message(_("Calculating areas for quality measures..."))

        # intersection to get area that is equal in both layers
        intersect = f"intersect_{os.getpid()}"
        rm_vectors.append(intersect)
        grass.run_command(
            "v.overlay",
            ainput=ref_tmp2,  # reference
            atype="area",
            binput=bu_input,  # buildings
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
                    map=bu_input,
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
                    map=ref_tmp2,
                    option="area",
                    columns=area_col,
                    units="meters",
                    flags="pc",
                    quiet=True,
                ).keys()
            )[-1].split("|")[1]
        )

        grass.message(
            _(
                f"Area calculation DONE \n"
                f"area identified is: <{area_identified}> \n"
                f"area buildings input is: <{area_input}> \n"
                f"area buildings reference is: <{area_ref}>"
            )
        )


def main():

    global rm_vectors

    path = get_lib_path(modname="m.analyse.buildings", libname="analyse_buildings_lib")
    if path is None:
        grass.fatal("Unable to find the analyse buildings library directory")
    sys.path.append(path)
    try:
        from analyse_buildings_lib import switch_to_new_mapset
    except Exception:
        grass.fatal("m.analyse.buildings library is not installed")

    bu_input = options["input"]
    bu_ref = options["reference"]
    output = options["output"]
    min_size = options["min_size"]
    max_fd = options["max_fd"]
    new_mapset = options["new_mapset"]
    area = options["area"]
    qa_flag = flags["q"]

    grass.message(_(f"Applying change detection to region {area}..."))

    # switch to another mapset for parallel processing
    gisrc, newgisrc, old_mapset = switch_to_new_mapset(new_mapset)

    area += f"@{old_mapset}"
    bu_input += f"@{old_mapset}"
    bu_ref += f"@{old_mapset}"

    grass.run_command(
        "g.region",
        vector=area,
        quiet=True,
    )

    # clip building input to region
    bu_input_clipped = f"bu_input_clipped_{os.getpid()}"
    rm_vectors.append(bu_input_clipped)
    grass.run_command(
        "v.clip", input=bu_input, output=bu_input_clipped, flags="r", quiet=True
    )

    # clip buildings reference to region
    bu_ref_clipped = f"bu_ref_clipped_{os.getpid()}"
    rm_vectors.append(bu_ref_clipped)
    grass.run_command(
        "v.clip", input=bu_ref, output=bu_ref_clipped, flags="r", quiet=True
    )

    # check if buildings remain
    warn_msg = "At least one of the inputs is missing. Skipping..."
    db_connection_input = grass.parse_command(
        "v.db.connect", map=bu_input_clipped, flags="p", quiet=True
    )

    db_connection_ref = grass.parse_command(
        "v.db.connect", map=bu_ref_clipped, flags="p", quiet=True
    )
    if not db_connection_input or not db_connection_ref:
        grass.warning(_(f"{warn_msg}"))

        return 0

    grass.message(_(f"Current region (Tile: {area}):\n{grass.region()}"))

    # start change detection
    kwargs = {
        "output": output,
        "input": bu_input_clipped,
        "reference": bu_ref_clipped,
        "min_size": min_size,
        "max_fd": max_fd,
    }

    if qa_flag:
        kwargs["flags"] = "q"

    # run building_extraction
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
