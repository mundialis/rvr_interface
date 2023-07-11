#!/usr/bin/env python3

############################################################################
#
# MODULE:       r.extract.buildings.worker
#
# AUTHOR(S):    Julia Haas and Guido Riembauer
#
# PURPOSE:      Extracts buildings from nDSM, NDVI and FNK
#
# COPYRIGHT:	(C) 2023 by mundialis and the GRASS Development Team
#
# 		This program is free software under the GNU General Public
# 		License (>=v2). Read the file COPYING that comes with GRASS
# 		for details.
#
#############################################################################

# %Module
# % description: Extracts buildings from nDSM, NDVI and FNK.
# % keyword: raster
# % keyword: statistics
# % keyword: change detection
# % keyword: classification
# %end

# %option G_OPT_R_INPUT
# % key: ndsm
# % type: string
# % required: yes
# % multiple: no
# % label: Name of the nDSM
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
# % required: no
# % multiple: no
# % label: Vector map containing Flaechennutzungskatalog
# %end

# %option G_OPT_R_INPUTS
# % key: fnk_raster
# % type: string
# % required: no
# % multiple: no
# % label: Raster map containing Flaechennutzungskatalog
# %end

# %option G_OPT_R_INPUTS
# % key: fnk_column
# % type: string
# % required: no
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
# % key: ndvi_thresh
# % type: integer
# % required: yes
# % multiple: no
# % label: NDVI threshold (user-defined or estimated from FNK, scale 0-255)
# %end

# %option G_OPT_MEMORYMB
# %end

# %option G_OPT_R_OUTPUT
# % key: output
# % type: string
# % required: yes
# % multiple: no
# % label: Name for output vector map
# % guisection: Output
# %end

# %option
# % key: new_mapset
# % type: string
# % required: yes
# % multiple: no
# % key_desc: name
# % description: Name for new mapset
# %end

# %option G_OPT_V_INPUT
# % key: area
# % multiple: no
# % description: Input natural tiles as vector map
# %end

# %flag
# % key: s
# % description: Segment image based on nDSM and NDVI before building extraction
# %end

# %rules
# % exclusive: fnk_vector, fnk_raster
# % required: fnk_vector, fnk_raster
# % requires_all: fnk_vector, fnk_column
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
tmp_mask_old = None


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
    if grass.find_file(name="MASK", element="cell")["file"]:
        try:
            grass.run_command("r.mask", flags="r", quiet=True)
        except Exception:
            pass
    # reactivate potential old mask
    if tmp_mask_old:
        grass.run_command("r.mask", raster=tmp_mask_old, quiet=True)


def extract_buildings(**kwargs):
    from analyse_buildings_lib import get_bins
    from analyse_buildings_lib import test_memory

    grass.message(_("Preparing input data..."))
    if grass.find_file(name="MASK", element="cell")["file"]:
        tmp_mask_old = f"tmp_mask_old_{os.getgid()}"
        grass.run_command(
            "g.rename", raster=f'{"MASK"},{tmp_mask_old}', quiet=True
        )

    ndsm = kwargs["ndsm"]
    ndvi = kwargs["ndvi_raster"]
    ndvi_thresh = kwargs["ndvi_thresh"]
    memory = kwargs["memory"]
    output = kwargs["output"]
    user_min_size = kwargs["min_size"]

    # rasterizing fnk vect
    if "fnk_vector" in kwargs:
        fnk_vect = kwargs["fnk_vector"]
        fnk_column = kwargs["fnk_column"]

        fnk_rast = f"fnk_rast_{os.getgid()}"
        rm_rasters.append(fnk_rast)
        grass.run_command(
            "v.to.rast",
            input=fnk_vect,
            use="attr",
            attribute_column=fnk_column,
            output=fnk_rast,
            quiet=True,
        )
    elif "fnk_raster" in kwargs:
        fnk_rast = kwargs["fnk_raster"]

    # fnk-codes with potential tree growth (400+ = Vegetation)
    fnk_codes_trees = ["400", "410", "420", "431", "432", "441", "472"]

    # create binary vegetation raster
    veg_raster = f"vegetation_raster_{os.getpid()}"
    rm_rasters.append(veg_raster)
    veg_expression = f"{veg_raster} = if({ndvi}>{ndvi_thresh},1,0)"
    grass.run_command("r.mapcalc", expression=veg_expression, quiet=True)

    # identifying ignored areas
    grass.message(
        _("Excluding land-use classes without potential buildings...")
    )
    # codes are : 'moegliche Lagerflaechen, Reserveflaechen (2x),
    # Lager f. Rohstoffe', Bahnanlagen, Flug- und Landeplätze (2x),
    # Freiflächen (2x), Abgrabungsflächen (3x), Friedhof (2x), Begleitgrün (3x),
    # Wasserflaechen (9x), Wiesen & Weiden (2x), Ackerflächen, Berghalden (2x)
    non_dump_areas = f"non_dump_areas_{os.getpid()}"
    rm_rasters.append(non_dump_areas)
    fnk_codes_dumps = [
        "62",
        "63",
        "53",
        "65",
        "183",
        "192",
        "193",
        "215",
        "234",
        "262",
        "263",
        "264",
        "282",
        "283",
        "322",
        "323",
        "324",
        "325",
        "326",
        "331",
        "332",
        "342",
        "343",
        "351",
        "353",
        "354",
        "355",
        "357",
        "361",
        "362",
        "370",
        "501",
        "502",
    ]

    fnk_codes_dumps.extend(fnk_codes_trees)

    fnk_codes_roads = ["110", "140", "151", "152", "321"]
    exclude_roads = True
    if exclude_roads:
        fnk_codes_dumps.extend(fnk_codes_roads)

    grass.run_command(
        "r.null", map=fnk_rast, setnull=fnk_codes_dumps, quiet=True
    )
    exp_string = f"{non_dump_areas} = if(isnull({fnk_rast}), null(),1)"
    grass.run_command("r.mapcalc", expression=exp_string, quiet=True)

    # ndsm buildings thresholds (for buildings with one and more stories)
    ndsm_thresh1 = 2.0
    if flags["s"]:
        ####################
        # with segmentation
        ###################
        options["memory"] = test_memory(options["memory"])
        # cut the nDSM
        # transform ndsm
        grass.message(_("nDSM Transformation..."))
        ndsm_cut_tmp = f"ndsm_cut_tmp_{os.getpid()}"
        rm_rasters.append(ndsm_cut_tmp)
        ndsm_cut = f"ndsm_cut_{os.getpid()}"
        rm_rasters.append(ndsm_cut)
        # cut dtm extensively to also emphasize low buildings
        percentiles = "5,50,95"
        bins = get_bins()
        perc_values_list = list(
            grass.parse_command(
                "r.quantile",
                input=ndsm,
                percentile=percentiles,
                bins=bins,
                quiet=True,
            ).keys()
        )
        perc_values = [item.split(":")[2] for item in perc_values_list]
        grass.message(_(f"perc values are {perc_values}"))
        med = perc_values[1]
        p_low = perc_values[0]
        p_high = perc_values[2]
        trans_expression = (
            f"{ndsm_cut} = float(if({ndsm} >= {med}, sqrt(({ndsm} - "
            f"{med}) / ({p_high} - {med})), -1.0 * "
            f"sqrt(({med} - {ndsm}) / ({med} - "
            f"{p_low}))))"
        )

        grass.run_command("r.mapcalc", expression=trans_expression, quiet=True)

        grass.message(_("Image segmentation..."))
        # segmentation
        seg_group = f"seg_group_{os.getpid()}"
        rm_groups.append(seg_group)
        grass.run_command(
            "i.group", group=seg_group, input=f"{ndsm_cut},{ndvi}", quiet=True
        )
        segmented = f"segmented_{os.getpid()}"
        rm_rasters.append(segmented)
        grass.run_command(
            "i.segment",
            group=seg_group,
            output=segmented,
            threshold=0.075,
            minsize=10,
            memory=memory,
            quiet=True,
        )

        grass.message(_("Extracting potential buildings..."))
        ndsm_zonal_stats = f"ndsm_zonal_stats_{os.getpid()}"
        rm_rasters.append(ndsm_zonal_stats)
        grass.run_command(
            "r.stats.zonal",
            base=segmented,
            cover=ndsm,
            method="average",
            output=ndsm_zonal_stats,
            quiet=True,
        )
        veg_zonal_stats = f"veg_zonal_stats_{os.getpid()}"
        rm_rasters.append(veg_zonal_stats)
        grass.run_command(
            "r.stats.zonal",
            base=segmented,
            cover=veg_raster,
            method="average",
            output=veg_zonal_stats,
            quiet=True,
        )

        # extract building objects by: average nDSM height > 2m and
        # majority vote of vegetation pixels (implemented by average of binary
        # raster (mean < 0.5))
        buildings_raw_rast = f"buildings_raw_rast_{os.getpid()}"
        rm_rasters.append(buildings_raw_rast)
        expression_building = (
            f"{buildings_raw_rast} = if({ndsm_zonal_stats}>{ndsm_thresh1} && "
            f"{veg_zonal_stats}<0.5 && {non_dump_areas}==1,1,null())"
        )
        grass.run_command(
            "r.mapcalc", expression=expression_building, quiet=True
        )

    else:
        ######################
        # without segmentation
        ######################

        grass.message(_("Extracting potential buildings..."))
        buildings_raw_rast = f"buildings_raw_rast_{os.getpid()}"
        rm_rasters.append(buildings_raw_rast)

        expression_building = (
            f"{buildings_raw_rast} = if({ndsm}>{ndsm_thresh1} && "
            f"{veg_raster}==0 && {non_dump_areas}==1,1,null())"
        )
        grass.run_command(
            "r.mapcalc", expression=expression_building, quiet=True
        )

    # check if potential buildings have been detected
    warn_msg = "No potential buildings detected. Skipping..."
    buildings_stats = grass.parse_command(
        "r.univar", map=buildings_raw_rast, flags="g", quiet=True
    )
    if int(buildings_stats["n"]) == 0:
        grass.warning(_(f"{warn_msg}"))

        return 0

    # vectorize & filter
    vector_tmp1 = f"buildings_vect_tmp1_{os.getpid()}"
    rm_vectors.append(vector_tmp1)
    vector_tmp2 = f"{output}"
    rm_vectors.append(vector_tmp2)
    grass.run_command(
        "r.to.vect",
        input=buildings_raw_rast,
        output=vector_tmp1,
        type="area",
        quiet=True,
    )

    grass.message(_("Filtering buildings by size..."))
    area_col = "area_sqm"
    min_size = float(user_min_size)/2
    grass.run_command(
        "v.to.db",
        map=vector_tmp1,
        option="area",
        columns=area_col,
        units="meters",
        quiet=True,
    )

    grass.run_command(
        "v.db.droprow",
        input=vector_tmp1,
        output=vector_tmp2,
        where=f"{area_col}<{min_size}",
        quiet=True,
    )

    # check if potential buildings remain
    db_connection = grass.parse_command(
        "v.db.connect", map=vector_tmp2, flags="p", quiet=True
    )
    if not db_connection:
        grass.warning(_(f"{warn_msg}"))

        return 0

    vector_tmp1_feat = grass.parse_command(
        "v.db.select", map=vector_tmp1, column="cat", flags="c", quiet=True
    )
    vector_tmp2_feat = grass.parse_command(
        "v.db.select", map=vector_tmp2, column="cat", flags="c", quiet=True
    )
    if len(vector_tmp1_feat.keys()) == 0 or len(vector_tmp2_feat.keys()) == 0:
        grass.warning(_(f"{warn_msg}"))

        return 0

    grass.message(_(f"Created output vector layer <{output}>"))


def main():
    global rm_rasters, tmp_mask_old, rm_vectors, rm_groups

    path = get_lib_path(
        modname="m.analyse.buildings", libname="analyse_buildings_lib"
    )
    if path is None:
        grass.fatal("Unable to find the analyse buildings library directory")
    sys.path.append(path)
    try:
        from analyse_buildings_lib import switch_to_new_mapset
    except Exception:
        grass.fatal("m.analyse.buildings library is not installed")

    ndsm = options["ndsm"]
    ndvi = options["ndvi_raster"]
    min_size = options["min_size"]
    max_fd = options["max_fd"]
    ndvi_thresh = options["ndvi_thresh"]
    memory = options["memory"]
    output = options["output"]
    new_mapset = options["new_mapset"]
    area = options["area"]

    if options["fnk_vector"]:
        fnk_vect = options["fnk_vector"]
        fnk_column = options["fnk_column"]
    elif options["fnk_raster"]:
        fnk_rast = options["fnk_raster"]

    grass.message(_(f"Applying building extraction to region {area}..."))

    # switch to another mapset for parallel processing
    gisrc, newgisrc, old_mapset = switch_to_new_mapset(new_mapset)

    area += f"@{old_mapset}"
    ndsm += f"@{old_mapset}"
    ndvi += f"@{old_mapset}"
    if options["fnk_vector"]:
        fnk_vect += f"@{old_mapset}"
    if options["fnk_raster"]:
        fnk_rast += f"@{old_mapset}"

    grass.run_command(
        "g.region",
        vector=area,
        align=ndsm,
        quiet=True,
    )
    grass.message(_(f"Current region (Tile: {area}):\n{grass.region()}"))

    # check input data (nDSM and NDVI)
    ndsm_stats = grass.parse_command(
        "r.univar", map=ndsm, flags="g", quiet=True
    )
    ndvi_stats = grass.parse_command(
        "r.univar", map=ndvi, flags="g", quiet=True
    )
    if int(ndsm_stats["n"]) == 0 or int(ndvi_stats["n"] == 0):
        grass.warning(
            _(
                f"At least one of {ndsm}, {ndvi} not available in {area}. Skipping..."
            )
        )
        # set GISRC to original gisrc and delete newgisrc
        os.environ["GISRC"] = gisrc
        grass.utils.try_remove(newgisrc)

        return 0

    # copy FNK to temporary mapset
    if options["fnk_vector"]:
        fnk_vect_tmp = f'{options["fnk_vector"]}_{os.getpid()}'
        rm_vectors.append(fnk_vect_tmp)
        grass.run_command(
            "g.copy", vector=f"{fnk_vect},{fnk_vect_tmp}", quiet=True
        )
    elif options["fnk_raster"]:
        fnk_rast_tmp = f'{options["fnk_raster"]}_{os.getpid()}'
        rm_rasters.append(fnk_rast_tmp)
        grass.run_command(
            "g.copy", raster=f"{fnk_rast},{fnk_rast_tmp}", quiet=True
        )

    # start building extraction
    kwargs = {
        "output": output,
        "ndsm": ndsm,
        "ndvi_raster": ndvi,
        "min_size": min_size,
        "max_fd": max_fd,
        "ndvi_thresh": ndvi_thresh,
        "memory": memory,
    }

    if flags["s"]:
        kwargs["flags"] = "s"
    if options["fnk_vector"]:
        kwargs["fnk_vector"] = fnk_vect_tmp
        kwargs["fnk_column"] = fnk_column
    elif options["fnk_raster"]:
        kwargs["fnk_raster"] = fnk_rast_tmp

    # run building_extraction
    extract_buildings(**kwargs)

    # set GISRC to original gisrc and delete newgisrc
    os.environ["GISRC"] = gisrc
    grass.utils.try_remove(newgisrc)

    grass.message(
        _(
            f"Building extraction for {area} DONE \n"
            f"Output is: <{output}@{new_mapset}>"
        )
    )
    return 0


if __name__ == "__main__":
    options, flags = grass.parser()
    atexit.register(cleanup)
    main()
