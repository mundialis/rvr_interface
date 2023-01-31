#!/usr/bin/env python3

import grass.script as grass
import psutil
import subprocess
import os
import shutil
import gc


def general_cleanup(
    rm_rasters=[],
    rm_vectors=[],
    rm_files=[],
    rm_dirs=[],
    rm_groups=[],
    rm_groups_wo_rasters=[],
    rm_regions=[],
    rm_strds=[],
    orig_region=None,
):

    grass.message(_("Cleaning up..."))
    nulldev = open(os.devnull, "w")
    kwargs = {"flags": "f", "quiet": True, "stderr": nulldev}
    for rmg in rm_groups:
        if grass.find_file(name=rmg, element="group")["file"]:
            group_rasters = grass.parse_command(
                "i.group", flags="lg", group=rmg
            )
            rm_rasters.extend(group_rasters)
            grass.run_command("g.remove", type="group", name=rmg, **kwargs)
    for rmg_wor in rm_groups_wo_rasters:
        if grass.find_file(name=rmg_wor, element="group")["file"]:
            grass.run_command("g.remove", type="group", name=rmg_wor, **kwargs)
    for rmrast in rm_rasters:
        if grass.find_file(name=rmrast, element="raster")["file"]:
            grass.run_command("g.remove", type="raster", name=rmrast, **kwargs)
    for rmvect in rm_vectors:
        if grass.find_file(name=rmvect, element="vector")["file"]:
            grass.run_command("g.remove", type="vector", name=rmvect, **kwargs)
    for rmfile in rm_files:
        if os.path.isfile(rmfile):
            os.remove(rmfile)
    for rmdir in rm_dirs:
        if os.path.isdir(rmdir):
            shutil.rmtree(rmdir)
    if orig_region is not None:
        if grass.find_file(name=orig_region, element="windows")["file"]:
            grass.run_command("g.region", region=orig_region)
            grass.run_command(
                "g.remove", type="region", name=orig_region, **kwargs
            )
    for rmreg in rm_regions:
        if grass.find_file(name=rmreg, element="windows")["file"]:
            grass.run_command("g.remove", type="region", name=rmreg, **kwargs)
    strds = grass.parse_command("t.list", type="strds")
    mapset = grass.gisenv()["MAPSET"]
    for rm_s in rm_strds:
        if f"{rm_s}@{mapset}" in strds:
            grass.run_command(
                "t.remove",
                flags="rf",
                type="strds",
                input=rm_s,
                quiet=True,
                stderr=nulldev,
            )

    # get location size
    get_location_size()

    # Garbage Collector: release unreferenced memory
    gc.collect()


def get_location_size():
    current_gisdbase = grass.gisenv()["GISDBASE"]
    cmd = grass.Popen(
        "df -h %s" % current_gisdbase, shell=True, stdout=subprocess.PIPE
    )
    grass.message(
        "\nDisk usage of GRASS GIS database:\n %s\n"
        % cmd.communicate()[0].decode("utf-8").rstrip()
    )


def communicate_grass_command(*args, **kwargs):
    kwargs["stdout"] = grass.PIPE
    kwargs["stderr"] = grass.PIPE
    ps = grass.start_command(*args, **kwargs)
    return ps.communicate()


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
