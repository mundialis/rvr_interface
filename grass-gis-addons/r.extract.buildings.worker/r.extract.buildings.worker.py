#!/usr/bin/env python3

############################################################################
#
# MODULE:       r.extract.buildings.worker
#
# AUTHOR(S):    Julia Haas <haas at mundialis.de>
#               Guido Riembauer <riembauer at mundialis.de>
#
# PURPOSE:      Extracts buildings from nDOM, NDVI and FNK
#
# COPYRIGHT:	(C) 2023 by mundialis and the GRASS Development Team
#
#		This program is free software under the GNU General Public
#		License (>=v2). Read the file COPYING that comes with GRASS
#		for details.
#
#############################################################################

# %Module
# % description: Extracts buildings from nDOM, NDVI and FNK
# % keyword: raster
# % keyword: statistics
# % keyword: change detection
# % keyword: classification
# %end

# %option G_OPT_R_INPUT
# % key: ndom
# % type: string
# % required: yes
# % multiple: no
# % label: Name of the nDOM
# %end

# %option G_OPT_R_INPUT
# % key: ndvi_raster
# % type: string
# % required: yes
# % multiple: no
# % label: Name of the NDVI raster
# %end

# %option G_OPT_R_INPUTS
# % key: fnk_vector
# % type: string
# % required: yes
# % multiple: no
# % label: Vector map containing Flaechennutzungskatalog
# %end

# %option G_OPT_R_INPUTS
# % key: fnk_column
# % type: string
# % required: yes
# % multiple: no
# % label: Integer column containing FNK-code
# %end

# %option
# % key: min_size
# % type: integer
# % required: no
# % multiple: no
# % label: Minimum size of buildings in sqm
# % answer: 20
# %end

# %option
# % key: max_fd
# % type: double
# % required: no
# % multiple: no
# % label: Maximum value of fractal dimension of identified objects (see v.to.db)
# % answer: 2.1
# %end

# %option
# % key: ndvi_perc
# % type: integer
# % required: no
# % multiple: no
# % label: ndvi percentile in vegetated areas to use for thresholding
# %end

# %option
# % key: ndvi_thresh
# % type: integer
# % required: no
# % multiple: no
# % label: define fix NDVI threshold (on a scale from 0-255) instead of estimating it from FNK
# %end

# %option G_OPT_MEMORYMB
# %end

# %option G_OPT_R_OUTPUT
# % key: output
# % type: string
# % required: yes
# % multiple: no
# % description: Name for output vector map
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
# % key: s
# % description: segment image based on nDOM and NDVI before building extraction
# %end

# %rules
# % exclusive: ndvi_perc, ndvi_thresh
# % required: ndvi_perc, ndvi_thresh
# %end

import atexit
import psutil
import os
import grass.script as grass
import shutil
from subprocess import Popen, PIPE

# initialize global vars
rm_rasters = []
rm_vectors = []
rm_groups = []
tmp_mask_old = None


def cleanup():
    nuldev = open(os.devnull, 'w')
    kwargs = {
        'flags': 'f',
        'quiet': True,
        'stderr': nuldev
    }
    for rmrast in rm_rasters:
        if grass.find_file(name=rmrast, element='raster')['file']:
            grass.run_command(
                'g.remove', type='raster', name=rmrast, **kwargs)
    for rmv in rm_vectors:
        if grass.find_file(name=rmv, element='vector')['file']:
            grass.run_command(
                'g.remove', type='vector', name=rmv, **kwargs)
    for rmgroup in rm_groups:
        if grass.find_file(name=rmgroup, element='group')['file']:
            grass.run_command(
                'g.remove', type='group', name=rmgroup, **kwargs)
    if grass.find_file(name='MASK', element='raster')['file']:
        try:
            grass.run_command("r.mask", flags='r', quiet=True)
        except:
            pass
    # reactivate potential old mask
    if tmp_mask_old:
        grass.run_command('r.mask', raster=tmp_mask_old, quiet=True)


def switch_to_new_mapset(new_mapset):
    """The function switches to a new mapset and changes the GISRC file for
    parallel processing.

    Args:
        new_mapset (string): Unique name of the new mapset
    Returns:
        gisrc (string): The path of the old GISRC file
        newgisrc (string): The path of the new GISRC file
        old_mapset (string): The name of the old mapset
    """
    # current gisdbase, location
    env = grass.gisenv()
    gisdbase = env["GISDBASE"]
    location = env["LOCATION_NAME"]
    old_mapset = env["MAPSET"]

    grass.message("New mapset. %s" % new_mapset)
    grass.utils.try_rmdir(os.path.join(gisdbase, location, new_mapset))

    gisrc = os.environ["GISRC"]
    newgisrc = "%s_%s" % (gisrc, str(os.getpid()))
    grass.try_remove(newgisrc)
    shutil.copyfile(gisrc, newgisrc)
    os.environ["GISRC"] = newgisrc

    grass.message("GISRC: %s" % os.environ["GISRC"])
    grass.run_command("g.mapset", flags="c", mapset=new_mapset)

    # verify that switching of the mapset worked
    cur_mapset = grass.gisenv()["MAPSET"]
    if cur_mapset != new_mapset:
        grass.fatal(
            "new mapset is %s, but should be %s" % (cur_mapset, new_mapset)
        )
    return gisrc, newgisrc, old_mapset


# def get_percentile(raster, percentile):
#     return float(list((grass.parse_command(
#         'r.quantile', input=raster, percentiles=percentile, quiet=True)).keys())[0].split(':')[2])


def main():

    global rm_rasters, tmp_mask_old, rm_vectors, rm_groups

    ndom = options['ndom']
    ndvi = options['ndvi_raster']
    fnk_vect = options['fnk_vector']
    fnk_column = options['fnk_column']
    min_size = options['min_size']
    max_fd = options['max_fd']
    ndvi_perc = options['ndvi_perc']
    ndvi_thresh = options['ndvi_thresh']
    memory = options['memory']
    output_vect = options['output']
    new_mapset = options['new_mapset']
    area = options['area']

    grass.message(_(f"Applying building extraction to region {area}..."))

    # switch to another mapset for parallel processing
    gisrc, newgisrc, old_mapset = switch_to_new_mapset(new_mapset)

    area += f"@{old_mapset}"
    ndom += f"@{old_mapset}"
    ndvi += f"@{old_mapset}"
    fnk_vect += f"@{old_mapset}"

    grass.run_command(
        "g.region",
        vector=area,
        align=ndom,
        #grow=100,
        quiet=True,
    )
    grass.message(_(f"current region (Tile: {area}):\n{grass.region()}"))

    # check input data (nDOM and NDVI)
    ndom_stats = grass.parse_command("r.univar", map=ndom, flags="g")
    ndvi_stats = grass.parse_command("r.univar", map=ndvi, flags="g")
    if int(ndom_stats['n']) == 0 or int(ndvi_stats['n'] == 0):
        grass.warning(_(f"At least one of {ndom}, {ndvi} not available in {area}. Skipping..."))
        # set GISRC to original gisrc and delete newgisrc
        os.environ["GISRC"] = gisrc
        grass.utils.try_remove(newgisrc)

        return 0

    # start building extraction
    param = {
        "output": output_vect,
        "ndom": ndom,
        "ndvi_raster": ndvi,
        "fnk_vector": fnk_vect,
        "fnk_column": fnk_column,
        "min_size": min_size,
        "max_fd": max_fd,
        "memory": memory
    }

    if ndvi_thresh:
        param["ndvi_thresh"] = ndvi_thresh
    if ndvi_perc:
        param["ndvi_perc"] = ndvi_perc
    if flags["s"]:
        param["flags"] = "s"

    # run r.extract buildings
    grass.run_command("r.extract.buildings", **param, quiet=True)

    # set GISRC to original gisrc and delete newgisrc
    os.environ["GISRC"] = gisrc
    grass.utils.try_remove(newgisrc)

    grass.message(_(f"Building extraction for {area} DONE \n"
                    f"Output is: <{output_vect}@{new_mapset}>"))
    return 0


if __name__ == "__main__":
    options, flags = grass.parser()
    atexit.register(cleanup)
    main()
