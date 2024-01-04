#!/usr/bin/env python3

############################################################################
#
# MODULE:       r.extract.greenroofs.worker
#
# AUTHOR(S):    Julia Haas, Guido Riembauer and Anika Weinmann
#
# PURPOSE:      Worker GRASS GIS addon to extract greenroofs
#
# COPYRIGHT:	(C) 2023 - 2024 by mundialis and the GRASS Development Team
#
# 		This program is free software under the GNU General Public
# 		License (>=v2). Read the file COPYING that comes with GRASS
# 		for details.
#
#############################################################################

# %Module
# % description: Worker GRASS GIS addon to extract greenroofs.
# % keyword: raster
# % keyword: classification
# % keyword: statistics
# % keyword: worker
# %end

# %option
# % key: new_mapset
# % type: string
# % required: yes
# % multiple: no
# % label: Name of new mapset where to compute the building MASK
# %end

# %option G_OPT_V_INPUT
# % key: area
# % type: string
# % required: yes
# % label: Vector map containing area
# %end

# %option G_OPT_V_INPUT
# % key: building_outlines
# % type: string
# % required: yes
# % label: Vector map containing outlines of buildings
# %end

# %option G_OPT_R_INPUT
# % key: buildings
# % type: string
# % required: yes
# % label: Raster map containing buildings
# %end

# %option G_OPT_R_INPUT
# % key: ndsm
# % type: string
# % required: yes
# % label: Name of the nDSM raster
# %end

# %option G_OPT_R_INPUT
# % key: gb_ratio
# % type: string
# % required: yes
# % label: Name of the GB-ratio raster
# %end

# %option G_OPT_R_INPUT
# % key: rg_ratio
# % type: string
# % required: yes
# % label: Name of the RG-ratio raster
# %end

# %option G_OPT_R_INPUT
# % key: brightness
# % type: string
# % required: yes
# % label: Name of the brightness raster
# %end

# %option G_OPT_R_INPUT
# % key: ndvi
# % type: string
# % required: yes
# % label: Name of the NDVI raster
# %end

# %option
# % key: gb_thresh
# % type: integer
# % required: yes
# % multiple: no
# % label: Define fix Green_blue_ratio threshold (on a scale from 0-255)
# %end

# %option
# % key: ndsm_med
# % type: integer
# % required: no
# % multiple: no
# % label: Define fix nDSM median
# %end

# %option
# % key: ndsm_p_low
# % type: integer
# % required: no
# % multiple: no
# % label: Define fix nDSM low percentile
# %end

# %option
# % key: ndsm_p_high
# % type: integer
# % required: no
# % multiple: no
# % label: Define fix nDSM high percentile
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

# %option G_OPT_V_OUTPUT
# % key: output_vegetation
# % required: yes
# % label: Name of output roof vegetation vector map
# %end

# %option G_OPT_MEMORYMB
# %end

# %flag
# % key: s
# % label: Segment image based on nDSM, NDVI and blue/green ratio before green roof extraction
# %end

# %flag
# % key: t
# % label: Use trees for the selection
# %end

# %rules
# % requires_all: -s,ndsm_med,ndsm_p_low,ndsm_p_high
# %end


import atexit
import json
import os
import sys

import grass.script as grass
from grass.pygrass.utils import get_lib_path

# initialize global vars
rm_rasters = []
rm_vectors = []
rm_groups = []

# thresholds for roof vegetation extraction
ndvi_thresh = 100
rg_thresh = 145
bn_thresh = 80
ndsm_thresh = 2


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
    try_remove_mask()


def prepare_buildings_of_area(area, building_rast, building_vect):
    """Function to set the region and prepare the buildings for this region"""
    b_vect = f"building_vect_{area.split('@')[0]}"
    rm_vectors.append(b_vect)
    grass.run_command(
        "v.select",
        ainput=building_vect,
        binput=area,
        operator="overlap",
        output=b_vect,
        quiet=True,
    )
    grass.run_command("g.region", vector=b_vect, align=building_rast)
    grass.run_command("r.mask", raster=building_rast)


def main():
    global rm_rasters, rm_vectors, rm_groups

    path = get_lib_path(
        modname="m.analyse.buildings",
        libname="analyse_buildings_lib",
    )
    if path is None:
        grass.fatal("Unable to find the analyse buildings library directory")
    sys.path.append(path)
    try:
        from analyse_buildings_lib import switch_to_new_mapset
    except Exception:
        grass.fatal("m.analyse.buildings library is not installed")

    # switch to another mapset for parallel processing
    new_mapset = options["new_mapset"]
    gisrc, newgisrc, old_mapset = switch_to_new_mapset(new_mapset)

    area = (
        f"{options['area']}@{old_mapset}"
        if "@" not in options["area"]
        else options["area"]
    )
    num = options["area"].rsplit("_", 1)[1]
    building_outlines = (
        f"{options['building_outlines']}@{old_mapset}"
        if "@" not in options["building_outlines"]
        else options["building_outlines"]
    )
    buildings = f"{options['buildings']}@{old_mapset}"
    ndsm = (
        f"{options['ndsm']}@{old_mapset}"
        if "@" not in options["ndsm"]
        else options["ndsm"]
    )
    ndvi = (
        f"{options['ndvi']}@{old_mapset}"
        if "@" not in options["ndvi"]
        else options["ndvi"]
    )
    green_blue_ratio = (
        f"{options['gb_ratio']}@{old_mapset}"
        if "@" not in options["gb_ratio"]
        else options["gb_ratio"]
    )
    red_green_ratio = (
        f"{options['rg_ratio']}@{old_mapset}"
        if "@" not in options["rg_ratio"]
        else options["rg_ratio"]
    )
    brightness = (
        f"{options['brightness']}@{old_mapset}"
        if "@" not in options["brightness"]
        else options["brightness"]
    )
    min_veg_size = float(options["min_veg_size"])
    min_veg_proportion = int(options["min_veg_proportion"])
    output_vegetation = options["output_vegetation"]

    # set region, mask and prepare buildings
    prepare_buildings_of_area(area, buildings, building_outlines)

    # segmentation
    segment_flag = flags["s"]
    if segment_flag:
        # nDSM transformation
        med = options["ndsm_med"]
        p_low = options["ndsm_p_low"]
        p_high = options["ndsm_p_high"]
        ndsm_cut = f"ndsm_cut_{num}"
        rm_rasters.append(ndsm_cut)
        trans_expression = (
            f"{ndsm_cut} = float(if({ndsm} >= {med},"
            f"sqrt(({ndsm} - {med}) / ({p_high} - {med})),"
            f"-1.0 * sqrt(({med} - {ndsm}) / ({med} - {p_low}))))"
        )
        grass.run_command("r.mapcalc", expression=trans_expression, quiet=True)

        grass.message(_("Image segmentation..."))
        seg_group = f"seg_group_{num}"
        rm_groups.append(seg_group)
        group_inp = []
        for rast in [ndsm_cut, green_blue_ratio, ndvi]:
            rast_stats = grass.parse_command("r.univar", map=rast, flags="g")
            if (
                rast_stats["min"] != rast_stats["max"]
                and rast_stats["min"] != "nan"
                and rast_stats["max"] != "nan"
            ):
                group_inp.append(rast)
        if len(group_inp) > 0:
            grass.run_command(
                "i.group",
                group=seg_group,
                input=group_inp,
                quiet=True,
            )
            segmented = f"segmented_{num}"
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
        else:
            segmented = buildings
        # calculate raster stats on raster segments
        # calculate ndvi, ndsm, gb_ratio and brightness average to select
        # potential segments
        ndvi_average_seg = f"ndvi_average_seg_rast_{num}"
        ndsm_average_seg = f"ndsm_average_seg_rast_{num}"
        gbr_average_seg = f"gbr_average_seg_rast_{num}"
        rgr_average_seg = f"rgr_average_seg_rast_{num}"
        brightness_average_seg = f"brightness_average_seg_rast_{num}"
        stat_rasts = {
            ndvi: ndvi_average_seg,
            ndsm: ndsm_average_seg,
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
    # red green ratio to eliminate very red roofs
    pot_veg_rast = f"pot_veg_rast_{num}"
    rm_rasters.append(pot_veg_rast)
    gb_thresh = options["gb_thresh"]
    if segment_flag:
        extract_exp = (
            f"{pot_veg_rast} = if("
            f"{stat_rasts[ndsm]}>={ndsm_thresh} && "
            f"{stat_rasts[green_blue_ratio]}>={gb_thresh} && "
            f"{stat_rasts[red_green_ratio]}<={rg_thresh} && "
            f"{stat_rasts[ndvi]}>={ndvi_thresh} && "
            f"{stat_rasts[brightness]}>={bn_thresh}, 1, null())"
        )
    else:
        extract_exp = (
            f"{pot_veg_rast} = if("
            f"{ndsm}>={ndsm_thresh} && "
            f"{green_blue_ratio}>={gb_thresh} && "
            f"{red_green_ratio}<={rg_thresh} && "
            f"{ndvi}>={ndvi_thresh} && "
            f"{brightness}>={bn_thresh}, 1, null())"
        )
    grass.run_command("r.mapcalc", expression=extract_exp, quiet=True)

    pot_veg_rast_range = grass.parse_command(
        "r.info", map=pot_veg_rast, flags="r"
    )
    if pot_veg_rast_range["min"] == pot_veg_rast_range["max"] == "NULL":
        print(
            f"r.extract.greenroofs.worker skipped for buildings in tile {num}:"
            " No potential vegetation areas found."
        )
        return

    # vectorize segments
    segments_vect = f"segments_vect_{num}"
    rm_vectors.append(segments_vect)
    grass.run_command(
        "r.to.vect",
        input=pot_veg_rast,
        output=segments_vect,
        type="area",
        quiet=True,
    )
    grass.run_command("r.mask", flags="r", quiet=True)

    # remove small features
    bu_with_veg_intersect = f"bu_with_veg_intersect_{num}"
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
    seg_size_col = "seg_size"
    grass.run_command(
        "v.to.db",
        map=bu_with_veg_intersect,
        option="area",
        columns=seg_size_col,
        units="meters",
        quiet=True,
    )
    pot_veg_areas = f"pot_veg_areas_{num}"
    rm_vectors.append(pot_veg_areas)
    grass.run_command(
        "v.db.droprow",
        input=bu_with_veg_intersect,
        where=f"{seg_size_col} <= {min_veg_size}",
        output=pot_veg_areas,
        quiet=True,
    )
    num_veg_areas = int(
        grass.parse_command(
            "v.info",
            flags="t",
            map=pot_veg_areas,
        )["centroids"]
    )
    if int(num_veg_areas) == 0:
        print(
            f"r.extract.greenroofs.worker skipped for buildings in tile {num}:"
            " No large enough potential vegetation areas found."
        )
        return

    # calculate ndsm average for the final potential vegetation objects
    method = "percentile"
    percentile = 50
    grass.run_command(
        "v.rast.stats",
        map=pot_veg_areas,
        raster=ndsm,
        method=f"{method},stddev",
        percentile=percentile,
        column_prefix="veg_ndsm",
        quiet=True,
    )

    grass.message("Select buildings with vegetation ...")
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

    # vegetation from rest of buildings and dissolve per building
    # to get ndsm statistics of remaining roof
    bu_with_veg_rest = f"bu_with_veg_rest_{num}"
    rm_vectors.append(bu_with_veg_rest)
    grass.run_command(
        "v.overlay",
        ainput=bu_with_veg,
        binput=pot_veg_areas,
        operator="not",
        output=bu_with_veg_rest,
        quiet=True,
    )
    bu_with_veg_rest_diss = f"bu_with_veg_rest_diss_{num}"
    rm_vectors.append(bu_with_veg_rest_diss)
    grass.run_command(
        "v.dissolve",
        input=bu_with_veg_rest,
        output=bu_with_veg_rest_diss,
        column="a_cat",
        quiet=True,
    )

    # get size of roof part that is not covered by vegetation
    grass.run_command("v.db.addtable", map=bu_with_veg_rest_diss, quiet=True)

    bu_rest_size_col = "bu_rest_size"
    grass.run_command(
        "v.to.db",
        map=bu_with_veg_rest_diss,
        option="area",
        columns=bu_rest_size_col,
        quiet=True,
    )

    # get ndsm average of roof part that is not covered by vegetation
    grass.run_command(
        "v.rast.stats",
        map=bu_with_veg_rest_diss,
        raster=ndsm,
        method=method,
        percentile=percentile,
        column_prefix="bu_ndsm",
        quiet=True,
    )

    # Only if no tree layer is given:
    # compare statistics of potential areas with surrounding areas
    # (e.g. to remove overlapping trees by height difference)
    # add bu_ndsm_stat as column to vegetation layer
    # remove potential vegetation polygons where difference between building
    # height average and vegetation height average is too high
    grass.run_command(
        "v.db.join",
        map=pot_veg_areas,
        column="a_cat",
        other_table=bu_with_veg_rest_diss,
        other_column="cat",
        subset_columns=f"bu_ndsm_{method}_{percentile},{bu_rest_size_col}",
        quiet=True,
    )
    col_str = (
        f"cat,a_cat,{seg_size_col},{bu_rest_size_col},"
        f"veg_ndsm_{method}_{percentile},bu_ndsm_{method}_{percentile}"
    )
    table = list(
        grass.parse_command(
            "v.db.select", map=pot_veg_areas, columns=col_str, flags="c"
        ).keys()
    )

    trees = flags["t"]
    prop_thresh = 0.75
    diff_thresh = 1.5

    building_dicts = []
    for item in table:
        # skip rows with empty entries
        if not any([True for t in item.split("|") if len(t) == 0]):
            cat = item.split("|")[0]
            building_cat = item.split("|")[1]
            seg_size = float(item.split("|")[2])
            bu_rest_size = float(item.split("|")[3])
            veg_ndsm_stat = float(item.split("|")[4])
            bu_ndsm_stat = float(item.split("|")[5])
            # assumption: potential vegetation areas that cover large proportion
            # of underlying building are not trees
            # therefore proportion is checked before ndsm difference check
            # ndsm difference check only for small proportions (likely trees)
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
                    if veg_ndsm_stat - bu_ndsm_stat <= diff_thresh:
                        building_dicts.append(building_dict)

    # check proportion of total vegetation area per building (not individual
    # vegetation elements)
    res_list = []
    veg_list = []
    unique_bu_cats = list(
        set([item["building_cat"] for item in building_dicts])
    )
    for building_cat in unique_bu_cats:
        unique_segs = [
            item
            for item in building_dicts
            if item["building_cat"] == building_cat
        ]
        bu_rest_size = unique_segs[0]["bu_rest_size"]
        total_veg_size = sum([item["seg_size"] for item in unique_segs])
        seg_cats = [item["seg_cat"] for item in unique_segs]
        proportion = total_veg_size / (bu_rest_size + total_veg_size) * 100
        if proportion >= min_veg_proportion:
            res_list.append(
                {"building_cat": building_cat, "proportion": proportion}
            )
            veg_list.extend(seg_cats)

    if len(veg_list) > 0:
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
    else:
        print(
            f"r.extract.greenroofs.worker skipped for buildings of tile {num}:"
            " All potential vegetation areas removed."
        )

    if len(res_list) > 0:
        print("r.extract.greenroofs.worker output is:")
        print(json.dumps(res_list))
        print("End of r.extract.greenroofs.worker output.")
    else:
        print(
            f"r.extract.greenroofs.worker skipped for buildings of tile {num}:"
            " All potential vegetation areas removed."
        )

    # set GISRC to original gisrc and delete newgisrc
    os.environ["GISRC"] = gisrc
    grass.utils.try_remove(newgisrc)

    print(f"Output vector created <{output_vegetation}@{new_mapset}>.")
    return 0


if __name__ == "__main__":
    options, flags = grass.parser()
    atexit.register(cleanup)
    main()
