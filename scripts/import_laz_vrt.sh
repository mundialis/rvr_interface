#!/bin/sh
#
########################################################################
#
# MODULE:    LAZ-Import
# AUTHOR(S): Julia Haas, Guido Riembauer and mundialis GmbH & Co. KG
# PURPOSE:   Script to import LAZ files in GRASS with r.in.pdal
# COPYRIGHT: (c) 2021 by Julia Haas, Guido Riembauer and mundialis GmbH & Co. KG
#
#   This program is free software under the GNU General Public
#   License (>=v2). Read the file COPYING that comes with GRASS
#   for details.
#
########################################################################

# ###
# # first time only, create location:
# grass78 -c epsg:25832
#
# # first time only, install r.in.pdal addon:
# g.extension extension=r.in.pdal
#
# ###
#
# # for all subsequent uses, start GRASS GIS in created location:
# grass78 ~/grassdata/epsg25832/PERMANENT/

if  [ -z "$GISBASE" ] ; then
 echo "You must be in GRASS GIS to run this program." >&2
 exit 1
fi

# Variables
INPUT=$1/*.laz
VRT_LIST=$2
OUTPUT=$3
OUTPUT_FOLDER=$4
RES=0.5


### nothing to change below ###

# import LAZ-tiles and create VRT-list
for FILE in ${INPUT}
do
    # create output name from filename (remove file suffix)
    OUTNAME=$(basename -s .laz ${FILE})_res${RES}_m
    echo "The OUTNAME is ${OUTNAME}"

    # redirect to stdout (for unknown reasons r.out.pdal prints to stderr)
    eval $(r.in.pdal -sg input=${FILE} output=dummy   2>&1 | tr -s ' ' '\n')

    # set the region to the LAZ extent and define resolution
    g.region n=$n s=$s  w=$w e=$e res=${RES} -p -a

    # generate 95%-max DSM
    r.in.pdal input=${FILE} output=${OUTNAME} resolution=${RES} type=FCELL method=percentile pth=5
    # append to a list
    echo "${OUTNAME}" >> ${VRT_LIST}
done

# reduce VRT-list to unique entries
sort ${VRT_LIST} -u -o ${VRT_LIST}

# create VRT
r.buildvrt file=${VRT_LIST} out=${OUTPUT} --overwrite

# optionally export raster (if $OUTPUT_FOLDER ist specified by user):
if [ -z "$4" ]
  then
    echo "No output directory supplied, skipping export of raster as Tif."
  else
    echo "Exporting raster as Tif"
    g.region raster=${OUTPUT}
    r.out.gdal input=${OUTPUT} output=${OUTPUT_FOLDER}/${OUTPUT}.tif create="TILED=YES,COMPRESS=LZW" overviews=5 -mt --overwrite
fi
