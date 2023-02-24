#!/usr/bin/env python3

############################################################################
#
# MODULE:       r.import.ndsm_nrw
#
# AUTHOR(S):    Guido Riembauer and Anika Weinmann
#
# PURPOSE:      calculates nDSM from DSM and digital terrain model (DTM) data
#
#
# COPYRIGHT:	(C) 2021-2023 by mundialis and the GRASS Development Team
#
# 		This program is free software under the GNU General Public
# 		License (>=v2). Read the file COPYING that comes with GRASS
# 		for details.
#
#############################################################################

# %Module
# % description: Calculates nDSM from DSM and digital terrain model (DTM) data.
# % keyword: raster
# % keyword: import
# % keyword: digital elevation model
# % keyword: digital surface model
# %end

# %option G_OPT_M_DIR
# % key: directory
# % required: no
# % multiple: no
# % label: Directory path where to download and temporarily store the DTM data. If not set, the data will be downloaded to a temporary directory. The downloaded data will be removed after the import.
# %end

# %option G_OPT_MEMORYMB
# %end

# %option G_OPT_R_INPUT
# % key: dsm
# % type: string
# % required: yes
# % multiple: no
# % description: Name of input DSM raster map
# % guisection: Input
# %end

# %option G_OPT_R_OUTPUT
# % key: output_ndsm
# % type: string
# % required: yes
# % multiple: no
# % description: Name for output nDSM raster map
# % guisection: Output
# %end

# %option G_OPT_R_INPUT
# % key: dtm
# % type: string
# % required: no
# % multiple: no
# % description: Name of input DTM map. If none is defined, NRW DTM is downloaded automatically
# % guisection: Input
# %end

# %option G_OPT_R_OUTPUT
# % key: output_dtm
# % type: string
# % required: no
# % multiple: no
# % description: Name for output DTM raster map
# % guisection: Output
# %end

import atexit
import psutil
import os
import grass.script as grass

# initialize global vars
rm_rasters = []
old_region = None


def cleanup():
    nuldev = open(os.devnull, "w")
    kwargs = {"flags": "f", "quiet": True, "stderr": nuldev}
    for rmrast in rm_rasters:
        if grass.find_file(name=rmrast, element="cell")["file"]:
            grass.run_command("g.remove", type="raster", name=rmrast, **kwargs)
    if old_region:
        grass.run_command("g.region", region=old_region)
        grass.run_command("g.remove", type="region", name=old_region, **kwargs)


def freeRAM(unit, percent=100):
    """The function gives the amount of the percentages of the installed RAM.
    Args:
        unit(string): 'GB' or 'MB'
        percent(int): number of percent which should be used of the free RAM
                      default 100%
    Returns:
        memory_MB_percent/memory_GB_percent(int): percent of the free RAM in
                                                  MB or GB

    """
    # use psutil cause of alpine busybox free version for RAM/SWAP usage
    mem_available = psutil.virtual_memory().available
    swap_free = psutil.swap_memory().free
    memory_GB = (mem_available + swap_free) / 1024.0**3
    memory_MB = (mem_available + swap_free) / 1024.0**2

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
    memory = int(options["memory"])
    free_ram = freeRAM("MB", 100)
    if free_ram < memory:
        grass.warning(
            "Using %d MB but only %d MB RAM available." % (memory, free_ram)
        )
        options["memory"] = free_ram
        grass.warning("Set used memory to %d MB." % (options["memory"]))


def main():
    global rm_rasters, old_region
    dsm = options["dsm"]
    dtm = options["dtm"]
    if not dtm:
        if not grass.find_program("r.import.dtm_nrw", "--help"):
            grass.fatal(
                _(
                    "The 'r.import.dtm_nrw' module was not found"
                    ", install it first:\ng.extension "
                    "r.import.dtm_nrw url=path/to/addon"
                )
            )

    # save old region
    old_region = "saved_region_1_{}".format(os.getpid())
    grass.run_command("g.region", save=old_region)
    grass.message(_("Filling NoData areas in DSM..."))
    grass.run_command("g.region", align=dsm)
    dsm_nullsfilled = "dsm_nullsfilled_{}".format(os.getpid())
    rm_rasters.append(dsm_nullsfilled)
    test_memory()
    grass.run_command(
        "r.fillnulls",
        input=dsm,
        output=dsm_nullsfilled,
        method="bilinear",
        memory=options["memory"],
        quiet=True,
    )
    # downloading and importing DTM
    if not dtm:
        grass.message(_("Retrieving NRW DTM1 data..."))
        tmp_dtm_1 = "tmp_dtm_1_{}".format(os.getpid())
        rm_rasters.append(tmp_dtm_1)
        kwargs_dtm = {"output": tmp_dtm_1}
        if options["directory"]:
            kwargs_dtm["directory"] = options["directory"]
        if options["memory"]:
            kwargs_dtm["memory"] = options["memory"]
        grass.run_command("r.import.dtm_nrw", **kwargs_dtm)
    else:
        grass.message(_(f"Using raster <{options['dtm']}> as DTM data..."))
        tmp_dtm_1 = dtm
    # resampling dtm to match dsm resolution
    grass.run_command("g.region", raster=dsm_nullsfilled, quiet=True)
    if options["output_dtm"]:
        dtm_resampled = options["output_dtm"]
    else:
        dtm_resampled = "tmp_dtm_1_resampled_{}".format(os.getpid())
        rm_rasters.append(dtm_resampled)
    grass.run_command(
        "r.resamp.interp",
        input=tmp_dtm_1,
        output=dtm_resampled,
        method="bilinear",
        quiet=True,
    )
    # calculate first version of ndsm
    grass.message(_("nDSM creation..."))
    ndsm_raw = "ndsm_raw_{}".format(os.getpid())
    rm_rasters.append(ndsm_raw)
    grass.run_command(
        "r.mapcalc",
        expression="{} = float({} - {})".format(
            ndsm_raw, dsm_nullsfilled, dtm_resampled
        ),
        quiet=True,
    )
    # resample ndsm to match original region
    grass.run_command("g.region", region=old_region, quiet=True)
    ndsm_resampled_tmp = "ndsm_resampled_tmp_{}".format(os.getpid())
    rm_rasters.append(ndsm_resampled_tmp)
    grass.run_command(
        "r.resamp.interp",
        input=ndsm_raw,
        output=ndsm_resampled_tmp,
        method="bilinear",
        quiet=True,
    )
    grass.run_command(
        "r.mapcalc",
        expression="{} = float({})".format(
            options["output_ndsm"], ndsm_resampled_tmp
        ),
        quiet=True,
    )
    grass.message(
        _("Created nDSM raster map <{}>").format(options["output_ndsm"])
    )


if __name__ == "__main__":
    options, flags = grass.parser()
    atexit.register(cleanup)
    main()
