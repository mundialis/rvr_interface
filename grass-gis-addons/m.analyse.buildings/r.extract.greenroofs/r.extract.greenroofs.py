#!/usr/bin/env python3

############################################################################
#
# MODULE:       r.extract.greenroofs
#
# AUTHOR(S):    Julia Haas <haas at mundialis.de>
#               Guido Riembauer <riembauer at mundialis.de>
#               Anika Weinmann <weinmann at mundialis.de>
#
# PURPOSE:      Extracts green roofs on buildings from nDOM, NDVI, GB-Ratio,
#               FNK and building outlines
#
# COPYRIGHT:	(C) 2022-2023 by mundialis and the GRASS Development Team
#
# 		This program is free software under the GNU General Public
# 		License (>=v2). Read the file COPYING that comes with GRASS
# 		for details.
#
#############################################################################

# %Module
# % description: Extracts green roofs from nDOM, NDVI, GB-Ratio, FNK and building outlines
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
# % key: ndvi
# % type: string
# % required: yes
# % multiple: no
# % label: Name of the NDVI raster
# %end

# %option G_OPT_R_INPUT
# % key: red
# % type: string
# % required: yes
# % multiple: no
# % label: Name of the red DOP raster
# %end

# %option G_OPT_R_INPUT
# % key: green
# % type: string
# % required: yes
# % multiple: no
# % label: Name of the green DOP raster
# %end

# %option G_OPT_R_INPUT
# % key: blue
# % type: string
# % required: yes
# % multiple: no
# % label: Name of the blue DOP raster
# %end

# %option G_OPT_V_INPUT
# % key: fnk
# % type: string
# % required: no
# % multiple: no
# % label: Vector map containing Flaechennutzungskatalog
# %end

# %option
# % key: fnk_column
# % type: string
# % required: no
# % multiple: no
# % label: Integer column containing FNK-code
# %end

# %option G_OPT_V_INPUT
# % key: buildings
# % type: string
# % required: yes
# % multiple: no
# % label: Vector map containing outlines of buildings
# %end

# %option G_OPT_V_INPUT
# % key: trees
# % type: string
# % required: no
# % multiple: no
# % label: Vector map containing tree polygons
# %end

# %option
# % key: gb_thresh
# % type: integer
# % required: no
# % multiple: no
# % label: define fix Green_blue_ratio threshold (on a scale from 0-255)
# %end

# %option
# % key: gb_perc
# % type: integer
# % required: no
# % multiple: no
# % label: Define Green_blue_ratio threshold as this percentile of green areas
# %end

# %option
# % key: min_veg_size
# % type: integer
# % required: yes
# % multiple: no
# % label: Minimum size of roof vegetation in sqm
# % answer: 5
# %end

# %option
# % key: min_veg_proportion
# % type: integer
# % required: yes
# % multiple: no
# % label: Minimum percentage of vegetation cover on roof
# % answer: 10
# %end

# %option G_OPT_MEMORYMB
# %end

# %option G_OPT_M_NPROCS
# % answer: -2
# %end

# %option G_OPT_V_OUTPUT
# % key: output_buildings
# % required: yes
# % multiple: no
# % label: Name of output building vector map
# %end

# %option G_OPT_V_OUTPUT
# % key: output_vegetation
# % required: yes
# % multiple: no
# % label: Name of output roof vegetation vector map
# %end

# %flag
# % key: s
# % description: segment image based on nDOM, NDVI and blue/green ratio before green roof extraction
# %end

# %rules
# % exclusive: gb_perc, gb_thresh
# % required: gb_perc, gb_thresh
# % requires_all: gb_perc, fnk_column, fnk
# %end

import atexit
import os
import sys

import grass.script as grass
from grass.pygrass.modules import Module, ParallelModuleQueue
from grass.pygrass.utils import get_lib_path

# initialize global vars
rm_rasters = []
rm_vectors = []
rm_groups = []
rm_tables = []
tmp_mask_old = None
mapcalc_tiled_kwargs = {}
r_mapcalc_cmd = "r.mapcalc"


def cleanup():
    nuldev = open(os.devnull, "w")
    kwargs = {"flags": "f", "quiet": True, "stderr": nuldev}
    for rmrast in rm_rasters:
        if grass.find_file(name=rmrast, element="raster")["file"]:
            grass.run_command("g.remove", type="raster", name=rmrast, **kwargs)
    for rmv in rm_vectors:
        if grass.find_file(name=rmv, element="vector")["file"]:
            grass.run_command("g.remove", type="vector", name=rmv, **kwargs)
    for rmgroup in rm_groups:
        if grass.find_file(name=rmgroup, element="group")["file"]:
            grass.run_command("g.remove", type="group", name=rmgroup, **kwargs)
    for rmtable in rm_tables:
        grass.run_command("db.droptable", table=rmtable, flags="f", quiet=True)
    if grass.find_file(name="MASK", element="raster")["file"]:
        try:
            grass.run_command("r.mask", flags="r", quiet=True)
        except:
            pass
    # reactivate potential old mask
    if tmp_mask_old:
        grass.run_command("r.mask", raster=tmp_mask_old, quiet=True)


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
    grass.run_command(
        "g.rename", raster=f"{fnk_rast},MASK", quiet=True
    )
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
    global mapcalc_tiled_kwargs, r_mapcalc_cmd

    path = get_lib_path(
        modname="m.analyse.buildings",
        libname="analyse_buildings_lib",
    )
    if path is None:
        grass.fatal("Unable to find the analyse buildings library directory")
    sys.path.append(path)
    try:
        from analyse_buildings_lib import (
            build_raster_vrt,
            check_addon,
            get_percentile,
            set_nprocs,
            test_memory,
            verify_mapsets,
        )
    except Exception:
        grass.fatal("m.analyse.buildings library is not installed")

    ndom = options["ndom"]
    ndvi = options["ndvi"]
    red = options["red"]
    green = options["green"]
    blue = options["blue"]
    trees = options["trees"]
    fnk_vect = options["fnk"]
    building_outlines = options["buildings"]
    gb_perc = options["gb_perc"]
    min_veg_size = options["min_veg_size"]
    min_veg_proportion = int(options["min_veg_proportion"])
    output_buildings = options["output_buildings"]
    output_vegetation = options["output_vegetation"]
    segment_flag = flags["s"]
    nprocs = int(options["nprocs"])

    nprocs = set_nprocs(nprocs)
    options["memory"] = test_memory(options["memory"])
    memory_per_parallel_proc = int(int(options["memory"]) / nprocs)
    start_cur_mapset = grass.gisenv()["MAPSET"]

    if nprocs > 1:
        check_addon("r.mapcalc.tiled")
        check_addon("r.extract.greenroofs.worker1", url="...")
        mapcalc_tiled_kwargs = {
            "nprocs": nprocs,
            "patch_backend": "r.patch",
        }
        r_mapcalc_cmd = "r.mapcalc.tiled"
    else:
        r_mapcalc_cmd = "r.mapcalc"

    if grass.find_file(name="MASK", element="raster")["file"]:
        tmp_mask_old = f"tmp_mask_old_{os.getpid()}"
        grass.run_command(
            "g.rename", raster=f'MASK,{tmp_mask_old}', quiet=True
        )

    # calculate auxiliary datasets
    green_blue_ratio, red_green_ratio, brightness = \
        calculate_auxiliary_datasets_and_brightness(red, green, blue)

    # define GB-ratio threshold (threshold or percentile)
    if gb_perc:
        gb_thresh = calculate_gb_threshold(green_blue_ratio, fnk_vect, gb_perc)
    elif options["gb_thresh"]:
        gb_thresh = options["gb_thresh"]

    # cut study area to buildings
    grass.message(_("Preparing input data..."))
    building_rast = create_building_mask(building_outlines, trees)
    buildings_cats = [x for x in grass.parse_command(
        "r.category", map=building_rast
    )]

    # Segmentation
    #  region growing segmentation to create distinct polygons
    if segment_flag:
        # cut and transform nDOM
        grass.message(_("nDOM transformation..."))
        ndom_cut = f"ndom_cut_{os.getpid()}"
        rm_rasters.append(ndom_cut)
        # cut dem extensively to also emphasize low buildings
        percentiles = [5, 50, 95]
        perc_values = get_percentile(ndom, percentiles)
        med = perc_values[1]
        p_low = perc_values[0]
        p_high = perc_values[2]


    import pdb; pdb.set_trace()
    # TODO parallel in own mapset
    builing_out = list()
    veg_out = list()
    del buildings_cats[3:]
    queue = ParallelModuleQueue(nprocs=nprocs)
    try:
        for b_cat in buildings_cats:
            new_mapset = f"tmp_r_extract_greenroofs{b_cat}"
            param = {
                "new_mapset": new_mapset,
                "building_outlines": building_outlines,
                "buildings": building_rast,
                "cat": b_cat,
                "memory": memory_per_parallel_proc,
                "ndom": ndom,
                "gb_ratio": green_blue_ratio,
                "rg_ratio": red_green_ratio,
                "brightness": brightness,
                "ndvi": ndvi,
                "gb_thresh": gb_thresh,
            }
            if segment_flag:
                param["flags"] = "s"
                param["ndom_med"] = med
                param["ndom_p_low"] = p_low
                param["ndom_p_high"] = p_high

            # r.extract.greenroofs.worker
            # r_extract_greenroofs_worker = Module(
            grass.run_command(
                "r.extract.greenroofs.worker",
                **param,
                # run_=False,
            )
            # catch all GRASS outputs to stdout and stderr
            # r_extract_greenroofs_worker.stdout_ = grass.PIPE
            # r_extract_greenroofs_worker.stderr_ = grass.PIPE
        #     queue.put(r_extract_greenroofs_worker)
        # queue.wait()
    except Exception:
        for proc_num in range(queue1.get_num_run_procs()):
            proc = queue1.get(proc_num)
            if proc.returncode != 0:
                # save all stderr to a variable and pass it to a GRASS
                # exception
                errmsg = proc.outputs["stderr"].value.strip()
                grass.fatal(_(f"\nERROR by processing <{proc.get_bash()}>: {errmsg}"))
    # print all logs of successfully run modules ordered by module as GRASS
    # message
    for proc in queue1.get_finished_modules():
        msg = proc.outputs["stderr"].value.strip()
        grass.message(_(f"\nLog of {proc.get_bash()}:"))
        for msg_part in msg.split("\n"):
            grass.message(_(msg_part))

    # verify that switching back to original mapset worked
    verify_mapsets(start_cur_mapset)
    # build_raster_vrt(building_mask, "MASK_tmp")



    import pdb; pdb.set_trace()


    #     # remove small features
    #     bu_with_veg_intersect = f"bu_with_veg_intersect_{os.getpid()}"
    #     rm_vectors.append(bu_with_veg_intersect)
    #     grass.run_command(
    #         "v.overlay",
    #         ainput=building_outlines,
    #         binput=segments_vect,
    #         operator="and",
    #         output=bu_with_veg_intersect,
    #         quiet=True,
    #     )
    #
    #     # remove small remaining elements
    #     seg_size = "seg_size"
    #     grass.run_command(
    #         "v.to.db",
    #         map=bu_with_veg_intersect,
    #         option="area",
    #         columns=seg_size,
    #         quiet=True,
    #     )
    #
    #     pot_veg_areas = f"pot_veg_areas_{os.getpid()}"
    #     rm_vectors.append(pot_veg_areas)
    #     grass.run_command(
    #         "v.db.droprow",
    #         input=bu_with_veg_intersect,
    #         where=f"{seg_size} <= {min_veg_size}",
    #         output=pot_veg_areas,
    #         quiet=True,
    #     )
    #
    #     # calculate ndom average for the final potential vegetation objects
    #     method = "percentile"
    #     percentile = 50
    #     grass.run_command(
    #         "v.rast.stats",
    #         map=pot_veg_areas,
    #         raster=ndom,
    #         method=f"{method},stddev",
    #         percentile=percentile,
    #         column_prefix="veg_ndom",
    #         quiet=True,
    #     )
    #
    #     # select buildings with vegetation cover (note: there may be too many
    #     # objects in the result vector, but the column in pot_veg_areas contains
    #     # the correct building ID)
    #     bu_with_veg = f"bu_with_veg_{os.getpid()}"
    #     rm_vectors.append(bu_with_veg)
    #     grass.run_command(
    #         "v.select",
    #         ainput=building_outlines,
    #         binput=pot_veg_areas,
    #         operator="overlap",
    #         output=bu_with_veg,
    #         quiet=True,
    #     )
    #
    #     # erase vegetation from rest of buildings and dissolve per building
    #     # to get ndom statistics of remaining roof
    #     bu_with_veg_rest = f"bu_with_veg_rest_{os.getpid()}"
    #     rm_vectors.append(bu_with_veg_rest)
    #     grass.run_command(
    #         "v.overlay",
    #         ainput=bu_with_veg,
    #         binput=pot_veg_areas,
    #         operator="not",
    #         output=bu_with_veg_rest,
    #         quiet=True,
    #     )
    #
    #     bu_with_veg_rest_diss = f"bu_with_veg_rest_diss_{os.getpid()}"
    #     rm_vectors.append(bu_with_veg_rest_diss)
    #     grass.run_command(
    #         "v.dissolve",
    #         input=bu_with_veg_rest,
    #         output=bu_with_veg_rest_diss,
    #         column="a_cat",
    #         quiet=True,
    #     )
    #
    #     grass.run_command("v.db.addtable", map=bu_with_veg_rest_diss, quiet=True)
    #
    #     # get size of roof part that is not covered by vegetation
    #     bu_rest_size = "bu_rest_size"
    #     grass.run_command(
    #         "v.to.db",
    #         map=bu_with_veg_rest_diss,
    #         option="area",
    #         columns=bu_rest_size,
    #         quiet=True,
    #     )
    #
    #     # get ndom average of roof part that is not covered by vegetation
    #     grass.run_command(
    #         "v.rast.stats",
    #         map=bu_with_veg_rest_diss,
    #         raster=ndom,
    #         method=method,
    #         percentile=percentile,
    #         column_prefix="bu_ndom",
    #         quiet=True,
    #     )
    #
    #     # Only if no tree layer is given:
    #     # compare statistics of potential areas with surrounding areas
    #     # (e.g. to remove overlapping trees by height difference)
    #     # add bu_ndom_stat as column to vegetation layer
    #     # remove potential vegetation polygons where difference between building
    #     # height average and vegetation height average is too high
    #     grass.run_command(
    #         "v.db.join",
    #         map=pot_veg_areas,
    #         column="a_cat",
    #         other_table=bu_with_veg_rest_diss,
    #         other_column="cat",
    #         subset_columns=f"bu_ndom_{method}_{percentile},bu_rest_size",
    #         quiet=True,
    #     )
    #
    # # TODO for all v.patch -e
    # # grass.run_command("v.patch", )
    # col_str = (
    #     f"cat,a_cat,{seg_size},{bu_rest_size},"
    #     f"veg_ndom_{method}_{percentile},bu_ndom_{method}_{percentile}"
    # )
    # table = list(
    #     grass.parse_command(
    #         "v.db.select", map=pot_veg_areas, columns=col_str, flags="c"
    #     ).keys()
    # )
    # res_list = []
    # veg_list = []
    #
    # building_dicts = []
    #
    # prop_thresh = 0.75
    # diff_thresh = 1.5
    #
    # for item in table:
    #     # skip rows with empty entries
    #     if not any([True for t in item.split("|") if len(t) == 0]):
    #         cat = item.split("|")[0]
    #         building_cat = item.split("|")[1]
    #         seg_size = float(item.split("|")[2])
    #         bu_rest_size = float(item.split("|")[3])
    #         veg_ndom_stat = float(item.split("|")[4])
    #         bu_ndom_stat = float(item.split("|")[5])
    #         # assumption: potential vegetation areas that cover large proportion
    #         # of underlying building are not trees
    #         # therefore proportion is checked before ndom difference check
    #         # ndom difference check only for small proportions (likely trees)
    #         # NOTE: This is only applied if no external tree layer is given
    #         building_dict = {
    #             "building_cat": building_cat,
    #             "seg_cat": cat,
    #             "seg_size": seg_size,
    #             "bu_rest_size": bu_rest_size,
    #         }
    #         if trees:
    #             building_dicts.append(building_dict)
    #         else:
    #             if seg_size / (seg_size + bu_rest_size) >= prop_thresh:
    #                 building_dicts.append(building_dict)
    #             else:
    #                 if veg_ndom_stat - bu_ndom_stat <= diff_thresh:
    #                     building_dicts.append(building_dict)
    #
    # # check proportion of total vegetation area per building (not individual
    # # vegetation elements)
    # res_list = []
    # veg_list = []
    # unique_bu_cats = list(set([item["building_cat"] for item in building_dicts]))
    # for building_cat in unique_bu_cats:
    #     unique_segs = [
    #         item for item in building_dicts if item["building_cat"] == building_cat
    #     ]
    #     bu_rest_size = unique_segs[0]["bu_rest_size"]
    #     total_veg_size = sum([item["seg_size"] for item in unique_segs])
    #     seg_cats = [item["seg_cat"] for item in unique_segs]
    #     proportion = total_veg_size / (bu_rest_size + total_veg_size) * 100
    #     if proportion >= min_veg_proportion:
    #         res_list.append({"building_cat": building_cat, "proportion": proportion})
    #         veg_list.extend(seg_cats)
    #
    # # TODO alles
    #
    # # save vegetation areas without attributes
    # # TODO v.patch stattdessen?
    # grass.run_command(
    #     "v.extract",
    #     input=pot_veg_areas,
    #     output=output_vegetation,
    #     cats=veg_list,
    #     flags="t",
    #     quiet=True,
    # )
    # grass.run_command("v.db.addtable", map=output_vegetation, quiet=True)
    # building_cats = [item["building_cat"] for item in res_list]
    #
    # # extract buildings with vegetation on roof and attach vegetation proportion
    # # TODO v.patch stattdessen?
    # grass.run_command(
    #     "v.extract",
    #     input=building_outlines,
    #     output=output_buildings,
    #     cats=building_cats,
    #     quiet=True,
    # )
    #
    # # it is faster to create a table, fill it, and join tables than using
    # # v.db.update for each building cat
    # veg_proportion_col = "vegetation_proportion"
    # temp_table = f"buildings_table_{os.getpid()}"
    # rm_tables.append(temp_table)
    # create_table_str = (
    #     f"CREATE TABLE {temp_table} (cat integer,"
    #     f" {veg_proportion_col} double precision)"
    # )
    # grass.run_command("db.execute", sql=create_table_str)
    # fill_table_str = (
    #     f"INSERT INTO {temp_table} " f"( cat, {veg_proportion_col} ) VALUES "
    # )
    # for dic in res_list:
    #     fill_table_str += (
    #         f"( {dic['building_cat']}, " f"{round(dic['proportion'],2)} ), "
    #     )
    # # remove final comma
    # fill_table_str = fill_table_str[:-2]
    # grass.run_command("db.execute", sql=fill_table_str)
    # grass.run_command(
    #     "v.db.join",
    #     map=output_buildings,
    #     column="cat",
    #     other_table=temp_table,
    #     other_column="cat",
    #     quiet=True,
    # )
    #
    # grass.message(_(f"Created result maps '{output_buildings}' and '{output_vegetation}'."))


if __name__ == "__main__":
    options, flags = grass.parser()
    atexit.register(cleanup)
    main()
