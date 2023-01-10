#!/usr/bin/env python3

############################################################################
#
# MODULE:       r.extract.buildings.worker
#
# AUTHOR(S):    Julia Haas <haas at mundialis.de>
#               Guido Riembauer <riembauer at mundialis.de>
#
# PURPOSE:      Extracts buildings from nDOM, NDVI and FNK
#
# COPYRIGHT:	(C) 2023 by mundialis and the GRASS Development Team
#
# 		This program is free software under the GNU General Public
# 		License (>=v2). Read the file COPYING that comes with GRASS
# 		for details.
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

# %option G_OPT_R_INPUTS
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
# % description: segment image based on nDOM and NDVI before building extraction
# %end


import atexit
import os
import shutil

import grass.script as grass
import psutil

# initialize global vars
rm_rasters = []
rm_vectors = []
rm_groups = []
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
    if grass.find_file(name="MASK", element="raster")["file"]:
        try:
            grass.run_command("r.mask", flags="r", quiet=True)
        except:
            pass
    # reactivate potential old mask
    if tmp_mask_old:
        grass.run_command("r.mask", raster=tmp_mask_old, quiet=True)


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

    grass.message(_(f"New mapset. {new_mapset}"))
    grass.utils.try_rmdir(os.path.join(gisdbase, location, new_mapset))

    gisrc = os.environ["GISRC"]
    newgisrc = f"{gisrc}_{str(os.getpid())}"
    grass.try_remove(newgisrc)
    shutil.copyfile(gisrc, newgisrc)
    os.environ["GISRC"] = newgisrc

    grass.message(_(f'GISRC: {os.environ["GISRC"]}'))
    grass.run_command("g.mapset", flags="c", mapset=new_mapset)

    # verify that switching of the mapset worked
    cur_mapset = grass.gisenv()["MAPSET"]
    if cur_mapset != new_mapset:
        grass.fatal(_(f"New mapset is {cur_mapset}, but should be {new_mapset}"))
    return gisrc, newgisrc, old_mapset


def freeRAM(unit, percent=100):
    """The function gives the amount of the percentages of the installed RAM.
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
    memory_GB = (mem_available + swap_free) / 1024.0**3
    memory_MB = (mem_available + swap_free) / 1024.0**2

    if unit == "MB":
        memory_MB_percent = memory_MB * percent / 100.0
        return int(round(memory_MB_percent))
    elif unit == "GB":
        memory_GB_percent = memory_GB * percent / 100.0
        return int(round(memory_GB_percent))
    else:
        grass.fatal(_(f"Memory unit <{unit}> not supported"))


def test_memory():
    # check memory
    memory = int(options["memory"])
    free_ram = freeRAM("MB", 100)
    if free_ram < memory:
        grass.warning(_(f"Using {memory} MB but only {free_ram} MB RAM available."))
        options["memory"] = free_ram
        grass.warning(_(f'Set used memory to {options["memory"]} MB.'))


def extract_buildings(**kwargs):
    global rm_rasters, tmp_mask_old, rm_vectors, rm_groups

    grass.message(_("Preparing input data..."))
    if grass.find_file(name="MASK", element="raster")["file"]:
        tmp_mask_old = f"tmp_mask_old_{os.getgid()}"
        grass.run_command("g.rename", raster=f'{"MASK"},{tmp_mask_old}', quiet=True)

    ndom = kwargs["ndom"]
    ndvi = kwargs["ndvi_raster"]
    fnk_vect = kwargs["fnk_vector"]
    fnk_column = kwargs["fnk_column"]
    ndvi_thresh = kwargs["ndvi_thresh"]
    # min_size = kwargs["min_size"]
    # max_fd = kwargs["max_fd"]
    memory = kwargs["memory"]
    output = kwargs["output"]

    # rasterizing fnk vect
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

    # fnk-codes with potential tree growth (400+ = Vegetation)
    fnk_codes_trees = ["400", "410", "420", "431", "432", "441", "472"]
    fnk_codes_mask = " ".join(fnk_codes_trees)

    # create binary vegetation raster
    veg_raster = f"vegetation_raster_{os.getpid()}"
    rm_rasters.append(veg_raster)
    veg_expression = f"{veg_raster} = if({ndvi}>{ndvi_thresh},1,0)"
    grass.run_command("r.mapcalc", expression=veg_expression, quiet=True)

    # identifying ignored areas
    grass.message(_("Excluding land-use classes without potential buildings..."))
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

    grass.run_command("r.null", map=fnk_rast, setnull=fnk_codes_dumps, quiet=True)
    exp_string = f"{non_dump_areas} = if(isnull({fnk_rast}), null(),1)"
    grass.run_command("r.mapcalc", expression=exp_string, quiet=True)

    # ndom buildings thresholds (for buildings with one and more stories)
    ndom_thresh1 = 2.0
    if flags["s"]:
        ####################
        # with segmentation
        ###################
        test_memory()
        # cut the nDOM
        # transform ndom
        grass.message(_("nDOM Transformation..."))
        ndom_cut_tmp = f"ndom_cut_tmp_{os.getpid()}"
        rm_rasters.append(ndom_cut_tmp)
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
        grass.message(_(f"perc values are {perc_values}"))
        med = perc_values[1]
        p_low = perc_values[0]
        p_high = perc_values[2]
        trans_expression = (
            f"{ndom_cut} = float(if({ndom} >= {med}, sqrt(({ndom} - "
            f"{med}) / ({p_high} - {med})), -1.0 * "
            f"sqrt(({med} - {ndom}) / ({med} - "
            f"{p_low}))))"
        )

        grass.run_command("r.mapcalc", expression=trans_expression, quiet=True)

        grass.message(_("Image segmentation..."))
        # segmentation
        seg_group = f"seg_group_{os.getpid()}"
        rm_groups.append(seg_group)
        grass.run_command(
            "i.group", group=seg_group, input=f"{ndom_cut},{ndvi}", quiet=True
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
        ndom_zonal_stats = f"ndom_zonal_stats_{os.getpid()}"
        rm_rasters.append(ndom_zonal_stats)
        grass.run_command(
            "r.stats.zonal",
            base=segmented,
            cover=ndom,
            method="average",
            output=ndom_zonal_stats,
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

        # extract building objects by: average nDOM height > 2m and
        # majority vote of vegetation pixels (implemented by average of binary
        # raster (mean < 0.5))
        buildings_raw_rast = f"buildings_raw_rast_{os.getpid()}"
        rm_rasters.append(buildings_raw_rast)
        expression_building = (
            f"{buildings_raw_rast} = if({ndom_zonal_stats}>{ndom_thresh1} && "
            f"{veg_zonal_stats}<0.5 && {non_dump_areas}==1,1,null())"
        )
        grass.run_command("r.mapcalc", expression=expression_building, quiet=True)

    else:
        ######################
        # without segmentation
        ######################

        grass.message(_("Extracting potential buildings..."))
        buildings_raw_rast = f"buildings_raw_rast_{os.getpid()}"
        rm_rasters.append(buildings_raw_rast)

        expression_building = (
            f"{buildings_raw_rast} = if({ndom}>{ndom_thresh1} && "
            f"{veg_raster}==0 && {non_dump_areas}==1,1,null())"
        )
        grass.run_command("r.mapcalc", expression=expression_building, quiet=True)

    # check if potential buildings have been detected
    warn_msg = "No potential buildings detected. Skipping..."
    buildings_stats = grass.parse_command("r.univar", map=buildings_raw_rast, flags="g")
    if int(buildings_stats["n"]) == 0:
        grass.warning(_(f"{warn_msg}"))

        return 0

    # vectorize & filter
    vector_tmp1 = f"buildings_vect_tmp1_{os.getpid()}"
    rm_vectors.append(vector_tmp1)
    # vector_tmp2 = f"buildings_vect_tmp2_{os.getpid()}"
    # rm_vectors.append(vector_tmp2)
    vector_tmp3 = f"{output}"
    rm_vectors.append(vector_tmp3)
    grass.run_command(
        "r.to.vect",
        input=buildings_raw_rast,
        output=vector_tmp1,
        type="area",
        quiet=True,
    )

    grass.message(_("Filtering buildings by size..."))
    # remove small gaps in objects
    fill_gapsize = 10
    grass.run_command(
        "v.clean",
        input=vector_tmp1,
        output=vector_tmp3,
        tool="rmarea",
        threshold=fill_gapsize,
        quiet=True,
    )

    # check if potential buildings remain
    # db_connection = grass.parse_command(
    #     "v.db.connect", map=vector_tmp2, flags="p", quiet=True
    # )
    # if not db_connection:
    #     grass.warning(_(f"{warn_msg}"))
    #
    #     return 0

    vector_tmp1_feat = grass.parse_command(
        "v.db.select", map=vector_tmp1, column="cat", flags="c"
    )
    vector_tmp3_feat = grass.parse_command(
        "v.db.select", map=vector_tmp3, column="cat", flags="c"
    )
    if len(vector_tmp1_feat.keys()) == 0 or len(vector_tmp3_feat.keys()) == 0:
        grass.warning(_(f"{warn_msg}"))

        return 0

    grass.message(_(f"Created output vector layer <{output}>"))


def main():

    global rm_rasters, tmp_mask_old, rm_vectors, rm_groups

    ndom = options["ndom"]
    ndvi = options["ndvi_raster"]
    fnk_vect = options["fnk_vector"]
    fnk_column = options["fnk_column"]
    min_size = options["min_size"]
    max_fd = options["max_fd"]
    ndvi_thresh = options["ndvi_thresh"]
    memory = options["memory"]
    output = options["output"]
    new_mapset = options["new_mapset"]
    area = options["area"]

    grass.message(_(f"Applying building extraction to region {area}..."))

    # switch to another mapset for parallel processing
    gisrc, newgisrc, old_mapset = switch_to_new_mapset(new_mapset)

    area += f"@{old_mapset}"
    ndom += f"@{old_mapset}"
    ndvi += f"@{old_mapset}"
    fnk_vect += f"@{old_mapset}"

    grass.run_command(
        "g.region",
        vector=area,
        align=ndom,
        quiet=True,
    )
    grass.message(_(f"Current region (Tile: {area}):\n{grass.region()}"))

    # check input data (nDOM and NDVI)
    ndom_stats = grass.parse_command("r.univar", map=ndom, flags="g")
    ndvi_stats = grass.parse_command("r.univar", map=ndvi, flags="g")
    if int(ndom_stats["n"]) == 0 or int(ndvi_stats["n"] == 0):
        grass.warning(
            _(f"At least one of {ndom}, {ndvi} not available in {area}. Skipping...")
        )
        # set GISRC to original gisrc and delete newgisrc
        os.environ["GISRC"] = gisrc
        grass.utils.try_remove(newgisrc)

        return 0

    # copy FNK to temporary mapset
    fnk_vect_tmp = f'{options["fnk_vector"]}_{os.getpid()}'
    rm_vectors.append(fnk_vect_tmp)
    grass.run_command("g.copy", vector=f"{fnk_vect},{fnk_vect_tmp}", quiet=True)

    # start building extraction
    kwargs = {
        "output": output,
        "ndom": ndom,
        "ndvi_raster": ndvi,
        "fnk_vector": fnk_vect_tmp,
        "fnk_column": fnk_column,
        "min_size": min_size,
        "max_fd": max_fd,
        "ndvi_thresh": ndvi_thresh,
        "memory": memory,
    }

    if flags["s"]:
        kwargs["flags"] = "s"

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
