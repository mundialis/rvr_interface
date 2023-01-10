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
# % key: area
# % required: yes
# % multiple: no
# % label: The vector file (e.g. GPKG or Shapefile format) of the study area
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

# %option G_OPT_M_DIR
# % key: dop_dir
# % required: no
# % multiple: no
# % label: The directory where the digital orthophots (DOPs) are stored as GeoTifs
# % description: The DOPs are required for the processing of gebaeudedetection and dachbegruenung
# %end

# %option G_OPT_M_DIR
# % key: dsm_dir
# % required: yes
# % multiple: no
# % label: The directory where the digital surface model (DSM) is stored as laz files
# % description: The DSM is required for the processing of gebaeudedetection, dachbegruenung and einzelbaumerkennung
# %end

# %option G_OPT_F_INPUT
# % key: dem_file
# % required: no
# % multiple: no
# % label: The raster file of the digital elevation model (DEM)
# % description: The DEM is required for the processing of gebaeudedetection, dachbegruenung and einzelbaumerkennung
# %end

# TODO add einzelbaumerkennung
# %option
# % key: type
# % required: yes
# % multiple: yes
# % label: The type of processing for which the data should be imported
# % options: gebaeudedetection,dachbegruenung
# % answer: gebaeudedetection,dachbegruenung
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
rm_vectors = list()
rm_files = list()


# dict to list the needed datasets for the processing type with the following
# values: (resolution, purpose, requiered, needed input information, import
#          or computation type)
needed_datasets = {
    "gebaeudedetection": {
        # vector
        "fnk": (None, "output", True, "fnk_file", "vector"),
        "reference_buildings": (
            None, "output", False, "reference_buildings_file", "vector"
        ),
        # raster
        "dop": ([0.5], "output,ndvi", True, "dop_dir", "rasterdir"),
        "ndvi": ([0.5], "output", True, "", "dop_ndvi"),
        "dsm": ([0.5], "ndom", True, "dsm_dir", "lazdir"),
        "dem": ([0.5], "ndom", False, "dem_file", "raster"),
        "ndom": ([0.5], "output", True, "", "ndom"),
    },
    "dachbegruenung": {
        # vector
        "fnk": (None, "output", False, "fnk_file", "vector"),
        "trees": (None, "output", False, "tree_file", "vector"),
        "houserings": (
            None, "output", True, "houserings_file", "buildings"
        ),
        # raster
        "dop": ([0.5], "output,ndvi", True, "dop_dir", "rasterdir"),
        "ndvi": ([0.5], "output", True, "", "dop_ndvi"),
        "dsm": ([0.5], "ndom", True, "dsm_dir", "lazdir"),
        "ndom": ([0.5], "output", True, "", "ndom"),
        "dem": ([0.5], "ndom", False, "dem_file", "raster"),
    },
    # # TODO
    # "einzelbaumerkennung": {
    #     "top": "",
    #     "s2_statistics": ""
    # }
}


def decorator_check_grass_data(grass_data_type):
    def decorator(function):
        def wrapper_check_grass_data(*args, **kwargs):
            if "resolutions" in kwargs:
                output_names = list()
                resolutions = kwargs["resolutions"]
                for res in kwargs["resolutions"]:
                    output_names.append(
                        f"{kwargs['output_name']}_{get_res_str(res)}"
                    )
            else:
                output_names = [kwargs["output_name"]]
                resolutions = [None]
            for output_name, res in zip(output_names, resolutions):
                grass_file = grass.find_file(
                    name=output_name, element=grass_data_type, mapset="."
                )["file"]
                grass_overwrite = (
                    True if "GRASS_OVERWRITE" in os.environ and
                    os.environ["GRASS_OVERWRITE"] == "1" else False
                )
                if not grass_file or grass_overwrite:
                    if res:
                        kwargs["resolutions"] = [res]
                    function(*args, **kwargs)
                    grass.message(_(
                        f"The {grass_data_type} map <{output_name}> imported."
                    ))
                else:
                    grass.warning(_(
                        f"Vector map <{output_name}> already exists."
                        "If you want to reimport all existing data use --o "
                        f"and if you only want to reimport {output_name}, "
                        "please delete the vector map first with:\n"
                        f"<g.remove -f type=vector name={output_name}>"
                    ))
        return wrapper_check_grass_data
    return decorator


def reset_region(region):
    nulldev = open(os.devnull, "w")
    kwargs = {"flags": "f", "quiet": True, "stderr": nulldev}
    if region is not None:
        if grass.find_file(name=region, element="windows")["file"]:
            grass.run_command("g.region", region=region)
            grass.run_command(
                "g.remove", type="region", name=region, **kwargs
            )


def cleanup():
    grass.message(_("Cleaning up ..."))
    reset_region(orig_region)
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
    for rmvect in rm_vectors:
        if grass.find_file(name=rmvect, element="vector")["file"]:
            grass.run_command("g.remove", type="vector", name=rmvect, **kwargs)
    for rmfile in rm_files:
        if os.path.isfile(rmfile):
            os.remove(rmfile)
    # for rmdir in rm_dirs:
    #     if os.path.isdir(rmdir):
    #         shutil.rmtree(rmdir)
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


@decorator_check_grass_data('raster')
def compute_ndvi(nir, red, output_name, scalled=False):
    """Computes and returns the NDVI as a value using given inputs"""
    grass.message(f"Computing NDVI {output_name} ...")
    # g.region
    region = f"ndvi_region_{os.getpid()}"
    grass.run_command("g.region", save=region)
    grass.run_command("g.region", raster=nir, flags="p")
    ndvi = f"float({nir} - {red})/({nir} + {red})"
    if scalled is False:
        formular = f"{output_name} = {ndvi}"
    else:
        formular = f"{output_name} = round(255*(1.0+({ndvi})/2"
    # TODO test r.mapcalc.tiled
    grass.run_command("r.mapcalc", expression=formular)
    reset_region(region)


@decorator_check_grass_data('raster')
def compute_ndom(dsm, output_name, dem=None):
    """Computes nDOM with the help of r.import.ndom_nrw grass addon"""
    grass.message(f"Computing nDOM {output_name} ...")
    # g.region
    region = f"ndom_region_{os.getpid()}"
    grass.run_command("g.region", save=region)
    grass.run_command("g.region", raster=dsm, flags="p")
    if dem:
        grass.run_command("r.import.ndom_nrw", dom=dsm, dgm=dem,
                          output_ndom=output_name, memory=options["memory"])
    else:
        grass.run_command("r.import.ndom_nrw", dom=dsm,
                          output_ndom=output_name, memory=options["memory"])
    reset_region(region)


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
    """Checks if all requiered data are set and the data files or folder
    exists.
    Args:
        ptype (str): processing type (gebaeudedetection, dachbegruenung or
                     einzelbaumerkennung)
        data (str):  Name or type of the data
        val (tuple): Tuple with values of the data: (resolution, purpose,
                     requiered, needed input information, import
                     or computation type)
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
            check_addon(
                "v.alkis.buildings.import",
                "https://github.com/mundialis/v.alkis.buildings.import",
            )
            grass.message(_(
                f"The data <{data}> will be downloaded from openNRW."
            ))
        else:
            grass.message(_(f"The {data} data are not used."))
    elif data == "dem":
        if val[2] and options[val[3]]:
            check_data_exists(options[val[3]], val[3])
        else:
            grass.message(_(f"The {data} data are downlowded form OpenNRW."))
    elif val[2] and val[3] == "":
        pass
    elif val[2] and not options[val[3]]:
        grass.fatal(_(
            f"For the processing type <{ptype}> the option <{val[3]}> "
            f"has to be set. Please set <{val[3]}>."
        ))
    elif not options[val[3]]:
        grass.message(_(f"The {data} data are not used."))
    else:
        check_data_exists(options[val[3]], val[3])


@decorator_check_grass_data("raster")
def import_laz(data, output_name, resolutions, study_area=None):
    """ Imports LAZ data files listed in a folder and builds a vrt file out
     of them"""
    grass.message(f"Importing {output_name} LAZ data ...")
    for res in resolutions:
        out_name = f"{output_name}_{get_res_str(res)}"
        raster_list = list()
        if study_area:
            create_tindex(data, f"{output_name}_tindex", type="LAZ")
            laz_list = select_location_from_tindex(study_area, f"{output_name}_tindex")
            import pdb; pdb.set_trace()
        else:
            laz_list = glob(f"{data}/**/*.laz", recursive=True)
        for laz_file in laz_list:
            name = (
                f"{output_name}_{os.path.basename(laz_file).split('.')[0]}"
                f"_{get_res_str(res)}"
            )
            raster_list.append(name)
            # generate 95%-max DSM
            grass.run_command(
                "r.in.pdal",
                input=laz_file,
                output=name,
                resolution=res,
                type="FCELL",
                method="percentile",
                pth=5,
                quiet=True
            )
        grass.run_command(
            "r.buildvrt",
            input=raster_list,
            output=out_name,
        )
    # "dsm": ([0.5], "ndom", True, "dsm_dir", "lasdir"),


@decorator_check_grass_data("vector")
def import_vector(file, output_name):
    """Importing vector data if does not exists
    Args:
        file (str):        The path of the vector data file
        output_name (str): The output name for the vector
    """
    grass.message(f"Importing {output_name} vector data ...")
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
    grass.message(f"Downloading and importing {output_name} building data from OpenNRW ...")
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


def get_res_str(res):
    """Returns string from resoltion value
    Args:
        res (float/int/str): The resolution value
    """
    return str(res).replace(".", "")


@decorator_check_grass_data("raster")
def import_raster(data, output_name, resolutions):
    """TODO"""
    grass.message(f"Importing {output_name} raster data ...")
    for res in resolutions:
        name = f"{output_name}_{get_res_str(res)}"
        # TODO rm_rasters.append(name)
        grass.run_command(
                "r.import",
                input=data,
                output=name,
                memory=options["memory"],
                resolution="value",
                resolution_value=res,
                resample="bilinear",  # TODO MM ist das für DEM ok?
                quiet=True,
            )


def create_tindex(data_dir, tindex_name, type="tif"):
    rm_vectors.append(tindex_name)
    rm_files.append(f"{tindex_name}.gpkg")
    nulldev = open(os.devnull, "w+")

    if type=="tif":
        tif_list = glob(f"{data_dir}/**/*.tif", recursive=True)
        cmd = [
                "gdaltindex",
                "-f",
                "GPKG",
                f"{tindex_name}.gpkg",
        ]
        cmd.extend(tif_list)

    else:
        cmd = [
            "pdal",
            "tindex",
            "create",
            f"{tindex_name}.gpkg",
            f"{data_dir}/*.laz",
            "-f",
            "GPKG"
        ]
    ps = grass.Popen(cmd, stdout=nulldev)
    ps.wait()
    grass.run_command(
        "v.import",
        input=f"{tindex_name}.gpkg",
        output=tindex_name
    )


def select_location_from_tindex(study_area, tindex):
    grass.run_command(
        "v.select",
        ainput=tindex,
        binput=study_area,
        output=f"{tindex}_overlap",
        operator="overlap",
        quiet=True,
    )
    rm_vectors.append(f"{tindex}_overlap")

    tif_list = list(
        grass.parse_command(
            "v.db.select",
            map=f"{tindex}_overlap",
            columns="location",
            flags="c",
            quiet=True
        ).keys()
    )
    return tif_list


@decorator_check_grass_data("group")
def import_raster_from_dir(data, output_name, resolutions, study_area=None):
    """Imports and reprojects raster data
    Args:
        data (str) .......... The path of the raster data directory, which
                              contains raster images which should be imported
        output_name (str) ... The output name for the vector

    """
    grass.message(f"Importing {output_name} raster data from folder ...")
    group_names = list()
    if study_area:
        create_tindex(data, f"{output_name}_tindex")
        tif_list = select_location_from_tindex(study_area, f"{output_name}_tindex")

    else:
        tif_list = glob(f"{data}/**/*.tif", recursive=True)

    for tif in tif_list:
        # TODO check if this can be parallized with r.import.worker
        name = f"{output_name}_{os.path.basename(tif).split('.')[0]}"
        group_names.append(name)
        g_gr = grass.find_file(name=name, element="group", mapset=".")["file"]
        if not g_gr:
            grass.run_command(
                "r.import",
                input=tif,
                output=name,
                memory=options["memory"],
                quiet=True,
            )
    # save current region for reset in the cleanup
    rimport_region = f"r_import_region_{os.getpid()}"
    grass.run_command("g.region", save=rimport_region)
    # resample rasters
    for res in resolutions:
        res_str = get_res_str(res)
        for name in group_names:
            raster_list = [
                x for x in grass.parse_command(
                    "i.group", flags="lg", group=name
                )
            ]
            grass.run_command(
                "g.region", raster=raster_list[0], res=res, flags="ap"
            )
            for raster in raster_list:
                cur_r_reg = grass.parse_command(
                    "g.region",
                    flags="ug",
                    raster="dop_2018_DOP10_374000_5725000.1"
                )
                resampled_rast = f"{raster.split('@')[0]}_resampled_{res_str}"
                if (
                    float(cur_r_reg["nsres"]) == float(cur_r_reg["ewres"])
                    and float(cur_r_reg["nsres"]) == res
                ):
                    grass.run_command(
                        "g.rename",
                        raster=f"{raster},{resampled_rast}"
                    )
                else:
                    # TODO check if this can be parallized with r.import.worker
                    grass.run_command(
                        "r.resamp.stats",
                        input=raster,
                        output=resampled_rast,
                        method="median",
                        quiet=True,
                    )
            if name not in rm_groups:
                rm_groups.append(name)
        reset_region(rimport_region)
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
                pattern=f"{output_name}_*.{band}_resampled_{res_str}",
                separator="comma",
            )][0]
            band_out = f"{output_name}_{band_mapping[band]}_{res_str}"
            grass.run_command(
                "r.buildvrt",
                input=raster_of_band,
                output=band_out,
                quiet=True,
            )
            grass.run_command(
                "i.group",
                group=f"{output_name}_{res_str}",
                input=band_out
            )


def import_data(data, dataimport_type, output_name, res=None):
    """Importing data depending on the data import type"""
    if dataimport_type == "vector":
        if data:
            import_vector(data, output_name=output_name)
    elif dataimport_type == "buildings":
        import_buildings(data, output_name)
    elif dataimport_type == "rasterdir":
        if data:
            import_raster_from_dir(data, output_name=output_name, resolutions=res, study_area="study_area")
    elif dataimport_type == "raster":
        if data:
            import_raster(data, output_name=output_name, resolutions=res)
    elif dataimport_type == "lazdir":
        import_laz(data, output_name=output_name, resolutions=res, study_area="study_area")
    else:
        grass.warning(_(
            f"Import of data type <{dataimport_type}> not yet supported."
        ))


def compute_data(compute_type, output_name, resoultions=[0.1]):
    if compute_type == "dop_ndvi":
        for res in resoultions:
            compute_ndvi(
                f"dop_nir_{get_res_str(res)}",
                f"dop_red_{get_res_str(res)}",
                output_name=output_name,
            )
    elif compute_type == "ndom":
        for res in resoultions:
            kwargs = {
                "dsm": f"dsm_{get_res_str(res)}",
                "output_name": output_name,
            }
            if options["dem_file"]:
                kwargs["dem"] = f"dem_{get_res_str(res)}"
            compute_ndom(**kwargs)
    else:
        grass.warning(_(
            f"Computation of <{compute_type}> not yet supported."
        ))


def main():

    global orig_region, rm_rasters, rm_groups, rm_vectors, rm_files

    types = options["type"].split(",")

    # save orignal region
    orig_region = f"orig_region_{os.getpid()}"

    # check if needed addons are installed
    check_addon("r.in.pdal")
    check_addon("r.import.ndom_nrw", "/path/to/r.import.ndom_nrw")
    check_addon("r.import.dgm_nrw", "/path/to/r.import.dgm_nrw")

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

    import_vector(options["area"], output_name="study_area")
    for ptype in types:
        for data, val in needed_datasets[ptype].items():
            if val[3]:
                import_data(options[val[3]], val[4], data, val[0])

    grass.message(_("Compute needed data sets ..."))
    for ptype in types:
        for data, val in needed_datasets[ptype].items():
            if not val[3]:
                compute_data(val[4], data, val[0])

    grass.message(_("Importing needed data sets done"))


if __name__ == "__main__":
    options, flags = grass.parser()
    atexit.register(cleanup)
    main()
