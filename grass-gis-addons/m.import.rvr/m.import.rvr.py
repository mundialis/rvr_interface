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
# % description: Required for the processing type gebaeudedetection and optional for dachbegruenung
# %end

# %option G_OPT_F_INPUT
# % key: reference_buildings_file
# % required: no
# % multiple: no
# % label: The vector file (e.g. GPKG or Shapefile format) of the building reference data
# % description: Needed for the change detection after the gebaeudedetection
# %end

# %option G_OPT_F_INPUT
# % key: houserings_file
# % required: no
# % multiple: no
# % label: The vector file (e.g. GPKG or Shapefile format) of the house ring data
# % description: Required inside the processing of dachbegruenung
# %end

# %option G_OPT_F_INPUT
# % key: tree_file
# % required: no
# % multiple: no
# % label: The vector file (e.g. GPKG or Shapefile format) of the tree data
# % description: The tree data can be used inside the processing of dachbegruenung
# %end

# TODO: Frage an JH, MM, LK DOP und TOP gleich behandeln?
# %option G_OPT_M_DIR
# % key: dop_dir
# % required: no
# % multiple: no
# % label: The directory where the digital orthophots (DOPs) are stored as GeoTifs
# % description: The DOPs are required for the processing of gebaeudedetection and dachbegruenung
# %end

# %option
# % key: type
# % required: yes
# % multiple: yes
# % label: The type of processing for which the data should be imported
# % options: gebaeudedetection,dachbegruenung,einzelbaumerkennung
# % answer: gebaeudedetection,dachbegruenung,einzelbaumerkennung
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
from glob import glob

# initialize global vars
orig_region = None
rm_rasters = list()
rm_groups = list()
# dict to list the needed datasets for the processing type with the following
# values: (resolution, purpose, requiered, needed input information, import
#          type, output name)
needed_datasets = {
    "gebaeudedetection": {
        # vector
        "fnk": (None, "output", True, "fnk_file", "vector"),
        "reference_buildings": (
            None, "output", False, "reference_buildings_file", "vector"
        ),
        # raster
        "dop": (0.5, "output", True, "dop_dir", "rasterdir"),
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
            None, "output", True, "houserings_file", "buildings"
        ),
        # raster
        "dop": (0.5, "output", True, "dop_dir", "rasterdir"),
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
    nulldev = open(os.devnull, "w")
    kwargs = {"flags": "f", "quiet": True, "stderr": nulldev}
    # TODO
    # import pdb; pdb.set_trace()
    for rmg in rm_groups:
        if grass.find_file(name=rmg, element="group")["file"]:
            group_rasters = grass.parse_command(
                "i.group", flags="lg", group=rmg
            )
            rm_rasters.extend(group_rasters)
            grass.run_command("g.remove", type="group", name=rmg, **kwargs)
    # for rmg_wor in rm_groups_wo_rasters:
    #     if grass.find_file(name=rmg_wor, element="group")["file"]:
    #         grass.run_command("g.remove", type="group", name=rmg_wor, **kwargs)
    for rmrast in rm_rasters:
        if grass.find_file(name=rmrast, element="raster")["file"]:
            grass.run_command("g.remove", type="raster", name=rmrast, **kwargs)
    # for rmvect in rm_vectors:
    #     if grass.find_file(name=rmvect, element="vector")["file"]:
    #         grass.run_command("g.remove", type="vector", name=rmvect, **kwargs)
    # for rmfile in rm_files:
    #     if os.path.isfile(rmfile):
    #         os.remove(rmfile)
    # for rmdir in rm_dirs:
    #     if os.path.isdir(rmdir):
    #         shutil.rmtree(rmdir)
    if orig_region is not None:
        if grass.find_file(name=orig_region, element="windows")["file"]:
            grass.run_command("g.region", region=orig_region)
            grass.run_command(
                "g.remove", type="region", name=orig_region, **kwargs
            )
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


def check_data_exists(data, optionname):
    """Check if data exist in right format (depending on the option name)"""
    if "file" in optionname:
        if not os.path.isfile(data):
            grass.fatal(_(f"The data file <{data}> does not exists."))
    elif "dir" in optionname:
        if not os.path.isdir(data):
            grass.fatal(_(f"The data directory <{data}> does not exists."))


def check_addon(addon, url=None):
    """Check if addon is installed.
    Args:
        addon (str): Name of the addon
        url (str):   Url to download the addon
    """
    if not grass.find_program(addon, "--help"):
        msg = (
            f"The '{addon}' module was not found, install  it first:\n"
            f"g.extension {addon}"
        )
        if url:
            msg += f" url={url}"
        grass.fatal(_(msg))


def check_data(ptype, data, val):
    """TODO
    Args:
        ptype (str): processing type (gebaeudedetection, dachbegruenung or
                     einzelbaumerkennung)
        data (str):  TODO
        val (tuple): TODO
    """
    if data in ["reference_buildings", "houserings"]:
        # check if data is required
        if val[2] and options[val[3]]:
            check_data_exists(options[val[3]], val[3])
        elif val[2] and not flags["b"]:
            grass.fatal(_(
                f"For the processing type <{ptype}> the option <{val[3]}> "
                f"has to be set or the data can be downloaded from "
                "openNRW for this set the flag '-b'. Please set the "
                f"option <{val[3]}> or the flag '-b'."
            ))
        elif val[2] and flags["b"]:
            check_addon("v.alkis.buildings.import", "TODO")
            grass.message(_(
                f"The data <{data}> will be downloaded from openNRW."
            ))
        else:
            grass.message(_(f"The {data} data is not used."))
    elif val[2] and not options[val[3]]:
        grass.fatal(_(
            f"For the processing type <{ptype}> the option <{val[3]}> "
            f"has to be set. Please set <{val[3]}>."
        ))
    elif not options[val[3]]:
        grass.message(_(f"The {data} data is not used."))
    else:
        check_data_exists(options[val[3]], val[3])


def decorator_check_grass_data(grass_data_type):
    def decorator(function):
        def wrapper_check_grass_data(*args, **kwargs):
            output_name = kwargs["output_name"]
            grass_file = grass.find_file(
                name=output_name, element=grass_data_type, mapset="."
            )["file"]
            grass_overwrite = (
                True if "GRASS_OVERWRITE" in os.environ and
                os.environ["GRASS_OVERWRITE"] == "1" else False
            )
            if not grass_file or grass_overwrite:
                function(*args, **kwargs)
                grass.message(_(
                    f"The {grass_data_type} map <{output_name}> imported."
                ))
            else:
                grass.warning(_(
                    f"Vector map <{output_name}> already exists."
                    "If you want to reimport all existing data use --o and if "
                    f"you only want to reimport {output_name}, please delete "
                    "the vector map first with:\n"
                    f"<g.remove -f type=vector name={output_name}>"
                ))
        return wrapper_check_grass_data
    return decorator


@decorator_check_grass_data("vector")
def import_vector(file, output_name):
    """Importing vector data if does not exists
    Args:
        file (str):        The path of the vector data file
        output_name (str): The output name for the vector
    """
    grass.run_command(
        "v.import",
        input=file,
        output=output_name,
        extent="region",
        quiet=True,
    )


@decorator_check_grass_data("vector")
def import_buildings_from_opennrw(output_name):
    """Download builings from openNRW and import them"""
    grass.run_command(
        "v.alkis.buildings.import",
        flags="r",
        output=output_name,
        federal_state="Nordrhein-Westfalen",
        quiet=True,
    )


def import_buildings(file, output_name):
    """Importing vector data if does not exists
    Args:
        file (str) .......... The path of the vector data file
        output_name (str) ... The output name for the vector
    """
    if file:
        import_vector(file, output_name=output_name)
    elif flags["b"]:
        import_buildings_from_opennrw(output_name=output_name)


# @decorator_check_grass_data("raster")
def import_raster_from_dir(data, output_name, res):
    """ TODO """
    group_names = list()
    for tif in glob(f"{data}/**/*.tif", recursive=True):
        # TODO check if this can be parallized with r.import.worker
        name = f"{output_name}_{os.path.basename(tif).split('.')[0]}"
        group_names.append(name)
        grass.run_command(
            "r.import",
            input=tif,
            output=name,
            memory=options["memory"],
            quiet=True,
        )
    # save current region for reset in the cleanup
    orig_region = f"orig_region_{os.getpid()}"
    grass.run_command("g.region", save=orig_region)
    # resample rasters
    for name in group_names:
        raster_list = [
            x for x in grass.parse_command("i.group", flags="lg", group=name)
        ]
        grass.run_command(
            "g.region", raster=raster_list[0], res=res, flags="ap"
        )
        for raster in raster_list:
            # TODO check if this can be parallized with r.import.worker
            resampled_raster = raster.split("@")[0] + "_resampled"
            grass.run_command(
                "r.resamp.stats",
                input=raster,
                output=resampled_raster,
                method="median"
                quiet=True,
            )
        rm_groups.append(name)
    # create vrt for each band
    band_mapping = {
        "1": "red",
        "red": "red",
        "2": "green",
        "green": "green",
        "3": "blue",
        "blue": "blue",
        "4": "nir",
        "nir": "nir",
        "ir": "nir"
    }
    bands = [rast.split("@")[0].split(".")[1] for rast in raster_list]
    for band in bands:
        raster_of_band = [x for x in grass.parse_command(
            "g.list",
            type="raster",
            pattern=f"{output_name}_*.{band}_resampled",
            separator="comma"
        )][0]
        grass.run_command(
            "r.buildvrt",
            input=raster_of_band,
            output=f"{output_name}_{band_mapping[band]}",
            quiet=True,
        )


def import_data(data, dataimport_type, output_name, res=None):
    """Importing data depending on the data import type"""
    if dataimport_type == "vector":
        if data:
            import_vector(data, output_name=output_name)
    elif dataimport_type == "buildings":
        import_buildings(data, output_name)
    elif dataimport_type == "rasterdir":
        import_raster_from_dir(data, output_name, res)
    else:
        grass.warning(_(
            f"Import of data type <{datatype}> not yet supported."
        ))


def main():

    global orig_region, rm_rasters, rm_groups

    types = options["type"].split(",")

    # check if needed pathes to data are set
    grass.message(_("Checking input parameters ..."))
    for ptype in types:
        for data, val in needed_datasets[ptype].items():
            check_data(ptype, data, val)

    if flags["c"]:
        grass.message(_(
            "Only the data are checked. For import do not set the '-c' flag."
        ))
        exit(0)

    grass.message(_("Importing needed data sets ..."))
    for ptype in types:
        for data, val in needed_datasets[ptype].items():
            import_data(options[val[3]], val[4], data, val[0])

    grass.message(_("Importing needed data sets done"))



if __name__ == "__main__":
    options, flags = grass.parser()
    atexit.register(cleanup)
    main()
