#!/usr/bin/env python3

############################################################################
#
# MODULE:       lib for m.analyse.buildings
#
# AUTHOR(S):    Julia Haas
#               Anika Weinmann
#
# PURPOSE:      lib for m.analyse.buildings
#
# COPYRIGHT:	(C) 2023 by mundialis and the GRASS Development Team
#
# 		This program is free software under the GNU General Public
# 		License (>=v2). Read the file COPYING that comes with GRASS
# 		for details.
#
#############################################################################

import os
import multiprocessing as mp
import shutil

import grass.script as grass
import psutil


def build_raster_vrt(raster_list, output_name):
    """Build raster VRT if the length of the raster list is greater 1 otherwise
    renaming of the raster
    Args:
        raster_list (list of strings): List of raster maps
        output_name (str): Name of the output raster map
    """
    if isinstance(raster_list, list) > 1:
        grass.run_command(
            "r.buildvrt",
            input=raster_list,
            output=output_name,
            quiet=True,
        )
    else:
        grass.run_command(
            "g.rename",
            raster=f"{raster_list[0]},{output_name}",
            quiet=True,
        )


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


def create_grid(tile_size, grid_prefix, area):
    """Create a grid for parallelization
    Args:
        tile_size (float): the size for the tiles in map units
        grid_prefix (str): the prefix name for the output grid
        area (str): the name of area for which to create the grid tiles
    Return:
        grid_prefix (list): list with the names of the created vector map tiles
        number_tiles (int): Number of created tiles
    """
    # check if region is smaller than tile size
    region = grass.region()
    dist_ns = abs(region["n"] - region["s"])
    dist_ew = abs(region["w"] - region["e"])

    grass.message(_("Creating tiles..."))
    grid = f"tmp_grid_{os.getpid()}"
    if dist_ns <= float(tile_size) and dist_ew <= float(tile_size):
        grass.run_command("v.in.region", output=grid, quiet=True)
        grass.run_command(
            "v.db.addtable", map=grid, columns="cat int", quiet=True
        )
    else:
        # set region
        orig_region = f"grid_region_{os.getpid()}"
        grass.run_command("g.region", save=orig_region, quiet=True)
        grass.run_command("g.region", res=tile_size, flags="a", quiet=True)

        # create grid
        grass.run_command(
            "v.mkgrid", map=grid, box=f"{tile_size},{tile_size}", quiet=True
        )
        # reset region
        reset_region(orig_region)
    grid_name = f"tmp_grid_area_{os.getpid()}"
    grass.run_command(
        "v.select",
        ainput=grid,
        binput=area,
        output=grid_name,
        operator="overlap",
        quiet=True,
    )
    if grass.find_file(name=grid_name, element="vector")["file"] == "":
        grass.fatal(
            _(
                f"The set region is not overlapping with {area}. "
                f"Please define another region."
            )
        )

    # create list of tiles
    tiles_num_list = list(
        grass.parse_command(
            "v.db.select", map=grid_name, columns="cat", flags="c", quiet=True
        ).keys()
    )

    number_tiles = len(tiles_num_list)
    grass.message(_(f"Number of tiles is: {number_tiles}"))
    tiles_list = []
    for tile in tiles_num_list:
        tile_area = f"{grid_prefix}_{tile}"
        grass.run_command(
            "v.extract",
            input=grid_name,
            where=f"cat == {tile}",
            output=tile_area,
            quiet=True,
        )
        tiles_list.append(tile_area)

    # cleanup
    nuldev = open(os.devnull, "w")
    kwargs = {"flags": "f", "quiet": True, "stderr": nuldev}
    for rmv in [grid, grid_name]:
        if grass.find_file(name=rmv, element="vector")["file"]:
            grass.run_command("g.remove", type="vector", name=rmv, **kwargs)

    return tiles_list, number_tiles


def get_bins():
    cells = grass.region()["cells"]
    cells_div = cells / 1000000
    bins = 1000000 if cells_div <= 1000000 else round(cells_div)

    return bins


def get_percentile(raster, percentiles):
    bins = get_bins()
    perc_values_list = list(
        (
            grass.parse_command(
                "r.quantile",
                input=raster,
                percentiles=percentiles,
                bins=bins,
                quiet=True,
            )
        ).keys()
    )
    if isinstance(percentiles, list):
        return [item.split(":")[2] for item in perc_values_list]
    else:
        return float(perc_values_list[0].split(":")[2])


def get_free_ram(unit, percent=100):
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
        grass.fatal(_(f"Memory unit <{unit}> not supported"))


def reset_region(region):
    """Function to set the region to the given region
    Args:
        region (str): the name of the saved region which should be set and
                      deleted
    """
    nulldev = open(os.devnull, "w")
    kwargs = {"flags": "f", "quiet": True, "stderr": nulldev}
    if region:
        if grass.find_file(name=region, element="windows")["file"]:
            grass.run_command("g.region", region=region)
            grass.run_command("g.remove", type="region", name=region, **kwargs)


def set_nprocs(nprocs):
    if nprocs == -2:
        nprocs = mp.cpu_count() - 1 if mp.cpu_count() > 1 else 1
    elif nprocs in (-1, 0):
        grass.warning(
            _(
                f"Number of cores for multiprocessing must be 1 or "
                f"higher. Option <nprocs> will be set to 1 (serial "
                f"processing). \n To use other number of cores, please "
                f"set <nprocs> to 1 or higher. To use all available "
                f"cores -1 do not set the <nprocs> option."
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

    grass.message(_(f"New mapset. {new_mapset}"))
    grass.utils.try_rmdir(os.path.join(gisdbase, location, new_mapset))

    gisrc = os.environ["GISRC"]
    newgisrc = f"{gisrc}_{str(os.getpid())}"
    grass.try_remove(newgisrc)
    shutil.copyfile(gisrc, newgisrc)
    os.environ["GISRC"] = newgisrc

    grass.message(_(f'GISRC: {os.environ["GISRC"]}'))
    grass.run_command("g.mapset", flags="c", mapset=new_mapset, quiet=True)

    # verify that switching of the mapset worked
    cur_mapset = grass.gisenv()["MAPSET"]
    if cur_mapset != new_mapset:
        grass.fatal(
            _(f"New mapset is {cur_mapset}, but should be {new_mapset}")
        )
    return gisrc, newgisrc, old_mapset


def test_memory(memory_string):
    # check memory
    memory = int(memory_string)
    free_ram = get_free_ram("MB", 100)
    if free_ram < memory:
        grass.warning(
            _(f"Using {memory} MB but only {free_ram} MB RAM available.")
        )
        grass.warning(_(f"Set used memory to {free_ram} MB."))
        return free_ram
    else:
        return memory


def verify_mapsets(start_cur_mapset):
    """The function verifies the switches to the start_cur_mapset.

    Args:
        start_cur_mapset (string): Name of the mapset which is to verify
    Returns:
        location_path (string): The path of the location
    """
    env = grass.gisenv()
    gisdbase = env["GISDBASE"]
    location = env["LOCATION_NAME"]
    cur_mapset = env["MAPSET"]
    if cur_mapset != start_cur_mapset:
        grass.fatal(
            _(f"New mapset is {cur_mapset}, but should be {start_cur_mapset}")
        )
    location_path = os.path.join(gisdbase, location)
    return location_path
