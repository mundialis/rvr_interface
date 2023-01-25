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
# % key: ndom
# % type: string
# % required: yes
# % multiple: no
# % label: Name of the nDOM raster
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
# % key: brighness
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
# % key: ndom_med
# % type: integer
# % required: no
# % multiple: no
# % label: define fix nDOM median
# %end

# %option
# % key: ndom_p_low
# % type: integer
# % required: no
# % multiple: no
# % label: define fix nDOM low percentile
# %end

# %option
# % key: ndom_p_high
# % type: integer
# % required: no
# % multiple: no
# % label: define fix nDOM high percentile
# %end

# %flag
# % key: s
# % description: segment image based on nDOM, NDVI and blue/green ratio before green roof extraction
# %end

# %rules
# % requires_all: -s,ndom_med,ndom_p_low,ndom_p_high
# %end



import atexit
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
ndom_thresh = 2


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
    ndom = f"{options['ndom']}@{old_mapset}"
    ndvi = f"{options['ndvi']}@{old_mapset}"
    green_blue_ratio = f"{options['gb_ratio']}@{old_mapset}"
    red_green_ratio = f"{options['rg_ratio']}@{old_mapset}"
    brightness = f"{options['brightness']}@{old_mapset}"

    # region to one building with buffer
    b_cat = options["cat"]
    set_region_to_one_building(b_cat, buildings)
    grass.run_command("r.mask", raster=buildings)

    # segmentation
    segment_flag = flags["s"]
    if segment_flag:
        # nDOM transformation
        med = options["ndom_med"]
        p_low = options["ndom_p_low"]
        p_high = options["ndom_p_high"]
        ndom_cut = f"ndom_cut_{b_cat}"
        rm_rasters.append(ndom_cut)
        trans_expression = (
            f"{ndom_cut} = float(if({ndom} >= {med},"
            f"sqrt(({ndom} - {med}) / ({p_high} - {med})),"
            f"-1.0 * sqrt(({med} - {ndom}) / ({med} - {p_low}))))"
        )
        grass.run_command("r.mapcalc", expression=trans_expression, quiet=True)

        grass.message(_("Image segmentation..."))
        seg_group = f"seg_group_{b_cat}"
        rm_groups.append(seg_group)
        grass.run_command(
            "i.group",
            group=seg_group,
            input=f"{ndom_cut},{green_blue_ratio},{ndvi}",
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
        # calculate raster stats on raster segments
        # calculate ndvi, ndom, gb_ratio and brightness average to select
        # potential segments
        ndvi_average_seg = f"ndvi_average_seg_rast_{b_cat}"
        ndom_average_seg = f"ndom_average_seg_rast_{b_cat}"
        gbr_average_seg = f"gbr_average_seg_rast_{b_cat}"
        rgr_average_seg = f"rgr_average_seg_rast_{b_cat}"
        brightness_average_seg = f"brightness_average_seg_rast_{b_cat}"
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
    # red green ratio to eliminate very red roofs
    pot_veg_rast = f"pot_veg_rast_{b_cat}"
    rm_rasters.append(pot_veg_rast)
    gb_thresh = options["gb_thresh"]
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

    import pdb; pdb.set_trace()
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

    import pdb; pdb.set_trace()
    # remove small features
    bu_with_veg_intersect = f"bu_with_veg_intersect_{b_cat}"
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

    import pdb; pdb.set_trace()
    # if seg_size <= min_veg_size:

    # mask_vector = f"{options['buildings']}@{old_mapset}"
    # # building_outlines = f"{options['building_outlines']}@{old_mapset}"
    # b_cat = int(options["cat"])
    # cat_col = options["cat_col"]
    #
    # grass.message(_(f"Computing building MASK for {b_cat} ..."))
    #
    # # create MASK fpr buildings or buildings without trees
    # # if trees:
    # #     # TODO check if this is only done for the region
    # #     # alle drinnen
    # #     # buildings_clipped = f"buildings_clipped_{b_cat}"
    # #     # rm_vectors.append(buildings_clipped)
    # #     # grass.run_command(
    # #     #     "v.overlay",
    # #     #     ainput=building_outlines,
    # #     #     binput=trees,
    # #     #     operator="not",
    # #     #     output=buildings_clipped,
    # #     #     quiet=True,
    # #     # )
    # #     mask_vector = buildings_clipped
    # #     mask_param = {"where": f"a_cat = '{b_cat}'"}
    # # else:
    # #     mask_vector = building_outlines
    # #     mask_param = {"cat": b_cat}
    # # set new mask
    # grass.run_command(
    #     "r.mask",
    #     vector=mask_vector,
    #     where=f"{cat_col} = '{b_cat}'",
    #     quiet=True,
    # )

    # set GISRC to original gisrc and delete newgisrc
    os.environ["GISRC"] = gisrc
    grass.utils.try_remove(newgisrc)

    grass.message(_(
        f"r.extract.greenroofs.worker1 created <MASK@{new_mapset}>."
    ))
    return 0


if __name__ == "__main__":
    options, flags = grass.parser()
    atexit.register(cleanup)
    main()
