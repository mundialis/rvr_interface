#!/usr/bin/env python3

############################################################################
#
# MODULE:       m.import.rvr
#
# AUTHOR(S):    Anika Weinmann
#
# PURPOSE:      TODO
#
#
# COPYRIGHT:	(C) 2023 by mundialis and the GRASS Development Team
#
#		This program is free software under the GNU General Public
#		License (>=v2). Read the file COPYING that comes with GRASS
#		for details.
#
#############################################################################

# %Module
# % description: TODO.
# % keyword: raster
# % keyword: vector
# % keyword: import
# %end

# %option G_OPT_MEMORYMB
# %end

# %option G_OPT_F_INPUT
# % key: fnk_file
# % required: no
# % multiple: no
# % label: The vector file (e.g. GPKG or Shapefile format) of the Flächennutzungskatalog (FNK)
# % description: Is required for the processing type gebauededetection and optional for dachbegruenung
# %end

# %option G_OPT_F_INPUT
# % key: reference_buildings_file
# % required: no
# % multiple: no
# % label: The vector file (e.g. GPKG or Shapefile format) of the building reference data
# % description: Needed for the change detection after the gebauededetection
# %end

# %option G_OPT_F_INPUT
# % key: tree_file
# % required: no
# % multiple: no
# % label: The vector file (e.g. GPKG or Shapefile format) of the tree data
# % description: The tree data can be used inside the processing of dachbegruenung
# %end


# %option
# % key: type
# % required: yes
# % multiple: yes
# % label: The type of processing for which the data should be imported
# % options: gebauededetection,dachbegruenung,einzelbaumerkennung
# % answer: gebauededetection,dachbegruenung,einzelbaumerkennung
# %end

# %flag
# % key: c
# % label: Only check input parameters
# %end

# %flag
# % key: b
# % label: Download buildings for reference buildings or houserings from openNRW if files are not set
# %end


import atexit
import os
import psutil
import grass.script as grass

# initialize global vars
opennrw_buildings = "https://www.opengeodata.nrw.de/produkte/geobasis/lk/akt" \
"/hu_shp/hu_EPSG4647_Shape.zip"
# dict to list the needed datasets for the processing type with the following
# values: (resolution, purpose, requiered, needed input information, import
#          type, output name)
needed_datasets = {
    # TODO split: gebauededetection,dachbegruenung
    "gebauededetection": {
        # vector
        "fnk": (None, "output", True, "fnk_file", "vector"),
        "reference_buildings": (
            None, "output", False, "reference_buildings_file", "vector"
        ),
        # # raster
        # "dop": (0.5, "output", True, ""),
        # # "ndvi": (??, "output", True),
        # # "ndom": (??, "output", True),
        # # "dgm": (??, "ndom", True),
        # # "dsm": (??, "ndom", True),
    },
    "dachbegruenung": {
        # vector
        "fnk": (None, "output", False, "fnk_file", "vector"),
        "trees": (None, "output", False, "tree_file", "vector"),
        "houserings": (
            None, "output", True, "houserings_file", "vector"
        ),
        # # raster
        # "dop": (0.5, "output", True),
        # # "ndvi": (??, "output", True),
        # # "ndom": (??, "output", True),
        # # "dgm": (??, "ndom", True),
        # # "dsm": (??, "ndom", True),
    },
    # TODO
    "einzelbaumerkennung": {
        "top": "",
        "s2_statistics": ""
    }
}


def cleanup():
    grass.message(_("Cleaning up ..."))
    # TODO
    # import pdb; pdb.set_trace()
    # nulldev = open(os.devnull, "w")
    # kwargs = {"flags": "f", "quiet": True, "stderr": nulldev}
    # for rmg in rm_groups:
    #     if grass.find_file(name=rmg, element="group")["file"]:
    #         group_rasters = grass.parse_command(
    #             "i.group", flags="lg", group=rmg
    #         )
    #         rm_rasters.extend(group_rasters)
    #         grass.run_command("g.remove", type="group", name=rmg, **kwargs)
    # for rmg_wor in rm_groups_wo_rasters:
    #     if grass.find_file(name=rmg_wor, element="group")["file"]:
    #         grass.run_command("g.remove", type="group", name=rmg_wor, **kwargs)
    # for rmrast in rm_rasters:
    #     if grass.find_file(name=rmrast, element="raster")["file"]:
    #         grass.run_command("g.remove", type="raster", name=rmrast, **kwargs)
    # for rmvect in rm_vectors:
    #     if grass.find_file(name=rmvect, element="vector")["file"]:
    #         grass.run_command("g.remove", type="vector", name=rmvect, **kwargs)
    # for rmfile in rm_files:
    #     if os.path.isfile(rmfile):
    #         os.remove(rmfile)
    # for rmdir in rm_dirs:
    #     if os.path.isdir(rmdir):
    #         shutil.rmtree(rmdir)
    # if orig_region is not None:
    #     if grass.find_file(name=orig_region, element="windows")["file"]:
    #         grass.run_command("g.region", region=orig_region)
    #         grass.run_command(
    #             "g.remove", type="region", name=orig_region, **kwargs
    #         )
    # for rmreg in rm_regions:
    #     if grass.find_file(name=rmreg, element="windows")["file"]:
    #         grass.run_command(
    #             "g.remove", type="region", name=rmreg, **kwargs
    #         )
    # strds = grass.parse_command("t.list", type="strds")
    # mapset = grass.gisenv()["MAPSET"]
    # for rm_s in rm_strds:
    #     if f"{rm_s}@{mapset}" in strds:
    #         grass.run_command(
    #             "t.remove",
    #             flags="rf",
    #             type="strds",
    #             input=rm_s,
    #             quiet=True,
    #             stderr=nulldev,
    #         )


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


def import_vector(file, output_name):
    grass_file = grass.find_file(name=output_name, element="vector")["file"]
    grass_overwrite = (
        True if "GRASS_OVERWRITE" in os.environ and
        os.environ["GRASS_OVERWRITE"] == "1" else False
    )
    if not grass_file or grass_overwrite:
        grass.run_command(
            "v.import",
            input=file,
            output=output_name,
            extent="region",
            quiet=True,
        )
        grass.message(_(f"Vector map <{output_name}> imported."))
    else:
        grass.warning(_(
            f"Vector map <{output_name}> already exists."
            "If you want to reimport all existing data use --o and if you "
            f"only want to reimport {output_name}, please delete the vector "
            f"map first with:\n<g.remove -f type=vector name={output_name}>"
        ))


def check_data(data, optionname):
    """Check if data exists in right format (depending on the option name)"""
    if "file" in optionname:
        if not os.path.isfile(data):
            grass.fatal(_(f"The data file <{val[3]}> does not exists."))


def import_data(data, datatype, output_name):
    """Importing data depending on the data type"""
    if datatype:
        import_vector(data, output_name)
    else:
        grass.warning(_(
            f"Import of data type <{datatype}> not yet supported."
        ))


def main():

    types = options["type"].split(",")

    # check if needed pathes to data are set
    grass.message(_("Checking input parameters ..."))
    for type in types:
        for data, val in needed_datasets[type].items():
            if data == "reference_buildings_file"
            if val[2] and not options[val[3]]:
                grass.fatal(_(
                    f"For the processing type <{type}> the option <{val[3]}> "
                    f"has to be set. Please set <{val[3]}>."
                ))
            elif not options[val[3]]:
                grass.warning(_(f"The {data} data is not used."))
            else:
                check_data(options[val[3]], val[3])

    if flags["c"]:
        exit(0)

    grass.message(_("Importing needed data sets ..."))
    for type in types:
        for data, val in needed_datasets[type].items():
            if options[val[3]]:
                import_data(options[val[3]], val[4], data)

    grass.message(_("Importing needed data sets done"))



if __name__ == "__main__":
    options, flags = grass.parser()
    atexit.register(cleanup)
    main()
