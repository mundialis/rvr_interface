#!/usr/bin/env python3

############################################################################
#
# MODULE:       r.in.pdal.worker
#
# AUTHOR(S):    Weinmann
#
# PURPOSE:      Worker GRASS GIS addon for r.in.pdal
#
# COPYRIGHT:	(C) 2023 by mundialis and the GRASS Development Team
#
# 		This program is free software under the GNU General Public
# 		License (>=v2). Read the file COPYING that comes with GRASS
# 		for details.
#
#############################################################################

# %Module
# % description: Worker GRASS GIS addon for r.in.pdal.
# % keyword: raster
# % keyword: import
# % keyword: LIDAR
# % keyword: statistics
# % keyword: conversion
# % keyword: aggregation
# % keyword: binning
# % keyword: parallel
# %end

# %option
# % key: new_mapset
# % type: string
# % required: yes
# % multiple: no
# % label: Name of new mapset where to compute the building MASK
# %end

# %option
# % key: res
# % type: double
# % required: yes
# % multiple: no
# % description: Resolution which is set with g.region before r.in.pdal
# %end

# %option
# % key: input
# % type: string
# % required: no
# % multiple: no
# % key_desc: name
# % label: LAS input file
# % description: LiDAR input files in LAS format (*.las or *.laz)
# % gisprompt: old,bin,file
# % guisection: Input
# %end

# %option
# % key: output
# % type: string
# % required: no
# % multiple: no
# % key_desc: name
# % description: Name for output raster map
# % gisprompt: new,cell,raster
# % guisection: Output
# %end

# %option
# % key: file
# % type: string
# % required: no
# % multiple: no
# % key_desc: name
# % label: File containing names of LAS input files
# % description: LiDAR input files in LAS format (*.las or *.laz)
# % gisprompt: old,file,file
# % guisection: Input
# %end

# %option
# % key: method
# % type: string
# % required: no
# % multiple: no
# % options: n,min,max,range,sum,mean,stddev,variance,coeff_var,median,mode,percentile,skewness,trimmean,sidnmax,sidnmin,ev1,ev2,ev3
# % description: Statistic to use for raster values
# % descriptions: n;Number of points in cell;min;Minimum value of point values in cell;max;Maximum value of point values in cell;range;Range of point values in cell;sum;Sum of point values in cell;mean;Mean (average) value of point values in cell;stddev;Standard deviation of point values in cell;variance;Variance of point values in cell;coeff_var;Coefficient of variance of point values in cell;median;Median value of point values in cell;mode;Mode value of point values in cell;percentile;pth (nth) percentile of point values in cell;skewness;Skewness of point values in cell;trimmean;Trimmed mean of point values in cell;sidnmax;Maximum number of points in cell per source ID;sidnmin;Minimum number of points in cell per source ID;ev1;First eigenvalue of point x, y, z coordinates;ev2;Second eigenvalue of point x, y, z coordinates;ev3;Third eigenvalue of point x, y, z coordinates;
# % answer: mean
# % guisection: Statistic
# %end

# %option
# % key: type
# % type: string
# % required: no
# % multiple: no
# % options: CELL,FCELL,DCELL
# % label: Type of raster map to be created
# % description: Storage type for resultant raster map
# % descriptions: CELL;Integer;FCELL;Single precision floating point;DCELL;Double precision floating point
# % answer: FCELL
# %end

# %option
# % key: base_raster
# % type: string
# % required: no
# % multiple: no
# % key_desc: name
# % label: Subtract raster values from the Z coordinates
# % description: The scale for Z is applied beforehand, the range filter for Z afterwards
# % gisprompt: old,cell,raster
# % guisection: Transform
# %end

# %option
# % key: zrange
# % type: double
# % required: no
# % multiple: no
# % key_desc: min,max
# % label: Filter range for Z data (min,max)
# % description: Applied after base_raster transformation step
# % guisection: Selection
# %end

# %option
# % key: zscale
# % type: double
# % required: no
# % multiple: no
# % description: Scale to apply to Z data
# % answer: 1.0
# % guisection: Transform
# %end

# %option
# % key: irange
# % type: double
# % required: no
# % multiple: no
# % key_desc: min,max
# % description: Filter range for intensity values (min,max)
# % guisection: Selection
# %end

# %option
# % key: iscale
# % type: double
# % required: no
# % multiple: no
# % description: Scale to apply to intensity values
# % answer: 1.0
# % guisection: Transform
# %end

# %option
# % key: drange
# % type: double
# % required: no
# % multiple: no
# % key_desc: min,max
# % description: Filter range for output dimension values (min,max)
# % guisection: Selection
# %end

# %option
# % key: dscale
# % type: double
# % required: no
# % multiple: no
# % label: Scale to apply to output dimension values
# % description: Use if output dimension is not Z or intensity
# % guisection: Transform
# %end

# %option
# % key: input_srs
# % type: string
# % required: no
# % multiple: no
# % label: Input dataset projection (WKT or EPSG, e.g. EPSG:4326)
# % description: Override input dataset coordinate system using EPSG code or WKT definition
# % guisection: Projection
# %end

# %option
# % key: pth
# % type: integer
# % required: no
# % multiple: no
# % options: 1-100
# % description: pth percentile of the values
# % guisection: Statistic
# %end

# %option
# % key: trim
# % type: double
# % required: no
# % multiple: no
# % options: 0-50
# % label: Discard given percentage of the smallest and largest values
# % description: Discard <trim> percent of the smallest and <trim> percent of the largest observations
# % guisection: Statistic
# %end

# %option
# % key: resolution
# % type: double
# % required: no
# % multiple: no
# % description: Output raster resolution
# % guisection: Output
# %end

# %option
# % key: return_filter
# % type: string
# % required: no
# % multiple: no
# % options: first,last,mid
# % label: Only import points of selected return type
# % description: If not specified, all points are imported
# % guisection: Selection
# %end

# %option
# % key: class_filter
# % type: integer
# % required: no
# % multiple: yes
# % label: Only import points of selected class(es)
# % description: Input is comma separated integers. If not specified, all points are imported.
# % guisection: Selection
# %end

# %option
# % key: dimension
# % type: string
# % required: no
# % multiple: no
# % options: z,intensity,number,returns,direction,angle,class,source
# % label: Dimension (variable) to use for raster values
# % descriptions: z;Z coordinate;intensity;Intensity;number;Return number;returns;Number of returns;direction;Scan direction;angle;Scan angle;class;Point class value;source;Source ID
# % answer: z
# % guisection: Selection
# %end

# %option
# % key: user_dimension
# % type: string
# % required: no
# % multiple: no
# % label: Custom dimension (variable) to use for raster values
# % description: PDAL dimension name
# % guisection: Selection
# %end

# %flag
# % key: w
# % label: Reproject to location's coordinate system if needed
# % description: Reprojects input dataset to the coordinate system of the GRASS location (by default only datasets with the matching cordinate system can be imported
# % guisection: Projection
# %end

# %flag
# % key: e
# % label: Use the extent of the input for the raster extent
# % description: Set internally computational region extents based on the point cloud
# % guisection: Output
# %end

# %flag
# % key: n
# % label: Set computation region to match the new raster map
# % description: Set computation region to match the 2D extent and resolution of the newly created new raster map
# % guisection: Output
# %end

# %flag
# % key: o
# % label: Override projection check (use current location's projection)
# % description: Assume that the dataset has same projection as the current location
# % guisection: Projection
# %end

# %flag
# % key: d
# % label: Use base raster resolution instead of computational region
# % description: For getting values from base raster, use its actual resolution instead of computational region resolution
# % guisection: Transform
# %end

# %flag
# % key: p
# % description: Print LAS file info and exit
# %end

# %flag
# % key: g
# % description: Print data file extent in shell script style and then exit
# %end


import atexit
import os
import shutil

import grass.script as grass


# initialize global vars
orig_region = None


def reset_region(region):
    """Function to set the region to the given region
    Args:
        region (str): the name of the saved region which should be set and
                      deleted
    """
    nulldev = open(os.devnull, "w")
    kwargs = {"flags": "f", "quiet": True, "stderr": nulldev}
    if region:
        if grass.find_file(name=region, element="windows")["file"]:
            grass.run_command("g.region", region=region)
            grass.run_command("g.remove", type="region", name=region, **kwargs)


def cleanup():
    """Cleanup function"""
    grass.message(_("Cleaning up ..."))
    reset_region(orig_region)


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
    grass.run_command("g.mapset", flags="c", mapset=new_mapset, quiet=True)

    # verify that switching of the mapset worked
    cur_mapset = grass.gisenv()["MAPSET"]
    if cur_mapset != new_mapset:
        grass.fatal(
            _(f"New mapset is {cur_mapset}, but should be {new_mapset}")
        )
    return gisrc, newgisrc, old_mapset


def main():
    global orig_region

    res = options["res"]

    orig_region = grass.tempname(12)
    grass.run_command("g.region", save=orig_region, quiet=True)

    # switch to another mapset for parallel processing
    new_mapset = options["new_mapset"]
    if new_mapset:
        gisrc, newgisrc, old_mapset = switch_to_new_mapset(new_mapset)

    r_in_pdal_kwargs = dict()
    for key, val in options.items():
        if key not in ["new_mapset", "res"]:
            if val:
                r_in_pdal_kwargs[key] = val

    reg_extent_laz = grass.parse_command(
        "r.in.pdal",
        flags="g",
        **r_in_pdal_kwargs,
    )
    reg_laz_split = reg_extent_laz["n"].split(" ")
    grass.run_command(
        "g.region",
        n=float(reg_laz_split[0]),
        s=float(reg_laz_split[1].replace("s=", "")),
        e=float(reg_laz_split[2].replace("e=", "")),
        w=float(reg_laz_split[3].replace("w=", "")),
        res=1,
        flags="a",
    )
    grass.run_command(
        "g.region",
        res=res,
    )
    # for no missing values at the border of the whole area we grow it
    grass.run_command("g.region", grow=5)
    r_in_pdal_kwargs["flags"] = ""
    for key, val in flags.items():
        if val:
            r_in_pdal_kwargs["flags"] += key
    grass.run_command("r.in.pdal", **r_in_pdal_kwargs)

    # set GISRC to original gisrc and delete newgisrc
    if new_mapset:
        os.environ["GISRC"] = gisrc
        grass.utils.try_remove(newgisrc)
        msg = f"Output raster created <{options['output']}@{new_mapset}>."
    else:
        msg = f"Output raster created <{options['output']}>."

    grass.message(_(msg))
    return 0


if __name__ == "__main__":
    options, flags = grass.parser()
    atexit.register(cleanup)
    main()
