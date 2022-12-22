#!/usr/bin/env python3

############################################################################
#
# MODULE:       r.extract.buildings
#
# AUTHOR(S):    Guido Riembauer <riembauer at mundialis.de>
#
# PURPOSE:      Extracts buildings from nDOM, NDVI and FNK
#
#
# COPYRIGHT:	(C) 2021 by mundialis and the GRASS Development Team
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


def freeRAM(unit, percent=100):
    """ The function gives the amount of the percentages of the installed RAM.
    Args:
        unit(string): 'GB' or 'MB'
        percent(int): number of percent which shoud be used of the free RAM
                      default 100%
    Returns:
        memory_MB_percent/memory_GB_percent(int): percent of the free RAM in
                                                  MB or GB

    """
    # use psutil cause of alpine busybox free version for RAM/SWAP usage
    mem_available = psutil.virtual_memory().available
    swap_free = psutil.swap_memory().free
    memory_GB = (mem_available + swap_free)/1024.0**3
    memory_MB = (mem_available + swap_free)/1024.0**2

    if unit == "MB":
        memory_MB_percent = memory_MB * percent / 100.0
        return int(round(memory_MB_percent))
    elif unit == "GB":
        memory_GB_percent = memory_GB * percent / 100.0
        return int(round(memory_GB_percent))
    else:
        grass.fatal("Memory unit <%s> not supported" % unit)


def test_memory():
    # check memory
    memory = int(options['memory'])
    free_ram = freeRAM('MB', 100)
    if free_ram < memory:
        grass.warning(
            "Using %d MB but only %d MB RAM available."
            % (memory, free_ram))
        options['memory'] = free_ram
        grass.warning(
            "Set used memory to %d MB." % (options['memory']))


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

    # switch to another mapset for parallel postprocessing
    gisrc, newgisrc, old_mapset = switch_to_new_mapset(new_mapset)

    area += f"@{old_mapset}"
    ndom += f"@{old_mapset}"
    ndvi += f"@{old_mapset}"
    fnk_vect += f"@{old_mapset}"

    grass.run_command(
        "g.region",
        vector=area,
        align=ndom,
        grow=100,
        quiet=True,
    )
    grass.message(_(f"current region (Tile: {area}):\n{grass.region()}"))

    # check input data
    ndom_stats = grass.parse_command("r.univar", map=ndom, flags="g")
    ndvi_stats = grass.parse_command("r.univar", map=ndvi, flags="g")
    if int(ndom_stats['n']) == 0 or int(ndvi_stats['n'] == 0):
        grass.warning(_(f"At least one of {ndom}, {ndvi} not available in {area}. Skipping..."))
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

    # ENTWEDER:
    # ps = grass.start_command("r.extract.buildings", **param)
    #
    # response = ps.communicate()
    #
    # import pdb; pdb.set_trace()

    # ODER
    dict_to_list = [f"{item[0]}={item[1]}" for item in param.items()]
    #command_str = f"r.extract.buildings {' '.join(dict_to_list)}"
    extract_list = ["r.extract.buildings"]
    extract_list.extend(dict_to_list)
    process = Popen(extract_list, stdout=PIPE, stderr=PIPE)

    response = process.communicate()[1].decode("utf-8").strip()
    import pdb; pdb.set_trace()
    # ENDE

    #if "test_message" in response:
        # grass.message(_("bla"))
        # diese wird von Master aufgefangen -> dort dann dict zusammenbasteln je nach dem was in Log drin ist



    # grass.run_command("r.extract.buildings", **param, quiet=True)

    # set GISRC to original gisrc and delete newgisrc
    os.environ["GISRC"] = gisrc
    grass.utils.try_remove(newgisrc)

    grass.message(_(f"Building extraction for {area} DONE"))
    return 0


if __name__ == "__main__":
    options, flags = grass.parser()
    atexit.register(cleanup)
    main()
