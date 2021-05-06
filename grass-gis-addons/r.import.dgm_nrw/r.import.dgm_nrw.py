#!/usr/bin/env python3

############################################################################
#
# MODULE:       r.import.dgm_nrw
#
# AUTHOR(S):    Guido Riembauer <riembauer at mundialis.de>
#
# PURPOSE:      downloads and imports the NRW DGM 1m into the current
#               mapset.
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
#% description: downloads and imports the NRW DGM 1m into the current mapset.
#% keyword: raster
#% keyword: import
#% keyword: cdigital elevation model
#%end

#%option G_OPT_M_DIR
#% key: directory
#% required: no
#% multiple: no
#% label: Directory path where to download and temporarily store the DGM data. If not set, the data will be downloaded to a temporary directory. The downloaded data will be removed after the import.
#%end

#%option G_OPT_MEMORYMB
#%end

#%option G_OPT_R_OUTPUT
#% key: output
#% type: string
#% required: yes
#% multiple: no
#% description: Name of output dgm raster map
#% guisection: Output
#%end

import atexit
import psutil
import os
from pyproj import Transformer
import gzip
from itertools import product
import requests
import shutil
import grass.script as grass
import wget

# initialize global vars
TMPLOC = None
SRCGISRC = None
TGTGISRC = None
GISDBASE = None
rm_vectors = []
rm_rasters = []
old_region = None
rm_files = []
rm_folders = []


def cleanup():
    nuldev = open(os.devnull, 'w')
    kwargs = {
        'flags': 'f',
        'quiet': True,
        'stderr': nuldev
    }
    if TGTGISRC:
        os.environ['GISRC'] = str(TGTGISRC)
    # remove temp location
    if TMPLOC:
        grass.try_rmdir(os.path.join(GISDBASE, TMPLOC))
    if SRCGISRC:
        grass.try_remove(SRCGISRC)
    for rmv in rm_vectors:
        if grass.find_file(name=rmv, element='vector')['file']:
            grass.run_command(
                'g.remove', type='vector', name=rmv, **kwargs)
    for rmrast in rm_rasters:
        if grass.find_file(name=rmrast, element='raster')['file']:
            grass.run_command(
                'g.remove', type='raster', name=rmrast, **kwargs)
    if old_region:
        grass.run_command(
            'g.region', region=old_region)
        grass.run_command(
            'g.remove', type='region', name=old_region, **kwargs)
    for rmfile in rm_files:
        try:
            os.remove(rmfile)
        except Exception as e:
            grass.warning(_('Cannot remove file <%s>: %s' % (rmfile, e)))
    for folder in rm_folders:
        if os.path.isdir(folder):
            try:
                shutil.rmtree(folder)
            except Exception as e:
                grass.warning(_('Cannot remove dir <%s>: %s' % (folder, e)))


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


def transform_coord(x, y, from_epsg, to_epsg):
    transformer = Transformer.from_crs("epsg:%s" % from_epsg,
                                       "epsg:%s" % to_epsg, always_xy=True)
    transformed = transformer.transform(x, y)
    return (transformed[0], transformed[1])


def get_required_tiles():
    # tiles are of 1 * 1 km size
    # the tilename is defined by the lower left corner
    region_dict = grass.parse_command("g.region", flags="g")
    north_raw = region_dict["n"]
    south_raw = region_dict["s"]
    west_raw = region_dict["w"]
    east_raw = region_dict["e"]
    # get projection of current location
    proj = grass.parse_command('g.proj', flags='g')
    if 'epsg' in proj:
        epsg = proj['epsg']
    else:
        epsg = proj['srid'].split('EPSG:')[1]
    if epsg == '25832':
        north = north_raw
        south = south_raw
        west = west_raw
        east = east_raw
        lowerleft = (float(west), float(south))
        upperright = (float(east), float(north))
    else:
        lowerleft = transform_coord(west_raw, south_raw, epsg, "25832")
        upperright = transform_coord(east_raw, north_raw, epsg, "25832")

    required_ns_tiles = list(range(int(lowerleft[1] / 1000),
                             int(upperright[1] / 1000) + 1, 1))
    required_ew_tiles = list(range(int(lowerleft[0] / 1000),
                             int(upperright[0] / 1000) + 1, 1))
    required_tiles_raw = list(product(required_ew_tiles, required_ns_tiles))
    required_tiles = []
    for tile in required_tiles_raw:
        tilename = "dgm1_32_{}_{}_1_nw.xyz.gz".format(tile[0], tile[1])
        required_tiles.append(tilename)
    return(required_tiles)


def createTMPlocation(epsg=4326):
    global TMPLOC, SRCGISRC
    SRCGISRC = grass.tempfile()
    TMPLOC = 'temp_import_location_' + str(os.getpid())
    f = open(SRCGISRC, 'w')
    f.write('MAPSET: PERMANENT\n')
    f.write('GISDBASE: %s\n' % GISDBASE)
    f.write('LOCATION_NAME: %s\n' % TMPLOC)
    f.write('GUI: text\n')
    f.close()

    proj_test = grass.parse_command('g.proj', flags='g')
    if 'epsg' in proj_test:
        epsg_arg = {'epsg': epsg}
    else:
        epsg_arg = {'srid': "EPSG:{}".format(epsg)}
    # create temp location from input without import
    grass.verbose(_("Creating temporary location with EPSG:%d...") % epsg)
    grass.run_command('g.proj', flags='c', location=TMPLOC, quiet=True,
                      **epsg_arg)

    # switch to temp location
    os.environ['GISRC'] = str(SRCGISRC)
    proj = grass.parse_command('g.proj', flags='g')
    if 'epsg' in proj:
        new_epsg = proj['epsg']
    else:
        new_epsg = proj['srid'].split('EPSG:')[1]
    if new_epsg != str(epsg):
        grass.fatal("Creation of temporary location failed!")


def get_actual_location():
    global TGTGISRC, GISDBASE
    # get actual location, mapset, ...
    grassenv = grass.gisenv()
    tgtloc = grassenv['LOCATION_NAME']
    tgtmapset = grassenv['MAPSET']
    GISDBASE = grassenv['GISDBASE']
    TGTGISRC = os.environ['GISRC']
    return tgtloc, tgtmapset


def main():

    global rm_rasters, rm_vectors, old_region, rm_folders, rm_files
    # save old region
    old_region = "saved_region_{}".format(os.getpid())
    grass.run_command("g.region", save=old_region)
    if options['directory']:
        download_dir = options['directory']
        if not os.path.isdir(download_dir):
            os.makedirs(download_dir)
    else:
        download_dir = grass.tempdir()
        rm_folders.append(download_dir)
    required_tiles = get_required_tiles()
    baseurl = ("https://www.opengeodata.nrw.de/produkte/geobasis/hm/"
               "dgm1_xyz/dgm1_xyz/")
    # check if tiles exist
    dl_urls = []
    grass.message(_("Verifying Tile-URLS..."))
    for tile in required_tiles:
        dl_url = os.path.join(baseurl, tile)
        response = requests.get(dl_url)
        if response.status_code != 200:
            grass.warning(_("Tile {} is not available. The region is"
                            " probably partially outside of NRW.").format(
                            tile))
        else:
            dl_urls.append((tile, dl_url))
    if len(dl_urls) == 0:
        grass.fatal(_("No valid tiles found."))
    # Downloading
    grass.message(_("Downloading data..."))
    local_paths = []
    for tile_tuple in dl_urls:
        url = tile_tuple[1]
        tilename = tile_tuple[0]
        dl_target = os.path.join(download_dir, tilename)
        rm_files.append(dl_target)
        try:
            wget.download(url, dl_target)
            local_paths.append((tilename, dl_target))
        except Exception as e:
            grass.fatal(_("There was a problem downloading {}: {}").format(
                url, e))
    # create temp import location if the current location is not 25832
    # save current region as vector
    region_vect = "tmp_region_vect_{}".format(os.getpid())
    rm_vectors.append(region_vect)
    grass.run_command("v.in.region", output=region_vect, quiet=True)
    # get projection of current location
    proj = grass.parse_command('g.proj', flags='g')
    if 'epsg' in proj:
        epsg = proj['epsg']
    else:
        epsg = proj['srid'].split('EPSG:')[1]
    reproject = False
    if epsg != "25832":
        reproject = True
        # get actual location, mapset, ...
        tgtloc, tgtmapset = get_actual_location()
        createTMPlocation(25832)
        grass.run_command("v.proj", location=tgtloc, mapset=tgtmapset,
                          input=region_vect, output=region_vect, quiet=True)

    raster_maps = []
    grass.message(_("\nImporting data..."))
    for idx, path_tuple in enumerate(local_paths):
        path = path_tuple[1]
        tilename = path_tuple[0]
        basename_tmp = os.path.basename(path)
        basename = os.path.splitext(basename_tmp)[0].split(".xyz")[0]
        raster_maps.append(basename)
        rm_rasters.append(basename)
        with gzip.open(path, "rb") as file:
            file_content = file.read()
        region_proc = grass.start_command('r.in.xyz', output="dummy",
                                          input="-", flags="sg",
                                          separator="space", stdin=grass.PIPE,
                                          stdout=grass.PIPE)
        region_proc.stdin.write(file_content)
        stdout = region_proc.communicate()[0].decode("ascii")
        region_proc.stdin.close()
        region_proc.wait()
        arglist = stdout.split(" ")
        north = float([item for item in arglist if "n=" in item][0].replace(
                "n=", "")) + 0.5
        south = float([item for item in arglist if "s=" in item][0].replace(
                "s=", "")) - 0.5
        west = float([item for item in arglist if "w=" in item][0].replace(
                "w=", "")) - 0.5
        east = float([item for item in arglist if "e=" in item][0].replace(
                "e=", "")) + 0.5
        grass.run_command("g.region", n=north, s=south, w=west, e=east, res=1)
        import_proc = grass.feed_command('r.in.xyz', output=basename,
                                         input="-", method="mean",
                                         separator="space", quiet=True)
        import_proc.stdin.write(file_content)
        import_proc.stdin.close()
        import_proc.wait()
    grass.run_command("g.region", vector=region_vect, res=1, quiet=True)
    grass.run_command("r.patch", input=",".join(raster_maps),
                      output=options["output"])
    if reproject is True:
        test_memory()
        # switch to target location
        os.environ['GISRC'] = str(TGTGISRC)
        grass.run_command("g.region", region=old_region, quiet=True)
        grass.run_command("r.proj", location=TMPLOC, mapset="PERMANENT",
                          input=options["output"], output=options["output"],
                          memory=options["memory"], resolution=1.0,
                          method="bilinear", quiet=True)

    grass.message(_("Created output dgm raster map <{}>").format(
        options["output"]))


if __name__ == "__main__":
    options, flags = grass.parser()
    atexit.register(cleanup)
    main()
