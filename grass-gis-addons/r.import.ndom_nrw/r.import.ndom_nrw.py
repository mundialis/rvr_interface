#!/usr/bin/env python3

############################################################################
#
# MODULE:       r.import.ndom_nrw
#
# AUTHOR(S):    Guido Riembauer <riembauer at mundialis.de>
#
# PURPOSE:      calculates nDOM from DOM and DGM data
#
#
# COPYRIGHT:	(C) 2021 by mundialis and the GRASS Development Team
#
#		This program is free software under the GNU General Public
#		License (>=v2). Read the file COPYING that comes with GRASS
#		for details.
#
#############################################################################

#%Module
#% description: Calculates nDOM from DOM and DGM data.
#% keyword: raster
#% keyword: import
#% keyword: digital elevation model
#% keyword: digital surface model
#%end

#%option G_OPT_M_DIR
#% key: directory
#% required: no
#% multiple: no
#% label: Directory path where to download and temporarily store the DGM data. If not set, the data will be downloaded to a temporary directory. The downloaded data will be removed after the import.
#%end

#%option G_OPT_R_INPUT
#% key: dgm
#% type: string
#% required: no
#% multiple: no
#% description: Name of input DGM raster map
#% guisection: Input
#%end

#%option G_OPT_MEMORYMB
#%end

#%option G_OPT_R_INPUT
#% key: dom
#% type: string
#% required: yes
#% multiple: no
#% description: Name of input DOM raster map
#% guisection: Input
#%end

#%option G_OPT_R_OUTPUT
#% key: output_ndom
#% type: string
#% required: yes
#% multiple: no
#% description: Name for output nDOM raster map
#% guisection: Output
#%end

#%option G_OPT_R_INPUT
#% key: dgm
#% type: string
#% required: no
#% multiple: no
#% description: Name of input DGM map. If none is defined, NRW DGM is downloaded automatically
#% guisection: Input
#%end

#%option G_OPT_R_OUTPUT
#% key: output_dgm
#% type: string
#% required: no
#% multiple: no
#% description: Name for output DGM raster map
#% guisection: Output
#%end

import atexit
import psutil
import os
import grass.script as grass

# initialize global vars
rm_rasters = []
old_region = None


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
    if old_region:
        grass.run_command(
            'g.region', region=old_region)
        grass.run_command(
            'g.remove', type='region', name=old_region, **kwargs)


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

    global rm_rasters, old_region
    dom = options["dom"]
    dgm = options["dgm"]
    if not dgm:
        if not grass.find_program('r.import.dgm_nrw', '--help'):
            grass.fatal(_("The 'r.import.dgm_nrw' module was not found"
                          ", install it first:\ng.extension "
                          "r.import.dgm_nrw url=path/to/addon"))

    # save old region
    old_region = "saved_region_1_{}".format(os.getpid())
    grass.run_command("g.region", save=old_region)
    grass.message(_("Filling NoData areas in DOM..."))
    grass.run_command("g.region", align=dom)
    dom_nullsfilled = "dom_nullsfilled_{}".format(os.getpid())
    rm_rasters.append(dom_nullsfilled)
    test_memory()
    grass.run_command("r.fillnulls", input=dom, output=dom_nullsfilled,
                      method="bilinear", memory=options["memory"], quiet=True)
    # downloading and importing DGM
    if not dgm:
        grass.message(_("Retrieving NRW DGM1 data..."))
        tmp_dgm_1 = "tmp_dgm_1_{}".format(os.getpid())
        rm_rasters.append(tmp_dgm_1)
        kwargs_dgm = {"output": tmp_dgm_1}
        if options["directory"]:
            kwargs_dgm["directory"] = options["directory"]
        if options["memory"]:
            kwargs_dgm["memory"] = options["memory"]
        grass.run_command("r.import.dgm_nrw", **kwargs_dgm)
    else:
        grass.message(_(f"Using raster <{options['dgm']}> as DGM data..."))
        tmp_dgm_1 = dgm
    # resampling dgm to match dom resolution
    grass.run_command("g.region", raster=dom_nullsfilled, quiet=True)
    if options["output_dgm"]:
        dgm_resampled = options["output_dgm"]
    else:
        dgm_resampled = "tmp_dgm_1_resampled_{}".format(os.getpid())
        rm_rasters.append(dgm_resampled)
    grass.run_command("r.resamp.interp", input=tmp_dgm_1, output=dgm_resampled,
                      method="bilinear", quiet=True)
    # calculate first version of ndom
    grass.message(_("nDOM creation..."))
    ndom_raw = "ndom_raw_{}".format(os.getpid())
    rm_rasters.append(ndom_raw)
    grass.run_command("r.mapcalc", expression="{} = float({} - {})".format(
        ndom_raw, dom_nullsfilled, dgm_resampled), quiet=True)
    # resample ndom to match original region
    grass.run_command("g.region", region=old_region, quiet=True)
    ndom_resampled_tmp = "ndom_resampled_tmp_{}".format(os.getpid())
    rm_rasters.append(ndom_resampled_tmp)
    grass.run_command("r.resamp.interp", input=ndom_raw,
                      output=ndom_resampled_tmp, method="bilinear", quiet=True)
    grass.run_command("r.mapcalc", expression = "{} = float({})".format(
        options["output_ndom"], ndom_resampled_tmp), quiet=True)
    grass.message(_("Created nDOM raster map <{}>").format(
        options["output_ndom"]))


if __name__ == "__main__":
    options, flags = grass.parser()
    atexit.register(cleanup)
    main()
