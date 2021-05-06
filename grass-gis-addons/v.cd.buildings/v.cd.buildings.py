#!/usr/bin/env python3

############################################################################
#
# MODULE:       v.cd.buildings
#
# AUTHOR(S):    Julia Haas <haas at mundialis.de>
#
# PURPOSE:      Calculates difference between two vector layers (buildings)
#
#
# COPYRIGHT:	(C) 2021 by mundialis and the GRASS Development Team
#
#		This program is free software under the GNU General Public
#		License (>=v2). Read the file COPYING that comes with GRASS
#		for details.
#
#############################################################################

#%Module
#% description: Calculates difference between two vector layers (buildings)
#% keyword: vector
#% keyword: statistics
#% keyword: change detection
#% keyword: classification
#%end

#%option G_OPT_V_INPUT
#% label: Name of the input vector layer
#%end

#%option G_OPT_V_INPUT
#% key: reference
#% type: string
#% required: yes
#% multiple: no
#% label: Name of the reference vector layer
#%end

#%option
#% key: min_size
#% type: integer
#% required: no
#% multiple: no
#% label: Minimum size of identified change areas in sqm
#% answer: 5
#%end

#%option
#% key: max_fd
#% type: double
#% required: no
#% multiple: no
#% label: Maximum value of fractal dimension of identified change areas (see v.to.db)
#% answer: 2.5
#%end

#%option G_OPT_R_OUTPUT
#% key: output
#% type: string
#% required: yes
#% multiple: no
#% description: Name for output vector map
#% guisection: Output
#%end


import os
import atexit
import grass.script as grass

# initialize global vars
rm_vectors = []

def cleanup():
    nuldev = open(os.devnull, 'w')
    kwargs = {
        'flags': 'f',
        'quiet': True,
        'stderr': nuldev
    }
    for rmv in rm_vectors:
        if grass.find_file(name=rmv, element='vector')['file']:
            grass.run_command(
                'g.remove', type='vector', name=rmv, **kwargs)


def main():

    global rm_vectors

    # calculate symemtrial difference of two input vector layers
    input = options['input']
    ref = options['reference']

    # buffer reference back and forth to remove very thin gaps
    grass.message("Closing small gaps in reference map...")
    buffdist = 0.5
    buf_tmp1 = "{}_buf_tmp1".format(ref)
    rm_vectors.append(buf_tmp1)
    buf_tmp2 = "{}_buf_tmp2".format(ref)
    rm_vectors.append(buf_tmp2)
    grass.run_command("v.buffer", input=ref, distance=buffdist, flags="cs",
                      output=buf_tmp1, quiet=True)
    grass.run_command("v.buffer", input=buf_tmp1, distance=-buffdist,
                      output=buf_tmp2, flags="cs", quiet=True)

    grass.message(_("Creation of difference vector map..."))
    vector_tmp1 = 'change_vect_tmp1_{}'.format(os.getpid())
    rm_vectors.append(vector_tmp1)
    grass.run_command('v.overlay', ainput=buf_tmp2, atype="area", binput=input,
                      btype="area", operator='xor', output=vector_tmp1,
                      quiet=True)

    # filter with area and fractal dimension
    grass.message(_("Cleaning up based on shape and size..."))
    area_col = 'area_sqm'
    fd_col = 'fractal_d'

    grass.run_command('v.to.db', map=vector_tmp1, option='area',
                      columns=area_col, units='meters', quiet=True)

    grass.run_command('v.to.db', map=vector_tmp1, option='fd',
                      columns=fd_col, units='meters', quiet=True)

    grass.run_command('v.db.droprow', input=vector_tmp1,
                      output=options['output'], where='{}<{} OR {}>{}'.format(
                          area_col, options['min_size'], fd_col,
                          options['max_fd']), quiet=True)

    # rename columns and remove unnecessary columns
    columns_raw = list(grass.parse_command("v.info", map=options["output"],
                                           flags="cg").keys())
    columns = [item.split('|')[1] for item in columns_raw]
    # initial list of columns to be removed
    dropcolumns = [area_col, fd_col, "b_cat"]
    for col in columns:
        items = list(grass.parse_command("v.db.select", flags="c",
                                         map=options["output"], columns=col,
                                         quiet=True).keys())
        if len(items) < 2 or col.startswith("a_"):
            # empty cols return a length of 1 with ['']
            # all columns from reference ("a_*") lose information during buffer
            dropcolumns.append(col)
        elif col.startswith("b_"):
            if col != "b_cat":
                grass.run_command("v.db.renamecolumn", map=options["output"],
                                  column="{},{}".format(col, col[2:]),
                                  quiet=True)

    # add column "source" and populate with name of ref or input map
    grass.run_command("v.db.addcolumn", map=options["output"],
                      columns="source VARCHAR(100)", quiet=True)
    grass.run_command("v.db.update", map=options["output"], column="source",
                      value=input.split('@')[0],
                      where="b_cat IS NOT NULL", quiet=True)
    grass.run_command("v.db.update", map=options["output"], column="source",
                      value=ref.split('@')[0],
                      where="a_cat IS NOT NULL", quiet=True)

    grass.run_command("v.db.dropcolumn", map=options["output"],
                      columns=dropcolumns, quiet=True)

    grass.message(_('Created output vector map <{}>').format(
        options['output']))


if __name__ == "__main__":
    options, flags = grass.parser()
    atexit.register(cleanup)
    main()
