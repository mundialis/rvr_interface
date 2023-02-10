#!/usr/bin/env python3

############################################################################
#
# MODULE:       m.import.rvr
#
# AUTHOR(S):    Anika Weinmann and Momen Mawad
#
# PURPOSE:      Imports data for the processing of gebaeudedetektion,
#               dachbegruenung and/or einzelbaumerkennung
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
# % description: Import data for the processing of gebaeudedetektion, dachbegruenung and/or einzelbaumerkennung.
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
# % description: Required for the processing type gebaeudedetektion and optional for dachbegruenung
# %end

# %option G_OPT_DB_COLUMN
# % key: fnk_column
# % required: no
# % label: The name of class code attribute column of the FNK map
# % description: Required for the processing type gebaeudedetektion and optional for dachbegruenung
# %end

# %option G_OPT_F_INPUT
# % key: reference_buildings_file
# % required: no
# % multiple: no
# % label: The vector file (e.g. GPKG or Shapefile format) of the building reference data
# % description: Needed for the change detection after the gebaeudedetektion
# %end

# %option G_OPT_F_INPUT
# % key: building_outlines_file
# % required: no
# % multiple: no
# % label: The vector file (e.g. GPKG or Shapefile format) of the building outlines data
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
# % label: The directory where the digital orthophots (DOPs) are stored as GeoTiffs
# % description: The DOPs are required for the processing of gebaeudedetektion and dachbegruenung
# %end

# %option G_OPT_F_INPUT
# % key: dop_tindex
# % required: no
# % multiple: no
# % label: The name of the DOP tindex which should be used or created
# % description: If this is set the tindex needs a column <location> with the absolute path to the DOP files
# %end

# %option G_OPT_M_DIR
# % key: top_dir
# % required: no
# % multiple: no
# % label: The directory where the true digital orthophots (TOPs) are stored as GeoTiffs
# % description: The TOPs are required for the processing of einzelbaumerkennung
# %end

# %option G_OPT_F_INPUT
# % key: top_tindex
# % required: no
# % multiple: no
# % label: The name of the TOP tindex which should be used or created
# % description: If this is set the tindex needs a column location with the absolute path to the TOP files
# %end

# %option G_OPT_M_DIR
# % key: dsm_dir
# % required: yes
# % multiple: no
# % label: The directory where the digital surface model (DSM) is stored as laz files
# % description: The DSM is required for the processing of gebaeudedetektion, dachbegruenung and einzelbaumerkennung
# %end

# %option G_OPT_F_INPUT
# % key: dsm_tindex
# % required: no
# % multiple: no
# % label: The name of the DSM tindex which should be used or created
# % description: If this is set the tindex needs a column <location> with the absolute path to the DSM files
# %end

# %option G_OPT_F_INPUT
# % key: dtm_file
# % required: no
# % multiple: no
# % label: The raster file of the digital terrain model (DTM)
# % description: The DTM is required for the processing of gebaeudedetektion, dachbegruenung and einzelbaumerkennung
# %end

# %option
# % key: dtm_resolution
# % type: double
# % required: no
# % multiple: yes
# % label: The resolution of the source DTM XYZ file
# %end

# %option
# % key: type
# % type: string
# % required: yes
# % multiple: yes
# % label: The type of processing for which the data should be imported
# % options: gebaeudedetektion,dachbegruenung,einzelbaumerkennung
# % answer: gebaeudedetektion,dachbegruenung,einzelbaumerkennung
# %end

# %option G_OPT_M_NPROCS
# % description: Number of cores for multiprocessing, -2 is n_cores-1
# % answer: -2
# %end

# %flag
# % key: c
# % label: Only check input parameters
# %end

# %flag
# % key: b
# % label: Download buildings for reference buildings or building outlines from openNRW if files are not set
# %end


import atexit
import os
import psutil
import grass.script as grass
from grass.pygrass.modules import Module, ParallelModuleQueue
from grass.pygrass.modules.grid.grid import GridModule

from glob import glob
import multiprocessing as mp

# initialize global vars
orig_region = None
rm_rasters = list()
rm_groups = list()
rm_vectors = list()
rm_files = list()
rm_regions = list()
tmp_dir = None
nprocs = -2


# dict to list the needed datasets for the processing type with the following
# values: (resolution, purpose, requiered, needed input information, import
#          or computation type)
needed_datasets = {
    "gebaeudedetektion": {
        # vector
        "fnk": (None, "output", True, "fnk_file,fnk_column", "vector"),
        "reference_buildings": (
            None,
            "output",
            False,
            "reference_buildings_file",
            "buildings",
        ),
        # raster
        "dop": ([0.5], "output,ndvi", True, "dop_dir", "rasterdir"),
        "ndvi": ([0.5], "output", True, "", "dop_ndvi_scalled"),
        "dsm": ([0.5], "ndsm", True, "dsm_dir", "lazdir"),
        "dtm": ([0.5], "ndsm", False, "dtm_file", "rasterORxyz"),
        "ndsm": ([0.5], "output", True, "", "ndsm"),
    },
    "dachbegruenung": {
        # vector
        "fnk": (None, "output", False, "fnk_file,fnk_column", "vector"),
        "trees": (None, "output", False, "tree_file", "vector"),
        "building_outlines": (
            None,
            "output",
            True,
            "building_outlines_file",
            "buildings",
        ),
        # raster
        "dop": ([0.5], "output,ndvi", True, "dop_dir", "rasterdir"),
        "ndvi": ([0.5], "output", True, "", "dop_ndvi_scalled"),
        "dsm": ([0.5], "ndsm", True, "dsm_dir", "lazdir"),
        "ndsm": ([0.5], "output", True, "", "ndsm"),
        "dtm": ([0.5], "ndsm", False, "dtm_file", "rasterORxyz"),
    },
    # TODO: S2
    "einzelbaumerkennung": {
        # vector
        "reference_buildings": (
            None,
            "output",
            False,
            "reference_buildings_file",
            "vector",
        ),
        # raster
        "top": ([0.2], "output,ndvi", True, "top_dir", "rasterdir"),
        "ndvi": ([0.2], "output", True, "", "top_ndvi_scalled"),
        "dtm": ([0.2], "ndsm", False, "dtm_file", "rasterORxyz"),
        "dsm": ([0.2], "ndsm", True, "dsm_dir", "lazdir"),
        "ndsm": ([0.2], "output", True, "", "ndsm"),
    },
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
                    True
                    if "GRASS_OVERWRITE" in os.environ
                    and os.environ["GRASS_OVERWRITE"] == "1"
                    else False
                )
                if not grass_file or grass_overwrite:
                    if res:
                        kwargs["resolutions"] = [res]
                    function(*args, **kwargs)
                    grass.message(
                        _(
                            f"The {grass_data_type} map <{output_name}> imported."
                        )
                    )
                else:
                    grass.warning(
                        _(
                            f"Map <{output_name}> already exists."
                            "If you want to reimport all existing data use --o "
                            f"and if you only want to reimport {output_name}, "
                            "please delete the map first with:\n"
                            f"<g.remove -rf type={grass_data_type} name={output_name}>"
                        )
                    )

        return wrapper_check_grass_data

    return decorator


def reset_region(region):
    """Function to reset the region to the given region
    Args:
        region (str): the name of the saved region which should be set and
                      deleted
    """
    nulldev = open(os.devnull, "w")
    kwargs = {"flags": "f", "quiet": True, "stderr": nulldev}
    if region is not None:
        if grass.find_file(name=region, element="windows")["file"]:
            grass.run_command("g.region", region=region)
            grass.run_command("g.remove", type="region", name=region, **kwargs)


def cleanup():
    """Cleanup function"""
    grass.message(_("Cleaning up ..."))
    reset_region(orig_region)
    nulldev = open(os.devnull, "w")
    kwargs = {"flags": "f", "quiet": True, "stderr": nulldev}
    for rmg in rm_groups:
        if grass.find_file(name=rmg, element="group")["file"]:
            group_rasters = grass.parse_command(
                "i.group", flags="lg", group=rmg
            )
            rm_rasters.extend(group_rasters)
            grass.run_command("g.remove", type="group", name=rmg, **kwargs)
    for rmrast in rm_rasters:
        if grass.find_file(name=rmrast, element="raster")["file"]:
            grass.run_command("g.remove", type="raster", name=rmrast, **kwargs)
    for rmvect in rm_vectors:
        if grass.find_file(name=rmvect, element="vector")["file"]:
            grass.run_command("g.remove", type="vector", name=rmvect, **kwargs)
    for rmfile in rm_files:
        if os.path.isfile(rmfile):
            os.remove(rmfile)
    if tmp_dir:
        if os.path.isdir(tmp_dir):
            grass.try_rmdir(tmp_dir)
    for rmreg in rm_regions:
        if grass.find_file(name=rmreg, element="windows")["file"]:
            grass.run_command("g.remove", type="region", name=rmreg, **kwargs)


def freeRAM(unit, percent=100):
    """The function gives the amount of the percentages of the installed RAM.
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


def set_nprocs(nprocs):
    if nprocs == -2:
        nprocs = mp.cpu_count() - 1 if mp.cpu_count() > 1 else 1
    elif nprocs in (-1, 0):
        grass.warning(
            _(
                "Number of cores for multiprocessing must be 1 or "
                "higher. Option <nprocs> will be set to 1 (serial "
                "processing). \n To use other number of cores, please "
                "set <nprocs> to 1 or higher. To use all available "
                "cores -1 do not set the <nprocs> option."
            )
        )
        nprocs = 1
    else:
        # Test nprocs settings
        nprocs_real = mp.cpu_count()
        if nprocs > nprocs_real:
            grass.warning(
                _(
                    f"Using {nprocs} parallel processes but only {nprocs_real} CPUs available."
                )
            )
            nprocs = nprocs_real

    return nprocs


def test_memory():
    """Function to check the free memory and print a warning if the memory
    option is set to more
    """
    memory = int(options["memory"])
    free_ram = freeRAM("MB", 100)
    if free_ram < memory:
        grass.warning(
            "Using %d MB but only %d MB RAM available." % (memory, free_ram)
        )
        options["memory"] = free_ram
        grass.warning("Set used memory to %d MB." % (options["memory"]))


@decorator_check_grass_data("raster")
def compute_ndvi(nir, red, output_name, scalled=False):
    """Computes and returns the NDVI as a value using given inputs
    Args:
        nir (str): the name of the NIR raster
        red (str): the name of the red raster
        output_name (str): the name for the output NDVI raster
        scalled (str): boolean if the NDVI should be scalled from 0 to 255
    """
    grass.message(f"Computing NDVI {output_name} ...")
    # g.region
    region = f"ndvi_region_{os.getpid()}"
    rm_regions.append(region)
    grass.run_command("g.region", save=region)
    grass.run_command("g.region", raster=nir, flags="p")
    ndvi = f"float({nir} - {red})/({nir} + {red})"
    if scalled is False:
        formular = f"{output_name} = {ndvi}"
    else:
        formular = f"{output_name} = round(255*(1.0+({ndvi}))/2)"
    mapcalc_tiled_kwargs = {}
    if nprocs > 1:
        mapcalc_tiled_kwargs = {
            "nprocs": nprocs,
            "patch_backend": "r.patch",
        }
        r_mapcalc_cmd = "r.mapcalc.tiled"
    else:
        r_mapcalc_cmd = "r.mapcalc"
    grass.run_command(
        r_mapcalc_cmd, expression=formular, **mapcalc_tiled_kwargs
    )
    reset_region(region)


@decorator_check_grass_data("raster")
def compute_ndsm(dsm, output_name, dtm=None):
    """Computes nDSM with the help of r.import.ndsm_nrw grass addon
    Args:
        dsm (str): the name of the digital surface model (DSM) raster
        output_name (str): the name for the output nDSM raster
        dtm (str): the name of the digital terrain model (DTM) raster; if not
                   set the DTM is downloaded from openNRW
    """
    grass.message(f"Computing nDSM {output_name} ...")
    # g.region
    region = f"ndsm_region_{os.getpid()}"
    rm_regions.append(region)
    grass.run_command("g.region", save=region)
    grass.run_command("g.region", raster=dsm, flags="p")
    cur_region = grass.region()
    dsm_region = grass.parse_command(
        "g.region",
        flags="ug",
        raster=dsm,
        zoom=dsm,
    )
    if (
        float(dsm_region["n"]) < float(cur_region["n"])
        or float(dsm_region["s"]) > float(cur_region["s"])
        or float(dsm_region["e"]) < float(cur_region["e"])
        or float(dsm_region["w"]) > float(cur_region["w"])
    ):
        grass.warning(
            _(
                "Imported DSM file smaller than region of area, "
                "so that no nDSM can be computed. Please reimport bigger DSM "
                f"{dsm} raster map."
            )
        )
    else:
        ndsm_proc_kwargs = {
            "dsm": dsm,
            "output_ndsm": output_name,
            "output_dtm": "dtm_resampled",
            "memory": options["memory"],
        }
        rm_rasters.append("dtm_resampled")
        if dtm:
            ndsm_proc_kwargs["dtm"] = dtm
        if nprocs > 1:
            ndsm_grid_module = GridModule(
                "r.import.ndsm_nrw",
                width=1000,
                height=1000,
                overlap=10,  # more than 4 (bilinear method in r.resamp.interp)
                split=False,  # r.tile nicht verwenden?
                mapset_prefix="tmp_ndsm",
                # patch_backend="r.patch",  # does not work with overlap
                processes=nprocs,
                overwrite=True,
                **ndsm_proc_kwargs,
            )
            ndsm_grid_module.run()
        else:
            grass.run_command(
                "r.import.ndsm_nrw", overwrite=True, **ndsm_proc_kwargs
            )
    reset_region(region)


def check_data_exists(data, optionname):
    """Check if data exist in right format (depending on the option name)
    Args:
        data (str): the value which is set for the option parameter
        optionname (str): the name of the option name of this module
    """
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
        ptype (str): processing type (gebaeudedetektion, dachbegruenung or
                     einzelbaumerkennung)
        data (str):  Name or type of the data
        val (tuple): Tuple with values of the data: (resolution, purpose,
                     requiered, needed input information, import
                     or computation type)
    """
    if data in ["reference_buildings", "building_outlines"]:
        # check if data is required
        if val[2] and options[val[3]]:
            check_data_exists(options[val[3]], val[3])
        elif val[2] and not flags["b"]:
            grass.fatal(
                _(
                    f"For the processing type <{ptype}> the option <{val[3]}> "
                    f"has to be set or the data can be downloaded from "
                    "openNRW for this set the flag '-b'. Please set the "
                    f"option <{val[3]}> or the flag '-b'."
                )
            )
        elif flags["b"]:
            check_addon(
                "v.alkis.buildings.import",
                "https://github.com/mundialis/v.alkis.buildings.import",
            )
            grass.message(
                _(f"The data <{data}> will be downloaded from openNRW.")
            )
        else:
            grass.message(_(f"The {data} data are not used."))
    elif data == "dtm":
        if options[val[3]]:
            check_data_exists(options[val[3]], val[3])
            if (
                options[val[3]].endswith(".xyz")
                and not options["dtm_resolution"]
            ):
                grass.fatal(
                    _(
                        f"The <{data}> XYZ file is used but no <dtm_resolution> "
                        "is set."
                    )
                )
        else:
            grass.message(_(f"The {data} data are downloaded from OpenNRW."))
    elif val[2] and val[3] == "":
        pass
    elif "," in val[3]:
        used = True
        for key in val[3].split(","):
            if val[2] and not options[key]:
                grass.fatal(
                    _(
                        f"For the processing type <{ptype}> the option <{key}> "
                        f"has to be set. Please set <{key}>."
                    )
                )
            elif not options[key]:
                used = False
        if not used:
            grass.message(_(f"The {data} data are not used."))
        else:
            check_data_exists(
                options[val[3].split(",")[0]], val[3].split(",")[0]
            )
    elif val[2] and not options[val[3]]:
        grass.fatal(
            _(
                f"For the processing type <{ptype}> the option <{val[3]}> "
                f"has to be set. Please set <{val[3]}>."
            )
        )
    elif not options[val[3]]:
        grass.message(_(f"The {data} data are not used."))
    else:
        check_data_exists(options[val[3]], val[3])


def build_raster_vrt(raster_list, output_name):
    """Build raster VRT if the length of the raster list is greater 1 otherwise
    renaming of the raster
    Args:
        raster_list (list of strings): List of raster maps
        output_name (str): Name of the output raster map
    """
    if isinstance(raster_list, list) and len(raster_list) > 1:
        grass.run_command(
            "r.buildvrt",
            input=raster_list,
            output=output_name,
            quiet=True,
        )
    elif isinstance(raster_list, list) and len(raster_list) == 1:
        grass.run_command(
            "g.rename",
            raster=f"{raster_list[0]},{output_name}",
            quiet=True,
        )
    else:
        grass.run_command(
            "g.rename",
            raster=f"{raster_list},{output_name}",
            quiet=True,
        )


@decorator_check_grass_data("raster")
def import_laz(data, output_name, resolutions, study_area=None):
    """Imports LAZ data files listed in a folder and builds a vrt file out
    of them
    Args:
       data (str): the path of the directory where the LAZ files are stored
       output_name (str): the name for the output raster
       resolutions (list of float): a list of resolution values where the
                                    output should be resamped to
       study_area (str): the name of the study area vector
    """
    grass.message(f"Importing {output_name} LAZ data ...")
    for res in resolutions:
        out_name = f"{output_name}_{get_res_str(res)}"
        raster_list = list()
        if study_area:
            tindex_file = options[f"{output_name}_tindex"]
            # tindex exists and should be used
            if tindex_file and os.path.isfile(tindex_file):
                grass.message(
                    _(f"Using tindex <{os.path.basename(tindex_file)}> ...")
                )
                grass.run_command(
                    "v.import",
                    input=tindex_file,
                    output=f"{output_name}_tindex",
                    quiet=True,
                    overwrite=True,
                )
                rm_vectors.append(f"{output_name}_tindex")
            else:
                out_path = None
                # tindex file is set and should be created
                if tindex_file:
                    out_path = tindex_file
                create_tindex(
                    data,
                    f"{output_name}_tindex",
                    type="LAZ",
                    out_path=out_path,
                )
            laz_list = select_location_from_tindex(
                study_area, f"{output_name}_tindex"
            )
        else:
            laz_list = glob(f"{data}/**/*.laz", recursive=True)
        # set region so that all pixels in region are selected
        if study_area:
            region = f"laz_import_region_{os.getpid()}"
            rm_regions.append(region)
            grass.run_command("g.region", save=region)
            grass.run_command(
                "g.region", vector=study_area, res=res, flags="a"
            )
            grass.run_command("g.region", grow=2)
        r_in_pdal_kwargs = {
            "resolution": res,
            "type": "FCELL",
            "method": "percentile",
            "pth": 95,
            "quiet": True,
            "flags": "o",
            "overwrite": True,
        }
        if nprocs > 1:
            nprocs_laz = nprocs
            if len(laz_list) < nprocs:
                nprocs_laz = len(laz_list)
            queue = ParallelModuleQueue(nprocs=nprocs_laz)
            try:
                for laz_file in laz_list:
                    name = (
                        f"{output_name}_{os.path.basename(laz_file).split('.')[0]}"
                        f"_{get_res_str(res)}"
                    )
                    raster_list.append(name)
                    r_in_pdal_kwargs["input"] = laz_file
                    r_in_pdal_kwargs["output"] = name
                    # generate 95%-max DSM
                    r_in_pdal = Module(
                        "r.in.pdal", **r_in_pdal_kwargs, run_=False
                    )
                    # catch all GRASS outputs to stdout and stderr
                    r_in_pdal.stdout_ = grass.PIPE
                    r_in_pdal.stderr_ = grass.PIPE
                    queue.put(r_in_pdal)
                queue.wait()
            except Exception:
                for proc_num in range(queue.get_num_run_procs()):
                    proc = queue.get(proc_num)
                    if proc.returncode != 0:
                        # save all stderr to a variable and pass it to a GRASS
                        # exception
                        errmsg = proc.outputs["stderr"].value.strip()
                        grass.fatal(
                            _(
                                f"\nERROR by processing <{proc.get_bash()}>: {errmsg}"
                            )
                        )
        else:
            for laz_file in laz_list:
                name = (
                    f"{output_name}_{os.path.basename(laz_file).split('.')[0]}"
                    f"_{get_res_str(res)}"
                )
                raster_list.append(name)
                r_in_pdal_kwargs["input"] = laz_file
                r_in_pdal_kwargs["output"] = name
                # generate 95%-max DSM
                grass.run_command("r.in.pdal", **r_in_pdal_kwargs)
        build_raster_vrt(raster_list, out_name)
        reset_region(region)


@decorator_check_grass_data("vector")
def import_vector(file, output_name, extent="region", area=None, column=None):
    """Importing vector data if it does not already exist
    Args:
        file (str):        The path of the vector data file
        output_name (str): The output name for the vector
        area (str): The area vector map
        column (str): The name of the attribute column to transform to integer
    """
    grass.message(f"Importing {output_name} vector data ...")
    buildings = output_name
    if area:
        buildings = grass.tempname(12)
        rm_vectors.append(buildings)
    grass.run_command(
        "v.import",
        input=file,
        output=buildings,
        extent=extent,
        snap=0.001,
        quiet=True,
    )
    if area:
        grass.run_command(
            "v.select",
            ainput=buildings,
            binput=area,
            output=output_name,
            operator="overlap",
            quiet=True,
        )
    # Convert column to INTEGER column for FNK
    if column:
        v_info_c = grass.vector_columns(output_name)
        if column not in v_info_c:
            grass.fatal(
                _(
                    f"The requiered column <{column}> is not in the <{file}> data."
                )
            )
        if v_info_c[column]["type"] != "INTEGER":
            try:
                tmp_col_name = grass.tempname(8)
                grass.run_command(
                    "v.db.addcolumn",
                    map=output_name,
                    columns=f"{tmp_col_name} INTEGER",
                    quiet=True,
                )
                grass.run_command(
                    "v.db.update",
                    map=output_name,
                    column=tmp_col_name,
                    query_column=column,
                    quiet=True,
                )
                grass.run_command(
                    "v.db.dropcolumn",
                    map=output_name,
                    columns=column,
                    quiet=True,
                )
                grass.run_command(
                    "v.db.renamecolumn",
                    map=output_name,
                    column=f"{tmp_col_name},{column}",
                    quiet=True,
                )
            except Exception:
                grass.fatal(
                    _(f"Could not convert column <{column}> to INTEGER.")
                )


@decorator_check_grass_data("vector")
def import_buildings_from_opennrw(output_name, area):
    """Download buildings from openNRW and import them
    Args:
        output_name (str): the name for the output buildings vector map
        area (str): The area vector map
    """
    grass.message(
        _(
            f"Downloading and importing {output_name} building data "
            "from OpenNRW ..."
        )
    )
    buildings = grass.tempname(12)
    rm_vectors.append(buildings)
    grass.run_command(
        "v.alkis.buildings.import",
        flags="r",
        output=buildings,
        federal_state="Nordrhein-Westfalen",
        quiet=True,
    )
    grass.run_command(
        "v.select",
        ainput=buildings,
        binput=area,
        output=output_name,
        operator="overlap",
        quiet=True,
    )


def import_buildings(file, output_name, area, column=None):
    """Importing vector data if does not exists
    Args:
        file (str): The path of the vector data file
        output_name (str): The output name for the vector
        area (str): The area vector map
        column (str): The name of the attribute column to transform to integer
    """
    if file:
        import_vector(file, output_name=output_name, area=area, column=column)
    elif flags["b"]:
        import_buildings_from_opennrw(output_name=output_name, area=area)


def get_res_str(res):
    """Returns string from resolution value
    Args:
        res (float/int/str): The resolution value
    """
    return str(res).replace(".", "")


@decorator_check_grass_data("raster")
def import_raster(data, output_name, resolutions):
    """Imports raster map with reprojecting the raster
    Args:
        data (str): the raster GeoTiff which should be imported
        output_name (str): the base name for the output raster
        resolutions (list of float): a list of resolution values where the
                                     output should be resampled to
    """
    grass.message(f"Importing {output_name} raster data ...")
    for res in resolutions:
        name = f"{output_name}_{get_res_str(res)}"
        grass.run_command(
            "r.import",
            input=data,
            output=name,
            memory=options["memory"],
            resolution="value",
            resolution_value=res,
            resample="bilinear",
            extent="region",
            quiet=True,
        )


@decorator_check_grass_data("raster")
def import_xyz(data, src_res, dest_res, output_name):
    """Imports and resamples XYZ files (for the digital terrain model (DTM;
    german DGM))
    Args:
        data (str): the XYZ file
        output_name (str): the base name for the output raster
        src_res (float): the resolution of the data in the XYZ file
        dest_res (float): the resolution to resample the raster map
    """
    grass.message(f"Importing {output_name} XYZ raster data ...")
    out_name = src_res
    if dest_res != src_res:
        out_name = grass.tempname(12)
        rm_rasters.append(out_name)
    # save old region
    region = f"ndvi_region_{os.getpid()}"
    rm_regions.append(region)
    grass.run_command("g.region", save=region)
    # set region to xyz file
    xyz_reg_str = grass.read_command(
        "r.in.xyz",
        output="dummy",
        input=data,
        flags="sg",
        separator="space",
    )
    xyz_reg = {
        item.split("=")[0]: float(item.split("=")[1])
        for item in xyz_reg_str.strip().split(" ")
    }
    dtm_res_h = src_res / 2.0
    north = xyz_reg["n"] + dtm_res_h
    south = xyz_reg["s"] - dtm_res_h
    west = xyz_reg["w"] - dtm_res_h
    east = xyz_reg["e"] + dtm_res_h
    # import only study area
    area_reg = grass.parse_command("g.region", flags="ug", vector="study_area")
    while (north - src_res) > float(area_reg["n"]):
        north -= src_res
    while (south + src_res) < float(area_reg["s"]):
        south += src_res
    while (west + src_res) < float(area_reg["w"]):
        west += src_res
    while (east - src_res) > float(area_reg["e"]):
        east -= src_res
    if north < south:
        north += src_res
        south -= src_res
    if east < west:
        east += src_res
        west -= src_res
    grass.run_command(
        "g.region", n=north, s=south, w=west, e=east, res=src_res
    )
    grass.run_command(
        "r.in.xyz",
        input=data,
        output=out_name,
        method="mean",
        separator="space",
        quiet=True,
    )
    grass.run_command(
        "g.region",
        n=f"n+{dtm_res_h}",
        s=f"s+{dtm_res_h}",
        w=f"w+{dtm_res_h}",
        e=f"e+{dtm_res_h}",
        res=src_res,
    )
    grass.run_command("r.region", map=out_name, flags="c")
    # resample data
    if dest_res != src_res:
        grass.run_command(
            "g.region", vector="study_area", res=dest_res, flags="pa"
        )
        grass.run_command(
            "r.resamp.interp",
            input=out_name,
            output=output_name,
            method="bilinear",
            quiet=True,
        )
    # reset region
    reset_region(region)


def create_tindex(data_dir, tindex_name, type="tif", out_path=None):
    """Function to create a tile index for GeoTiff or LAZ files
    Args:
        data_dir (str): the directory where the GeoTiff or LAZ files are stored
        tindex_name (str): the name for the output tile index
        type (str): tif or laz depending of the input data for which to
                    generate the tile index
        out_path (str): the output path where to save the tindex
    """
    rm_vectors.append(tindex_name)
    nulldev = open(os.devnull, "w+")
    if out_path:
        tindex = out_path
    else:
        tindex = os.path.join(tmp_dir, f"{tindex_name}.gpkg")
        rm_files.append(tindex)

    if type == "tif":
        tif_list = glob(f"{data_dir}/**/*.tif", recursive=True)
        cmd = [
            "gdaltindex",
            "-f",
            "GPKG",
            tindex,
        ]
        cmd.extend(tif_list)

    else:
        cmd = [
            "pdal",
            "tindex",
            "create",
            tindex,
            f"{data_dir}/*.laz",
            "-f",
            "GPKG",
        ]
    ps = grass.Popen(cmd, stdout=nulldev)
    ps.wait()
    rm_vectors.append(tindex_name)
    grass.run_command(
        "v.import",
        input=tindex,
        output=tindex_name,
        quiet=True,
    )


def select_location_from_tindex(study_area, tindex):
    """The function selects the locations of the tile index which overlap with
    the study_area
    Args:
        study_area (str): the name of the study area vector map
        tindex (str): the name of the tile index vector map
    """
    grass.run_command(
        "v.select",
        ainput=tindex,
        binput=study_area,
        output=f"{tindex}_overlap",
        operator="overlap",
        quiet=True,
    )
    rm_vectors.append(f"{tindex}_overlap")
    if not grass.find_file(name=f"{tindex}_overlap", element="vector")["file"]:
        grass.fatal(_(f"Selected study area and {tindex} does not overlap."))

    tif_list = list(
        grass.parse_command(
            "v.db.select",
            map=f"{tindex}_overlap",
            columns="location",
            flags="c",
            quiet=True,
        ).keys()
    )
    return tif_list


@decorator_check_grass_data("group")
def import_raster_from_dir(data, output_name, resolutions, study_area=None):
    """Imports and reprojects raster data
    Args:
        data (str): The path of the raster data directory, which
                              contains raster images which should be imported
        output_name (str): The output name for the vector

    """
    grass.message(f"Importing {output_name} raster data from folder ...")
    group_names = list()
    if study_area:
        tindex_file = options[f"{output_name}_tindex"]
        # tindex exists and should be used
        if tindex_file and os.path.isfile(tindex_file):
            grass.message(
                _(f"Using tindex <{os.path.basename(tindex_file)}> ...")
            )
            grass.run_command(
                "v.import",
                input=tindex_file,
                output=f"{output_name}_tindex",
                quiet=True,
                overwrite=True,
            )
            rm_vectors.append(f"{output_name}_tindex")
        else:
            out_path = None
            # tindex file is set and should be created
            if tindex_file:
                out_path = tindex_file
            create_tindex(data, f"{output_name}_tindex", out_path=out_path)
        tif_list = select_location_from_tindex(
            study_area, f"{output_name}_tindex"
        )
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
                extent="region",
                overwrite=True,
            )
    # save current region for reset in the cleanup
    rimport_region = f"r_import_region_{os.getpid()}"
    rm_regions.append(rimport_region)
    grass.run_command("g.region", save=rimport_region)
    # resample rasters
    for res in resolutions:
        res_str = get_res_str(res)
        for name in group_names:
            raster_list = [
                x
                for x in grass.parse_command("i.group", flags="lg", group=name)
            ]
            grass.run_command(
                "g.region", raster=raster_list[0], res=res, flags="ap"
            )
            for raster in raster_list:
                cur_r_reg = grass.parse_command(
                    "g.region", flags="ug", raster=raster
                )
                resampled_rast = f"{raster.split('@')[0]}_resampled_{res_str}"
                if (
                    float(cur_r_reg["nsres"]) == float(cur_r_reg["ewres"])
                    and float(cur_r_reg["nsres"]) == res
                ):
                    grass.run_command(
                        "g.rename",
                        raster=f"{raster},{resampled_rast}",
                        overwrite=True,
                    )
                else:
                    # TODO check if this can be parallized
                    grass.run_command(
                        "r.resamp.stats",
                        input=raster,
                        output=resampled_rast,
                        method="median",
                        quiet=True,
                        overwrite=True,
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
            "ir": "nir",
        }
        bands = [rast.split("@")[0].split(".")[1] for rast in raster_list]
        for band in bands:
            raster_of_band = [
                x.split(",")
                for x in grass.parse_command(
                    "g.list",
                    type="raster",
                    pattern=f"{output_name}_*.{band}_resampled_{res_str}",
                    separator="comma",
                )
            ][0]
            band_out = f"{output_name}_{band_mapping[band]}_{res_str}"
            build_raster_vrt(raster_of_band, band_out)
            grass.run_command(
                "i.group", group=f"{output_name}_{res_str}", input=band_out
            )


def import_data(data, dataimport_type, output_name, res=None):
    """Importing data depending on the data import type
    Args:
        data ():
        dataimport_type (str): the import type e.g. vector, buildings,
                               rasterdir or lazdir
        output_name (str): the name or base name for the output data
        res (list of float): a list of resolution values where the
                             output should be resamped to
    """
    if dataimport_type == "vector":
        datakey, col = data, None
        if "," in data:
            datakey, col = data.split(",")
        if options[datakey]:
            col_param = options[col] if col else None
            import_vector(
                options[datakey],
                output_name=output_name,
                area="study_area",
                column=col_param,
            )
    elif dataimport_type == "buildings":
        import_buildings(options[data], output_name, area="study_area")
    elif dataimport_type == "rasterdir":
        if data:
            import_raster_from_dir(
                options[data],
                output_name=output_name,
                resolutions=res,
                study_area="study_area",
            )
    elif dataimport_type == "raster":
        if options[data]:
            import_raster(
                options[data],
                output_name=output_name,
                resolutions=res,
            )
    elif dataimport_type == "rasterORxyz":
        if options[data]:
            if options[data].endswith(".xyz"):
                import_xyz(
                    options[data],
                    float(options["dtm_resolution"]),
                    res,
                    output_name=output_name,
                )
            elif options[data].endswith(".tif"):
                import_raster(
                    options[data], output_name=output_name, resolutions=res
                )
            else:
                grass.fatal(
                    _(
                        f"The <{data}> raster file can not be imported; wrong "
                        "extension. Use a .xyz or .tif file."
                    )
                )
    elif dataimport_type == "lazdir":
        import_laz(
            options[data],
            output_name=output_name,
            resolutions=res,
            study_area="study_area",
        )
    elif dataimport_type in [
        "dop_ndvi",
        "dop_ndvi_scalled",
        "top_ndvi",
        "top_ndvi_scalled",
        "ndsm",
    ]:
        # calculation types nothing to import
        pass
    else:
        grass.warning(
            _(f"Import of data type <{dataimport_type}> not yet supported.")
        )


def compute_data(compute_type, output_name, resoultions=[0.1]):
    """The function to compute data; e.g. computing the NDVI of DOPs or TOPs
    or the nDSM
    compute_type (str): the name of the computing type e.g. dop_ndvi, ndsm,
                        top_ndvi, dop_ndvi_scalled, top_ndvi_scalled
    output_name (str): the name of the generated output raster map
    resolutions (list of float): a list of resolution values where the
                                 output should be resamped to
    """
    if compute_type in ["dop_ndvi", "dop_ndvi_scalled"]:
        scalled = True if "scalled" in compute_type else False
        for res in resoultions:
            compute_ndvi(
                f"dop_nir_{get_res_str(res)}",
                f"dop_red_{get_res_str(res)}",
                output_name=f"dop_{output_name}_{get_res_str(res)}",
                scalled=scalled,
            )
    elif compute_type in ["top_ndvi", "top_ndvi_scalled"]:
        scalled = True if "scalled" in compute_type else False
        for res in resoultions:
            compute_ndvi(
                f"top_nir_{get_res_str(res)}",
                f"top_red_{get_res_str(res)}",
                output_name=f"top_{output_name}_{get_res_str(res)}",
                scalled=scalled,
            )
    elif compute_type == "ndsm":
        for res in resoultions:
            kwargs = {
                "dsm": f"dsm_{get_res_str(res)}",
                "output_name": output_name,
            }
            if options["dtm_file"]:
                kwargs["dtm"] = f"dtm_{get_res_str(res)}"
            compute_ndsm(**kwargs)
    else:
        grass.warning(_(f"Computation of <{compute_type}> not yet supported."))


def main():
    global orig_region, rm_rasters, rm_groups, rm_vectors, rm_files, tmp_dir
    global rm_regions, nprocs

    types = options["type"].split(",")
    nprocs = set_nprocs(int(options["nprocs"]))

    if nprocs > 1:
        check_addon("r.mapcalc.tiled")

    # save orignal region
    orig_region = f"orig_region_{os.getpid()}"
    grass.run_command("g.region", save=orig_region)

    # check if needed addons are installed
    check_addon("r.import.ndsm_nrw", "/path/to/r.import.ndsm_nrw")
    check_addon("r.import.dtm_nrw", "/path/to/r.import.dtm_nrw")

    # check if needed paths to data are set
    grass.message(_("Checking input parameters ..."))
    for ptype in types:
        for data, val in needed_datasets[ptype].items():
            check_data(ptype, data, val)

    if flags["c"]:
        grass.message(
            _(
                "Only the data are checked. For import do not set the '-c' flag."
            )
        )
        exit(0)

    grass.message(_("Importing needed data sets ..."))
    # importing area and set region to area
    import_vector(options["area"], output_name="study_area", extent="input")
    grass.run_command("g.region", vector="study_area", flags="p")
    tmp_dir = grass.tempdir()

    # import other data sets
    for ptype in types:
        for data, val in needed_datasets[ptype].items():
            import_data(val[3], val[4], data, val[0])

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
