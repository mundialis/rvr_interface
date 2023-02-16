#!/usr/bin/env python3
############################################################################
#
# MODULE:       r.trees.mlapply.worker
# AUTHOR(S):    Markus Metz
# PURPOSE:      Applies the classification model to the current region
# COPYRIGHT:    (C) 2018-2023 by mundialis GmbH & Co. KG and the GRASS
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
# % description: Applies the classification model.
# % keyword: raster
# % keyword: machine learning
# %end

# %option G_OPT_V_INPUT
# % key: area
# % multiple: no
# % description: Input natural tiles as vector map
# %end

# %option G_OPT_I_GROUP
# % key: group
# % multiple: no
# % description: Name of input group
# %end

# %option G_OPT_F_INPUT
# % key: model
# % multiple: no
# % description: Name of input model file
# %end

# %option G_OPT_R_OUTPUT
# % key: output
# % multiple: no
# % description: Name of classified output raster map
# %end

# %option
# % key: new_mapset
# % type: string
# % required: yes
# % key_desc: name
# % description: Name for new mapset
# %end

import sys
import os

import grass.script as grass
from grass.pygrass.utils import get_lib_path


def main():
    path = get_lib_path(modname="m.analyse.trees", libname="analyse_trees_lib")
    if path is None:
        grass.fatal("Unable to find the analyse trees library directory.")
    sys.path.append(path)
    try:
        from analyse_trees_lib import switch_to_new_mapset
    except Exception:
        grass.fatal("m.analyse.trees library is not installed")

    area = options["area"]
    group = options["group"]
    output = options["output"]
    model = options["model"]
    new_mapset = options["new_mapset"]

    # Test if all required data are there
    g_rasters = grass.read_command("i.group", group=group, flags="lg").split(
        os.linesep
    )[:-1]
    for gr in g_rasters:
        if not grass.find_file(name=gr, element="raster")["file"]:
            grass.fatal(_(f"Raster map <{gr}> not found"))
    if not grass.find_file(name=area, element="vector")["file"]:
        grass.fatal(_(f"Vector map <{area}> not found"))

    # set some common environmental variables, like:
    os.environ.update(
        dict(
            GRASS_COMPRESSOR="LZ4",
            GRASS_MESSAGE_FORMAT="plain",
        )
    )

    grass.message(_(f"Applying classification model to region {area}..."))

    # switch to another mapset for parallel postprocessing
    gisrc, newgisrc, old_mapset = switch_to_new_mapset(new_mapset)

    grass.run_command(
        "g.region",
        vector=f"{area}@{old_mapset}",
        align=g_rasters[0],
        quiet=True,
    )
    grass.message(_(f"current region (Tile: {area}):\n{grass.region()}"))

    # mask, otherwise the region is used
    grass.run_command("r.mask", vector=area + "@" + old_mapset, quiet=True)
    grass.run_command("g.copy", group=f"{group}@{old_mapset},{group}")

    # classification
    grass.run_command(
        "r.learn.predict",
        group=group,
        output=output,
        load_model=model,
        chunksize=50000,
        quiet=True,
    )

    grass.run_command("r.mask", flags="r", quiet=True)

    grass.message(_(f"Applying of classification model to region {area} DONE"))

    # set GISRC to original gisrc and delete newgisrc
    os.environ["GISRC"] = gisrc
    grass.utils.try_remove(newgisrc)


if __name__ == "__main__":
    options, flags = grass.parser()
    sys.exit(main())
