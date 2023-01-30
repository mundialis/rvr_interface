#!/usr/bin/env python3

############################################################################
#
# MODULE:       r.extract.greenroofs.worker
#
# AUTHOR(S):    Julia Haas <haas at mundialis.de>
#               Guido Riembauer <riembauer at mundialis.de>
#               Anika Weinmann <weinmann at mundialis.de>
#
# PURPOSE:      Worker GRASS GIS addon to TODO
#
# COPYRIGHT:	(C) 2023 by mundialis and the GRASS Development Team
#
# 		This program is free software under the GNU General Public
# 		License (>=v2). Read the file COPYING that comes with GRASS
# 		for details.
#
#############################################################################

# %Module
# % description: Worker GRASS GIS addon to TODO.
# % keyword: raster
# % keyword: statistics
# % keyword: change detection
# % keyword: classification
# %end

# %option
# % key: new_mapset
# % type: string
# % required: yes
# % multiple: no
# % label: Name of new mapset where to compute the building MASK
# %end

# %option G_OPT_V_INPUT
# % key: building_outlines
# % type: string
# % required: yes
# % multiple: no
# % label: Vector map containing outlines of buildings
# %end

# %option G_OPT_R_INPUT
# % key: buildings
# % type: string
# % required: yes
# % multiple: no
# % label: Raster map containing buildings
# %end

# %option
# % key: cat
# % type: integer
# % required: yes
# % multiple: no
# % label: Building category value to compute the MASK for
# %end

# %option G_OPT_MEMORYMB
# %end

# %option G_OPT_R_INPUT
# % key: ndsm
# % type: string
# % required: yes
# % multiple: no
# % label: Name of the nDSM raster
# %end

# %option G_OPT_R_INPUT
# % key: gb_ratio
# % type: string
# % required: yes
# % multiple: no
# % label: Name of the GB-ratio raster
# %end

# %option G_OPT_R_INPUT
# % key: rg_ratio
# % type: string
# % required: yes
# % multiple: no
# % label: Name of the RG-ratio raster
# %end

# %option G_OPT_R_INPUT
# % key: brightness
# % type: string
# % required: yes
# % multiple: no
# % label: Name of the brighness raster
# %end

# %option G_OPT_R_INPUT
# % key: ndvi
# % type: string
# % required: yes
# % multiple: no
# % label: Name of the NDVI raster
# %end

# %option
# % key: gb_thresh
# % type: integer
# % required: yes
# % multiple: no
# % label: define fix Green_blue_ratio threshold (on a scale from 0-255)
# %end

# %option
# % key: ndsm_med
# % type: integer
# % required: no
# % multiple: no
# % label: define fix nDSM median
# %end

# %option
# % key: ndsm_p_low
# % type: integer
# % required: no
# % multiple: no
# % label: define fix nDSM low percentile
# %end

# %option
# % key: ndsm_p_high
# % type: integer
# % required: no
# % multiple: no
# % label: define fix nDSM high percentile
# %end

# %option
# % key: min_veg_size
# % type: integer
# % required: yes
# % multiple: no
# % label: Minimum size of roof vegetation in sqm
# % answer: 5
# %end

# %flag
# % key: s
# % description: segment image based on nDSM, NDVI and blue/green ratio before green roof extraction
# %end

# %flag
# % key: t
# % description: trees are used for the selection
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


def cleanup():
    nuldev = open(os.devnull, "w")
    kwargs = {"flags": "f", "quiet": True, "stderr": nuldev}
    for rmrast in rm_rasters:
        if grass.find_file(name=rmrast, element="raster")["file"]:
            grass.run_command("g.remove", type="raster", name=rmrast, **kwargs)
    for rmv in rm_vectors:
        if grass.find_file(name=rmv, element="vector")["file"]:
            grass.run_command("g.remove", type="vector", name=rmv, **kwargs)


def set_region_to_one_building(b_cat, building_rast):
    """Function to set region to only one building
    Args:
        b_cat (int): Cat integer value of building
        building_rast (str): Name of building raster map
    """
    rule = f"{b_cat} = 1\n* = NULL"
    building_reclassed = grass.tempname(12)
    rm_rasters.append(building_reclassed)
    reclass_proc = grass.start_command(
        "r.reclass",
        input=building_rast,
        output=building_reclassed,
        rules="-",
        stdin=grass.PIPE,
        stdout=grass.PIPE,
    )
    reclass_proc.stdin.write(str.encode(rule))
    reclass_proc.stdin.close()
    reclass_proc.wait()
    grass.run_command(
        "g.region",
        raster=building_reclassed,
        zoom=building_reclassed,
        flags="p",
    )
    grass.run_command("g.region", grow=1, flags="p")
    return building_reclassed


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

    building_outlines = f"{options['building_outlines']}@{old_mapset}"
    buildings = f"{options['buildings']}@{old_mapset}"
    ndsm = f"{options['ndsm']}@{old_mapset}"
    ndvi = f"{options['ndvi']}@{old_mapset}"
    green_blue_ratio = f"{options['gb_ratio']}@{old_mapset}"
    red_green_ratio = f"{options['rg_ratio']}@{old_mapset}"
    brightness = f"{options['brightness']}@{old_mapset}"
    min_veg_size = float(options["min_veg_size"])

    # region to one building with buffer
    b_cat = options["cat"]
    building_reclassed = set_region_to_one_building(b_cat, buildings)
    selected_building = f"building_{b_cat}"
    rm_vectors.append(selected_building)
    grass.run_command(
        "v.extract",
        input=building_outlines,
        cat=b_cat,
        output=selected_building,
        quiet=True,
    )
    building_outlines = selected_building

    grass.run_command("r.mask", raster=buildings, maskcats=b_cat)

    # segmentation
    segment_flag = flags["s"]
    if segment_flag:
        # nDsM transformation
        med = options["ndsm_med"]
        p_low = options["ndsm_p_low"]
        p_high = options["ndsm_p_high"]
        ndsm_cut = f"ndsm_cut_{b_cat}"
        rm_rasters.append(ndsm_cut)
        trans_expression = (
            f"{ndsm_cut} = float(if({ndsm} >= {med},"
            f"sqrt(({ndsm} - {med}) / ({p_high} - {med})),"
            f"-1.0 * sqrt(({med} - {ndsm}) / ({med} - {p_low}))))"
        )
        grass.run_command("r.mapcalc", expression=trans_expression, quiet=True)

        grass.message(_("Image segmentation..."))
        seg_group = f"seg_group_{b_cat}"
        rm_groups.append(seg_group)
        group_inp = []
        for rast in [ndsm_cut, green_blue_ratio, ndvi]:
            rast_stats = grass.parse_command("r.univar", map=rast, flags="g")
            if (
                rast_stats["min"] != rast_stats["max"] and
                rast_stats["min"] != 'nan' and rast_stats["max"] != 'nan'
            ):
                group_inp.append(rast)
        if len(group_inp) > 0:
            grass.run_command(
                "i.group",
                group=seg_group,
                input=group_inp,
                quiet=True,
            )
            segmented = f"segmented_{b_cat}"
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
            segmented = building_reclassed
        # calculate raster stats on raster segments
        # calculate ndvi, ndsm, gb_ratio and brightness average to select
        # potential segments
        ndvi_average_seg = f"ndvi_average_seg_rast_{b_cat}"
        ndsm_average_seg = f"ndsm_average_seg_rast_{b_cat}"
        gbr_average_seg = f"gbr_average_seg_rast_{b_cat}"
        rgr_average_seg = f"rgr_average_seg_rast_{b_cat}"
        brightness_average_seg = f"brightness_average_seg_rast_{b_cat}"
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
    pot_veg_rast = f"pot_veg_rast_{b_cat}"
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

    pot_veg_rast_range = grass.parse_command("r.info", map=pot_veg_rast, flags="r")
    if (pot_veg_rast_range["min"] == pot_veg_rast_range["max"] == "NULL"):
        print(
            f"r.extract.greenroofs.worker skipped for building {b_cat}:"
            " No potential vegetation areas found."
        )
        return

    # vectorize segments
    segments_vect = f"segments_vect_{b_cat}"
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
    # bu_with_veg_intersect = f"bu_with_veg_intersect_{b_cat}"
    pot_veg_areas = f"pot_veg_areas_{b_cat}"
    rm_vectors.append(pot_veg_areas)
    grass.run_command(
        "v.overlay",
        ainput=building_outlines,
        binput=segments_vect,
        operator="and",
        output=pot_veg_areas,
        quiet=True,
    )

    # remove small remaining elements
    seg_size_col = "seg_size"
    seg_size = float(
        [*grass.parse_command(
                "v.to.db",
                map=pot_veg_areas,
                option="area",
                columns=seg_size_col,
                units="meters",
                flags="pc",
                quiet=True,
            ).keys()
        ][-1].split("|")[1]
    )
    if seg_size <= min_veg_size:
        print(
            f"r.extract.greenroofs.worker skipped for building {b_cat}:"
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
    bu_with_veg = building_outlines

    # vegetation from rest of buildings and dissolve per building
    # to get ndsm statistics of remaining roof
    bu_with_veg_rest = f"bu_with_veg_rest_{b_cat}"
    rm_vectors.append(bu_with_veg_rest)
    grass.run_command(
        "v.overlay",
        ainput=bu_with_veg,
        binput=pot_veg_areas,
        operator="not",
        output=bu_with_veg_rest,
        quiet=True,
    )
    bu_with_veg_rest_diss = f"bu_with_veg_rest_diss_{b_cat}"
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
    bu_rest_size = float(
        [*grass.parse_command(
                "v.to.db",
                map=bu_with_veg_rest_diss,
                option="area",
                columns=bu_rest_size_col,
                units="meters",
                flags="pc",
                quiet=True,
            ).keys()
        ][-1].split("|")[1]
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

    veg_attributes = [entry for entry in grass.parse_command(
        "v.db.select",
        map=pot_veg_areas,
        columns=f"cat,veg_ndsm_{method}_{percentile}",
        flags="c",
    )]
    import pdb; pdb.set_trace()
    bu_ndsm_stat = float(list(grass.parse_command(
        "v.db.select",
        map=bu_with_veg_rest_diss,
        columns=f"bu_ndsm_{method}_{percentile}",
        flags="c",
    ).keys())[0])

    drop_rows = []
    trees = flags["t"]
    prop_thresh = 0.75
    diff_thresh = 1.5
    building_dicts = list()
    for veg_attr in veg_attributes:
        cat, veg_ndsm_stat = veg_attr.split("|")
        veg_ndsm_stat = float(veg_ndsm_stat)
        building_dict = {
            "building_cat": b_cat,
            "seg_cat": cat,
            "seg_size": seg_size,
            "bu_rest_size": bu_rest_size,
        }
        if trees:
            building_dicts.append(building_dict)
        else:
            if seg_size / (seg_size + bu_rest_size) >= prop_thresh:
                building_dicts.append(building_dict)
            elif veg_ndsm_stat - bu_ndsm_stat <= diff_thresh:
                building_dicts.append(building_dict)
            else:
                drop_rows.append(f"cat='{cat}'")
    if len(building_dicts) >= 1:
        print("r.extract.greenroofs.worker output is:")
        print(json.dumps(building_dicts))
        print("End of r.extract.greenroofs.worker output.")
    else:
        print(
            f"r.extract.greenroofs.worker skipped for building {b_cat}:"
            " All potential vegetation areas removed."
        )

    resulting_pot_veg_areas = f"resulting_pot_veg_areas_{b_cat}"
    if len(drop_rows) > 0:
        grass.run_command(
            "v.db.droprow",
            input=pot_veg_areas,
            where=" or ".join(drop_rows),
            output=resulting_pot_veg_areas,
            quiet=True,
        )
    else:
        grass.run_command(
            "g.rename", vector=f"{pot_veg_areas},{resulting_pot_veg_areas}"
        )

    # set GISRC to original gisrc and delete newgisrc
    os.environ["GISRC"] = gisrc
    grass.utils.try_remove(newgisrc)

    grass.message(_(
        f"Output vector created <{resulting_pot_veg_areas}@{new_mapset}>."
    ))
    return 0


if __name__ == "__main__":
    options, flags = grass.parser()
    atexit.register(cleanup)
    main()
