#!/usr/bin/env python3

############################################################################
#
# MODULE:       r.analyse.buildings
#
# AUTHOR(S):    Julia Haas <haas at mundialis.de>
#               Guido Riembauer <riembauer at mundialis.de>
#
# PURPOSE:      Extracts buildings from nDOM, NDVI and FNK
#
# COPYRIGHT:	(C) 2023 by mundialis and the GRASS Development Team
#
#		This program is free software under the GNU General Public
#		License (>=v2). Read the file COPYING that comes with GRASS
#		for details.
#
#############################################################################

# %Module
# % description: Extracts buildings from nDOM, NDVI and FNK
# % keyword: raster
# % keyword: statistics
# % keyword: change detection
# % keyword: classification
# %end

# %option G_OPT_R_INPUT
# % key: ndom
# % type: string
# % required: yes
# % multiple: no
# % label: Name of the nDOM
# %end

# %option G_OPT_R_INPUT
# % key: ndvi_raster
# % type: string
# % required: yes
# % multiple: no
# % label: Name of the NDVI raster
# %end

# %option G_OPT_V_INPUTS
# % key: fnk_vector
# % type: string
# % required: yes
# % multiple: no
# % label: Vector map containing Flaechennutzungskatalog
# %end

# %option G_OPT_V_INPUTS
# % key: fnk_column
# % type: string
# % required: yes
# % multiple: no
# % label: Integer column containing FNK-code
# %end

# %option
# % key: min_size
# % type: integer
# % required: no
# % multiple: no
# % label: Minimum size of buildings in sqm
# % answer: 20
# %end

# %option
# % key: max_fd
# % type: double
# % required: no
# % multiple: no
# % label: Maximum value of fractal dimension of identified objects (see v.to.db)
# % answer: 2.1
# %end

# %option
# % key: ndvi_perc
# % type: integer
# % required: no
# % multiple: no
# % label: ndvi percentile in vegetated areas to use for thresholding
# %end

# %option
# % key: ndvi_thresh
# % type: integer
# % required: no
# % multiple: no
# % label: define fix NDVI threshold (on a scale from 0-255) instead of estimating it from FNK
# %end

# %option G_OPT_MEMORYMB
# %end

# %option G_OPT_V_OUTPUT
# % key: output
# % type: string
# % required: yes
# % multiple: no
# % description: Name for output vector map
# % guisection: Output
# %end

# %option
# % key: nprocs
# % type: integer
# % required: no
# % multiple: no
# % label: Number of parallel processes
# % description: Number of cores for multiprocessing, -2 is the number of available cores - 1
# % answer: -2
# %end

# %option
# % key: tile_size
# % type: integer
# % required: yes
# % multiple: no
# % label: define edge length of grid tiles for parallel processing
# %end

# %flag
# % key: s
# % description: segment image based on nDOM and NDVI before building extraction
# %end

# %rules
# % exclusive: ndvi_perc, ndvi_thresh
# % required: ndvi_perc, ndvi_thresh
# %end

import atexit
import psutil
import os
import re
import multiprocessing as mp
from uuid import uuid4
import grass.script as grass
from grass.pygrass.modules import Module, ParallelModuleQueue

# initialize global vars
rm_rasters = []
rm_vectors = []
rm_groups = []
tmp_mask_old = None
orig_region = None


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
    for rmv in rm_vectors:
        if grass.find_file(name=rmv, element='vector')['file']:
            grass.run_command(
                'g.remove', type='vector', name=rmv, **kwargs)
    for rmgroup in rm_groups:
        if grass.find_file(name=rmgroup, element='group')['file']:
            grass.run_command(
                'g.remove', type='group', name=rmgroup, **kwargs)
    if orig_region is not None:
        if grass.find_file(name=orig_region, element="windows")["file"]:
            grass.run_command("g.region", region=orig_region)
            grass.run_command(
                "g.remove", type="region", name=orig_region, **kwargs
            )
    if grass.find_file(name='MASK', element='raster')['file']:
        try:
            grass.run_command("r.mask", flags='r', quiet=True)
        except:
            pass
    # reactivate potential old mask
    if tmp_mask_old:
        grass.run_command('r.mask', raster=tmp_mask_old, quiet=True)


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


def main():

    global rm_rasters, tmp_mask_old, rm_vectors, rm_groups, orig_region

    ndom = options['ndom']
    ndvi = options['ndvi_raster']
    fnk_vect = options['fnk_vector']
    fnk_column = options['fnk_column']
    min_size = options['min_size']
    max_fd = options['max_fd']
    ndvi_perc = options['ndvi_perc']
    ndvi_thresh = options['ndvi_thresh']
    memory = options['memory']
    output_vect = options['output']
    nprocs = int(options['nprocs'])
    tile_size = options['tile_size']
    #cd_flag = flags["c"]

    if nprocs == -2:
        nprocs = mp.cpu_count() - 1 if mp.cpu_count() > 1 else 1
    else:
        # Test nprocs settings
        nprocs_real = mp.cpu_count()
        if nprocs > nprocs_real:
            grass.warning(
                f"Using {nprocs} parallel processes but only {nprocs_real} CPUs available."
            )
            nprocs = nprocs_real

    # set region
    orig_region = f"grid_region_{os.getpid()}"
    grass.run_command("g.region", save=orig_region)
    grass.run_command("g.region", res=tile_size, flags="a")

    # create grid
    grass.message(_("Creating tiles..."))
    grid = f"grid_{os.getpid()}"
    rm_vectors.append(grid)
    grass.run_command(
        "v.mkgrid",
        map=grid,
        box=f"{tile_size},{tile_size}",
        quiet=True
    )

    # reset region
    grass.run_command("g.region", region=orig_region)
    orig_region = None

    # grid only for tiles with fnk
    grid_fnk = f"grid_with_FNK_{os.getpid()}"
    rm_vectors.append(grid_fnk)
    grass.run_command(
        "v.select",
        ainput=grid,
        binput=fnk_vect,
        output=grid_fnk,
        operator="overlap",
        quiet=True
    )

    # create list of tiles
    tiles_list = list(grass.parse_command(
                        "v.db.select",
                        map=grid_fnk,
                        columns="cat",
                        flags="c",
                        quiet=True
                      ).keys())

    # tiles_list = [8, 19]
    number_tiles = len(tiles_list)
    grass.message(_(f"Number of tiles is: {number_tiles}"))

    # Start building detection in parallel
    grass.message(_("Applying building detection..."))
    # save current mapset
    start_cur_mapset = grass.gisenv()["MAPSET"]

    # Loop over tiles_list
    if number_tiles < nprocs:
        nprocs = number_tiles
    queue = ParallelModuleQueue(nprocs=nprocs)
    output_list = list()
    mapset_names = list()
    buildings_list = list()

    for tile in tiles_list:
        # Module
        new_mapset = f"tmp_mapset_apply_extraction_{tile}_{uuid4()}"
        mapset_names.append(new_mapset)
        tile_area = f"grid_cell_{tile}_{os.getpid()}"
        rm_vectors.append(tile_area)
        grass.run_command(
            "v.extract",
            input=grid_fnk,
            where=f"cat == {tile}",
            output=tile_area,
            quiet=True
        )
        bu_output = f"buildings_{tile}_{os.getpid()}"
        buildings_list.append(bu_output)

        param = {
            "area": tile_area,
            "output": bu_output,
            "new_mapset": new_mapset,
            "ndom": ndom,
            "ndvi_raster": ndvi,
            "fnk_vector": fnk_vect,
            "fnk_column": fnk_column,
            "min_size": min_size,
            "max_fd": max_fd,
            "memory": memory,
        }

        if ndvi_thresh:
            param["ndvi_thresh"] = ndvi_thresh
        if ndvi_perc:
            param["ndvi_perc"] = ndvi_perc

        if flags["s"]:
            param["flags"] = "s"

        r_extract_buildings_worker = Module(
            "r.extract.buildings.worker",
            **param,
            run_=False,
        )

        # catch all GRASS outputs to stdout and stderr
        r_extract_buildings_worker.stdout_ = grass.PIPE
        r_extract_buildings_worker.stderr_ = grass.PIPE
        queue.put(r_extract_buildings_worker)
    queue.wait()

    for proc in queue.get_finished_modules():
        msg = proc.outputs["stderr"].value.strip()
        grass.message(_(f"\nLog of {proc.get_bash()}:"))
        for msg_part in msg.split("\n"):
            grass.message(_(msg_part))
        # create mapset dict based on Log, so that only those with output are listed
        if "No potential buildings detected. Skipping..." not in msg:
            tile_output = re.search(r"Output is:\n<(.*?)>", msg).groups()[0]
            output_list.append(tile_output)

    #grass.run_command("r.extract.buildings.worker", **param, quiet=True)

    # verify that switching the mapset worked
    location_path = verify_mapsets(start_cur_mapset)

    # get outputs from mapsets and merge (minimize edge effects)
    for entry in output_list:
        import pdb; pdb.set_trace()
        #rm_vectors.append(building_vect)
        grass.run_command(
            "g.copy",
            vector=f"{entry},{building_vect}")

    # TODO: merge outputs

    # remove temporary mapsets
    for tmp_mapset in mapset_names:
        grass.utils.try_rmdir(os.path.join(location_path, tmp_mapset))
        print(os.path.join(location_path, tmp_mapset))

    import pdb; pdb.set_trace()
    a=1

    # if flag c is set, make change detection
    # Parallelisierung vermutlich sinnvoll wegen Buffering
    # if cd_flag:
    #     pass


if __name__ == "__main__":
    options, flags = grass.parser()
    atexit.register(cleanup)
    main()
