#!/usr/bin/env python3

import grass.script as grass
import multiprocessing as mp
import psutil
import os
import shutil


def freeRAM(unit, percent=100):
    """The function gives the amount of the percentages of the available
    RAM memory and free swap space.
    Args:
        unit(string): 'GB' or 'MB'
        percent(int): number of percent which shoud be used of the available
                      RAM memory and free swap space
                      default 100%
    Returns:
        memory_MB_percent/memory_GB_percent(int): percent of the the available
                                                  memory and free swap in MB or
                                                  GB

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
        grass.fatal("Memory unit %s not supported" % unit)


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
            f"new mapset is {cur_mapset}, but should be {start_cur_mapset}"
        )
    location_path = os.path.join(gisdbase, location)
    return location_path


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
                    f"Using {nprocs} parallel processes "
                    f"but only {nprocs_real} CPUs available."
                )
            )
            nprocs = nprocs_real

    return nprocs


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


def create_grid_cd(tile_size, vec1, vec2):
    """Create a grid for parallelization for change detection case
       (have to check two vector maps)
    Args:
        tile_size (float): the size for the tiles in map units
        vec1 (str): the name of the first vector map for which to
                    create the grid tiles
        vec2 (str): the name of the second vector map for which to
                    create the grid tiles
    Return:
        grid_trees (str): the name of the created grid vector map,
                          overlapping with vec1 and vec2
        tiles_list (list): list of created tiles
        number_tiles (int): Number of created tiles
        rm_vectors (list): list of vector maps which should be
                           deleted in the cleanup
    """
    # check if region is smaller than tile size
    region = grass.region()
    dist_ns = abs(region["n"] - region["s"])
    dist_ew = abs(region["w"] - region["e"])

    rm_vectors = list()

    # create tiles
    grass.message(_("Creating tiles..."))
    # if area smaller than one tile
    if dist_ns <= float(tile_size) and dist_ew <= float(tile_size):
        grid = f"grid_{os.getpid()}"
        rm_vectors.append(grid)
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
        grid = f"grid_{os.getpid()}"
        rm_vectors.append(grid)
        grass.run_command(
            "v.mkgrid", map=grid, box=f"{tile_size},{tile_size}", quiet=True
        )

        # reset region
        grass.run_command("g.region", region=orig_region, quiet=True)
        orig_region = None

    # grid only for tiles with trees
    grid_trees = f"grid_with_trees_{os.getpid()}"
    rm_vectors.append(grid_trees)
    grid_trees_t1 = f"{grid_trees}_t1"
    rm_vectors.append(grid_trees_t1)
    grid_trees_t2 = f"{grid_trees}_t2"
    rm_vectors.append(grid_trees_t2)
    grass.run_command(
        "v.select",
        ainput=grid,
        binput=vec1,
        output=grid_trees_t1,
        operator="overlap",
        quiet=True,
    )
    grass.run_command(
        "v.select",
        ainput=grid,
        binput=vec2,
        output=grid_trees_t2,
        operator="overlap",
        quiet=True,
    )
    grass.run_command(
        "v.overlay",
        ainput=grid_trees_t1,
        binput=grid_trees_t2,
        operator="or",
        output=grid_trees,
        quiet=True,
    )
    if not grass.find_file(name=grid_trees, element="vector")["file"]:
        grass.fatal(
            _(
                f"The set region is not overlapping with {grid_trees}. "
                "Please define another region."
            )
        )

    # create list of tiles
    tiles_list = list(
        grass.parse_command(
            "v.db.select", map=grid_trees, columns="cat", flags="c", quiet=True
        ).keys()
    )
    number_tiles = len(tiles_list)
    grass.message(_(f"Number of tiles is: {number_tiles}"))

    return grid_trees, tiles_list, number_tiles, rm_vectors
