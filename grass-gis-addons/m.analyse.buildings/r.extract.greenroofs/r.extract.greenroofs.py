#!/usr/bin/env python3

############################################################################
#
# MODULE:       r.extract.greenroofs
#
# AUTHOR(S):    Julia Haas <haas at mundialis.de>
#               Guido Riembauer <riembauer@mundialis.de>
#
# PURPOSE:      Extracts green roofs on buildings from nDOM, NDVI, GB-Ratio,
#               FNK and building outlines
#
# COPYRIGHT:	(C) 2022 by mundialis and the GRASS Development Team
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

import grass.script as grass
import psutil

# initialize global vars
rm_rasters = []
rm_vectors = []
rm_groups = []
rm_tables = []
tmp_mask_old = None


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


def get_percentile(raster, percentile):
    return float(
        list(
            (
                grass.parse_command(
                    "r.quantile", input=raster, percentiles=percentile, quiet=True
                )
            ).keys()
        )[0].split(":")[2]
    )


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
    memory_GB = (mem_available + swap_free) / 1024.0 ** 3
    memory_MB = (mem_available + swap_free) / 1024.0 ** 2

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
    memory = int(options["memory"])
    free_ram = freeRAM("MB", 100)
    if free_ram < memory:
        grass.warning("Using %d MB but only %d MB RAM available." % (memory, free_ram))
        options["memory"] = free_ram
        grass.warning("Set used memory to %d MB." % (options["memory"]))


def main():

    global rm_rasters, tmp_mask_old, rm_vectors, rm_groups, rm_tables

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

    # calculate auxiliary datasets
    grass.message(_("Calculating auxiliary datasets..."))

    green_blue_ratio = f"green_blue_ratio_{os.getpid()}"
    rm_rasters.append(green_blue_ratio)
    gb_expression = (
        f"{green_blue_ratio} = round(255*(1.0+"
        f"(float({green}-{blue})/({green}+{blue})))/2)"
    )
    grass.run_command("r.mapcalc", expression=gb_expression, quiet=True)

    red_green_ratio = f"red_green_ratio_{os.getpid()}"
    rm_rasters.append(red_green_ratio)
    rg_expression = (
        f"{red_green_ratio} = round(255*(1.0+"
        f"(float({red}-{green})/({red}+{green})))/2)"
    )
    grass.run_command("r.mapcalc", expression=rg_expression, quiet=True)

    # brightness
    brightness = f"brightness_{os.getpid()}"
    rm_rasters.append(brightness)
    bn_expression = f"{brightness} = ({red}+{green})/2"
    grass.run_command("r.mapcalc", expression=bn_expression, quiet=True)

    # define NDVI threshold (threshold or percentile)
    if gb_perc:
        grass.message(_("Calculating GB threshold..."))
        # rasterizing fnk vect
        fnk_rast = f"fnk_rast_{os.getpid()}"
        rm_rasters.append(fnk_rast)
        grass.run_command(
            "v.to.rast",
            input=fnk_vect,
            use="attr",
            attribute_column=options["fnk_column"],
            output=fnk_rast,
            quiet=True,
        )

        # fnk-codes with green areas (gardens, parks, meadows)
        fnk_codes_green = ["271", "272", "273", "361"]
        fnk_codes_mask = " ".join(fnk_codes_green)
        grass.run_command(
            "r.mask", raster=fnk_rast, maskcats=fnk_codes_mask, quiet=True
        )
        # get GB statistics
        gb_percentile = float(gb_perc)
        gb_thresh = get_percentile(green_blue_ratio, gb_percentile)
        grass.message(_(f"GB threshold is at {gb_thresh}"))
        grass.run_command("r.mask", flags="r", quiet=True)
    elif options["gb_thresh"]:
        gb_thresh = options["gb_thresh"]

    # cut study area to buildings
    # remove old mask
    grass.message(_("Preparing input data..."))

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
    else:
        mask_vector = building_outlines

    if grass.find_file(name="MASK", element="raster")["file"]:
        tmp_mask_old = f"tmp_mask_old_{os.getpid()}"
        grass.run_command("g.rename", raster=f'"MASK",{tmp_mask_old}', quiet=True)
    # set new mask
    grass.run_command("r.mask", vector=mask_vector, quiet=True)

    test_memory()

    #  region growing segmentation to create distinct polygons
    if segment_flag:
        # cut and transform nDOM
        grass.message(_("nDOM transformation..."))
        ndom_cut = f"ndom_cut_{os.getpid()}"
        rm_rasters.append(ndom_cut)
        # cut dem extensively to also emphasize low buildings
        percentiles = "5,50,95"
        perc_values_list = list(
            grass.parse_command(
                "r.quantile", input=ndom, percentile=percentiles, quiet=True
            ).keys()
        )
        perc_values = [item.split(":")[2] for item in perc_values_list]
        print(f"perc values are {perc_values}")
        med = perc_values[1]
        p_low = perc_values[0]
        p_high = perc_values[2]
        trans_expression = (
            f"{ndom_cut} = float(if({ndom} >= {med},"
            f"sqrt(({ndom} - {med}) / ({p_high} - {med})),"
            f"-1.0 * sqrt(({med} - {ndom}) / ({med} - {p_low}))))"
        )

        grass.run_command("r.mapcalc", expression=trans_expression, quiet=True)

        # segmentation
        grass.message(_("Image segmentation..."))
        seg_group = f"seg_group_{os.getpid()}"
        rm_groups.append(seg_group)
        grass.run_command(
            "i.group",
            group=seg_group,
            input=f"{ndom_cut},{green_blue_ratio},{ndvi}",
            quiet=True,
        )
        segmented = f"segmented_{os.getpid()}"
        rm_rasters.append(segmented)
        grass.run_command(
            "i.segment",
            group=seg_group,
            output=segmented,
            threshold=0.075,
            minsize=10,
            memory=options["memory"],
            quiet=True,
        )

        # calculate raster stats on raster segments
        # calculate ndvi, ndom, gb_ratio and brightness average to select
        # potential segments
        ndvi_average_seg = f"ndvi_average_seg_rast_{os.getpid()}"
        ndom_average_seg = f"ndom_average_seg_rast_{os.getpid()}"
        gbr_average_seg = f"gbr_average_seg_rast_{os.getpid()}"
        rgr_average_seg = f"rgr_average_seg_rast_{os.getpid()}"
        brightness_average_seg = f"brightness_average_seg_rast_{os.getpid()}"
        stat_rasts = {
            ndvi: ndvi_average_seg,
            ndom: ndom_average_seg,
            green_blue_ratio: gbr_average_seg,
            red_green_ratio: rgr_average_seg,
            brightness: brightness_average_seg,
        }
        for cover, output_rast in stat_rasts.items():
            rm_rasters.append(output_rast)
            grass.run_command(
                "r.stats.zonal",
                base=segmented,
                cover=cover,
                method="average",
                output=output_rast,
                quiet=True,
            )

    grass.message(_("Roof vegetation extraction..."))
    # apply thresholds
    ndvi_thresh = 100
    # red green ratio to eliminate very red roofs
    rg_thresh = 145
    bn_thresh = 80
    ndom_thresh = 2
    pot_veg_rast = f"pot_veg_rast_{os.getpid()}"
    rm_rasters.append(pot_veg_rast)

    if segment_flag:
        extract_exp = (
            f"{pot_veg_rast} = if("
            f"{stat_rasts[ndom]}>={ndom_thresh} && "
            f"{stat_rasts[green_blue_ratio]}>={gb_thresh} && "
            f"{stat_rasts[red_green_ratio]}<={rg_thresh} && "
            f"{stat_rasts[ndvi]}>={ndvi_thresh} && "
            f"{stat_rasts[brightness]}>={bn_thresh}, 1, null())"
        )
    else:
        extract_exp = (
            f"{pot_veg_rast} = if("
            f"{ndom}>={ndom_thresh} && "
            f"{green_blue_ratio}>={gb_thresh} && "
            f"{red_green_ratio}<={rg_thresh} && "
            f"{ndvi}>={ndvi_thresh} && "
            f"{brightness}>={bn_thresh}, 1, null())"
        )

    grass.run_command("r.mapcalc", expression=extract_exp, quiet=True)

    # vectorize segments
    segments_vect = f"segments_vect_{os.getpid()}"
    rm_vectors.append(segments_vect)
    grass.run_command(
        "r.to.vect", input=pot_veg_rast, output=segments_vect, type="area", quiet=True
    )

    grass.run_command("r.mask", flags="r", quiet=True)

    # remove small features
    bu_with_veg_intersect = f"bu_with_veg_intersect_{os.getpid()}"
    rm_vectors.append(bu_with_veg_intersect)
    grass.run_command(
        "v.overlay",
        ainput=building_outlines,
        binput=segments_vect,
        operator="and",
        output=bu_with_veg_intersect,
        quiet=True,
    )

    # remove small remaining elements
    seg_size = "seg_size"
    grass.run_command(
        "v.to.db",
        map=bu_with_veg_intersect,
        option="area",
        columns=seg_size,
        quiet=True,
    )

    pot_veg_areas = f"pot_veg_areas_{os.getpid()}"
    rm_vectors.append(pot_veg_areas)
    grass.run_command(
        "v.db.droprow",
        input=bu_with_veg_intersect,
        where=f"{seg_size} <= {min_veg_size}",
        output=pot_veg_areas,
        quiet=True,
    )

    # calculate ndom average for the final potential vegetation objects
    method = "percentile"
    percentile = 50
    grass.run_command(
        "v.rast.stats",
        map=pot_veg_areas,
        raster=ndom,
        method=f"{method},stddev",
        percentile=percentile,
        column_prefix="veg_ndom",
        quiet=True,
    )

    # select buildings with vegetation cover (note: there may be too many
    # objects in the result vector, but the column in pot_veg_areas contains
    # the correct building ID)
    bu_with_veg = f"bu_with_veg_{os.getpid()}"
    rm_vectors.append(bu_with_veg)
    grass.run_command(
        "v.select",
        ainput=building_outlines,
        binput=pot_veg_areas,
        operator="overlap",
        output=bu_with_veg,
        quiet=True,
    )

    # erase vegetation from rest of buildings and dissolve per building
    # to get ndom statistics of remaining roof
    bu_with_veg_rest = f"bu_with_veg_rest_{os.getpid()}"
    rm_vectors.append(bu_with_veg_rest)
    grass.run_command(
        "v.overlay",
        ainput=bu_with_veg,
        binput=pot_veg_areas,
        operator="not",
        output=bu_with_veg_rest,
        quiet=True,
    )

    bu_with_veg_rest_diss = f"bu_with_veg_rest_diss_{os.getpid()}"
    rm_vectors.append(bu_with_veg_rest_diss)
    grass.run_command(
        "v.dissolve",
        input=bu_with_veg_rest,
        output=bu_with_veg_rest_diss,
        column="a_cat",
        quiet=True,
    )

    grass.run_command("v.db.addtable", map=bu_with_veg_rest_diss, quiet=True)

    # get size of roof part that is not covered by vegetation
    bu_rest_size = "bu_rest_size"
    grass.run_command(
        "v.to.db",
        map=bu_with_veg_rest_diss,
        option="area",
        columns=bu_rest_size,
        quiet=True,
    )

    # get ndom average of roof part that is not covered by vegetation
    grass.run_command(
        "v.rast.stats",
        map=bu_with_veg_rest_diss,
        raster=ndom,
        method=method,
        percentile=percentile,
        column_prefix="bu_ndom",
        quiet=True,
    )

    # Only if no tree layer is given:
    # compare statistics of potential areas with surrounding areas
    # (e.g. to remove overlapping trees by height difference)
    # add bu_ndom_stat as column to vegetation layer
    # remove potential vegetation polygons where difference between building
    # height average and vegetation height average is too high
    grass.run_command(
        "v.db.join",
        map=pot_veg_areas,
        column="a_cat",
        other_table=bu_with_veg_rest_diss,
        other_column="cat",
        subset_columns=f"bu_ndom_{method}_{percentile},bu_rest_size",
        quiet=True,
    )
    col_str = (
        f"cat,a_cat,{seg_size},{bu_rest_size},"
        f"veg_ndom_{method}_{percentile},bu_ndom_{method}_{percentile}"
    )
    table = list(
        grass.parse_command(
            "v.db.select", map=pot_veg_areas, columns=col_str, flags="c"
        ).keys()
    )
    res_list = []
    veg_list = []

    building_dicts = []

    prop_thresh = 0.75
    diff_thresh = 1.5

    for item in table:
        # skip rows with empty entries
        if not any([True for t in item.split("|") if len(t) == 0]):
            cat = item.split("|")[0]
            building_cat = item.split("|")[1]
            seg_size = float(item.split("|")[2])
            bu_rest_size = float(item.split("|")[3])
            veg_ndom_stat = float(item.split("|")[4])
            bu_ndom_stat = float(item.split("|")[5])
            # assumption: potential vegetation areas that cover large proportion
            # of underlying building are not trees
            # therefore proportion is checked before ndom difference check
            # ndom difference check only for small proportions (likely trees)
            # NOTE: This is only applied if no external tree layer is given
            building_dict = {
                "building_cat": building_cat,
                "seg_cat": cat,
                "seg_size": seg_size,
                "bu_rest_size": bu_rest_size,
            }
            if trees:
                building_dicts.append(building_dict)
            else:
                if seg_size / (seg_size + bu_rest_size) >= prop_thresh:
                    building_dicts.append(building_dict)
                else:
                    if veg_ndom_stat - bu_ndom_stat <= diff_thresh:
                        building_dicts.append(building_dict)

    # check proportion of total vegetation area per building (not individual
    # vegetation elements)
    res_list = []
    veg_list = []
    unique_bu_cats = list(set([item["building_cat"] for item in building_dicts]))
    for building_cat in unique_bu_cats:
        unique_segs = [
            item for item in building_dicts if item["building_cat"] == building_cat
        ]
        bu_rest_size = unique_segs[0]["bu_rest_size"]
        total_veg_size = sum([item["seg_size"] for item in unique_segs])
        seg_cats = [item["seg_cat"] for item in unique_segs]
        proportion = total_veg_size / (bu_rest_size + total_veg_size) * 100
        if proportion >= min_veg_proportion:
            res_list.append({"building_cat": building_cat, "proportion": proportion})
            veg_list.extend(seg_cats)

    # save vegetation areas without attributes
    grass.run_command(
        "v.extract",
        input=pot_veg_areas,
        output=output_vegetation,
        cats=veg_list,
        flags="t",
        quiet=True,
    )
    grass.run_command("v.db.addtable", map=output_vegetation, quiet=True)
    building_cats = [item["building_cat"] for item in res_list]

    # extract buildings with vegetation on roof and attach vegetation proportion
    grass.run_command(
        "v.extract",
        input=building_outlines,
        output=output_buildings,
        cats=building_cats,
        quiet=True,
    )

    # it is faster to create a table, fill it, and join tables than using
    # v.db.update for each building cat
    veg_proportion_col = "vegetation_proportion"
    temp_table = f"buildings_table_{os.getpid()}"
    rm_tables.append(temp_table)
    create_table_str = (
        f"CREATE TABLE {temp_table} (cat integer,"
        f" {veg_proportion_col} double precision)"
    )
    grass.run_command("db.execute", sql=create_table_str)
    fill_table_str = (
        f"INSERT INTO {temp_table} " f"( cat, {veg_proportion_col} ) VALUES "
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

    grass.message(_(f"Created result maps '{output_buildings}' and '{output_vegetation}'."))


if __name__ == "__main__":
    options, flags = grass.parser()
    atexit.register(cleanup)
    main()
