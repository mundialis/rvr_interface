#!/usr/bin/env python3

############################################################################
#
# MODULE:       r.extract.buildings
#
# AUTHOR(S):    Guido Riembauer <riembauer at mundialis.de>
#
# PURPOSE:      Extracts buildings from nDOM, NDVI and FNK
#
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
# % key: ndvi_thresh
# % type: integer
# % required: yes
# % multiple: no
# % label: NDVI threshold (user-defined or estimated from FNK, scale 0-255)
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

# %flag
# % key: s
# % description: segment image based on nDOM and NDVI before building extraction
# %end

import atexit
import psutil
import os
import grass.script as grass

# initialize global vars
rm_rasters = []
rm_vectors = []
rm_groups = []
tmp_mask_old = None


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
    if grass.find_file(name='MASK', element='raster')['file']:
        try:
            grass.run_command("r.mask", flags='r', quiet=True)
        except:
            pass
    # reactivate potential old mask
    if tmp_mask_old:
        grass.run_command('r.mask', raster=tmp_mask_old, quiet=True)


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


def main():

    global rm_rasters, tmp_mask_old, rm_vectors, rm_groups
    grass.message(_("Preparing input data..."))
    if grass.find_file(name='MASK', element='raster')['file']:
        tmp_mask_old = 'tmp_mask_old_%s' % os.getpid()
        grass.run_command('g.rename', raster='%s,%s' % ('MASK', tmp_mask_old),
                          quiet=True)

    ndom = options['ndom']
    ndvi = options['ndvi_raster']
    fnk_vect = options['fnk_vector']
    ndvi_thresh = options['ndvi_thresh']

    # rasterizing fnk vect
    fnk_rast = 'fnk_rast_{}'.format(os.getpid())
    rm_rasters.append(fnk_rast)
    grass.run_command('v.to.rast', input=fnk_vect, use='attr',
                      attribute_column=options['fnk_column'],
                      output=fnk_rast, quiet=True)

    # fnk-codes with potential tree growth (400+ = Vegetation)
    fnk_codes_trees = ['400', '410', '420', '431', '432', '441', '472']
    fnk_codes_mask = ' '.join(fnk_codes_trees)

    # create binary vegetation raster
    veg_raster = 'vegetation_raster_{}'.format(os.getpid())
    rm_rasters.append(veg_raster)
    veg_expression = '{} = if({}>{},1,0)'.format(veg_raster, ndvi, ndvi_thresh)
    grass.run_command('r.mapcalc', expression=veg_expression, quiet=True)

    # identifying ignored areas
    grass.message(_('Excluding land-use classes without potential buildings...'))
    # codes are : 'moegliche Lagerflaechen, Reserveflaechen (2x),
    # Lager f. Rohstoffe', Bahnanlagen, Flug- und Landeplätze (2x),
    # Freiflächen (2x), Abgrabungsflächen (3x), Friedhof (2x), Begleitgrün (3x),
    # Wasserflaechen (9x), Wiesen & Weiden (2x), Ackerflächen, Berghalden (2x)
    non_dump_areas = 'non_dump_areas_{}'.format(os.getpid())
    rm_rasters.append(non_dump_areas)
    fnk_codes_dumps = ['62', '63', '53', '65', '183', '192', '193', '215', '234',
                       '262', '263', '264', '282', '283', '322', '323', '324',
                       '325', '326', '331', '332', '342', '343', '351', '353',
                       '354', '355', '357', '361', '362', '370', '501',
                       '502']

    fnk_codes_dumps.extend(fnk_codes_trees)

    fnk_codes_roads = ['110', '140', '151', '152', '321']
    exclude_roads = True
    if exclude_roads:
        fnk_codes_dumps.extend(fnk_codes_roads)

    grass.run_command("r.null", map=fnk_rast, setnull=fnk_codes_dumps,
                      quiet=True)
    exp_string = "{} = if(isnull({}), null(),1)".format(non_dump_areas,
                                                        fnk_rast)
    grass.run_command("r.mapcalc", expression=exp_string, quiet=True)

    # ndom buildings thresholds (for buildings with one and more stories)
    ndom_thresh1 = 2.0
    av_story_height = 3.0
    if flags['s']:
        ####################
        # with segmentation
        ###################
        test_memory()
        # cut the nDOM
        # transform ndom
        grass.message(_('nDOM Transformation...'))
        ndom_cut_tmp = 'ndom_cut_tmp_{}'.format(os.getpid())
        rm_rasters.append(ndom_cut_tmp)
        ndom_cut = 'ndom_cut_{}'.format(os.getpid())
        rm_rasters.append(ndom_cut)
        # cut dem extensively to also emphasize low buildings
        percentiles = '5,50,95'
        perc_values_list = list(grass.parse_command('r.quantile', input=ndom,
                                                    percentile=percentiles,
                                                    quiet=True).keys())
        perc_values = [item.split(':')[2] for item in perc_values_list]
        print('perc values are {}'.format(perc_values))
        trans_expression = ('{out} = float(if({inp} >= {med}, sqrt(({inp} - '
                            '{med}) / ({p_high} - {med})), -1.0 * '
                            'sqrt(({med} - {inp}) / ({med} - '
                            '{p_low}))))').format(inp=ndom, out=ndom_cut,
                                                  med=perc_values[1],
                                                  p_low=perc_values[0],
                                                  p_high=perc_values[2])

        grass.run_command('r.mapcalc', expression=trans_expression, quiet=True)

        grass.message(_('Image segmentation...'))
        # segmentation
        seg_group = 'seg_group_{}'.format(os.getpid())
        rm_groups.append(seg_group)
        grass.run_command('i.group', group=seg_group, input='{},{}'.format(
            ndom_cut, ndvi), quiet=True)
        segmented = 'segmented_{}'.format(os.getpid())
        rm_rasters.append(segmented)
        grass.run_command('i.segment', group=seg_group, output=segmented,
                          threshold=0.075, minsize=10, memory=options['memory'],
                          quiet=True)

        grass.message(_("Extracting potential buildings..."))
        ndom_zonal_stats = 'ndom_zonal_stats_{}'.format(os.getpid())
        rm_rasters.append(ndom_zonal_stats)
        grass.run_command('r.stats.zonal', base=segmented, cover=ndom,
                          method='average', output=ndom_zonal_stats,
                          quiet=True)
        veg_zonal_stats = 'veg_zonal_stats_{}'.format(os.getpid())
        rm_rasters.append(veg_zonal_stats)
        grass.run_command('r.stats.zonal', base=segmented, cover=veg_raster,
                          method='average', output=veg_zonal_stats, quiet=True)

        # extract building objects by: average nDOM height > 2m and
        # majority vote of vegetation pixels (implemented by average of binary
        # raster (mean < 0.5))

        buildings_raw_rast = 'buildings_raw_rast_{}'.format(os.getpid())
        rm_rasters.append(buildings_raw_rast)
        expression_building = ('{} = if({}>{} && {}<0.5 &&'
                               ' {}==1,1,null())').format(
            buildings_raw_rast, ndom_zonal_stats, ndom_thresh1, veg_zonal_stats,
            non_dump_areas)
        grass.run_command('r.mapcalc', expression=expression_building,
                          quiet=True)

    else:
        ######################
        # without segmentation
        ######################

        grass.message(_("Extracting potential buildings..."))
        buildings_raw_rast = 'buildings_raw_rast_{}'.format(os.getpid())
        rm_rasters.append(buildings_raw_rast)

        expression_building = ('{} = if({}>{} && {}==0 && '
                               '{}==1,1,null())').format(
            buildings_raw_rast, ndom, ndom_thresh1, veg_raster,
            non_dump_areas)

        grass.run_command('r.mapcalc', expression=expression_building,
                          quiet=True)

    # check if potential buildings have been detected
    warn_msg = "No potential buildings detected. Skipping..."
    buildings_stats = grass.parse_command("r.univar", map=buildings_raw_rast, flags="g")
    if int(buildings_stats['n']) == 0:
        grass.warning(_(f"{warn_msg}"))

        return 0

    # vectorize & filter
    vector_tmp1 = 'buildings_vect_tmp1_{}'.format(os.getpid())
    rm_vectors.append(vector_tmp1)
    vector_tmp2 = 'buildings_vect_tmp2_{}'.format(os.getpid())
    rm_vectors.append(vector_tmp2)
    vector_tmp3 = 'buildings_vect_tmp3_{}'.format(os.getpid())
    rm_vectors.append(vector_tmp3)
    grass.run_command('r.to.vect', input=buildings_raw_rast,
                      output=vector_tmp1, type='area', quiet=True)

    grass.message(_("Filtering buildings by shape and size..."))
    area_col = 'area_sqm'
    fd_col = 'fractal_d'
    grass.run_command('v.to.db', map=vector_tmp1, option='area',
                      columns=area_col, units='meters', quiet=True)
    grass.run_command('v.to.db', map=vector_tmp1, option='fd',
                      columns=fd_col, units='meters', quiet=True)

    grass.run_command('v.db.droprow', input=vector_tmp1,
                      output=vector_tmp2, where='{}<{} OR {}>{}'.format(
                        area_col, options['min_size'], fd_col,
                        options['max_fd']), quiet=True)

    # remove small gaps in objects
    fill_gapsize = 20
    grass.run_command('v.clean', input=vector_tmp2, output=vector_tmp3,
                      tool='rmarea', threshold=fill_gapsize, quiet=True)


    # check if potential buildings remain
    db_connection = grass.parse_command("v.db.connect", map=vector_tmp2, flags="p", quiet=True)
    if not db_connection:
        grass.warning(_(f"{warn_msg}"))

        return 0

    vector_tmp2_feat = grass.parse_command("v.db.select", map=vector_tmp2, column="cat", flags="c")
    vector_tmp3_feat = grass.parse_command("v.db.select", map=vector_tmp3, column="cat", flags="c")
    if len(vector_tmp2_feat.keys()) == 0 or len(vector_tmp3_feat.keys()) == 0:
        grass.warning(_(f"{warn_msg}"))

        return 0


    # assign building height to attribute and estimate no. of stories
    ####################################################################
    # ndom transformation and segmentation
    grass.message(_("Splitting up buildings by height..."))
    grass.run_command("r.mask", vector=vector_tmp3, quiet=True)
    percentiles = "1,50,99"
    quants_raw = list(grass.parse_command("r.quantile",
                      percentiles=percentiles, input=ndom, quiet=True).keys())
    quants = [item.split(":")[2] for item in quants_raw]
    grass.message(_("The percentiles are: {}".format((", ").join(quants))))
    trans_ndom_mask = "ndom_buildings_transformed_{}".format(os.getpid())
    rm_rasters.append(trans_ndom_mask)
    trans_expression = ('{out} = float(if({inp} >= {med}, sqrt(({inp} - '
                        '{med}) / ({p_high} - {med})), -1.0 * '
                        'sqrt(({med} - {inp}) / ({med} - '
                        '{p_low}))))').format(inp=ndom, out=trans_ndom_mask,
                                              med=quants[1],
                                              p_low=quants[0],
                                              p_high=quants[2])
    grass.run_command('r.mapcalc', expression=trans_expression, quiet=True)
    # add transformed and cut ndom to group
    segment_group = "segment_group_{}".format(os.getpid())
    rm_groups.append(segment_group)
    grass.run_command("i.group", group=segment_group, input=trans_ndom_mask,
                      quiet=True)

    segmented_ndom_buildings = "seg_ndom_buildings_{}".format(os.getpid())
    rm_rasters.append(segmented_ndom_buildings)
    grass.run_command("i.segment", group=segment_group,
                      output=segmented_ndom_buildings, threshold=0.25,
                      memory=options["memory"], minsize=50, quiet=True)

    grass.run_command("r.mask", flags="r", quiet=True)

    grass.run_command('r.to.vect', input=segmented_ndom_buildings,
                      output=options["output"], type='area',
                      column="building_cat", quiet=True)

    #####################################################################
    grass.message(_("Extracting building height statistics..."))
    grass.run_command('v.rast.stats', map=options['output'], raster=ndom,
                      method=("minimum,maximum,average,stddev,"
                      "median,percentile"), percentile=95,
                      column_prefix='ndom', quiet=True)
    column_etagen = "Etagen"
    grass.run_command("v.db.addcolumn", map=options["output"],
                      columns="{} INT".format(column_etagen), quiet=True)
    sql_string = "ROUND(ndom_percentile_95/{},0)".format(av_story_height)
    grass.run_command("v.db.update", map=options["output"],
                      column=column_etagen, query_column=sql_string,
                      quiet=True)

    grass.message(_('Created output vector layer <{}>').format(options['output']))


if __name__ == "__main__":
    options, flags = grass.parser()
    atexit.register(cleanup)
    main()
