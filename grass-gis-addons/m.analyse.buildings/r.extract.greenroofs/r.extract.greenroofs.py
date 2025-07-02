#!/usr/bin/env python3

############################################################################
#
# MODULE:       r.extract.greenroofs
#
# AUTHOR(S):    Julia Haas, Guido Riembauer and Anika Weinmann
#
# PURPOSE:      Extracts green roofs on buildings from nDSM, NDVI, GB-Ratio,
#               FNK and building outlines
#
# COPYRIGHT:	(C) 2022 - 2024 by mundialis and the GRASS Development Team
#
# 		This program is free software under the GNU General Public
# 		License (>=v2). Read the file COPYING that comes with GRASS
# 		for details.
#
#############################################################################

# %Module
# % description: Extracts green roofs from nDSM, NDVI, GB-Ratio, FNK and building outlines.
# % keyword: raster
# % keyword: classification
# % keyword: statistics
# % keyword: buildings analysis
# % keyword: green roofs
# %end

# %option G_OPT_R_INPUT
# % key: ndsm
# % label: Name of the nDSM raster
# % answer: ndsm
# % guisection: Input
# %end

# %option G_OPT_R_INPUT
# % key: ndvi
# % label: Name of the NDVI raster
# % answer: dop_ndvi_05
# % guisection: Input
# %end

# %option G_OPT_R_INPUT
# % key: red
# % label: Name of the red DOP raster
# % answer: dop_red_05
# % guisection: Input
# %end

# %option G_OPT_R_INPUT
# % key: green
# % label: Name of the green DOP raster
# % answer: dop_green_05
# % guisection: Input
# %end

# %option G_OPT_R_INPUT
# % key: blue
# % label: Name of the blue DOP raster
# % answer: dop_blue_05
# % guisection: Input
# %end

# %option G_OPT_V_INPUT
# % key: fnk
# % required: no
# % label: Name of vector map containing the Flaechennutzungskartierung
# % guisection: Optional input
# % guidependency: fnk_column
# %end

# %option G_OPT_DB_COLUMN
# % key: fnk_column
# % label: Name of integer column containing FNK-code
# % guisection: Optional input
# %end

# %option G_OPT_V_INPUT
# % key: buildings
# % label: Name of vector map containing outlines of buildings
# % answer: building_outlines
# % guisection: Input
# %end

# %option G_OPT_V_INPUT
# % key: trees
# % required: no
# % label: Vector map containing tree polygons
# % guisection: Optional input
# %end

# %option
# % key: used_thresh
# % required: yes
# % multiple: no
# % label: Set if the percentile or the threshold of the Green-Blue-Ratio should be used: gb_thresh or gb_perc
# % options: gb_thresh,gb_perc
# % answer: gb_thresh
# % guisection: Parameters
# %end

# %option
# % key: gb_thresh
# % type: integer
# % required: no
# % multiple: no
# % label: Fix Green-Blue-Ratio threshold (on a scale from 0-255)
# % options: 0-255
# % answer: 145
# % guisection: Parameters
# %end

# %option
# % key: gb_perc
# % type: integer
# % required: no
# % multiple: no
# % label: Green-Blue-Ratio percentile in green areas to use for thresholding
# % options: 0-100
# % answer: 25
# % guisection: Parameters
# %end

# %option
# % key: min_veg_size
# % type: integer
# % required: yes
# % multiple: no
# % label: Minimum size of roof vegetation in sqm
# % answer: 5
# % guisection: Parameters
# %end

# %option
# % key: min_veg_proportion
# % type: integer
# % required: yes
# % multiple: no
# % label: Minimum percentage of vegetation cover on roof
# % answer: 10
# % guisection: Parameters
# %end

# %option G_OPT_V_OUTPUT
# % key: output_buildings
# % label: Name for output buildings vector map
# % answer: buildings_with_green_roofs
# % guisection: Output
# %end

# %option G_OPT_V_OUTPUT
# % key: output_vegetation
# % label: Name for output roof vegetation vector map
# % answer: green_roofs
# % guisection: Output
# %end

# %option G_OPT_MEMORYMB
# % guisection: Parallel processing
# %end

# %option G_OPT_M_NPROCS
# % label: Number of cores for multiprocessing, -2 is the number of available cores - 1
# % answer: -2
# % guisection: Parallel processing
# %end

# %option
# % key: tile_size
# % type: integer
# % required: yes
# % multiple: no
# % label: Define edge length of grid tiles for parallel processing
# % answer: 1000
# % guisection: Parallel processing
# %end

# %flag
# % key: s
# % label: Segment image based on nDSM, NDVI and blue/green ratio before green roof extraction
# % guisection: Parameters
# %end

# %rules
# % requires_all: gb_perc, fnk_column, fnk
# %end

import atexit
import json
import os
import sys

import grass.script as grass
from grass.pygrass.modules import Module, ParallelModuleQueue
from grass.pygrass.utils import get_lib_path
import re

# initialize global vars
rm_rasters = []
rm_vectors = []
rm_groups = []
rm_tables = []
rm_mapsets = []
tmp_mask_old = None
mapcalc_tiled_kwargs = {}
r_mapcalc_cmd = "r.mapcalc"


def try_remove_mask():
    if grass.find_file(name="MASK", element="cell")["file"]:
        try:
            grass.run_command("r.mask", flags="r", quiet=True)
        except Exception:
            pass


def cleanup():
    nuldev = open(os.devnull, "w")
    kwargs = {"flags": "f", "quiet": True, "stderr": nuldev}
    for rmrast in rm_rasters:
        if grass.find_file(name=rmrast, element="cell")["file"]:
            grass.run_command("g.remove", type="raster", name=rmrast, **kwargs)
    for rmv in rm_vectors:
        if grass.find_file(name=rmv, element="vector")["file"]:
            grass.run_command("g.remove", type="vector", name=rmv, **kwargs)
    for rmgroup in rm_groups:
        if grass.find_file(name=rmgroup, element="group")["file"]:
            grass.run_command("g.remove", type="group", name=rmgroup, **kwargs)
    for rmtable in rm_tables:
        remove_table_str = f"DROP TABLE IF EXISTS {rmtable}"
        grass.run_command("db.execute", sql=remove_table_str)
    try_remove_mask()
    for rm_mapset in rm_mapsets:
        gisenv = grass.gisenv()
        mapset_path = os.path.join(
            gisenv["GISDBASE"], gisenv["LOCATION_NAME"], rm_mapset
        )
        grass.try_rmdir(mapset_path)
    # reactivate potential old mask
    if tmp_mask_old:
        if grass.find_file(name=tmp_mask_old, element="cell")["file"]:
            grass.run_command("r.mask", raster=tmp_mask_old, quiet=True)
            grass.run_command(
                "g.remove", type="raster", name=tmp_mask_old, **kwargs
            )


def calculate_auxiliary_datasets_and_brightness(red, green, blue):
    """Function to calculate auyiliary datasets and brightness
    Args:
        red (str): Name of red raster map
        green (str): Name of green raster map
        blue (str): Name of blue raster map
    """
    grass.message(_("Calculating auxiliary datasets..."))
    # GB-ratio
    green_blue_ratio = f"green_blue_ratio_{os.getpid()}"
    rm_rasters.append(green_blue_ratio)
    gb_expression = (
        f"{green_blue_ratio} = round(255*(1.0+"
        f"(float({green}-{blue})/({green}+{blue})))/2)"
    )
    grass.run_command(
        r_mapcalc_cmd,
        expression=gb_expression,
        quiet=True,
        **mapcalc_tiled_kwargs,
    )
    # RG_ratio
    red_green_ratio = f"red_green_ratio_{os.getpid()}"
    rm_rasters.append(red_green_ratio)
    rg_expression = (
        f"{red_green_ratio} = round(255*(1.0+"
        f"(float({red}-{green})/({red}+{green})))/2)"
    )
    grass.run_command(
        r_mapcalc_cmd,
        expression=rg_expression,
        quiet=True,
        **mapcalc_tiled_kwargs,
    )
    # brightness
    brightness = f"brightness_{os.getpid()}"
    rm_rasters.append(brightness)
    bn_expression = f"{brightness} = ({red}+{green})/2"
    grass.run_command(
        r_mapcalc_cmd,
        expression=bn_expression,
        quiet=True,
        **mapcalc_tiled_kwargs,
    )
    return green_blue_ratio, red_green_ratio, brightness


def calculate_gb_threshold(green_blue_ratio, fnk_vect, gb_perc):
    """Function to calculate GB-ratio threshold
    Args:
        green_blue_ratio (str): Name of GB-ratio raster map
        fnk_vect (str): Name of FNK vector map
        gb_perc (str of float): Name of GB-ration percentile to select
    """
    grass.message(_("Calculating GB threshold..."))
    try:
        from analyse_buildings_lib import get_percentile
    except Exception:
        grass.fatal("m.analyse.buildings library is not installed")
    # rasterizing fnk vector with fnk-codes with green areas
    # (gardens, parks, meadows) (not parallel)
    fnk_rast = f"fnk_rast_{os.getpid()}"
    rm_rasters.append(fnk_rast)
    col = options["fnk_column"]
    fnk_codes_green = [
        f"{col}='271'",
        f"{col}='272'",
        f"{col}='273'",
        f"{col}='361'",
    ]
    grass.run_command(
        "v.to.rast",
        input=fnk_vect,
        use="val",
        value=1,
        output=fnk_rast,
        where=" or ".join(fnk_codes_green),
        memory=options["memory"],
        quiet=True,
    )
    # set MASK
    grass.run_command("g.rename", raster=f"{fnk_rast},MASK", quiet=True)
    # get GB statistics
    gb_percentile = float(gb_perc)
    gb_thresh = get_percentile(green_blue_ratio, gb_percentile)
    grass.message(_(f"GB threshold is at {gb_thresh}"))
    grass.run_command("r.mask", flags="r", quiet=True)
    return gb_thresh


def create_building_mask(building_outlines, trees):
    """Function to create a MASK for the buildings (without trees)
    Args:
        building_outlines (str): Name of building vector map
        trees (str): Name of tree vector map
    """
    global rm_rasters, rm_vectors
    # create MASK
    if trees:
        buildings_clipped = f"buildings_clipped_{os.getpid()}"
        rm_vectors.append(buildings_clipped)
        grass.run_command(
            "v.overlay",
            ainput=building_outlines,
            binput=trees,
            operator="not",
            output=buildings_clipped,
            quiet=True,
        )
        mask_vector = buildings_clipped
        cat_col = "a_cat"
    else:
        mask_vector = building_outlines
        cat_col = "cat"
    building_rast = f"building_rast_{os.getpid()}"
    rm_rasters.append(building_rast)
    grass.run_command(
        "v.to.rast",
        input=mask_vector,
        use="attr",
        attribute_column=cat_col,
        output=building_rast,
        memory=options["memory"],
        quiet=True,
    )
    grass.run_command("r.mask", raster=building_rast, quiet=True)
    return building_rast


def main():
    global rm_rasters, tmp_mask_old, rm_vectors, rm_groups, rm_tables
    global mapcalc_tiled_kwargs, r_mapcalc_cmd, rm_mapsets

    path = get_lib_path(
        modname="m.analyse.buildings",
        libname="analyse_buildings_lib",
    )
    if path is None:
        grass.fatal("Unable to find the analyse buildings library directory")
    sys.path.append(path)
    try:
        from analyse_buildings_lib import (
            check_addon,
            create_grid,
            get_percentile,
            set_nprocs,
            test_memory,
            verify_mapsets,
        )
    except Exception:
        grass.fatal("m.analyse.buildings library is not installed")

    ndsm = options["ndsm"]
    ndvi = options["ndvi"]
    red = options["red"]
    green = options["green"]
    blue = options["blue"]
    trees = options["trees"]
    fnk_vect = options["fnk"]
    building_outlines = options["buildings"]
    min_veg_size = options["min_veg_size"]
    min_veg_proportion = int(options["min_veg_proportion"])
    output_buildings = options["output_buildings"]
    output_vegetation = options["output_vegetation"]
    segment_flag = flags["s"]
    nprocs = int(options["nprocs"])
    tile_size = options["tile_size"]
    verbose = False  # flags["v"]

    nprocs = set_nprocs(nprocs)
    options["memory"] = test_memory(options["memory"])
    memory_per_parallel_proc = int(int(options["memory"]) / nprocs)
    start_cur_mapset = grass.gisenv()["MAPSET"]

    if nprocs > 1:
        check_addon("r.mapcalc.tiled")
        check_addon("r.extract.greenroofs.worker", url="...")
        mapcalc_tiled_kwargs = {
            "nprocs": nprocs,
            "patch_backend": "r.patch",
        }
        r_mapcalc_cmd = "r.mapcalc.tiled"
    else:
        r_mapcalc_cmd = "r.mapcalc"

    if grass.find_file(name="MASK", element="cell")["file"]:
        tmp_mask_old = f"tmp_mask_old_{os.getpid()}"
        grass.run_command("g.rename", raster=f"MASK,{tmp_mask_old}", quiet=True)

    # calculate auxiliary datasets
    (
        green_blue_ratio,
        red_green_ratio,
        brightness,
    ) = calculate_auxiliary_datasets_and_brightness(red, green, blue)

    # define GB-ratio threshold (threshold or percentile)
    if options["used_thresh"] == "gb_perc":
        if not options["fnk_column"] or not options["fnk"]:
            grass.fatal(
                _("If <gb_perc> is used <fnk> and <fnk_column> have to be set.")
            )
        gb_perc = options["gb_perc"]
        gb_thresh = calculate_gb_threshold(green_blue_ratio, fnk_vect, gb_perc)
    elif options["used_thresh"] == "gb_thresh":
        gb_thresh = float(options["gb_thresh"])
    else:
        grass.fatal(
            _("The parameter <used_thresh> has to be <gb_thresh> or <gb_perc>!")
        )

    # Creating tiles
    grid = f"grid_{os.getpid()}"
    rm_vectors.append(grid)
    tiles_list, number_tiles = create_grid(tile_size, grid, building_outlines)
    rm_vectors.extend(tiles_list)

    # cut study area to buildings
    grass.message(_("Preparing input data..."))
    building_rast = create_building_mask(building_outlines, trees)
    rm_rasters.append(building_rast)

    # Segmentation
    #  region growing segmentation to create distinct polygons
    if segment_flag:
        # cut and transform nDSM
        grass.message(_("nDSM transformation..."))
        ndsm_cut = f"ndsm_cut_{os.getpid()}"
        rm_rasters.append(ndsm_cut)
        # cut dtm extensively to also emphasize low buildings
        percentiles = [5, 50, 95]
        perc_values = get_percentile(ndsm, percentiles)
        print(f"perc values are {perc_values}")
        med = perc_values[1]
        p_low = perc_values[0]
        p_high = perc_values[2]

    # parallel processing
    grass.message(_("Extracting greenroofs parallel ..."))
    # test nprocs setting
    if number_tiles < nprocs:
        nprocs = number_tiles
    queue = ParallelModuleQueue(nprocs=nprocs)
    try:
        for tile_area in tiles_list:
            tile = tile_area.rsplit("_", 1)[1]
            new_mapset = f"tmp_r_extract_greenroofs{tile}"
            rm_mapsets.append(new_mapset)
            out_veg = f"out_veg_{tile}"
            param = {
                "new_mapset": new_mapset,
                "area": tile_area,
                "building_outlines": building_outlines,
                "buildings": building_rast,
                "memory": memory_per_parallel_proc,
                "ndsm": ndsm,
                "gb_ratio": green_blue_ratio,
                "rg_ratio": red_green_ratio,
                "brightness": brightness,
                "ndvi": ndvi,
                "gb_thresh": gb_thresh,
                "min_veg_size": min_veg_size,
                "flags": "",
                "output_vegetation": out_veg,
                "min_veg_proportion": min_veg_proportion,
            }
            if segment_flag:
                param["flags"] += "s"
                param["ndsm_med"] = float(med)
                param["ndsm_p_low"] = float(p_low)
                param["ndsm_p_high"] = float(p_high)
            if trees:
                param["flags"] += "t"

            # r.extract.greenroofs.worker
            r_extract_greenroofs_worker = Module(
                # grass.run_command(
                "r.extract.greenroofs.worker",
                **param,
                run_=False,
            )
            # catch all GRASS outputs to stdout and stderr
            r_extract_greenroofs_worker.stdout_ = grass.PIPE
            r_extract_greenroofs_worker.stderr_ = grass.PIPE
            queue.put(r_extract_greenroofs_worker)
        queue.wait()
    except Exception:
        for proc_num in range(queue.get_num_run_procs()):
            proc = queue.get(proc_num)
            if proc.returncode != 0:
                # save all stderr to a variable and pass it to a GRASS
                # exception
                errmsg = proc.outputs["stderr"].value.strip()
                grass.fatal(
                    _(f"\nERROR by processing <{proc.get_bash()}>: {errmsg}")
                )
    # print all logs of successfully run modules ordered by module as GRASS
    # message
    res_list = []
    out_veg_vectors = []
    for proc in queue.get_finished_modules():
        # create mapset dict based on Log, so that only those with output are listed
        msg = proc.outputs["stderr"].value.strip()
        if verbose:
            grass.message(_(f"\nLog of {proc.get_bash()}:"))
            for msg_part in msg.split("\n"):
                grass.message(_(msg_part))
        stdout_msg = proc.outputs["stdout"].value.strip()
        if "r.extract.greenroofs.worker skipped" not in stdout_msg:
            out_veg = re.search(
                r"Output vector created <(.*?)>.", stdout_msg
            ).groups()[0]
            out_veg_vectors.append(out_veg)
            out_regex = (
                r"r.extract.greenroofs.worker output is:\n(.*?)\nEnd of "
                r"r.extract.greenroofs.worker output."
            )
            output = re.search(out_regex, stdout_msg).groups()[0]
            for item in json.loads(output):
                res_list.append(item)

    # verify that switching back to original mapset worked
    verify_mapsets(start_cur_mapset)

    # save vegetation areas without attributes
    if len(out_veg_vectors) > 0:
        grass.run_command(
            "v.patch",
            input=out_veg_vectors,
            output=output_vegetation,
            quiet=True,
        )
        grass.message(_(f"Created result map <{output_vegetation}>."))
    else:
        grass.message(_("No vegetation areas on buildings found."))

    # extract buildings with vegetation on roof and attach vegetation proportion
    building_cats = [item["building_cat"] for item in res_list]
    if len(building_cats) > 0:
        grass.run_command(
            "v.extract",
            input=building_outlines,
            output=output_buildings,
            cats=building_cats,
            quiet=True,
        )

        # it is faster to create a table, fill it, and join tables than using
        # v.db.update for each building cat
        veg_proportion_col = "veg_prop"
        temp_table = f"buildings_table_{os.getpid()}"
        rm_tables.append(temp_table)
        create_table_str = (
            f"CREATE TABLE {temp_table} (cat integer,"
            f" {veg_proportion_col} double precision)"
        )
        grass.run_command("db.execute", sql=create_table_str)
        fill_table_str = (
            f"INSERT INTO {temp_table} "
            f"( cat, {veg_proportion_col} ) VALUES "
        )
        for dic in res_list:
            fill_table_str += (
                f"( {dic['building_cat']}, " f"{round(dic['proportion'],2)} ), "
            )
        # remove final comma
        fill_table_str = fill_table_str[:-2]
        grass.run_command("db.execute", sql=fill_table_str)
        grass.run_command(
            "v.db.join",
            map=output_buildings,
            column="cat",
            other_table=temp_table,
            other_column="cat",
            quiet=True,
        )
        grass.message(_(f"Created result map <{output_buildings}>."))
    else:
        grass.message(_("No buildings with vegetation found."))


if __name__ == "__main__":
    options, flags = grass.parser()
    atexit.register(cleanup)
    main()
